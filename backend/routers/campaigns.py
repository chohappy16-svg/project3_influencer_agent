"""
[InfluenceOps] backend/routers/campaigns.py
==============================================================================
협찬 캠페인 관리 및 인플루언서 분석 API 라우터

제공 기능:
  - 캠페인 생성, 조회, 수정(제목/기간/상태), 소프트 삭제(휴지통 30일 보관), 복구, 영구 삭제
  - 제품 판매 링크 입력 시 대표 OpenGraph 썸네일(og:image) 자동 비동기 스크래핑
  - 후보 업로드(.csv / .txt / 수기 입력 가상 파일) 및 2단계 정밀 분석 비동기 파이프라인 가동
  - 캠페인 분석 결과 조회(매칭률 순 정렬), 다중 후보 좌우 비교(Compare), 확정자 엑셀(.xlsx) 내보내기
  - 마케터 섭외 상태 변경(검토 대기 <-> 승인 완료) 및 일괄 승인/취소
==============================================================================
"""

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from auth_utils import get_current_user
from database import get_db
from services.influencer_analyzer import run_batch_analysis

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns & Influencer Analysis"])
results_router = APIRouter(prefix="/api/results", tags=["Influencer Decisions"])

MAX_CANDIDATES_PER_UPLOAD = 50
HEADER_TOKENS = {"instagram_id", "id", "username", "handle", "인스타아이디", "아이디", "계정"}


def _parse_instagram_ids(raw_bytes: bytes, filename: str) -> List[str]:
    """
    업로드된 파일(.csv, .txt) 또는 수기 입력 가상 파일에서 인스타그램 아이디를 정제 추출합니다.
    - @ 기호 제거, 프로필 링크(URL)에서 순수 사용자명 추출, 헤더 행 제외, 중복 자동 필터링
    - 한 번에 최대 50명까지 지원
    """
    text = raw_bytes.decode("utf-8-sig", errors="ignore").strip()
    if not text:
        return []

    raw_items: List[str] = []
    if filename.lower().endswith(".csv"):
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if not row:
                continue
            raw_items.append(row[0].strip())
    else:
        for line in re.split(r"[\r\n,;]+", text):
            token = line.strip()
            if token:
                raw_items.append(token)

    cleaned_ids: List[str] = []
    seen = set()
    for item in raw_items:
        candidate = item.strip().lstrip("@").strip()
        if not candidate or candidate.lower() in HEADER_TOKENS:
            continue
        # URL이 들어온 경우 마지막 경로 추출 (예: https://instagram.com/user_id/)
        if "instagram.com/" in candidate.lower():
            candidate = candidate.rstrip("/").split("/")[-1].split("?")[0]
        if candidate and candidate.lower() not in seen:
            seen.add(candidate.lower())
            cleaned_ids.append(candidate)
        if len(cleaned_ids) >= MAX_CANDIDATES_PER_UPLOAD:
            break

    return cleaned_ids


async def extract_product_thumbnail(url: Optional[str]) -> Optional[str]:
    """제품 URL에서 OpenGraph 썸네일(og:image)을 비동기로 추출합니다. 실패 시 None 반환."""
    if not url or not url.strip():
        return None
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        target = "https://" + target

    parsed_path = urlparse(target).path.lower()
    if parsed_path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return target

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(target, headers=headers)
            if resp.status_code >= 400:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            for attrs in (
                {"property": "og:image"},
                {"name": "og:image"},
                {"name": "twitter:image"},
                {"property": "twitter:image"},
            ):
                tag = soup.find("meta", attrs=attrs)
                if tag and tag.get("content"):
                    return urljoin(str(resp.url), tag["content"].strip())
            link_tag = soup.find("link", rel="image_src")
            if link_tag and link_tag.get("href"):
                return urljoin(str(resp.url), link_tag["href"].strip())
    except Exception:
        return None
    return None


@router.post("", response_model=schemas.CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    req: schemas.CampaignCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그인한 마케터의 신규 협찬 캠페인을 생성하고 브랜드 DNA를 연결합니다."""
    target_dna_id = req.brand_dna_id
    if target_dna_id is not None:
        dna_obj = (
            db.query(models.BrandDNA)
            .filter(models.BrandDNA.id == target_dna_id, models.BrandDNA.user_id == current_user.id)
            .first()
        )
        if not dna_obj:
            target_dna_id = None

    if target_dna_id is None and current_user.brand_dnas:
        target_dna_id = current_user.brand_dnas[-1].id

    image_url = req.product_image_url
    if not image_url and req.product_url:
        image_url = await extract_product_thumbnail(req.product_url)

    new_campaign = models.Campaign(
        user_id=current_user.id,
        brand_dna_id=target_dna_id,
        title=req.title,
        product_name=req.product_name,
        product_url=req.product_url,
        product_image_url=image_url,
        preferred_format=req.preferred_format or "MIXED",
        status=req.status or "READY",
        start_date=req.start_date,
        end_date=req.end_date,
        is_sourcing_completed=req.is_sourcing_completed or False,
        is_deleted=False,
        campaign_appeal=req.campaign_appeal,
        total_candidates=0,
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign


@router.get("", response_model=List[schemas.CampaignResponse])
def list_my_campaigns(
    trash: bool = Query(default=False, description="휴지통(삭제 예정) 목록 조회 여부"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 로그인한 마케터가 생성한 캠페인 목록을 최신순으로 반환합니다 (30일 지난 휴지통 항목 자동 영구 삭제)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    expired = (
        db.query(models.Campaign)
        .filter(
            models.Campaign.user_id == current_user.id,
            models.Campaign.is_deleted == True,
            models.Campaign.deleted_at != None,
            models.Campaign.deleted_at < cutoff,
        )
        .all()
    )
    if expired:
        for exp in expired:
            db.delete(exp)
        db.commit()

    query = db.query(models.Campaign).filter(models.Campaign.user_id == current_user.id)
    if trash:
        query = query.filter(models.Campaign.is_deleted == True)
    else:
        query = query.filter((models.Campaign.is_deleted == False) | (models.Campaign.is_deleted == None))

    campaigns = query.order_by(models.Campaign.id.desc()).all()
    return campaigns


@router.patch("/{campaign_id}", response_model=schemas.CampaignResponse)
async def update_campaign(
    campaign_id: int,
    req: schemas.CampaignUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """캠페인 기간(연기/연장), 진행 상태(READY/IN_PROGRESS/COMPLETED), 제목을 수정합니다."""
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    if req.title is not None:
        campaign.title = req.title
    if req.product_name is not None:
        campaign.product_name = req.product_name
    if req.product_url is not None:
        campaign.product_url = req.product_url
        if not req.product_image_url:
            extracted = await extract_product_thumbnail(req.product_url)
            campaign.product_image_url = extracted
    if req.product_image_url is not None:
        campaign.product_image_url = req.product_image_url
    if req.status is not None:
        campaign.status = req.status
    if req.start_date is not None:
        campaign.start_date = req.start_date
    if req.end_date is not None:
        campaign.end_date = req.end_date
    if req.is_sourcing_completed is not None:
        campaign.is_sourcing_completed = req.is_sourcing_completed

    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}")
def soft_delete_campaign(
    campaign_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """캠페인을 휴지통으로 이동합니다 (30일간 보관 후 자동 영구 삭제)."""
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    campaign.is_deleted = True
    campaign.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "휴지통으로 이동되었습니다. 30일 이내 언제든 복구할 수 있습니다."}


@router.post("/{campaign_id}/restore", response_model=schemas.CampaignResponse)
def restore_campaign(
    campaign_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """휴지통에 있는 캠페인을 복구합니다."""
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    campaign.is_deleted = False
    campaign.deleted_at = None
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}/permanent")
def permanent_delete_campaign(
    campaign_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """휴지통의 캠페인을 즉시 영구 삭제합니다."""
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="캠페인을 찾을 수 없습니다.")

    db.delete(campaign)
    db.commit()
    return {"message": "캠페인이 영구 삭제되었습니다."}


@router.post("/{campaign_id}/upload", response_model=schemas.BatchUploadResponse)
async def upload_and_analyze_candidates(
    campaign_id: int,
    file: UploadFile = File(..., description="인스타그램 아이디 목록이 담긴 .csv 또는 .txt 파일 (최대 50명)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [2단계 핵심 엔진] .csv/.txt 파일(최대 50명)을 업로드받아 투트랙 AI 비동기 병렬 분석을 수행합니다.
    - 1차(Gemini 2.5 Flash): 광고 봇·비공개 계정 즉시 REJECT
    - 2차(GPT-4o): 생존 후보 미디어 3장 규격화, UNKNOWN 환각 방어 정밀 분석 및 원고료 산정
    - token_usages 비용 로깅 후 overall_match_percentage 내림차순 정렬 반환
    """
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="해당 캠페인을 찾을 수 없거나 접근 권한이 없습니다.")

    filename = file.filename or "candidates.txt"
    if not (filename.lower().endswith(".txt") or filename.lower().endswith(".csv")):
        raise HTTPException(status_code=400, detail=".csv 또는 .txt 파일만 업로드 가능합니다.")

    raw_bytes = await file.read()
    instagram_ids = _parse_instagram_ids(raw_bytes, filename)
    if not instagram_ids:
        raise HTTPException(status_code=400, detail="파일에서 유효한 인스타그램 아이디를 찾지 못했습니다.")

    # 동일 캠페인 내 이미 분석·등록된 중복 인플루언서 계정 자동 제외 (API 비용 이중 과금 방지)
    existing_ids = {
        row[0].strip().lstrip("@").lower()
        for row in db.query(models.InfluencerResult.instagram_id)
        .filter(models.InfluencerResult.campaign_id == campaign.id)
        .all()
        if row[0]
    }
    skipped_existing = 0
    unique_new_ids: List[str] = []
    for ig_id in instagram_ids:
        if ig_id.strip().lstrip("@").lower() in existing_ids:
            skipped_existing += 1
        else:
            unique_new_ids.append(ig_id)

    if not unique_new_ids:
        raise HTTPException(
            status_code=400,
            detail=f"업로드하신 {len(instagram_ids)}명의 인플루언서가 이미 이 캠페인에 등록되어 있습니다. 새로운 후보자를 업로드해 주세요.",
        )
    instagram_ids = unique_new_ids

    # 유저의 브랜드 DNA 텍스트 조회
    brand_dna_text = "따뜻한 자연광과 깨끗한 피부결·일상 여백의 미를 지향하는 클린 라이프스타일 브랜드"
    if campaign.brand_dna_id:
        dna_row = db.query(models.BrandDNA).filter(models.BrandDNA.id == campaign.brand_dna_id).first()
        if dna_row:
            brand_dna_text = dna_row.full_dna_text
    elif current_user.brand_dnas:
        brand_dna_text = current_user.brand_dnas[-1].full_dna_text

    # 비동기 병렬 투트랙 AI 파이프라인 실행
    analyzed_outputs = await run_batch_analysis(
        instagram_ids=instagram_ids,
        brand_dna=brand_dna_text,
        campaign_appeal=campaign.campaign_appeal,
        preferred_format=getattr(campaign, "preferred_format", None) or "MIXED",
    )

    saved_items: List[schemas.InfluencerResultItem] = []
    track1_calls = 0
    track1_rejected = 0
    track2_calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost_krw = 0.0

    for out in analyzed_outputs:
        rdata = out["result_data"]
        tlogs = out["token_logs"]

        db_result = models.InfluencerResult(
            campaign_id=campaign.id,
            instagram_id=rdata["instagram_id"],
            full_name=rdata["full_name"],
            followers_count=rdata["followers_count"],
            posts_count=rdata["posts_count"],
            engagement_rate=rdata["engagement_rate"],
            influencer_tier=rdata["influencer_tier"],
            primary_format=rdata.get("primary_format", "FEED"),
            recommended_fee=rdata["recommended_fee"],
            overall_match_percentage=rdata["overall_match_percentage"],
            fit_status=rdata["fit_status"],
            approval_state=rdata["approval_state"],
            skin_type=rdata["skin_type"],
            family_pet_exposure=rdata["family_pet_exposure"],
            communication_authenticity=rdata["communication_authenticity"],
            one_line_verdict=rdata["one_line_verdict"],
            rationale_json=json.dumps(rdata["rationale_bullets"], ensure_ascii=False),
            media_analysis_json=rdata["media_analysis_json"],
            thumbnails_json=rdata["thumbnails_json"],
        )
        db.add(db_result)
        db.flush()  # 생성된 db_result.id 확보

        for log in tlogs:
            db_log = models.TokenUsage(
                user_id=current_user.id,
                campaign_id=campaign.id,
                instagram_id=log["instagram_id"],
                track_stage=log["track_stage"],
                model_name=log["model_name"],
                prompt_tokens=log["prompt_tokens"],
                completion_tokens=log["completion_tokens"],
                total_tokens=log["total_tokens"],
                estimated_cost_usd=log["estimated_cost_usd"],
                estimated_cost_krw=log["estimated_cost_krw"],
                latency_sec=log["latency_sec"],
            )
            db.add(db_log)

            total_prompt_tokens += log["prompt_tokens"]
            total_completion_tokens += log["completion_tokens"]
            total_cost_krw += log["estimated_cost_krw"]
            if log["track_stage"] == "TRACK_1_SCREENING":
                track1_calls += 1
            elif log["track_stage"] == "TRACK_2_DEEP_EVAL":
                track2_calls += 1

        if rdata["track_stage_completed"] == "TRACK_1_REJECTED":
            track1_rejected += 1

        saved_items.append(
            schemas.InfluencerResultItem(
                id=db_result.id,
                campaign_id=campaign.id,
                instagram_id=db_result.instagram_id,
                full_name=db_result.full_name,
                followers_count=db_result.followers_count,
                posts_count=db_result.posts_count,
                engagement_rate=db_result.engagement_rate,
                influencer_tier=db_result.influencer_tier,
                primary_format=db_result.primary_format,
                recommended_fee=db_result.recommended_fee,
                overall_match_percentage=db_result.overall_match_percentage,
                fit_status=db_result.fit_status,
                approval_state=db_result.approval_state,
                skin_type=db_result.skin_type,
                family_pet_exposure=db_result.family_pet_exposure,
                communication_authenticity=db_result.communication_authenticity,
                one_line_verdict=db_result.one_line_verdict,
                rationale_bullets=rdata["rationale_bullets"],
                thumbnails=json.loads(rdata["thumbnails_json"]) if rdata.get("thumbnails_json") else [],
                track_stage_completed=rdata["track_stage_completed"],
            )
        )

    campaign.total_candidates = (campaign.total_candidates or 0) + len(saved_items)
    db.commit()

    # 매칭률(overall_match_percentage) 내림차순 정렬 (95% -> 80% -> 15%)
    saved_items.sort(key=lambda x: x.overall_match_percentage, reverse=True)

    # 전원 GPT-4o(1건당 약 13.9원 기준) 단독 처리 시 대비 비용 절감률 계산
    est_gpt4o_only = round(len(saved_items) * 13.9, 2)
    rounded_cost = round(total_cost_krw, 2)
    saving_pct = round(max(0.0, (1 - (rounded_cost / est_gpt4o_only)) * 100), 1) if est_gpt4o_only > 0 else 0.0

    skip_note = f" (기존 캠페인 중복 {skipped_existing}명 자동 제외)" if skipped_existing > 0 else ""
    return schemas.BatchUploadResponse(
        message=f"총 {len(saved_items)}명의 후보자 투트랙 AI 분석 및 DB 적재가 완료되었습니다.{skip_note}",
        campaign_id=campaign.id,
        campaign_title=campaign.title,
        total_uploaded=len(saved_items),
        cost_summary=schemas.TokenUsageSummary(
            track1_gemini_calls=track1_calls,
            track1_rejected_count=track1_rejected,
            track2_gpt4o_calls=track2_calls,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_cost_krw=rounded_cost,
            estimated_gpt4o_only_cost_krw=est_gpt4o_only,
            cost_saving_percentage=saving_pct,
        ),
        results=saved_items,
    )


@router.get("/{campaign_id}/results", response_model=List[schemas.InfluencerResultItem])
def get_campaign_results(
    campaign_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """캠페인에 저장된 후보자 분석 리스트를 overall_match_percentage 내림차순으로 반환합니다."""
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="해당 캠페인을 찾을 수 없거나 접근 권한이 없습니다.")

    rows = (
        db.query(models.InfluencerResult)
        .filter(models.InfluencerResult.campaign_id == campaign_id)
        .order_by(models.InfluencerResult.overall_match_percentage.desc())
        .all()
    )

    items: List[schemas.InfluencerResultItem] = []
    seen_ig = set()
    for r in rows:
        norm_ig = (r.instagram_id or "").strip().lstrip("@").lower()
        if norm_ig in seen_ig:
            continue
        seen_ig.add(norm_ig)
        try:
            bullets = json.loads(r.rationale_json) if r.rationale_json else []
        except Exception:
            bullets = []
        try:
            thumbs = json.loads(r.thumbnails_json) if r.thumbnails_json else []
        except Exception:
            thumbs = []
        items.append(
            schemas.InfluencerResultItem(
                id=r.id,
                campaign_id=r.campaign_id,
                instagram_id=r.instagram_id,
                full_name=r.full_name,
                followers_count=r.followers_count,
                posts_count=r.posts_count,
                engagement_rate=r.engagement_rate,
                influencer_tier=r.influencer_tier,
                primary_format=getattr(r, "primary_format", None) or "FEED",
                recommended_fee=r.recommended_fee,
                overall_match_percentage=r.overall_match_percentage,
                fit_status=r.fit_status,
                approval_state=r.approval_state,
                skin_type=r.skin_type,
                family_pet_exposure=r.family_pet_exposure,
                communication_authenticity=r.communication_authenticity,
                one_line_verdict=r.one_line_verdict,
                rationale_bullets=bullets,
                thumbnails=thumbs,
            )
        )
    return items


@router.get("/{campaign_id}/compare", response_model=schemas.CompareResponse)
def compare_candidates(
    campaign_id: int,
    ids: str = Query(..., description="비교할 후보자 result_id를 쉼표로 구분해 입력 (예: 16,17)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [3단계 ①] 대시보드에서 체크박스로 선택한 2~3명의 후보자 상세 데이터를 좌우 비교용으로 반환합니다.
    """
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="해당 캠페인을 찾을 수 없거나 접근 권한이 없습니다.")

    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids 파라미터는 쉼표로 구분된 정수여야 합니다 (예: 16,17).")

    if not id_list or len(id_list) > 5:
        raise HTTPException(status_code=400, detail="비교할 인플루언서 ID는 1개 이상 5개 이하로 지정해 주세요.")

    rows = (
        db.query(models.InfluencerResult)
        .filter(models.InfluencerResult.campaign_id == campaign_id, models.InfluencerResult.id.in_(id_list))
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="요청하신 ID에 해당하는 후보자 데이터를 찾지 못했습니다.")

    row_map = {r.id: r for r in rows}
    ordered_rows = [row_map[i] for i in id_list if i in row_map]

    candidates: List[schemas.CompareCandidateItem] = []
    for r in ordered_rows:
        try:
            bullets = json.loads(r.rationale_json) if r.rationale_json else []
        except Exception:
            bullets = []
        try:
            media_list = json.loads(r.media_analysis_json) if r.media_analysis_json else []
        except Exception:
            media_list = []
        try:
            thumbs = json.loads(r.thumbnails_json) if r.thumbnails_json else []
        except Exception:
            thumbs = []

        candidates.append(
            schemas.CompareCandidateItem(
                id=r.id,
                campaign_id=r.campaign_id,
                instagram_id=r.instagram_id,
                full_name=r.full_name,
                followers_count=r.followers_count,
                posts_count=r.posts_count,
                engagement_rate=r.engagement_rate,
                influencer_tier=r.influencer_tier,
                primary_format=getattr(r, "primary_format", None) or "FEED",
                recommended_fee=r.recommended_fee,
                overall_match_percentage=r.overall_match_percentage,
                fit_status=r.fit_status,
                approval_state=r.approval_state,
                skin_type=r.skin_type,
                family_pet_exposure=r.family_pet_exposure,
                communication_authenticity=r.communication_authenticity,
                one_line_verdict=r.one_line_verdict,
                rationale_bullets=bullets,
                media_analysis=media_list,
                thumbnails=thumbs,
            )
        )

    return schemas.CompareResponse(
        campaign_id=campaign.id,
        campaign_title=campaign.title,
        compared_count=len(candidates),
        candidates=candidates,
    )


@results_router.patch("/{result_id}/decision", response_model=schemas.DecisionResponse)
def update_candidate_decision(
    result_id: int,
    req: schemas.DecisionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [3단계 ②] 마케터의 Human-in-the-Loop 최종 승인/반려 상태 전이(PENDING ➔ APPROVED / REJECTED)
    및 해당 캠페인의 누적 토큰 과금 요약을 함께 반환합니다.
    """
    row = (
        db.query(models.InfluencerResult)
        .join(models.Campaign, models.InfluencerResult.campaign_id == models.Campaign.id)
        .filter(models.InfluencerResult.id == result_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="해당 후보자 결과를 찾을 수 없거나 수정 권한이 없습니다.")

    row.approval_state = req.decision
    db.commit()
    db.refresh(row)

    usage_agg = (
        db.query(
            func.coalesce(func.sum(models.TokenUsage.estimated_cost_krw), 0.0),
            func.coalesce(func.sum(models.TokenUsage.total_tokens), 0),
        )
        .filter(models.TokenUsage.campaign_id == row.campaign_id)
        .first()
    )
    cum_cost_krw = round(float(usage_agg[0] if usage_agg else 0.0), 2)
    cum_tokens = int(usage_agg[1] if usage_agg else 0)

    return schemas.DecisionResponse(
        message=f"@{row.instagram_id} 후보자의 최종 상태가 '{row.approval_state}'(으)로 변경되었습니다.",
        result_id=row.id,
        instagram_id=row.instagram_id,
        approval_state=row.approval_state,
        campaign_id=row.campaign_id,
        campaign_cumulative_cost_krw=cum_cost_krw,
        campaign_total_tokens=cum_tokens,
    )


@results_router.delete("/{result_id}")
def delete_candidate_result(
    result_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """분석 결과 목록에서 특정 인플루언서 후보 1명을 삭제합니다."""
    row = (
        db.query(models.InfluencerResult)
        .join(models.Campaign, models.InfluencerResult.campaign_id == models.Campaign.id)
        .filter(
            models.InfluencerResult.id == result_id,
            models.Campaign.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="해당 후보자 결과를 찾을 수 없거나 삭제 권한이 없습니다.")

    camp = db.query(models.Campaign).filter(models.Campaign.id == row.campaign_id).first()
    ig_id = row.instagram_id
    camp_id = row.campaign_id
    db.delete(row)
    if camp and camp.total_candidates and camp.total_candidates > 0:
        camp.total_candidates -= 1
    db.commit()
    return {
        "message": f"@{ig_id} 후보자가 목록에서 삭제되었습니다.",
        "deleted_id": result_id,
        "campaign_id": camp_id,
    }


@router.get("/{campaign_id}/export")
def export_approved_candidates_xlsx(
    campaign_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [3단계 ③] 최종 승인(approval_state == 'APPROVED')된 인플루언서만 추려 .xlsx 엑셀 파일로 다운로드합니다.
    """
    campaign = (
        db.query(models.Campaign)
        .filter(models.Campaign.id == campaign_id, models.Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="해당 캠페인을 찾을 수 없거나 접근 권한이 없습니다.")

    approved_rows = (
        db.query(models.InfluencerResult)
        .filter(
            models.InfluencerResult.campaign_id == campaign_id,
            models.InfluencerResult.approval_state == "APPROVED",
        )
        .order_by(models.InfluencerResult.overall_match_percentage.desc())
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "확정 인플루언서 리스트"

    headers = [
        "No",
        "인스타그램 ID",
        "이름",
        "팔로워 수",
        "게시물 수",
        "참여율(%)",
        "인플루언서 티어",
        "예상 원고료",
        "AI 매칭률(%)",
        "AI 판정",
        "최종 상태",
        "피부 타입",
        "가족/반려동물 노출",
        "소통 진정성",
        "AI 1줄 핵심 요약",
        "상세 판정 사유",
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, r in enumerate(approved_rows, start=1):
        try:
            bullets = json.loads(r.rationale_json) if r.rationale_json else []
            bullets_str = " / ".join(bullets)
        except Exception:
            bullets_str = ""

        ws.append(
            [
                idx,
                f"@{r.instagram_id}",
                r.full_name or "",
                r.followers_count,
                r.posts_count,
                r.engagement_rate,
                r.influencer_tier or "",
                r.recommended_fee or "",
                r.overall_match_percentage,
                r.fit_status,
                r.approval_state,
                r.skin_type,
                r.family_pet_exposure,
                r.communication_authenticity,
                r.one_line_verdict or "",
                bullets_str,
            ]
        )

    col_widths = [6, 20, 22, 12, 12, 11, 20, 18, 13, 18, 12, 13, 16, 13, 45, 60]
    for i, w in enumerate(col_widths, start=1):
        col_letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[col_letter].width = w

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"influenceops_campaign_{campaign_id}_approved.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
