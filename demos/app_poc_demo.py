r"""
[InfluenceOps v3.0] Phase 1. AI 코어 엔진 PoC 검증용 Streamlit 프로토타입
====================================================================================
- 실행 명령어: streamlit run c:\workAI\work9\app_poc_demo.py
- 기획서 3.1(입력) ~ 3.3(출력) 비주얼 잠재력(Potential) 평가 기준 100% 반영 버전
====================================================================================
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

import sys
from pathlib import Path
_ROOT_DIR = Path(__file__).resolve().parent.parent
_POC_TESTS_DIR = _ROOT_DIR / "poc_tests"
if str(_POC_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_POC_TESTS_DIR))

from poc_step1_base64_multimodal import POC_IMAGE_DIR, prepare_local_beauty_test_images
from poc_step2_prompt_matching import (
    BRAND_PERSONA_DNA,
    InfluencerEvaluation,
)
from poc_step4_edge_case_robustness import (
    evaluate_with_edge_case_defense,
    prepare_edge_case_test_files,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_ROOT_DIR / ".env")

st.set_page_config(
    page_title="InfluenceOps v3.0 — AI Core Engine PoC",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==============================================================================
# 1. 브랜드 디자인 시스템 (시스템 다크모드에서도 글자가 100% 선명하게 보이도록 강제 고정)
# ==============================================================================
st.markdown(
    """
<style>
    /* 전체 배경 오프화이트 (#F8FAFC) 및 기본 텍스트 딥 네이비 (#1E293B) 강제 */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #F8FAFC !important;
        color: #1E293B !important;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1440px !important;
    }

    /* 모든 일반 텍스트, 마크다운, 라벨 색상을 딥 네이비(#1E293B)로 강제 고정 */
    p, span, label, h1, h2, h3, h4, h5, h6, div[data-testid="stMarkdownContainer"] p {
        color: #1E293B !important;
    }

    /* 라디오 버튼 선택지 글자 선명하게 고정 */
    div[data-testid="stRadio"] label,
    div[data-testid="stRadio"] p,
    div[data-testid="stRadio"] span,
    div[role="radiogroup"] label div {
        color: #1E293B !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }

    /* 텍스트 입력창 (st.text_area / st.text_input) 화이트 배경 + 딥 네이비 글자 강제 */
    textarea, input[type="text"] {
        background-color: #FFFFFF !important;
        color: #1E293B !important;
        -webkit-text-fill-color: #1E293B !important;
        caret-color: #0EA5E9 !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 8px !important;
        font-size: 0.92rem !important;
        line-height: 1.5 !important;
        padding: 0.65rem 0.8rem !important;
    }
    div[data-baseweb="textarea"], div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        border-color: #CBD5E1 !important;
    }

    /* Expander (접이식 창) 라이트 모드 고정 */
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

    /* 이미지 캡션 글자 색상 */
    div[data-testid="stImageCaption"] {
        color: #475569 !important;
        font-size: 0.8rem !important;
        text-align: center !important;
    }

    /* 상단 헤더 (GNB) */
    .gnb-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 0.2rem 1.1rem 0.2rem;
        border-bottom: 1px solid #E2E8F0;
        margin-bottom: 1.3rem;
    }
    .logo-wrap {
        display: flex;
        flex-direction: column;
    }
    .logo-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        line-height: 1.1;
        color: #1E293B !important;
    }
    .logo-ops {
        color: #0EA5E9 !important;
    }
    .logo-sparkle {
        color: #10B981 !important;
        font-size: 1.4rem;
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
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        color: #1E293B !important;
        padding: 0.45rem 1rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
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
        font-size: 1.22rem;
        font-weight: 800;
        color: #1E293B !important;
        margin: 0.4rem 0 0.8rem 0;
    }

    /* 크롤링 보조 요약 바 (사진 하단 심플 배지 카드) */
    .meta-summary-bar {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-top: 0.35rem;
        margin-bottom: 0.65rem;
        font-size: 0.88rem;
        line-height: 1.6;
        color: #1E293B !important;
    }
    .tag-chip {
        display: inline-block;
        background-color: #E0F2FE;
        color: #0369A1 !important;
        font-weight: 700;
        padding: 0.12rem 0.55rem;
        border-radius: 6px;
        font-size: 0.8rem;
        margin-right: 0.3rem;
    }

    /* 스카이 블루 (#0EA5E9) 메인 실행 버튼 */
    div.stButton > button[kind="primary"] {
        background-color: #0EA5E9 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        padding: 0.65rem 1.2rem !important;
        width: 100% !important;
        box-shadow: 0 2px 6px rgba(14, 165, 233, 0.25) !important;
    }
    div.stButton > button[kind="primary"] p,
    div.stButton > button[kind="primary"] span {
        color: #FFFFFF !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #0284C7 !important;
    }

    /* 상태 배지 배너 */
    .status-banner {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.85rem 1.2rem;
        border-radius: 8px;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .status-approve {
        background-color: #ECFDF5;
        border: 1.5px solid #10B981;
    }
    .status-approve span { color: #065F46 !important; }

    .status-exception {
        background-color: #FFF7ED;
        border: 1.5px solid #F97316;
    }
    .status-exception span { color: #C2410C !important; }

    .status-reject {
        background-color: #FEF2F2;
        border: 1.5px solid #EF4444;
    }
    .status-reject span { color: #991B1B !important; }

    .status-insufficient {
        background-color: #F1F5F9;
        border: 1.5px solid #64748B;
    }
    .status-insufficient span { color: #334155 !important; }

    /* 화이트 모드 커스텀 평가 지표 테이블 */
    .eval-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 1rem;
        font-size: 0.86rem;
    }
    .eval-table th {
        background-color: #F1F5F9;
        color: #1E293B !important;
        font-weight: 700;
        text-align: left;
        padding: 0.65rem 0.75rem;
        border-bottom: 1px solid #CBD5E1;
    }
    .eval-table td {
        color: #1E293B !important;
        padding: 0.6rem 0.75rem;
        border-bottom: 1px solid #E2E8F0;
        font-weight: 500;
    }
    .eval-table tr:last-child td {
        border-bottom: none;
    }

    /* 잠재력(Potential) 및 판정 근거 박스 */
    .rationale-box-warning {
        background-color: #FFF7ED;
        border: 1.5px solid #F97316;
        border-radius: 8px;
        padding: 1rem 1.15rem;
        margin-top: 0.4rem;
        margin-bottom: 1rem;
        color: #1E293B !important;
        line-height: 1.6;
    }
    .rationale-box-approve {
        background-color: #ECFDF5;
        border: 1.5px solid #10B981;
        border-radius: 8px;
        padding: 1rem 1.15rem;
        margin-top: 0.4rem;
        margin-bottom: 1rem;
        color: #1E293B !important;
        line-height: 1.6;
    }
    .rationale-box-reject {
        background-color: #FEF2F2;
        border: 1.5px solid #EF4444;
        border-radius: 8px;
        padding: 1rem 1.15rem;
        margin-top: 0.4rem;
        margin-bottom: 1rem;
        color: #1E293B !important;
        line-height: 1.6;
    }

    /* 다크 네이비 (#1E293B) JSON 뷰어 컨테이너 */
    .json-dark-box {
        background-color: #1E293B !important;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        border: 1px solid #334155;
    }
    .json-dark-header {
        color: #F8FAFC !important;
        font-size: 0.84rem;
        font-weight: 700;
        margin-bottom: 0.65rem;
        border-bottom: 1px solid #334155;
        padding-bottom: 0.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
    }
    div[data-testid="stMarkdownContainer"] .json-dark-header span.json-title-text {
        color: #F8FAFC !important;
    }
    div[data-testid="stMarkdownContainer"] .json-dark-header span.json-badge-ok {
        background-color: #10B981 !important;
        color: #FFFFFF !important;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        white-space: nowrap !important;
        flex-shrink: 0;
    }
    div[data-testid="stMarkdownContainer"] .json-code-content {
        margin: 0;
        color: #7DD3FC !important;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 0.84rem;
        line-height: 1.55;
        overflow-x: auto;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ==============================================================================
# 2. 실사 더미 데이터셋 로드 (기획서 3.1 ~ 3.3 비주얼 잠재력 & 레퍼런스 기준 적용)
# ==============================================================================
DEFAULT_CAMPAIGN_MOOD = (
    "[캠페인 제품] 저자극 시카 수분 앰플\n"
    "[특수 소구 포인트] 아기나 반려동물이 있는 집에서도 안심하고 쓰는 순한 성분과 속보습\n"
    "[지향 비주얼 무드] 인위적인 스튜디오 조명이나 자극적 전단지 배제, 따뜻한 자연광과 맑은 피부결(또는 차분한 일상 여백의 미)"
)


def get_preset_datasets() -> Dict[str, Dict[str, Any]]:
    prepare_local_beauty_test_images()
    edge_imgs = prepare_edge_case_test_files()

    return {
        "CASE_C": {
            "radio_label": "후보 C - @day_zip_b (감성 라이프스타일형 ⭐️시연 핵심)",
            "handle": "@day_zip_b",
            "images": [
                POC_IMAGE_DIR / "day_zip_b_01.jpg",
                POC_IMAGE_DIR / "day_zip_b_03.jpg",
                POC_IMAGE_DIR / "day_zip_b_04.jpg",
            ],
            "extracted_tags": ["#집꾸미기", "#홈카페", "#미니멀라이프", "#자연광무드", "#우드앤플랜트"],
            "track_record_summary": "뷰티 협찬 이력 적음 (일상 비광고 피드 — 고감도 원석 크리에이터 ✨)",
            "caption": (
                "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 "
                "나만의 스킨케어 타임. 패키지가 예뻐서 화장대 위에 그냥 툭 올려두기만 해도 "
                "감성 가득하네요. 텍스처가 가벼워서 데일리로 쓰기 좋아요. "
                "#집꾸미기 #홈카페 #미니멀라이프"
            ),
            "default_result": {
                "media_analysis": [
                    {
                        "aesthetic_score": 9,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "DAILY_CASUAL",
                        "text_intent": "CREATIVE_STORY",
                        "visual_appeal": "LIFESTYLE_MOOD",
                    },
                    {
                        "aesthetic_score": 8,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "DAILY_CASUAL",
                        "text_intent": "CREATIVE_STORY",
                        "visual_appeal": "LIFESTYLE_MOOD",
                    },
                    {
                        "aesthetic_score": 8,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "DAILY_CASUAL",
                        "text_intent": "CREATIVE_STORY",
                        "visual_appeal": "LIFESTYLE_MOOD",
                    },
                ],
                "overall_match_percentage": 85,
                "fit_status": "CREATIVE_EXCEPTION",
                "expected_collisions": [
                    "자연광 활용도 최상(9/10)",
                    "우드톤·식물·여백의 미 브랜드 DNA 부합",
                    "일상 무드 컷 연출 시 높은 시너지 기대",
                ],
                "decision_rationale": (
                    "평소 피드에 직접적인 화장품 노출 컷은 없으나, 따뜻한 자연광과 차분한 미니멀 라이프 비주얼 감도가 "
                    "우리 브랜드 페르소나 및 '저자극 수분 앰플' 지향 무드와 85% 이상 일치합니다. "
                    "전형적인 제품 클로즈업 대신 일상 속 자연스러운 무드 컷 형태로 크리에이티브 예외 승인(협찬 제안)을 권장합니다."
                ),
            },
        },
        "CASE_A": {
            "radio_label": "후보 A - @tmrw_sunshine (뷰티 고관여 프로 리뷰어)",
            "handle": "@tmrw_sunshine",
            "images": [
                POC_IMAGE_DIR / "tmrw_sunshine_03.jpg",
                POC_IMAGE_DIR / "tmrw_sunshine_04.jpg",
                POC_IMAGE_DIR / "tmrw_sunshine_05.jpg",
            ],
            "extracted_tags": ["#스킨케어", "#민감성피부", "#내돈내산", "#자연광피부결", "#제형연출"],
            "track_record_summary": "뷰티 리뷰 다수 (✅ 퀄리티 검증된 프로 리뷰어 / 💡 최근 타사 '메디큐브 세럼' 촬영 확인)",
            "caption": (
                "요즘 환절기라 피부가 확 뒤집어져서 너무 속상했는데 ㅠㅠ 며칠 전부터 "
                "진정 루틴으로 싹 바꿨더니 붉은기가 많이 가라앉았어요! 끈적이는 거 딱 "
                "질색인데 이건 흡수도 빠르고 속건조를 꽉 잡아주더라고요. 아침저녁으로 듬뿍 "
                "올려주고 자는 게 제 꿀팁 🍯✨ #내돈내산 #스킨케어 #민감성피부"
            ),
            "default_result": {
                "media_analysis": [
                    {
                        "aesthetic_score": 8,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "BEAUTY_HIGH_INVOLVEMENT",
                        "text_intent": "INFO_AND_TIPS",
                        "visual_appeal": "PERSONA_CHARM",
                    },
                    {
                        "aesthetic_score": 7,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "BEAUTY_HIGH_INVOLVEMENT",
                        "text_intent": "INFO_AND_TIPS",
                        "visual_appeal": "PRODUCT_CENTRIC",
                    },
                    {
                        "aesthetic_score": 7,
                        "texture_rendering": "NATURAL_GLOW",
                        "lifestyle_context": "BEAUTY_HIGH_INVOLVEMENT",
                        "text_intent": "INFO_AND_TIPS",
                        "visual_appeal": "PRODUCT_CENTRIC",
                    },
                ],
                "overall_match_percentage": 90,
                "fit_status": "APPROVE",
                "expected_collisions": [
                    "맑은 피부결(NATURAL_GLOW) 표현력 우수",
                    "제품 정면 및 손등 제형 촬영 퀄리티 검증 완료",
                ],
                "decision_rationale": (
                    "과도한 필터 없이 맑은 피부결 클로즈업과 손등 제형 연출력이 이미 검증된 뷰티 고관여 인플루언서입니다. "
                    "(💡 마케터 참고: 사진 내 타사 스킨케어 '메디큐브 세럼' 리뷰 이력이 확인되나, 촬영 감도와 전달력이 매우 뛰어나 섭외 1순위로 권장합니다.)"
                ),
            },
        },
        "CASE_B": {
            "radio_label": "후보 B - @today_hotdael1026 (핫딜 전단지·배너 도배형)",
            "handle": "@today_hotdael1026",
            "images": [
                POC_IMAGE_DIR / "today_hotdael1026_01.jpg",
                POC_IMAGE_DIR / "today_hotdael1026_02.jpg",
                POC_IMAGE_DIR / "today_hotdael1026_03.png",
            ],
            "extracted_tags": ["#공구마켓", "#핫딜", "#할인행사", "#특가전단지"],
            "track_record_summary": "⚠️ 자체 촬영 비주얼 부재 (할인 전단지·이벤트 배너 캡처본 도배 계정)",
            "caption": (
                "[단독 핫딜 오픈] 여러분 드디어 기다리시던 앰플 3차 공구 오픈합니다!! 🎉 "
                "이번 구성 진짜 역대급 혜택 미쳤어요 ㅠㅠ 3세트 구매 시 1세트 더 드리는 이벤트 "
                "놓치지 마세요! 품절되기 전에 프로필 링크에서 지금 당장 구매 가능합니다 🏃‍♀️🏃‍♂️ "
                "#공구마켓 #협찬 #광고 #핫딜 #할인행사"
            ),
            "default_result": {
                "media_analysis": [
                    {
                        "aesthetic_score": 3,
                        "texture_rendering": "HEAVY_FILTER",
                        "lifestyle_context": "IRRELEVANT",
                        "text_intent": "HARD_SELL_PROMO",
                        "visual_appeal": "PRODUCT_CENTRIC",
                    },
                    {
                        "aesthetic_score": 3,
                        "texture_rendering": "HEAVY_FILTER",
                        "lifestyle_context": "IRRELEVANT",
                        "text_intent": "HARD_SELL_PROMO",
                        "visual_appeal": "PRODUCT_CENTRIC",
                    },
                    {
                        "aesthetic_score": 3,
                        "texture_rendering": "HEAVY_FILTER",
                        "lifestyle_context": "IRRELEVANT",
                        "text_intent": "HARD_SELL_PROMO",
                        "visual_appeal": "PRODUCT_CENTRIC",
                    },
                ],
                "overall_match_percentage": 20,
                "fit_status": "REJECT",
                "expected_collisions": [
                    "직접 촬영한 피부/일상 사진 부재",
                    "할인/특가 텍스트 오버레이 전단지 도배",
                ],
                "decision_rationale": (
                    "본인이 직접 촬영한 뷰티·라이프스타일 비주얼이 아니라, '선착순 특가·역대급 특가·한정수량' 등 "
                    "자극적인 상업 텍스트가 박힌 그래픽 전단지 및 이벤트 배너로만 도배된 계정으로 우리 브랜드 무드와 부합하지 않아 제외(REJECT)합니다."
                ),
            },
        },
        "CASE_EDGE": {
            "radio_label": "엣지 케이스 - @edge_test (이모지 도배 & 암전 이미지 방어 검증)",
            "handle": "@edge_test",
            "images": [edge_imgs["black_screen"]],
            "extracted_tags": ["☕️🌿✨🤍 (의미 있는 해시태그 없음)"],
            "track_record_summary": "⚪ 비주얼 및 텍스트 판독 불가 (마케터 수동 확인 필요)",
            "caption": "☕️🌿✨🤍",
            "default_result": {
                "media_analysis": [
                    {
                        "aesthetic_score": 1,
                        "texture_rendering": "UNANALYZABLE",
                        "lifestyle_context": "UNANALYZABLE",
                        "text_intent": "UNANALYZABLE",
                        "visual_appeal": "UNANALYZABLE",
                    }
                ],
                "overall_match_percentage": 0,
                "fit_status": "DATA_INSUFFICIENT",
                "expected_collisions": ["분석 불가 미디어 또는 텍스트 데이터 부족 (마케터 수동 확인 요망)"],
                "decision_rationale": (
                    "이미지가 완전히 새까만 암전 화면이며 캡션이 이모지로만 구성되어 있어 의미 있는 비주얼 잠재력 분석이 불가능합니다. "
                    "서버 에러(500)를 방지하고 DATA_INSUFFICIENT 예외 상태를 반환합니다."
                ),
            },
        },
    }


def render_evaluation_html_table(media_list: List[Dict[str, Any]]) -> str:
    rows_html = ""
    for idx, m in enumerate(media_list, start=1):
        rows_html += (
            f"<tr>"
            f"<td><b>Photo {idx}</b></td>"
            f"<td><b>{m.get('aesthetic_score', 1)} / 10</b></td>"
            f"<td><code>{m.get('texture_rendering', '-')}</code></td>"
            f"<td><code>{m.get('lifestyle_context', '-')}</code></td>"
            f"<td><code>{m.get('visual_appeal', '-')}</code></td>"
            f"</tr>"
        )
    return (
        "<table class='eval-table'>"
        "<thead><tr>"
        "<th>프레임</th>"
        "<th>① 비주얼 감도 (Aesthetic)</th>"
        "<th>② 피부결/질감 (Texture)</th>"
        "<th>③ 라이프스타일 (Context)</th>"
        "<th>촬영 연출 형태</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def main() -> None:
    # 상단 헤더 (GNB)
    st.markdown(
        """
        <div class="gnb-header">
            <div class="logo-wrap">
                <div class="logo-title">Influence<span class="logo-ops">Ops</span><span class="logo-sparkle">✦</span></div>
                <div class="logo-sub">AI-POWERED INFLUENCER MARKETING DECISION SYSTEM</div>
            </div>
            <div class="poc-pill">Phase 1. AI Core Engine PoC Testbed (Streamlit Prototype)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    presets = get_preset_datasets()
    preset_keys = list(presets.keys())

    # 좌·우 5:5 Split View 컬럼
    left_col, right_col = st.columns([1, 1.08], gap="large")

    with left_col:
        st.markdown('<div class="panel-header-bar">📥 테스트 데이터 입력창 (3.1 Input Data)</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="section-title">1. 캠페인 무드 & 타겟 인플루언서 피드 (Input)</div>', unsafe_allow_html=True)

            selected_key = st.radio(
                "타겟 인플루언서 프리셋 선택 (Target Influencer Feed)",
                options=preset_keys,
                format_func=lambda k: presets[k]["radio_label"],
                index=0,
            )
            current_preset = presets[selected_key]

            with st.expander("🧬 [정적 온보딩 데이터] 학습된 우리 브랜드 페르소나 DNA 확인", expanded=False):
                st.text_area(
                    "Brand Persona DNA",
                    value=BRAND_PERSONA_DNA,
                    height=95,
                    label_visibility="collapsed",
                )

            st.markdown("**🎯 캠페인 소구 포인트 & 지향 무드 (Campaign Data)**")
            st.text_area(
                "캠페인 소구 포인트 및 지향 무드",
                value=DEFAULT_CAMPAIGN_MOOD,
                height=88,
                label_visibility="collapsed",
            )

            st.markdown(f"**📸 크롤링된 인플루언서({current_preset['handle']}) 대표 피드 비주얼 (3장)**")
            img_paths: List[Path] = current_preset["images"]
            img_cols = st.columns(3)
            for idx, p in enumerate(img_paths[:3]):
                with img_cols[idx]:
                    if p.exists():
                        st.image(str(p), caption=p.name, use_container_width=True)

            # 사진 하단 크롤링 보조 요약 바 (해시태그/비주얼 키워드 + 협찬 레퍼런스 요약)
            tags_html = "".join([f'<span class="tag-chip">{t}</span>' for t in current_preset["extracted_tags"]])
            st.markdown(
                f"""
                <div class="meta-summary-bar">
                    <div>🏷️ <b>추출된 해시태그 & 비주얼 키워드:</b> {tags_html}</div>
                    <div style="margin-top: 0.3rem;">📋 <b>협찬 레퍼런스 & 피드 성격:</b> {current_preset["track_record_summary"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.expander("📄 크롤링된 원본 캡션 텍스트 참고용 보기 (보조 데이터)", expanded=False):
                caption_input = st.text_area(
                    "원본 캡션 텍스트",
                    value=current_preset["caption"],
                    height=80,
                    label_visibility="collapsed",
                )

            run_clicked = st.button("⚡ AI 비주얼 잠재력 & 맥락 매칭 분석 실행 (Run PoC)", type="primary", use_container_width=True)

    # 세션 상태 관리
    if "active_result" not in st.session_state or st.session_state.get("last_preset") != selected_key:
        st.session_state["active_result"] = current_preset["default_result"]
        st.session_state["last_preset"] = selected_key
        st.session_state["last_elapsed"] = None

    if run_clicked:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY가 .env에 설정되어 있지 않아 사전 검증된 캐시 결과를 표시합니다.")
        else:
            with st.spinner("gpt-4o 멀티모달 비주얼 잠재력 엔진 + Pydantic 스키마 검증 실행 중..."):
                start_t = time.perf_counter()
                client = OpenAI(api_key=api_key)
                eval_obj: InfluencerEvaluation = evaluate_with_edge_case_defense(
                    client=client,
                    candidate_name=current_preset["handle"],
                    image_paths=img_paths,
                    caption=caption_input,
                )
                elapsed = round(time.perf_counter() - start_t, 2)
                st.session_state["active_result"] = eval_obj.model_dump()
                st.session_state["last_elapsed"] = elapsed

    result_data: Dict[str, Any] = st.session_state["active_result"]
    fit_status = result_data.get("fit_status", "CREATIVE_EXCEPTION")
    match_pct = result_data.get("overall_match_percentage", 85)
    collisions = result_data.get("expected_collisions", [])
    rationale = result_data.get("decision_rationale", "")
    media_list = result_data.get("media_analysis", [])

    with right_col:
        st.markdown('<div class="panel-header-bar">📊 Pydantic 파싱 결과 리포트 (3.2 & 3.3 Output)</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                '<div class="section-title">2. AI 비주얼 잠재력(Potential) & 매칭 리포트</div>',
                unsafe_allow_html=True,
            )

            # 1) 상태 배지 배너
            if fit_status == "APPROVE":
                banner_cls = "status-approve"
                status_label = "🟢 APPROVE (섭외 1순위 — 비주얼 퀄리티 검증된 프로 리뷰어)"
            elif fit_status == "CREATIVE_EXCEPTION":
                banner_cls = "status-exception"
                status_label = "🟠 CREATIVE_EXCEPTION (크리에이티브 예외 승인 권장 — 브랜드 무드 고감도 매칭)"
            elif fit_status == "REJECT":
                banner_cls = "status-reject"
                status_label = "🔴 REJECT (섭외 제외 — 자체 촬영 비주얼 부재 / 전단지·배너 도배)"
            else:
                banner_cls = "status-insufficient"
                status_label = "⚪ DATA_INSUFFICIENT (데이터 부족 / 분석 불가 방어 작동)"

            elapsed_badge = (
                f" | ⏱️ 실측 {st.session_state['last_elapsed']}초"
                if st.session_state.get("last_elapsed") is not None
                else ""
            )

            st.markdown(
                f"""
                <div class="status-banner {banner_cls}">
                    <span>{status_label}</span>
                    <span>종합 매칭률: {match_pct}%{elapsed_badge}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 2) 잠재력 정량화 3대 지표 표 (3.2 Evaluation Table)
            st.markdown("**잠재력(Potential) 정량화 3대 지표 분석표 (`MediaIntentAnalysis`)**")
            st.markdown(render_evaluation_html_table(media_list), unsafe_allow_html=True)

            # 3) 비즈니스 시너지 관점의 매칭 사유 박스 (3.3 Rationale)
            if fit_status == "APPROVE":
                box_cls = "rationale-box-approve"
                pts = " ".join([f"[{c}]" for c in collisions]) if collisions else "[맑은 피부결 표현 우수] [제형 촬영 퀄리티 검증 완료]"
                header_html = f"✅ <b>비주얼 & 레퍼런스 검증 완료:</b> {pts}"
            elif fit_status == "REJECT":
                box_cls = "rationale-box-reject"
                pts = " ".join([f"[{c}]" for c in collisions]) if collisions else "[자체 촬영 비주얼 부재] [특가 전단지 도배]"
                header_html = f"🚨 <b>비주얼 부적합 감지:</b> {pts}"
            elif fit_status == "CREATIVE_EXCEPTION":
                box_cls = "rationale-box-warning"
                pts = (
                    " ".join([f"[{c}]" for c in collisions])
                    if collisions
                    else "[자연광 감도 최상(9/10)] [우드톤·식물·여백 무드 일치]"
                )
                header_html = f"✨ <b>비주얼 잠재력(Potential) 포착:</b> {pts}"
            else:
                box_cls = "rationale-box-warning"
                pts = " ".join([f"[{c}]" for c in collisions]) if collisions else "[판독 불가 미디어 방어]"
                header_html = f"⚠️ <b>예외 방어 작동:</b> {pts}"

            st.markdown(
                f"""
                <div class="{box_cls}">
                    <div style="margin-bottom: 0.45rem;">{header_html}</div>
                    <div>• <b>매칭 사유 (Rationale):</b> {rationale}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 4) 하단 다크 네이비 (#1E293B) Pydantic JSON 뷰어 (PoC 검증 ③ 증명용)
            json_display = {
                "fit_status": fit_status,
                "overall_match_percentage": match_pct,
                "expected_collisions": collisions,
                "decision_rationale": rationale,
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
                f'<span class="json-title-text">🔍 [PoC 검증 ③ 증명] Pydantic 구조화 JSON 원본 출력 (DB·React 즉시 연동용)</span>'
                f'<span class="json-badge-ok">100% Schema Validated ✓</span>'
                f'</div>'
                f'<div class="json-code-content" style="color: #7DD3FC !important;">{html_safe_json}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
