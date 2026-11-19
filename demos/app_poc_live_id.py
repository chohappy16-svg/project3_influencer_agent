r"""
[InfluenceOps v3.0] Phase 1 — 프로토타입 2: 인스타그램 ID 실시간 크롤링 & 원고료 산정 · AI 판정 버전
====================================================================================================
- 실행 명령어: streamlit run c:\workAI\work9\app_poc_live_id.py
- 핵심 반영 사항:
  1) 인스타 ID(@ 없이 입력 가능) 실시간 크롤링 (로컬 더미 미사용 · RAM Base64 직접 인코딩)
  2) 마이크로 인플루언서 기준 정립 & 원고료 자동 산정 (팔로워 7,000명 미만 0원 무상 시딩 /
     7,000명 이상 3만 원 시작 → 5만 / 10만 / 15만 ... 최대 50만 원, 10만+ 매크로는 50만 원+ 별도 협의)
  3) 멘토링용 AI 적합도 리포트 가독성 극대화:
     - 상단 배너: 판정 등급 + LLM이 직접 작성한 1줄 핵심 요약(one_line_verdict)
     - 3대 지표 표: 점수 등급화 + 한글 질감/맥락 배지 + 구체적 촬영 연출 형태(제형샷, 비포앤애프터, 자연광 무드컷 등)
     - 판정 사유: 줄글 대신 포인트별 1줄씩 엔터(개행) 처리된 개조식 불릿 리스트
  4) 지저분한 원본 캡션 텍스트 창 제거 → 대표 피드 썸네일(Photo 1~3) 클릭 시 해당 인스타그램 게시물로 새 탭 이동
====================================================================================================
"""

import base64
import datetime
import html
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageStat
from pydantic import BaseModel, Field

import sys
from pathlib import Path
_ROOT_DIR = Path(__file__).resolve().parent.parent
_POC_TESTS_DIR = _ROOT_DIR / "poc_tests"
if str(_POC_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_POC_TESTS_DIR))

from poc_step2_prompt_matching import BRAND_PERSONA_DNA, build_system_prompt
from test import (
    _extract_from_media_root_dict,
    _extract_post_metadata_from_dict,
    detect_instagram_url_type,
    fetch_live_profile_header,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_ROOT_DIR / ".env")

st.set_page_config(
    page_title="InfluenceOps v3.0 — Live Instagram ID & AI Evaluator",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ==============================================================================
# 1. 멘토링 가독성 고도화용 Pydantic 스키마 정의
# ==============================================================================
class LiveMediaAnalysis(BaseModel):
    aesthetic_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1~10점 사이의 비주얼 감도 점수 (자연광, 구도, 색감, 여백의 미 종합 평가)",
    )
    texture_rendering: Literal["NATURAL_GLOW", "MODERATE_EDIT", "HEAVY_FILTER", "UNANALYZABLE"] = Field(
        ...,
        description="피부결 및 피사체 질감 표현 방식",
    )
    lifestyle_context: Literal["BEAUTY_HIGH_INVOLVEMENT", "DAILY_CASUAL", "IRRELEVANT", "UNANALYZABLE"] = Field(
        ...,
        description="콘텐츠의 라이프스타일 및 카테고리 맥락",
    )
    visual_appeal: Literal["PRODUCT_CENTRIC", "LIFESTYLE_MOOD", "PERSONA_CHARM", "UNANALYZABLE"] = Field(
        ...,
        description="시각적 소구 방식 (기존 스키마 호환용)",
    )
    scene_type_kr: str = Field(
        ...,
        min_length=2,
        max_length=28,
        description=(
            "마케터가 직관적으로 이해할 수 있는 구체적 촬영 연출 형태 한글 요약 "
            "(예: '손등 제형 클로즈업샷', '사용 전후 비포앤애프터', '창가 자연광 피부결 셀카', "
            "'우드톤 감성 홈카페 무드컷', '특가 텍스트 전단지 배너', '음식·맛집 메뉴 클로즈업')"
        ),
    )


class LiveInfluencerEvaluation(BaseModel):
    media_analysis: List[LiveMediaAnalysis] = Field(
        ...,
        min_length=1,
        description="입력된 각 대표 피드 이미지(Photo 1~3)에 대한 개별 멀티모달 분석 리스트",
    )
    overall_match_percentage: int = Field(
        ...,
        ge=0,
        le=100,
        description="브랜드 DNA 및 캠페인 무드와의 종합 매칭률 (0~100%)",
    )
    fit_status: Literal["APPROVE", "CREATIVE_EXCEPTION", "REVIEW_NEEDED", "REJECT", "DATA_INSUFFICIENT"] = Field(
        ...,
        description="최종 섭외 적합도 판정 플래그",
    )
    one_line_verdict: str = Field(
        ...,
        min_length=10,
        max_length=85,
        description=(
            "상단 배너에 표시할 1줄 핵심 판정 요약 (하드코딩이 아닌 해당 계정 맞춤형 1줄 결론. "
            "부적합 시 왜 협찬하기에 적합하지 않은지, 적합 시 왜 추천하는지 65자 이내 한 줄로 명확히 작성)"
        ),
    )
    expected_collisions: List[str] = Field(
        default_factory=list,
        description="핵심 시너지 키워드 또는 부적합/주의 태그 리스트 (2~3개 짧은 구문)",
    )
    rationale_bullets: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description=(
            "가독성을 위해 포인트별로 분리한 3가지 상세 판정 사유 리스트. "
            "각 항목은 1줄(60~110자)로 작성하며, ① 비주얼/톤앤매너 평가, ② 촬영 연출력 및 카테고리 적합성, ③ 최종 협찬/섭외 제언 순서로 구성"
        ),
    )


# ==============================================================================
# 2. 브랜드 디자인 시스템 CSS (#1E293B, #0EA5E9, #10B981, #F97316, #F8FAFC)
# ==============================================================================
st.markdown(
    """
<style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #F8FAFC !important;
        color: #1E293B !important;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }
    .block-container {
        padding-top: 1.3rem !important;
        padding-bottom: 2rem !important;
        max-width: 1460px !important;
    }
    p, span, label, h1, h2, h3, h4, h5, h6, div[data-testid="stMarkdownContainer"] p {
        color: #1E293B !important;
    }

    /* 텍스트 입력창 화이트 배경 + 딥 네이비 글자 강제 */
    textarea, input[type="text"] {
        background-color: #FFFFFF !important;
        color: #1E293B !important;
        -webkit-text-fill-color: #1E293B !important;
        caret-color: #0EA5E9 !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-size: 0.93rem !important;
        line-height: 1.5 !important;
        padding: 0.55rem 0.8rem !important;
    }
    div[data-baseweb="textarea"], div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        border-color: #CBD5E1 !important;
    }

    /* Expander 라이트 모드 고정 */
    div[data-testid="stExpander"] details {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] summary span,
    div[data-testid="stExpander"] summary p {
        color: #1E293B !important;
        font-weight: 600 !important;
    }

    /* 상단 헤더 (GNB) */
    .gnb-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.35rem 0.2rem 0.9rem 0.2rem;
        border-bottom: 1px solid #E2E8F0;
        margin-bottom: 1.1rem;
    }
    .logo-title {
        font-size: 2.15rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        line-height: 1.1;
        color: #1E293B !important;
    }
    .logo-ops { color: #0EA5E9 !important; }
    .logo-sparkle {
        color: #10B981 !important;
        font-size: 1.35rem;
        vertical-align: super;
        margin-left: 2px;
    }
    .logo-sub {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        color: #475569 !important;
        margin-top: 4px;
    }
    .poc-pill {
        background-color: #E0F2FE;
        border: 1px solid #7DD3FC;
        color: #0369A1 !important;
        padding: 0.45rem 1rem;
        border-radius: 9999px;
        font-size: 0.84rem;
        font-weight: 700;
    }

    /* 패널 섹션 타이틀 */
    .panel-header-bar {
        background-color: #F1F5F9;
        border: 1px solid #E2E8F0;
        border-radius: 10px 10px 0 0;
        padding: 0.65rem 1.1rem;
        font-weight: 700;
        font-size: 1rem;
        color: #1E293B !important;
        margin-bottom: 0;
    }
    .section-title {
        font-size: 1.15rem;
        font-weight: 800;
        color: #1E293B !important;
        margin: 0.2rem 0 0.65rem 0;
    }

    /* 메인 CTA 버튼 (스카이 블루 #0EA5E9) */
    div.stButton > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] > button {
        background-color: #0EA5E9 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        padding: 0.6rem 1rem !important;
        width: 100% !important;
        box-shadow: 0 2px 6px rgba(14, 165, 233, 0.25) !important;
    }
    div.stButton > button[kind="primary"] p,
    div.stButton > button[kind="primary"] span,
    div[data-testid="stFormSubmitButton"] > button p,
    div[data-testid="stFormSubmitButton"] > button span {
        color: #FFFFFF !important;
    }

    /* 프로필 헬스 체크 바 */
    .profile-health-bar {
        background-color: #FFFFFF;
        border: 1.5px solid #CBD5E1;
        border-left: 5px solid #0EA5E9;
        border-radius: 8px;
        padding: 0.65rem 0.95rem;
        margin: 0.35rem 0 0.55rem 0;
        font-size: 0.85rem;
        line-height: 1.55;
    }

    /* 마이크로 인플루언서 등급 & 원고료 산정 카드 */
    .pricing-card {
        background-color: #F0FDF4;
        border: 1.5px solid #86EFAC;
        border-left: 5px solid #10B981;
        border-radius: 8px;
        padding: 0.7rem 0.95rem;
        margin: 0 0 0.75rem 0;
        font-size: 0.85rem;
        line-height: 1.55;
    }
    .pricing-card-reject {
        background-color: #FEF2F2;
        border: 1.5px solid #FCA5A5;
        border-left: 5px solid #EF4444;
        border-radius: 8px;
        padding: 0.7rem 0.95rem;
        margin: 0 0 0.75rem 0;
        font-size: 0.85rem;
        line-height: 1.55;
    }
    .fee-highlight {
        display: inline-block;
        background-color: #1E293B;
        color: #38BDF8 !important;
        font-weight: 800;
        font-size: 0.92rem;
        padding: 0.12rem 0.6rem;
        border-radius: 6px;
        margin-left: 0.25rem;
    }

    .selection-rule-banner {
        background-color: #F0F9FF;
        border: 1px solid #BAE6FD;
        border-radius: 6px;
        padding: 0.48rem 0.85rem;
        font-size: 0.8rem;
        color: #0369A1 !important;
        margin-bottom: 0.55rem;
        font-weight: 600;
    }

    /* 클릭 가능한 썸네일 카드 */
    .thumb-card-link {
        display: block;
        text-decoration: none !important;
        border: 1.5px solid #CBD5E1;
        border-radius: 8px;
        overflow: hidden;
        background-color: #FFFFFF;
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    .thumb-card-link:hover {
        transform: translateY(-2px);
        border-color: #0EA5E9;
        box-shadow: 0 6px 14px rgba(14, 165, 233, 0.18);
    }
    .slot-reason-badge {
        background-color: #1E293B;
        color: #FFFFFF !important;
        font-size: 0.73rem;
        font-weight: 700;
        padding: 0.3rem 0.45rem;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .thumb-img-wrap {
        width: 100%;
        aspect-ratio: 1 / 1;
        overflow: hidden;
        background-color: #F1F5F9;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .thumb-img-wrap img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .thumb-footer {
        padding: 0.38rem 0.5rem;
        font-size: 0.75rem;
        font-weight: 600;
        color: #0369A1 !important;
        background-color: #F8FAFC;
        text-align: center;
        border-top: 1px solid #E2E8F0;
    }

    /* 크롤링 보조 요약 바 */
    .meta-summary-bar {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 0.65rem 0.95rem;
        margin-top: 0.55rem;
        font-size: 0.84rem;
        line-height: 1.55;
    }
    .tag-chip {
        display: inline-block;
        background-color: #E0F2FE;
        color: #0369A1 !important;
        font-weight: 700;
        padding: 0.1rem 0.5rem;
        border-radius: 6px;
        font-size: 0.76rem;
        margin-right: 0.26rem;
        margin-bottom: 0.18rem;
    }

    /* 상단 적합 판정 배너 (2줄 구조: 등급+매칭률 / LLM 1줄 핵심 요약) */
    .status-banner-box {
        padding: 0.85rem 1.15rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .status-banner-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: 800;
        font-size: 1rem;
        margin-bottom: 0.35rem;
    }
    .status-banner-sub {
        font-size: 0.9rem;
        font-weight: 600;
        line-height: 1.45;
        padding-top: 0.3rem;
        border-top: 1px dashed rgba(100, 116, 139, 0.3);
    }
    .status-approve { background-color: #ECFDF5; border: 1.5px solid #10B981; }
    .status-approve .status-banner-top span, .status-approve .status-banner-sub { color: #065F46 !important; }
    .status-exception { background-color: #FFF7ED; border: 1.5px solid #F97316; }
    .status-exception .status-banner-top span, .status-exception .status-banner-sub { color: #C2410C !important; }
    .status-reject { background-color: #FEF2F2; border: 1.5px solid #EF4444; }
    .status-reject .status-banner-top span, .status-reject .status-banner-sub { color: #991B1B !important; }
    .status-insufficient { background-color: #F1F5F9; border: 1.5px solid #64748B; }
    .status-insufficient .status-banner-top span, .status-insufficient .status-banner-sub { color: #334155 !important; }

    /* 화이트 모드 커스텀 평가 지표 테이블 */
    .eval-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 1rem;
        font-size: 0.84rem;
    }
    .eval-table th {
        background-color: #F1F5F9;
        color: #1E293B !important;
        font-weight: 700;
        text-align: left;
        padding: 0.58rem 0.65rem;
        border-bottom: 1px solid #CBD5E1;
    }
    .eval-table td {
        color: #1E293B !important;
        padding: 0.55rem 0.65rem;
        border-bottom: 1px solid #E2E8F0;
        font-weight: 500;
        vertical-align: middle;
    }
    .scene-pill {
        display: inline-block;
        background-color: #F0F9FF;
        border: 1px solid #BAE6FD;
        color: #0369A1 !important;
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.16rem 0.55rem;
        border-radius: 6px;
    }

    /* 판단 근거 박스 (한 줄씩 개행된 불릿 리스트) */
    .rationale-box-warning {
        background-color: #FFF7ED; border: 1.5px solid #F97316;
        border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1rem; line-height: 1.65;
    }
    .rationale-box-approve {
        background-color: #ECFDF5; border: 1.5px solid #10B981;
        border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1rem; line-height: 1.65;
    }
    .rationale-box-reject {
        background-color: #FEF2F2; border: 1.5px solid #EF4444;
        border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1rem; line-height: 1.65;
    }
    .rationale-bullet-item {
        margin-top: 0.38rem;
        padding-left: 0.2rem;
        font-size: 0.88rem;
        color: #1E293B !important;
    }

    /* 다크 네이비 (#1E293B) JSON 뷰어 */
    .json-dark-box {
        background-color: #1E293B !important;
        border-radius: 8px;
        padding: 0.9rem 1.15rem;
        border: 1px solid #334155;
    }
    .json-dark-header {
        font-size: 0.82rem;
        font-weight: 700;
        margin-bottom: 0.55rem;
        border-bottom: 1px solid #334155;
        padding-bottom: 0.42rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    div[data-testid="stMarkdownContainer"] .json-dark-header span.json-title-text {
        color: #F8FAFC !important;
    }
    div[data-testid="stMarkdownContainer"] .json-dark-header span.json-badge-ok {
        background-color: #10B981 !important;
        color: #FFFFFF !important;
        padding: 0.16rem 0.58rem;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 700;
        white-space: nowrap !important;
    }
    div[data-testid="stMarkdownContainer"] .json-code-content {
        margin: 0;
        color: #7DD3FC !important;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 0.8rem;
        line-height: 1.48;
        overflow-x: auto;
    }
</style>
""",
    unsafe_allow_html=True,
)


DEFAULT_CAMPAIGN_MOOD = (
    "[캠페인 제품] 저자극 시카 수분 앰플\n"
    "[특수 소구 포인트] 아기나 반려동물이 있는 집에서도 안심하고 쓰는 순한 성분과 속보습\n"
    "[지향 비주얼 무드] 인위적인 스튜디오 조명이나 자극적 전단지 배제, 따뜻한 자연광과 맑은 피부결(또는 차분한 일상 여백의 미)"
)


# ==============================================================================
# 3. 유틸리티: 인스타 ID 정제 & RAM 이미지 다운로드/Base64 변환
# ==============================================================================
def normalize_instagram_username(raw_input: str) -> str:
    cleaned = raw_input.strip()
    if not cleaned:
        return ""
    if "instagram.com" in cleaned or "/" in cleaned:
        info = detect_instagram_url_type(cleaned)
        if info.get("username"):
            return info["username"].lstrip("@").strip().lower()
    return cleaned.lstrip("@").strip().lower()


def download_image_to_ram_and_base64(image_url: str) -> Tuple[Optional[bytes], Optional[str], bool]:
    """
    인스타그램 CDN 이미지 URL을 디스크에 저장하지 않고 RAM으로 직접 다운로드하여 Base64로 인코딩합니다.
    """
    if not image_url:
        return None, None, True
    try:
        resp = requests.get(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.instagram.com/",
            },
            timeout=10,
        )
        if not resp.ok or not resp.content:
            return None, None, True

        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        stat = ImageStat.Stat(img)
        mean_brightness = sum(stat.mean) / max(1, len(stat.mean))
        is_black = mean_brightness < 3.0

        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        jpeg_bytes = buf.getvalue()
        b64_str = base64.b64encode(jpeg_bytes).decode("utf-8")
        return jpeg_bytes, b64_str, is_black
    except Exception:
        return None, None, True


def format_compact_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


# ==============================================================================
# 4. 마이크로 인플루언서 등급 분류 & 권장 원고료 산정 엔진 (7,000명 유가 시작 기준)
# ==============================================================================
def calculate_influencer_tier_and_fee(
    followers_count: int,
    posts: List[Dict[str, Any]],
    fit_status: str,
    media_analysis: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    [확정된 원고료 산정 스텝 테이블]
    - 팔로워 7,000명 미만 (0 ~ 6,999명): 0원 (제품 무상 시딩 권장)
    - 팔로워 7,000명 ~ 1만 미만 (7,000 ~ 9,999명): 유가 원고료 시작가 '3만 원' (반응률·비주얼 최우수 시 '5만 원')
    - 팔로워 1만 ~ 10만 미만: 5만 원 단위로 끊어서 표기 ('5만 원', '10만 원', '15만 원' ... 최대 '50만 원')
    - 팔로워 10만 이상: '50만 원+ (매크로 티어 · 별도 단가 협의)'
    - 단, AI 판정이 REJECT이면 '산정 제외 (0원 — 섭외 비권장)'
    """
    # 최근 게시물 평균 반응률(ER) 계산
    if posts and followers_count > 0:
        avg_eng = sum(p.get("like_count", 0) + p.get("comment_count", 0) for p in posts) / len(posts)
        er_pct = round((avg_eng / followers_count) * 100, 2)
    else:
        er_pct = 0.0

    # 평균 비주얼 감도 점수 계산
    if media_analysis:
        avg_aes = sum(int(m.get("aesthetic_score", 5)) for m in media_analysis) / len(media_analysis)
    else:
        avg_aes = 5.0

    # 팔로워 구간별 인플루언서 티어 라벨
    if followers_count < 7_000:
        tier_label = "🌱 시딩 나노 (팔로워 7천 미만)"
    elif followers_count < 10_000:
        tier_label = "🌿 유가 진입 나노 (팔로워 7천~1만)"
    elif followers_count < 30_000:
        tier_label = "🎯 초기 마이크로 (팔로워 1만~3만)"
    elif followers_count < 100_000:
        tier_label = "💎 핵심 마이크로 (팔로워 3만~10만)"
    else:
        tier_label = "🚀 매크로 인플루언서 (팔로워 10만+)"

    # 1) 부적합(REJECT) 또는 데이터 부족(DATA_INSUFFICIENT) 예외 처리
    if fit_status == "REJECT":
        return {
            "tier_label": tier_label,
            "er_display": f"{er_pct}%",
            "strategy_text": "🚫 섭외 비권장 (캠페인 무드 부적합)",
            "fee_badge": "산정 제외 (0원)",
            "basis_note": "AI 비주얼 적합도 판정이 REJECT(부적합)이므로 원고료 및 시딩 예산을 배정하지 않습니다.",
            "is_rejected": "true",
        }
    if fit_status == "DATA_INSUFFICIENT":
        return {
            "tier_label": tier_label,
            "er_display": "-",
            "strategy_text": "⚪ 피드 확인 후 산정 가능",
            "fee_badge": "산정 보류",
            "basis_note": "계정 비공개 또는 게시물 미존재로 인해 원고료 산정을 보류합니다.",
            "is_rejected": "false",
        }

    # 2) 팔로워 7,000명 미만 -> 0원 (무상 시딩 전용 구간)
    if followers_count < 7_000:
        return {
            "tier_label": tier_label,
            "er_display": f"{er_pct}%",
            "strategy_text": "📦 제품 무상 시딩 (자연 DM 섭외 가능)",
            "fee_badge": "0원 (무상 시딩)",
            "basis_note": f"팔로워 7,000명 미만({followers_count:,}명) 구간으로, 원고료 없이 제품 무상 제공 DM만으로 섭외 진행을 권장합니다.",
            "is_rejected": "false",
        }

    # 3) 팔로워 7,000명 ~ 1만 명 미만 -> 유가 원고료 시작 구간 (3만 원 기본, 최우수 시 5만 원)
    if followers_count < 10_000:
        is_top_performer = (er_pct >= 3.0) and (avg_aes >= 8.0)
        fee_str = "5만 원" if is_top_performer else "3만 원"
        return {
            "tier_label": tier_label,
            "er_display": f"{er_pct}%",
            "strategy_text": "💌 제품 시딩 + 소액 원고료 병행 권장",
            "fee_badge": fee_str,
            "basis_note": (
                f"유가 원고료 시작 구간(팔로워 7천 명 이상, 현재 {followers_count:,}명 · 반응률 {er_pct}%)으로 "
                f"무상 DM 거절 방지를 위해 시작 원고료 {fee_str} 책정을 권장합니다."
            ),
            "is_rejected": "false",
        }

    # 4) 팔로워 1만 명 ~ 10만 명 미만 -> 5만 원 단위 스텝 (5만 / 10만 / 15만 ... 최대 50만 원)
    if followers_count < 100_000:
        # 기본 단가: 팔로워 1만 명당 8.5만 원 기준
        base_man = (followers_count / 10_000.0) * 8.5
        er_mult = 1.15 if er_pct >= 3.0 else (1.0 if er_pct >= 1.0 else 0.85)
        vis_mult = 1.1 if avg_aes >= 8.0 else 1.0
        raw_man = base_man * er_mult * vis_mult

        # 5만 원 단위 반올림 스냅핑 (최소 5만 원 ~ 최대 50만 원)
        snapped_man = int(round(raw_man / 5.0) * 5)
        snapped_man = max(5, min(50, snapped_man))
        fee_str = f"{snapped_man}만 원"

        strategy = (
            "💰 유가 원고료 필수 (자연 무상 DM 수락 어려움)"
            if followers_count >= 30_000
            else "💳 원고료 제안 권장 (수락률 및 퀄리티 보장)"
        )
        return {
            "tier_label": tier_label,
            "er_display": f"{er_pct}%",
            "strategy_text": strategy,
            "fee_badge": fee_str,
            "basis_note": (
                f"팔로워 {followers_count:,}명 · 평균 반응률 {er_pct}% · 비주얼 감도 {avg_aes:.1f}/10점 반영 "
                f"(5만 원 단위 스텝 적용 · 마이크로 상한 50만 원 기준)"
            ),
            "is_rejected": "false",
        }

    # 5) 팔로워 10만 명 이상 -> 50만 원+ (매크로 별도 단가 협의)
    return {
        "tier_label": tier_label,
        "er_display": f"{er_pct}%",
        "strategy_text": "🏢 유가 캠페인 / 에이전시 별도 협의 필수",
        "fee_badge": "50만 원+ (별도 협의)",
        "basis_note": (
            f"팔로워 10만 명 이상({followers_count:,}명) 매크로 구간으로 마이크로 원고료 상한(50만 원)을 초과합니다. "
            "MCN 소속사 또는 별도 광고 단가 협의를 권장합니다."
        ),
        "is_rejected": "false",
    }


# ==============================================================================
# 5. 대표 비주얼 3장 선별 알고리즘 (캠페인 연관 최신 + 최근 업로드 + 반응도 1위)
# ==============================================================================
def extract_campaign_keywords(campaign_text: str) -> List[str]:
    base_kw = [
        "수분", "앰플", "세럼", "피부", "스킨케어", "보습", "진정", "자연광",
        "홈카페", "미니멀", "클린", "루틴", "뷰티", "화장품", "크림", "광채", "케어",
    ]
    extra = re.findall(r"[가-힣a-zA-Z]{2,}", campaign_text)
    combined = list(dict.fromkeys(base_kw + [w for w in extra if len(w) >= 2]))
    return combined[:30]


def select_top3_representative_posts(
    posts: List[Dict[str, Any]],
    campaign_text: str,
) -> List[Dict[str, Any]]:
    if not posts:
        return []

    non_pinned = [p for p in posts if not p.get("is_pinned")]
    pool = sorted(
        non_pinned if non_pinned else posts,
        key=lambda x: x.get("taken_at_timestamp", 0),
        reverse=True,
    )

    keywords = extract_campaign_keywords(campaign_text)
    selected: List[Dict[str, Any]] = []
    used_codes = set()

    # Slot 1: 🎯 캠페인 연관 최신 1위
    best_rel_post = None
    best_rel_score = -1
    for p in pool:
        cap = str(p.get("caption", ""))
        hit_cnt = sum(1 for kw in keywords if kw in cap)
        if hit_cnt > best_rel_score:
            best_rel_score = hit_cnt
            best_rel_post = p

    if best_rel_post is None:
        best_rel_post = pool[0]

    p1 = dict(best_rel_post)
    p1["selection_badge"] = f"🎯 선정 1: 캠페인 연관 최신 ({p1.get('upload_date', '')})"
    selected.append(p1)
    used_codes.add(p1.get("shortcode"))

    # Slot 2: 🆕 최근 업로드 최신컷
    for p in pool:
        if p.get("shortcode") not in used_codes:
            p2 = dict(p)
            p2["selection_badge"] = f"🆕 선정 2: 최근 업로드 최신컷 ({p2.get('upload_date', '')})"
            selected.append(p2)
            used_codes.add(p2.get("shortcode"))
            break

    # Slot 3: 🔥 최근 반응도 1위 컷
    remaining = [p for p in pool if p.get("shortcode") not in used_codes]
    if remaining:
        by_engagement = sorted(
            remaining,
            key=lambda x: (x.get("like_count", 0) * 2 + x.get("comment_count", 0) * 5 + x.get("view_count", 0)),
            reverse=True,
        )
        p3 = dict(by_engagement[0])
        p3["selection_badge"] = f"🔥 선정 3: 반응도 1위 (♥{p3.get('like_count', 0):,})"
        selected.append(p3)

    return selected[:3]


# ==============================================================================
# 6. 실시간 인스타그램 크롤러 (100% Live Instagram Scraping)
# ==============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def crawl_live_instagram_account(username: str) -> Dict[str, Any]:
    clean_user = normalize_instagram_username(username)
    if not clean_user:
        return {"status": "ACCOUNT_NOT_FOUND", "username": "", "profile": {}, "posts": []}

    og_header = fetch_live_profile_header(clean_user)

    embed_ctx: Dict[str, Any] = {}
    raw_graphql_media: List[Dict[str, Any]] = []
    is_private_detected = False

    try:
        resp = requests.get(
            f"https://www.instagram.com/{clean_user}/embed/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.ok:
            if '"is_private":true' in resp.text:
                is_private_detected = True
            ctx_m = re.search(r'"contextJSON"\s*:\s*"((?:\\.|[^"\\])*)"', resp.text)
            if ctx_m:
                parsed_json = json.loads(json.loads(f'"{ctx_m.group(1)}"'))
                embed_ctx = parsed_json.get("context", {}) or {}
                raw_graphql_media = embed_ctx.get("graphql_media", []) or []
    except Exception:
        pass

    has_embed_profile = bool(embed_ctx.get("username") or embed_ctx.get("owner_id"))
    has_og_profile = bool(og_header.get("is_live_fetched"))

    if not has_embed_profile and not has_og_profile:
        return {
            "status": "ACCOUNT_NOT_FOUND",
            "username": clean_user,
            "profile": {
                "full_name": "조회 불가 계정",
                "followers_count": 0,
                "followers_display": "-",
                "posts_count": 0,
                "posts_display": "0",
                "biography": "",
            },
            "posts": [],
        }

    followers_cnt = embed_ctx.get("followers_count")
    if followers_cnt is None:
        followers_cnt = og_header.get("followers", 0)
    posts_cnt = embed_ctx.get("posts_count")
    if posts_cnt is None:
        posts_cnt = og_header.get("total_posts", 0)

    full_name = embed_ctx.get("full_name") or og_header.get("full_name") or clean_user
    followers_disp = (
        format_compact_number(int(followers_cnt))
        if isinstance(followers_cnt, int) and followers_cnt > 0
        else og_header.get("followers_display", "0")
    )
    posts_disp = f"{int(posts_cnt):,}" if isinstance(posts_cnt, int) else og_header.get("total_posts_display", "0")

    profile_summary = {
        "username": clean_user,
        "full_name": full_name,
        "followers_count": int(followers_cnt or 0),
        "followers_display": followers_disp,
        "posts_count": int(posts_cnt or 0),
        "posts_display": posts_disp,
        "biography": og_header.get("biography", ""),
        "is_verified": bool(embed_ctx.get("is_verified") or embed_ctx.get("verified")),
    }

    if is_private_detected or (int(posts_cnt or 0) > 0 and len(raw_graphql_media) == 0):
        return {
            "status": "PRIVATE_ACCOUNT",
            "username": clean_user,
            "profile": profile_summary,
            "posts": [],
        }

    if len(raw_graphql_media) == 0:
        return {
            "status": "EMPTY_ACCOUNT",
            "username": clean_user,
            "profile": profile_summary,
            "posts": [],
        }

    parsed_posts: List[Dict[str, Any]] = []
    now_ts = int(time.time())

    for item in raw_graphql_media:
        sm = item.get("shortcode_media", item) or {}
        sc = sm.get("shortcode")
        if not sc:
            continue

        slides = _extract_from_media_root_dict(sm)
        meta = _extract_post_metadata_from_dict(sm, sc)
        ts = int(meta.get("taken_at_timestamp") or now_ts)
        upload_dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        days_ago = max(0, int(round((now_ts - ts) / 86400)))

        img_url = sm.get("display_url") or (slides[0]["thumbnail_url"] if slides else "")
        caption_text = (meta.get("caption") or "").strip()

        parsed_posts.append(
            {
                "shortcode": sc,
                "post_url": f"https://www.instagram.com/p/{sc}/",
                "taken_at_timestamp": ts,
                "upload_date": upload_dt,
                "days_ago": days_ago,
                "is_pinned": bool(meta.get("is_pinned", False)),
                "is_video": bool(meta.get("is_video", False)),
                "is_carousel": len(slides) > 1,
                "slide_count": max(1, len(slides)),
                "like_count": int(meta.get("like_count", 0)),
                "comment_count": int(meta.get("comment_count", 0)),
                "view_count": int(meta.get("view_count", 0)),
                "caption": caption_text,
                "display_url": img_url,
                "is_paid_partnership": bool(sm.get("is_paid_partnership")),
            }
        )

    return {
        "status": "NORMAL_PUBLIC",
        "username": clean_user,
        "profile": profile_summary,
        "posts": parsed_posts,
    }


def extract_hashtags_and_sponsorship_summary(posts: List[Dict[str, Any]]) -> Tuple[List[str], str]:
    all_tags: List[str] = []
    ad_post_count = 0
    hotdeal_post_count = 0

    ad_keywords = ("#광고", "#협찬", "#제품제공", "#유료광고", "제공받아", "지원받아")
    hotdeal_keywords = ("핫딜", "특가", "공구", "최저가", "구매정보", "프로필 링크", "프로필하단")

    for p in posts:
        cap = p.get("caption", "") or ""
        found_tags = re.findall(r"#([가-힣a-zA-Z0-9_]+)", cap)
        for t in found_tags:
            tag_str = f"#{t}"
            if tag_str not in all_tags:
                all_tags.append(tag_str)

        if p.get("is_paid_partnership") or any(k in cap for k in ad_keywords):
            ad_post_count += 1
        if any(k in cap for k in hotdeal_keywords):
            hotdeal_post_count += 1

    if not all_tags:
        all_words: List[str] = []
        for p in posts:
            words = re.findall(r"[가-힣]{2,6}", p.get("caption", "") or "")
            for w in words:
                if w not in ("그리고", "너무", "진짜", "정말", "이번", "오늘", "바로") and f"#{w}" not in all_tags:
                    all_words.append(f"#{w}")
        all_tags = list(dict.fromkeys(all_words))[:6] or ["#해시태그없음"]

    total_p = len(posts)
    if hotdeal_post_count >= max(2, total_p // 2):
        summary = f"🚨 최근 게시물 {total_p}건 중 {hotdeal_post_count}건이 '핫딜·특가·링크 유도' 상업성 피드"
    elif ad_post_count >= 1:
        summary = f"✅ 최근 게시물 {total_p}건 중 협찬·광고 리뷰 {ad_post_count}건 확인 (가이드 수행 경험 보유)"
    else:
        summary = f"✨ 최근 게시물 {total_p}건 중 명시적 광고 태그 없음 (일상·오가닉 콘텐츠 중심)"

    return all_tags[:8], summary


def build_live_fallback_evaluation(reason_msg: str, one_line: str, frame_count: int = 1) -> Dict[str, Any]:
    return {
        "media_analysis": [
            {
                "aesthetic_score": 1,
                "texture_rendering": "UNANALYZABLE",
                "lifestyle_context": "UNANALYZABLE",
                "visual_appeal": "UNANALYZABLE",
                "scene_type_kr": "판독 불가 미디어",
            }
            for _ in range(max(1, frame_count))
        ],
        "overall_match_percentage": 0,
        "fit_status": "DATA_INSUFFICIENT",
        "one_line_verdict": one_line,
        "expected_collisions": ["비주얼/캡션 데이터 부족", "사전 방어 게이트 작동"],
        "rationale_bullets": [
            f"① [계정 상태 진단] {reason_msg}",
            "② [비용 및 에러 방어] 불필요한 LLM API 과금과 500 서버 에러를 사전 차단했습니다.",
        ],
        "decision_rationale": reason_msg,
    }


# ==============================================================================
# 7. 실시간 GPT-4o Vision API + 멘토링 맞춤 구조화 출력 (릴스 자막 vs 전단지 정밀 구분)
# ==============================================================================
def build_live_evaluation_system_prompt(brand_dna: str, campaign_text: str) -> str:
    return f"""
너는 InfluenceOps v3.0의 수석 뷰티·라이프스타일 인플루언서 스카우터 AI 에이전트야.
아래 [우리 브랜드 페르소나 DNA]와 [이번 캠페인 소구 포인트 & 지향 무드]를 기준으로,
실시간 크롤링된 인플루언서의 대표 피드(Photo 1~3) 이미지와 캡션 내용을 정밀 분석하여 LiveInfluencerEvaluation JSON으로 응답해.

[데이터 1: 우리 브랜드 페르소나 DNA]
{brand_dna}

[데이터 2: 이번 캠페인 소구 포인트 & 지향 무드]
{campaign_text}

[★ 핵심 판정 기준 및 오판 방지 지침 (매우 중요)]
1. "APPROVE" (섭외 추천 — 뷰티/스킨케어 고관여 & 꿀팁 크리에이터):
   - 캡션이나 영상/사진에서 구체적인 피부 고민(여드름, 지성, 건성, 속건조, 민감성, 환절기 뒤집어짐, 붉은기 등), 스킨케어 루틴, 화장품/연고/팩 사용 후기, 올리브영·다이소 추천템 꿀팁 등을 진정성 있게 다루는 계정은 팔로워 규모와 무관하게 반드시 "APPROVE"로 판정해!
   - [오판 절대 금지]: 뷰티 릴스(Reels) 영상 썸네일이나 정보성 카드뉴스 특성상, 사진 위에 '여드름 꿀팁', '단계별 추천템' 같은 제목 자막(타이포그래피)이 들어간 것은 상업 전단지가 아니라 **정보 전달력이 뛰어난 뷰티 고관여 콘텐츠(BEAUTY_HIGH_INVOLVEMENT)**야! 이를 절대 전단지나 HEAVY_FILTER로 오판하여 REJECT 주지 마!
   - 또한 뷰티 크리에이터가 '올영 블프 추천템', '구매방법 스토리 안내', '직접 구매 가격' 등을 적는 것은 팔로워를 위한 친절한 정보 공유이므로 긍정적으로 평가해.

2. "CREATIVE_EXCEPTION" (크리에이티브 예외 승인 권장 — 감성 라이프스타일/무드 매칭형):
   - 직접적인 스킨케어/화장품 리뷰는 적더라도, 따뜻한 자연광·홈카페·인테리어·미니멀 일상 등 비주얼 감도가 뛰어나 브랜드 무드 컷 시딩에 적합한 계정에 부여해.

3. "REJECT" (협찬 부적합 — 실제 부적합 사유를 구체적으로 명시할 것):
   - 아래 경우에 해당할 때만 "REJECT"를 부여해:
     (a) [카테고리 불일치]: 맛집·음식점 리뷰(라멘, 국밥 등), 단순 일상 유머, 혹은 소개팅 앱·경품 추첨 이벤트 등 스킨케어/감성 라이프스타일과 무관한 주제나 잡다한 협찬이 주를 이루는 계정
     (b) [단순 핫딜/할인 링크 봇]: 본인의 피부 사진이나 직접 겪은 후기 없이, 매일 '11월 X일자 오늘의 핫딜', '선착순 특가 프로필 링크' 같은 쇼핑몰 할인 전단지 배너만 기계적으로 올리는 계정
     (c) [브랜드 무드 상충]: 비주얼 톤이 캠페인 지향 무드와 심각하게 충돌하는 계정

[★ 문장 작성 필수 규칙 — 상투적/고정 멘트 절대 금지]
- '과도한 상업적 텍스트와 전단지형 이미지로 브랜드 무드와 맞지 않아 제외를 권장합니다' 같은 기계적이고 획일적인 문장을 절대 그대로 쓰지 마!
- `one_line_verdict`(1줄 요약)와 `rationale_bullets`(3줄 상세 사유)에는 반드시 **해당 인플루언서의 실제 캡션과 사진에 등장한 구체적 키워드(예: '지성·여드름 피부 단계별 추천템과 마스크팩 후기', '동성로 라멘 맛집 리뷰 및 경품·소개팅 협찬', '날짜별 오늘의 핫딜 링크 모음' 등)를 직접 언급**하여 계정마다 100% 고유하고 설득력 있는 분석 리포트를 작성해.
""".strip()


def run_live_gpt4o_evaluation(
    username: str,
    profile_summary: Dict[str, Any],
    all_posts: List[Dict[str, Any]],
    brand_dna: str,
    campaign_text: str,
    selected_posts: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], float]:
    start_t = time.perf_counter()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return (
            build_live_fallback_evaluation(
                "OPENAI_API_KEY가 설정되어 있지 않아 실시간 분석을 수행할 수 없습니다.",
                "API 키 미설정으로 분석 대기 중입니다.",
                frame_count=len(selected_posts),
            ),
            0.0,
        )

    valid_b64_list: List[str] = []
    black_count = 0
    for p in selected_posts:
        b64 = p.get("base64_image")
        if p.get("is_black_or_invalid"):
            black_count += 1
        if b64:
            valid_b64_list.append(b64)

    if not valid_b64_list or black_count == len(selected_posts):
        return (
            build_live_fallback_evaluation(
                f"{username} 계정의 대표 미디어가 암전(Black Screen) 상태이거나 이미지를 불러올 수 없습니다.",
                "판독 가능한 정상 피드 이미지가 없어 분석을 보류합니다.",
                frame_count=len(selected_posts),
            ),
            round(time.perf_counter() - start_t, 2),
        )

    combined_captions = []
    for idx, p in enumerate(selected_posts, start=1):
        cap_preview = (p.get("caption") or "(캡션 텍스트 없음)").strip()
        media_kind = (
            "릴스(Reels) 숏폼 영상 썸네일 (영상 자막 포함 가능)"
            if p.get("is_video")
            else ("다중 사진 캐러셀" if p.get("is_carousel") else "단일 사진 피드")
        )
        combined_captions.append(
            f"[Photo {idx} | 콘텐츠 형태: {media_kind} | 업로드일: {p.get('upload_date')} | 좋아요: {p.get('like_count', 0)}개]\n"
            f"캡션 원문: {cap_preview}"
        )
    joined_caption_text = "\n\n".join(combined_captions)

    # 전체 최근 게시물(최대 6건)의 캡션 요약도 함께 전달하여 계정 전체 성향을 정확히 파악하도록 지원
    other_caps = []
    selected_codes = {p.get("shortcode") for p in selected_posts}
    for p in all_posts:
        if p.get("shortcode") not in selected_codes and p.get("caption"):
            short_c = p["caption"].replace("\n", " ")[:110]
            other_caps.append(f"- ({p.get('upload_date')}, ♥{p.get('like_count', 0)}): {short_c}")
    other_context_str = "\n".join(other_caps) if other_caps else "(추가 게시물 없음)"

    system_prompt = build_live_evaluation_system_prompt(brand_dna, campaign_text)
    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"[실시간 크롤링 타겟 계정]: @{username} (이름: {profile_summary.get('full_name', username)}, "
                f"팔로워: {profile_summary.get('followers_count', 0):,}명, 총 게시물: {profile_summary.get('posts_count', 0)}개)\n"
                f"[프로필 소개글(Bio)]: {profile_summary.get('biography') or '(소개글 없음)'}\n\n"
                f"[선별된 대표 게시물 {len(valid_b64_list)}장의 메타데이터 및 원본 캡션]:\n{joined_caption_text}\n\n"
                f"[계정 내 다른 최근 게시물 캡션 참고]:\n{other_context_str}\n\n"
                "위 실시간 인스타그램 피드 이미지(Photo 1~3)와 캡션 전체 맥락을 분석하여 LiveInfluencerEvaluation 스키마로 판정해.\n"
                "작성 지침:\n"
                "1) `one_line_verdict`: 이 계정이 실제로 어떤 주제/콘텐츠를 다루는지 구체적으로 언급하며 왜 적합(APPROVE/CREATIVE_EXCEPTION)한지 또는 왜 부적합(REJECT)한지 1줄로 명확히 요약해. (상투적인 고정 멘트 절대 금지!)\n"
                "2) 각 사진의 `scene_type_kr`: 사진과 콘텐츠 형태를 보고 '여드름·스킨케어 꿀팁 릴스', '손등 제형 클로즈업샷', '비포앤애프터 비교컷', '창가 자연광 피부결 셀카', '우드톤 홈카페 무드컷', '맛집 음식 리뷰컷', '특가 텍스트 전단지 배너' 등 실제 연출 형태를 직관적인 한국어로 표기해.\n"
                "3) `rationale_bullets`: ① [비주얼·콘텐츠 성격], ② [연출력·캠페인 매칭도], ③ [최종 섭외 제언] 3가지 항목으로 나누어 이 계정의 실제 게시글 내용을 근거로 작성해."
            ),
        }
    ]

    for b64_img in valid_b64_list:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_img}",
                    "detail": "low",
                },
            }
        )

    try:
        client = OpenAI(api_key=api_key)
        response = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=LiveInfluencerEvaluation,
            temperature=0.0,
        )
        msg = response.choices[0].message
        if msg.refusal or msg.parsed is None:
            return (
                build_live_fallback_evaluation(
                    f"LLM 응답 거부 또는 파싱 불가: {msg.refusal or 'parsed is None'}",
                    "AI 모델 응답 제한으로 인해 판정을 보류합니다.",
                    frame_count=len(valid_b64_list),
                ),
                round(time.perf_counter() - start_t, 2),
            )

        elapsed = round(time.perf_counter() - start_t, 2)
        dumped = msg.parsed.model_dump()
        dumped["decision_rationale"] = "\n".join(dumped.get("rationale_bullets", []))
        return dumped, elapsed
    except Exception as e:
        return (
            build_live_fallback_evaluation(
                f"실시간 분석 중 예외 발생 ({type(e).__name__}: {str(e)[:100]})",
                "일시적인 분석 오류로 인해 안전 방어 모드가 작동했습니다.",
                frame_count=len(valid_b64_list),
            ),
            round(time.perf_counter() - start_t, 2),
        )


# ==============================================================================
# 8. 직관적인 한글 배지 기반 3대 지표 분석표 렌더러
# ==============================================================================
def render_evaluation_html_table(media_list: List[Dict[str, Any]]) -> str:
    texture_kr_map = {
        "NATURAL_GLOW": "✨ 맑은 자연광 · 본연 질감",
        "MODERATE_EDIT": "🎨 자연스러운 보정 · 무난",
        "HEAVY_FILTER": "⚠️ 과도한 필터 · 텍스트 배너",
        "UNANALYZABLE": "⚪ 판독 불가",
    }
    context_kr_map = {
        "BEAUTY_HIGH_INVOLVEMENT": "💄 뷰티 · 스킨케어 고관여",
        "DAILY_CASUAL": "🌿 감성 일상 · 라이프스타일",
        "IRRELEVANT": "🚫 캠페인 무관 (타 카테고리/단순광고)",
        "UNANALYZABLE": "⚪ 판독 불가",
    }

    rows_html = ""
    for idx, m in enumerate(media_list, start=1):
        score = int(m.get("aesthetic_score", 1))
        if score >= 8:
            score_badge = f"<b>{score} / 10</b> <span style='color:#059669 !important;font-weight:700;'>(우수 ✨)</span>"
        elif score >= 5:
            score_badge = f"<b>{score} / 10</b> <span style='color:#D97706 !important;font-weight:700;'>(보통 🟡)</span>"
        else:
            score_badge = f"<b>{score} / 10</b> <span style='color:#DC2626 !important;font-weight:700;'>(미흡 ⚠️)</span>"

        tex_raw = m.get("texture_rendering", "UNANALYZABLE")
        ctx_raw = m.get("lifestyle_context", "UNANALYZABLE")
        scene_kr = m.get("scene_type_kr") or "일반 피드 연출컷"

        rows_html += (
            f"<tr>"
            f"<td><b>Photo {idx}</b></td>"
            f"<td>{score_badge}</td>"
            f"<td>{texture_kr_map.get(tex_raw, tex_raw)}</td>"
            f"<td>{context_kr_map.get(ctx_raw, ctx_raw)}</td>"
            f"<td><span class='scene-pill'>📸 {html.escape(str(scene_kr))}</span></td>"
            f"</tr>"
        )
    return (
        "<table class='eval-table'>"
        "<thead><tr>"
        "<th>프레임</th>"
        "<th>① 비주얼 감도</th>"
        "<th>② 피부결 · 질감 표현</th>"
        "<th>③ 일상 · 카테고리 맥락</th>"
        "<th>④ 촬영 연출 형태 (AI 비전 판독)</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def main() -> None:
    st.markdown(
        """
        <div class="gnb-header">
            <div class="logo-wrap">
                <div class="logo-title">Influence<span class="logo-ops">Ops</span><span class="logo-sparkle">✦</span></div>
                <div class="logo-sub">AI-POWERED INFLUENCER MARKETING DECISION SYSTEM</div>
            </div>
            <div class="poc-pill">Prototype 2. 인스타 ID 실시간 크롤링 & 원고료 산정 · AI 판정 버전</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "target_ig_id" not in st.session_state:
        st.session_state["target_ig_id"] = "day_zip_b"
    if "live_eval_cache" not in st.session_state:
        st.session_state["live_eval_cache"] = {}

    left_col, right_col = st.columns([1.0, 1.08], gap="large")

    with left_col:
        st.markdown('<div class="panel-header-bar">📥 1. 캠페인 무드 & 인스타그램 ID 실시간 조회 (Live Input)</div>', unsafe_allow_html=True)
        with st.container(border=True):
            with st.expander("🧬 [정적 온보딩 데이터] 학습된 우리 브랜드 페르소나 DNA 확인", expanded=False):
                brand_dna_input = st.text_area(
                    "Brand Persona DNA",
                    value=BRAND_PERSONA_DNA,
                    height=85,
                    label_visibility="collapsed",
                )

            st.markdown("**🎯 캠페인 소구 포인트 & 지향 무드 (Campaign Data)**")
            campaign_text = st.text_area(
                "캠페인 소구 포인트",
                value=DEFAULT_CAMPAIGN_MOOD,
                height=80,
                label_visibility="collapsed",
            )

            st.markdown("**🔎 타겟 인플루언서 인스타그램 ID 입력 (`@` 없이 아이디만 입력)**")
            with st.form(key="ig_search_form", clear_on_submit=False, border=False):
                id_col, btn_col = st.columns([3.1, 1.3])
                with id_col:
                    typed_id = st.text_input(
                        "인스타그램 ID 입력",
                        value=st.session_state["target_ig_id"],
                        placeholder="예: day_zip_b, tmrw_sunshine, today_hotdael1026",
                        label_visibility="collapsed",
                    )
                with btn_col:
                    search_submitted = st.form_submit_button(
                        "🔍 실시간 크롤링 & 분석",
                        use_container_width=True,
                    )

            cleaned_id = normalize_instagram_username(typed_id)
            if search_submitted and cleaned_id:
                st.session_state["target_ig_id"] = cleaned_id
                cache_key_inv = f"v3::{cleaned_id}::{hash(campaign_text)}::{hash(brand_dna_input)}"
                st.session_state["live_eval_cache"].pop(cache_key_inv, None)

            active_username = normalize_instagram_username(st.session_state["target_ig_id"])

            # 1) 실시간 인스타그램 크롤링
            with st.spinner(f"인스타그램에서 '{active_username}' 계정의 실시간 프로필 및 최근 피드를 크롤링 중입니다..."):
                crawled = crawl_live_instagram_account(active_username)

            account_status = crawled["status"]
            prof = crawled["profile"]
            raw_posts = crawled["posts"]

            # 2) 대표 비주얼 3장 선별 & RAM 메모리 이미지 다운로드 + Base64 인코딩
            selected_posts: List[Dict[str, Any]] = []
            if account_status == "NORMAL_PUBLIC" and raw_posts:
                top3_candidates = select_top3_representative_posts(raw_posts, campaign_text)
                for p in top3_candidates:
                    img_bytes, b64_str, is_black = download_image_to_ram_and_base64(p.get("display_url", ""))
                    p_enriched = dict(p)
                    p_enriched["image_bytes"] = img_bytes
                    p_enriched["base64_image"] = b64_str
                    p_enriched["is_black_or_invalid"] = is_black
                    selected_posts.append(p_enriched)

            # 3) AI 평가 수행 (원고료 산정에 적합도 판정 결과를 함께 반영하기 위해 여기서 호출)
            elapsed_sec: Optional[float] = None
            if account_status == "ACCOUNT_NOT_FOUND":
                result_data = build_live_fallback_evaluation(
                    f"입력하신 인스타그램 아이디('{active_username}')가 존재하지 않거나 삭제된 계정입니다.",
                    f"존재하지 않는 인스타그램 아이디('{active_username}')입니다. 철자를 확인해 주세요.",
                    frame_count=1,
                )
            elif account_status == "PRIVATE_ACCOUNT":
                result_data = build_live_fallback_evaluation(
                    f"대상 계정('{active_username}', 팔로워 {prof.get('followers_display')})이 현재 비공개(Private) 상태여서 피드 수집이 차단되었습니다.",
                    f"현재 비공개(Private)로 전환된 계정이어서 피드 비주얼 열람이 불가능합니다.",
                    frame_count=1,
                )
            elif account_status == "EMPTY_ACCOUNT" or not selected_posts:
                result_data = build_live_fallback_evaluation(
                    f"대상 계정('{active_username}')에 분석 가능한 공개 게시물이 존재하지 않습니다.",
                    "업로드된 공개 게시물이 없어 비주얼 분석을 수행할 수 없습니다.",
                    frame_count=1,
                )
            else:
                cache_key = f"v3::{active_username}::{hash(campaign_text)}::{hash(brand_dna_input)}"
                if cache_key not in st.session_state["live_eval_cache"]:
                    with st.spinner(f"실시간 크롤링된 '{active_username}' 피드 {len(selected_posts)}장을 GPT-4o Vision으로 분석 중입니다..."):
                        eval_dict, elapsed = run_live_gpt4o_evaluation(
                            username=active_username,
                            profile_summary=prof,
                            all_posts=raw_posts,
                            brand_dna=brand_dna_input,
                            campaign_text=campaign_text,
                            selected_posts=selected_posts,
                        )
                        st.session_state["live_eval_cache"][cache_key] = (eval_dict, elapsed)
                result_data, elapsed_sec = st.session_state["live_eval_cache"][cache_key]

            fit_status = result_data.get("fit_status", "DATA_INSUFFICIENT")
            media_list = result_data.get("media_analysis", [])

            # 최근 실제 업로드 일자 진단 (상단 고정 제외)
            non_pinned_posts = [p for p in raw_posts if not p.get("is_pinned")] or raw_posts
            if non_pinned_posts:
                latest_p = max(non_pinned_posts, key=lambda x: x.get("taken_at_timestamp", 0))
                last_upload_str = f"📅 {latest_p['upload_date']} (최근 수집 {len(raw_posts)}건)"
            elif account_status == "PRIVATE_ACCOUNT":
                last_upload_str = "🔒 비공개 계정 (열람 제한)"
            else:
                last_upload_str = "확인 불가"

            status_badge_txt = (
                "🟢 공개 계정 (실시간 크롤링 완료)"
                if account_status == "NORMAL_PUBLIC"
                else (
                    "🔒 비공개 계정 (Private)"
                    if account_status == "PRIVATE_ACCOUNT"
                    else ("⚪ 게시물 없음" if account_status == "EMPTY_ACCOUNT" else "❌ 존재하지 않는 ID")
                )
            )

            # 👤 프로필 헬스 체크 바
            st.markdown(
                f"""
                <div class="profile-health-bar">
                    <div>👤 <b>조회 아이디:</b> <code>{active_username}</code> ({html.escape(str(prof.get('full_name', active_username)))}) &nbsp;|&nbsp; <b>상태:</b> {status_badge_txt}</div>
                    <div style="margin-top: 0.2rem;">📊 <b>팔로워:</b> {prof.get('followers_display', '-')} ({prof.get('followers_count', 0):,}명) &nbsp;|&nbsp; <b>총 게시물:</b> {prof.get('posts_display', '0')}개 &nbsp;|&nbsp; <b>최근 업로드:</b> {last_upload_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 💰 마이크로 인플루언서 등급 & 권장 원고료 산정 카드 (7,000명 유가 시작 기준)
            pricing_info = calculate_influencer_tier_and_fee(
                followers_count=int(prof.get("followers_count", 0)),
                posts=raw_posts,
                fit_status=fit_status,
                media_analysis=media_list,
            )
            p_card_cls = "pricing-card-reject" if pricing_info["is_rejected"] == "true" else "pricing-card"
            st.markdown(
                f"""
                <div class="{p_card_cls}">
                    <div>🏷️ <b>인플루언서 등급:</b> <b>{pricing_info['tier_label']}</b> (평균 반응률 {pricing_info['er_display']}) &nbsp;|&nbsp; <b>섭외 방식:</b> {pricing_info['strategy_text']}</div>
                    <div style="margin-top: 0.28rem;">💰 <b>AI 권장 원고료 (1건 기준):</b> <span class="fee-highlight">{pricing_info['fee_badge']}</span></div>
                    <div style="margin-top: 0.22rem; font-size: 0.79rem; color: #475569 !important;">• <b>산정 기준:</b> {pricing_info['basis_note']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 대표 피드 비주얼 3장 (클릭 시 인스타그램 원본 게시물 링크로 바로 이동!)
            if selected_posts:
                st.markdown(
                    """
                    <div class="selection-rule-banner">
                        📌 <b>실시간 대표 피드 3장 (썸네일 클릭 시 인스타그램 원본 게시물로 이동):</b> <b>① 캠페인 연관 최신</b> + <b>② 최근 업로드 최신컷</b> + <b>③ 반응도 1위</b>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                img_cols = st.columns(len(selected_posts))
                for idx, post_item in enumerate(selected_posts):
                    with img_cols[idx]:
                        b64_img = post_item.get("base64_image")
                        post_url = post_item.get("post_url", f"https://www.instagram.com/{active_username}/")
                        badge_txt = html.escape(post_item["selection_badge"])
                        footer_txt = f"🔗 Photo {idx+1} 인스타 원문 보기 (♥{post_item['like_count']:,})"
                        if b64_img:
                            st.markdown(
                                f"""
                                <a href="{post_url}" target="_blank" rel="noopener noreferrer" class="thumb-card-link" title="클릭하면 인스타그램 원본 게시물이 새 탭에서 열립니다">
                                    <div class="slot-reason-badge">{badge_txt}</div>
                                    <div class="thumb-img-wrap">
                                        <img src="data:image/jpeg;base64,{b64_img}" alt="Photo {idx+1}" />
                                    </div>
                                    <div class="thumb-footer">{footer_txt}</div>
                                </a>
                                """,
                                unsafe_allow_html=True,
                            )
                        else:
                            st.warning("이미지 로드 실패")

                extracted_tags, track_summary = extract_hashtags_and_sponsorship_summary(raw_posts)
            else:
                if account_status == "ACCOUNT_NOT_FOUND":
                    st.error(f"❌ 입력하신 아이디(`{active_username}`)는 인스타그램에 존재하지 않거나 조회할 수 없습니다.")
                    extracted_tags = ["#조회불가아이디"]
                    track_summary = "❌ 인스타그램에 존재하지 않는 계정으로 확인되어 LLM 호출을 사전 차단했습니다."
                elif account_status == "PRIVATE_ACCOUNT":
                    st.warning(f"🔒 `{active_username}` 계정은 현재 비공개(Private) 상태여서 피드 이미지를 가져올 수 없습니다.")
                    extracted_tags = ["#비공개계정"]
                    track_summary = "🔒 비공개 계정으로 전환되어 피드 수집이 차단되었습니다."
                else:
                    st.warning(f"⚪ `{active_username}` 계정에 공개된 게시물이 없습니다.")
                    extracted_tags = ["#게시물없음"]
                    track_summary = "⚪ 업로드된 게시물이 없는 계정입니다."

            # 크롤링 보조 요약 바 (지저분한 캡션 원문 창은 제거하고 핵심 태그/이력만 심플하게 표시)
            tags_html = "".join([f'<span class="tag-chip">{html.escape(t)}</span>' for t in extracted_tags])
            st.markdown(
                f"""
                <div class="meta-summary-bar">
                    <div>🏷️ <b>실시간 추출 해시태그 & 키워드:</b> {tags_html}</div>
                    <div style="margin-top: 0.25rem;">📋 <b>피드 광고/협찬 이력 진단:</b> {html.escape(track_summary)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ==============================================================================
    # 우측 패널: 멘토링 맞춤 가독성 고도화 AI 판정 리포트
    # ==============================================================================
    match_pct = result_data.get("overall_match_percentage", 0)
    one_line_verdict = result_data.get("one_line_verdict", "")
    collisions = result_data.get("expected_collisions", [])
    rationale_bullets = result_data.get("rationale_bullets", [])
    if not rationale_bullets and result_data.get("decision_rationale"):
        rationale_bullets = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", str(result_data["decision_rationale"])) if s.strip()
        ]

    with right_col:
        st.markdown('<div class="panel-header-bar">📊 2. 실시간 AI 비주얼 잠재력 & 적합도 판정 리포트 (Output)</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                f'<div class="section-title">{html.escape(active_username)} — 실시간 AI 적합도 판정 리포트</div>',
                unsafe_allow_html=True,
            )

            # 1) 상단 적합 판정 배너: 간결한 판정 등급 + LLM이 직접 작성한 1줄 핵심 사유
            if fit_status == "APPROVE":
                banner_cls = "status-approve"
                status_badge = "🟢 APPROVE (섭외 추천)"
            elif fit_status == "CREATIVE_EXCEPTION":
                banner_cls = "status-exception"
                status_badge = "🟠 CREATIVE_EXCEPTION (크리에이티브 예외 승인 권장)"
            elif fit_status == "REJECT":
                banner_cls = "status-reject"
                status_badge = "🔴 REJECT (협찬 부적합 · 섭외 제외)"
            else:
                banner_cls = "status-insufficient"
                status_badge = "⚪ DATA_INSUFFICIENT (분석 보류 · 사전 방어 작동)"

            elapsed_str = f" &nbsp;|&nbsp; ⚡ GPT-4o {elapsed_sec}초" if elapsed_sec is not None else ""

            st.markdown(
                f"""
                <div class="status-banner-box {banner_cls}">
                    <div class="status-banner-top">
                        <span>{status_badge}</span>
                        <span>종합 매칭률: {match_pct}%{elapsed_str}</span>
                    </div>
                    <div class="status-banner-sub">
                        💡 <b>AI 1줄 판정 요약:</b> {html.escape(str(one_line_verdict))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 2) 실시간 크롤링 대표 피드(Photo 1~3) 비주얼 잠재력 3대 지표 + 촬영 연출 형태
            st.markdown("**📸 대표 피드(Photo 1~3) 비주얼 잠재력 & 촬영 연출 형태 분석 (`MediaIntentAnalysis`)**")
            st.markdown(render_evaluation_html_table(media_list), unsafe_allow_html=True)

            # 3) 적합 / 부적합 상세 사유 박스 (포인트마다 1줄씩 엔터 처리하여 가독성 극대화)
            if fit_status == "APPROVE":
                box_cls = "rationale-box-approve"
                pts = " ".join([f"[{html.escape(str(c))}]" for c in collisions]) if collisions else "[비주얼 감도 및 피부결 연출 우수]"
                header_html = f"✅ <b>핵심 적합 포인트:</b> {pts}"
            elif fit_status == "REJECT":
                box_cls = "rationale-box-reject"
                pts = " ".join([f"[{html.escape(str(c))}]" for c in collisions]) if collisions else "[캠페인 무드 불일치]"
                header_html = f"🚨 <b>부적합 판정 핵심 요인:</b> {pts}"
            elif fit_status == "CREATIVE_EXCEPTION":
                box_cls = "rationale-box-warning"
                pts = " ".join([f"[{html.escape(str(c))}]" for c in collisions]) if collisions else "[감성 무드 잠재력 우수]"
                header_html = f"✨ <b>비주얼 잠재력(Potential) 포인트:</b> {pts}"
            else:
                box_cls = "rationale-box-warning"
                pts = " ".join([f"[{html.escape(str(c))}]" for c in collisions]) if collisions else "[사전 방어 게이트 작동]"
                header_html = f"🛡️ <b>사전 방어 게이트 작동 ({account_status}):</b> {pts}"

            bullets_html = "".join(
                [f'<div class="rationale-bullet-item">• {html.escape(str(b))}</div>' for b in rationale_bullets]
            )

            st.markdown(
                f"""
                <div class="{box_cls}">
                    <div style="margin-bottom: 0.4rem; padding-bottom: 0.35rem; border-bottom: 1px solid rgba(100,116,139,0.2);">{header_html}</div>
                    {bullets_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 4) 하단 다크 네이비 Pydantic JSON 뷰어
            json_display = {
                "queried_instagram_id": active_username,
                "influencer_tier": pricing_info["tier_label"],
                "recommended_fee": pricing_info["fee_badge"],
                "fit_status": fit_status,
                "overall_match_percentage": match_pct,
                "one_line_verdict": one_line_verdict,
                "expected_collisions": collisions,
                "rationale_bullets": rationale_bullets,
                "media_analysis": media_list,
            }
            formatted_json = json.dumps(json_display, ensure_ascii=False, indent=2)
            html_safe_json = (
                formatted_json.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace(" ", "&nbsp;")
                .replace("\n", "<br>")
            )
            st.markdown(
                f'<div class="json-dark-box">'
                f'<div class="json-dark-header">'
                f'<span class="json-title-text">🔍 [실시간 크롤링 + 원고료 산정 + Pydantic 구조화 JSON 출력]</span>'
                f'<span class="json-badge-ok">100% Live Schema Validated ✓</span>'
                f'</div>'
                f'<div class="json-code-content" style="color: #7DD3FC !important;">{html_safe_json}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
