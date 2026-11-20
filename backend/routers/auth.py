"""
[InfluenceOps Phase 2 MVP] backend/routers/auth.py
==============================================================================
회원가입(Bcrypt 암호화 + 브랜드 URL DNA 자동 추출·저장) & 로그인(JWT 토큰 발급) 라우터
- POST /api/auth/signup : users(password_hash) + brand_dnas(full_dna_text) 동시 적재
- POST /api/auth/login  : Bcrypt 검증 후 JWT access_token 반환
==============================================================================
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAI
from sqlalchemy.orm import Session

import models
import schemas
from auth_utils import create_access_token, get_current_user, hash_password, verify_password
from database import get_db

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

router = APIRouter(prefix="/api/auth", tags=["Auth & Brand DNA"])


async def extract_brand_dna_from_url(url: str) -> str:
    """
    1) 브랜드 자사몰 URL에서 타이틀, 메타 설명, 본문 텍스트를 비동기로 추출합니다.
    2) 봇 차단(403 등) 예외 발생 시 URL 도메인 기반으로 안전하게 폴백합니다.
    3) Gemini 2.5 Flash (OpenRouter 또는 Google Gemini API)를 호출해 브랜드 DNA를 3문장으로 요약합니다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            if desc_tag and desc_tag.get("content"):
                meta_desc = str(desc_tag["content"]).strip()
            body_text = " ".join(soup.get_text().split())[:1500]
            raw_info = f"URL: {url}\n타이틀: {title}\n설명: {meta_desc}\n본문 일부: {body_text}"
    except Exception:
        raw_info = f"URL: {url} (웹페이지 직접 접근 제한됨. URL 도메인명 기반으로 브랜드 페르소나를 추론하세요.)"

    prompt = (
        "당신은 뷰티·라이프스타일·F&B 브랜드 전략가입니다. 아래 브랜드 웹사이트 정보를 바탕으로 "
        "인플루언서 섭외 시 기준으로 삼을 '브랜드 추구미(타겟 고객, 톤앤매너, 선호 비주얼 무드)'를 "
        "한국어 3문장 이내로 명확하고 간결하게 요약하세요.\n\n"
        f"{raw_info}"
    )

    # 1순위: OpenRouter를 통한 Gemini 2.5 Flash 호출 (PoC 벤치마크에서 검증된 경로)
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        try:
            or_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_key,
            )
            completion = or_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            text = (completion.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass

    # 2순위: Google Gemini API 키 직접 호출 (GEMINI_API_KEY 또는 GEMINI_API_Key)
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_Key") or "").strip()
    if gemini_key:
        try:
            from google import genai

            g_client = genai.Client(api_key=gemini_key)
            resp = g_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            if resp and resp.text:
                return resp.text.strip()
        except Exception:
            pass

    # 3순위: API 호출 불가 시 안전 기본값 반환 (회원가입이 절대 실패하지 않도록 방어)
    domain = urlparse(url).netloc or url
    return (
        f"[{domain}] 인위적 조명과 과도한 광고 느낌을 배제하고, 따뜻한 자연광과 깨끗한 피부결·일상 여백의 미를 "
        "지향하는 클린 라이프스타일 브랜드 페르소나입니다."
    )


@router.post("/signup", response_model=schemas.UserSignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(req: schemas.UserSignupRequest, db: Session = Depends(get_db)):
    """마케터 회원가입(Bcrypt 암호화) + 브랜드 URL DNA 자동 추출 및 PostgreSQL 저장"""
    # 1. 이메일 중복 체크
    existing_user = db.query(models.User).filter(models.User.email == req.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    # 2. 유저 생성 (models.User.password_hash 컬럼에 Bcrypt 해시 저장)
    new_user = models.User(
        email=req.email,
        password_hash=hash_password(req.password),
        company_name=req.company_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. 브랜드 URL 기반 DNA 추출 및 models.BrandDNA 테이블 영구 저장
    dna_summary = await extract_brand_dna_from_url(req.brand_url)
    brand_title = req.company_name or (urlparse(req.brand_url).netloc or "My Brand")
    new_dna = models.BrandDNA(
        user_id=new_user.id,
        brand_name=brand_title,
        brand_url=req.brand_url,
        visual_mood="AI 자동 추출 (Gemini 2.5 Flash)",
        full_dna_text=dna_summary,
    )
    db.add(new_dna)
    db.commit()

    return schemas.UserSignupResponse(
        message="회원가입 및 브랜드 DNA 추출이 완료되었습니다.",
        user_id=new_user.id,
        email=new_user.email,
        company_name=new_user.company_name,
        brand_url=req.brand_url,
        brand_dna=dna_summary,
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(req: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    """이메일·비밀번호 Bcrypt 검증 후 JWT 액세스 토큰 발급"""
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    dna_text = user.brand_dnas[0].full_dna_text if user.brand_dnas else None

    return schemas.TokenResponse(
        access_token=token,
        user_id=user.id,
        company_name=user.company_name,
        brand_dna_summary=dna_text,
    )


@router.get("/me", response_model=schemas.UserMeResponse)
def get_my_profile(current_user: models.User = Depends(get_current_user)):
    """새로고침(F5) 시 JWT 토큰으로 현재 로그인 유저 정보와 브랜드 DNA 요약을 복원합니다."""
    latest_dna = current_user.brand_dnas[-1] if current_user.brand_dnas else None
    return schemas.UserMeResponse(
        user_id=current_user.id,
        email=current_user.email,
        company_name=current_user.company_name,
        brand_url=latest_dna.brand_url if latest_dna else None,
        brand_dna_summary=latest_dna.full_dna_text if latest_dna else None,
    )


@router.put("/brand-dna", response_model=schemas.BrandDnaResponse)
async def update_brand_dna(
    req: schemas.BrandDnaUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    브랜드명, 자사몰 URL, 브랜드 DNA 텍스트를 PostgreSQL에 영구 저장합니다.
    - re_extract=True : URL을 다시 스크래핑하여 Gemini 2.5 Flash로 새 DNA 추출 후 저장
    - re_extract=False: LLM 호출 없이 사용자가 편집한 텍스트만 즉시 DB에 UPDATE
    """
    if req.company_name is not None and req.company_name.strip():
        current_user.company_name = req.company_name.strip()

    latest_dna = current_user.brand_dnas[-1] if current_user.brand_dnas else None

    if req.re_extract:
        final_dna_text = await extract_brand_dna_from_url(req.brand_url)
    else:
        final_dna_text = (req.full_dna_text or "").strip()
        if not final_dna_text:
            final_dna_text = (
                latest_dna.full_dna_text
                if latest_dna
                else "따뜻한 자연광과 깨끗한 피부결·일상 여백의 미를 지향하는 클린 라이프스타일 브랜드 페르소나입니다."
            )

    brand_title = current_user.company_name or (urlparse(req.brand_url).netloc or "My Brand")

    if latest_dna:
        latest_dna.brand_name = brand_title
        latest_dna.brand_url = req.brand_url
        latest_dna.full_dna_text = final_dna_text
    else:
        latest_dna = models.BrandDNA(
            user_id=current_user.id,
            brand_name=brand_title,
            brand_url=req.brand_url,
            visual_mood="사용자 편집 / AI 추출",
            full_dna_text=final_dna_text,
        )
        db.add(latest_dna)

    db.commit()
    db.refresh(current_user)
    db.refresh(latest_dna)

    msg = (
        "자사몰 URL에서 브랜드 DNA를 다시 추출하여 저장했습니다."
        if req.re_extract
        else "수정된 브랜드 DNA가 데이터베이스에 영구 저장되었습니다."
    )
    return schemas.BrandDnaResponse(
        message=msg,
        user_id=current_user.id,
        company_name=current_user.company_name,
        brand_url=latest_dna.brand_url or req.brand_url,
        brand_dna_summary=latest_dna.full_dna_text,
    )


@router.delete("/me")
def delete_my_account(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회원 탈퇴: 현재 로그인한 계정과 연관 데이터(브랜드 DNA, 캠페인, 분석 결과)를 영구 삭제합니다."""
    email = current_user.email
    db.delete(current_user)
    db.commit()
    return {"message": f"계정({email})이 안전하게 탈퇴 처리되었습니다."}
