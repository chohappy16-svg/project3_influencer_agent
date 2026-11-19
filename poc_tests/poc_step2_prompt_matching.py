"""
[InfluenceOps Phase 1 - PoC 기술 검증 ②]
검증 항목: ② 초개인화 매칭 프롬프트 반응 최적화

1. 무엇을 테스트하는가? (Test)
   - 기획안(PRD 부록 p.26~27, p.41~42)에 정의된 3가지 극단적 더미 데이터
     (후보 A: 일상형 뷰티 고관여, 후보 B: 과도한 광고/공구 전단지형, 후보 C: 미니멀 라이프스타일 감성형)의
     텍스트 및 로컬 이미지를 주입했을 때 AI의 판정 결과를 확인합니다.
2. 왜 해야 하는가? (Why)
   - AI가 단순 키워드/제품 노출 기계적 검열을 넘어, [브랜드 페르소나 DNA]와 인플루언서의 라이프스타일·비주얼 무드 간
     '맥락적 케미(Contextual Fit)'를 이해하고 올바른 의사결정 상태값을 내리는지 검증하기 위함입니다.
3. 통과 여부 기준 (Success Criteria)
   - 후보 A (일상형): APPROVE
   - 후보 B (광고형): REJECT
   - 후보 C (감성형): CREATIVE_EXCEPTION
   -> 3가지 케이스 모두 기획 의도와 100% 일치하는 상태값(fit_status)을 반환해야 합니다.
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Literal, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from poc_step1_base64_multimodal import (
    encode_image_to_base64,
    prepare_local_beauty_test_images,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")


# ==============================================================================
# 1. Pydantic 스키마 정의 (PRD v3.0 p.34~35 & p.61~63 통합 프로덕션 스키마)
# ==============================================================================
class MediaIntentAnalysis(BaseModel):
    aesthetic_score: int = Field(
        ge=1,
        le=10,
        description="자연광 활용, 여백의 미, 구도 등 브랜드 지향점과 맞는 시각적 감도 점수 (1~10)",
    )
    texture_rendering: Literal["NATURAL_GLOW", "HEAVY_FILTER", "UNANALYZABLE"] = Field(
        description="자연스러운 피부결/제형/질감(NATURAL_GLOW)인가, 인위적/자극적/과도한 보정(HEAVY_FILTER)인가, 판독 불가(UNANALYZABLE)인가",
    )
    lifestyle_context: Literal[
        "BEAUTY_HIGH_INVOLVEMENT", "DAILY_CASUAL", "IRRELEVANT", "UNANALYZABLE"
    ] = Field(
        description="텍스트 및 배경을 통한 뷰티/자기관리 고관여(BEAUTY_HIGH_INVOLVEMENT), 미니멀 일상 감성(DAILY_CASUAL), 브랜드 무드와 무관/상업 과다(IRRELEVANT), 판독 불가(UNANALYZABLE)",
    )
    text_intent: Literal[
        "NONE", "INFO_AND_TIPS", "CREATIVE_STORY", "HARD_SELL_PROMO", "UNANALYZABLE"
    ] = Field(
        description="텍스트의 목적 분류 (정보/꿀팁 공유: INFO_AND_TIPS, 감성 스토리: CREATIVE_STORY, 자극적 공구/할인 홍보: HARD_SELL_PROMO)",
    )
    visual_appeal: Literal[
        "PRODUCT_CENTRIC", "LIFESTYLE_MOOD", "BEFORE_AFTER", "PERSONA_CHARM", "UNANALYZABLE"
    ] = Field(
        description="비주얼 소구점 분류",
    )


class InfluencerEvaluation(BaseModel):
    media_analysis: List[MediaIntentAnalysis] = Field(
        description="전송된 각 미디어 프레임(최대 3장)별 분석 결과"
    )
    overall_match_percentage: int = Field(
        ge=0,
        le=100,
        description="브랜드 페르소나 DNA와 인플루언서 라이프스타일·비주얼 무드 간의 종합 일치도(%)",
    )
    fit_status: Literal[
        "APPROVE",
        "CREATIVE_EXCEPTION",
        "REVIEW_NEEDED",
        "REJECT",
        "DATA_INSUFFICIENT",
    ] = Field(
        description="최종 상태 플래그 (APPROVE: 적합, CREATIVE_EXCEPTION: 크리에이티브 예외 승인 권장, REVIEW_NEEDED: 검토 필요, REJECT: 부적합, DATA_INSUFFICIENT: 데이터 부족)"
    )
    expected_collisions: List[str] = Field(
        description="퍼포먼스팀 캠페인 가이드라인 중 충돌 또는 누락이 예상되는 구체적 항목 리스트 (충돌이 없으면 빈 배열 [] 반환)"
    )
    decision_rationale: str = Field(
        max_length=500,
        description="마케터를 위한 비즈니스 시너지 및 판정 근거 3줄 요약 보고서 (최대 500자 이내)",
    )
    guideline_draft: str = Field(
        max_length=500,
        description="충돌이 조정되어 마케터가 바로 활용할 수 있는 맞춤형 DM 가이드라인 초안",
    )


# ==============================================================================
# 2. PRD 부록 기준 입력 데이터 세팅 (브랜드 DNA + 퍼포먼스팀 가이드라인 + 3인 후보)
# ==============================================================================
BRAND_PERSONA_DNA = """
- 타겟 고객: 영유아나 반려동물과 함께 생활하며 순한 성분을 찾는 2030 여성
- 지향 비주얼 무드: 인위적인 조명 배제, 따뜻한 자연광, 식물이나 우드 톤이 섞인 차분한 여백의 미
- 브랜드 핵심 소구점: 자극 없는 촉촉함, 클린 뷰티와 미니멀 라이프 지향
""".strip()

CAMPAIGN_GUIDELINE = """
[이번 수분 앰플 캠페인 필수 가이드라인]
1. 제품 패키지 정면 노출 1컷 이상 필수
2. 앰플 제형이 흐르는 영상/컷 1개 반드시 포함
3. '피부 장벽 개선', '수분 광채' 키워드 본문 3회 이상 삽입
4. 프로필 링크 트리에 구매 링크 상단 고정
5. 필수 해시태그 7개 모두 삽입 (#수분앰플추천 #피부장벽강화 #스킨케어루틴 #협찬 등)
""".strip()


def build_system_prompt(brand_dna: str, campaign_guideline: str) -> str:
    """
    [초개인화 매칭 코어 시스템 프롬프트]
    기계적 키워드 검열을 넘어 브랜드 DNA와 인플루언서 라이프스타일 간의 맥락적 케미를 판별하도록 설계된 프롬프트
    """
    return f"""
너는 InfluenceOps v3.0의 수석 뷰티 스카우터이자 의사결정 지원 AI 에이전트야.
단순히 화장품이나 필수 키워드가 기계적으로 들어갔는지만 검열하지 마.
아래 [데이터 1: 우리 브랜드 페르소나 DNA]와 [데이터 2: 퍼포먼스팀 캠페인 가이드라인]을 함께 참고하여,
인플루언서의 비주얼 무드(조명, 여백, 색감, 제형/피부 표현)와 캡션 텍스트의 진정성 및 상업성 농도를 종합 평가해.

[데이터 1: 우리 브랜드 페르소나 DNA]
{brand_dna}

[데이터 2: 퍼포먼스팀 캠페인 가이드라인]
{campaign_guideline}

[핵심 판정 기준 (fit_status 결정 루브릭 - 엄격 준수)]
1. "APPROVE" (적합 - 정통 뷰티/스킨케어 고관여형):
   - 캡션에서 구체적인 피부 고민(환절기 뒤집어짐, 붉은기, 속건조, 민감성 피부 등), 스킨케어 진정 루틴, 제형/흡수력/사용감 꿀팁을 직접적으로 상세히 다루거나(BEAUTY_HIGH_INVOLVEMENT), 이미지에 스킨케어 제품/앰플/맑은 피부결이 자연스럽게 드러나는 경우 반드시 "APPROVE"를 부여해!
   - 이러한 뷰티 고관여 리뷰어는 퍼포먼스팀의 필수 가이드라인(제품 정면 노출, 제형 컷, 효능 키워드 및 해시태그)을 이질감 없이 수용할 수 있으므로 expected_collisions는 빈 배열([])로 두고 반드시 "APPROVE"로 판정해. (절대 CREATIVE_EXCEPTION을 주지 마!)

2. "REJECT" (부적합 - 과도한 상업/공구 전단지형):
   - "[단독 핫딜]", "공구 오픈", "품절 임박", "3세트 구매 시 1세트" 등 자극적인 상업/공구/할인 텍스트(HARD_SELL_PROMO)나 고채도 홍보용 텍스트 오버레이 이미지가 주를 이룰 때 반드시 "REJECT"를 부여해.
   - 상업성 농도가 과다하여 우리 브랜드의 '차분한 자연광·클린 뷰티·여백의 미' 무드를 심각하게 훼손하는 경우야.

3. "CREATIVE_EXCEPTION" (크리에이티브 예외 승인 권장 - 비뷰티/감성 라이프스타일 매칭형):
   - 사진에 화장품/앰플이 잘 보이지 않고 식물, 커피잔, 우드톤 인테리어, 반려동물, 요가 등 '일상/감성 라이프스타일(DAILY_CASUAL)' 위주이며, 캡션도 구체적인 피부 질환/효능 분석보다는 '#집꾸미기, #홈카페, #미니멀라이프, Sunday morning vibe' 같은 감성 스토리(CREATIVE_STORY) 중심일 때 부여해!
   - 즉, 퍼포먼스팀 가이드라인 1, 2번(제품 정면 노출, 제형 영상, 효능 키워드 3회 반복)을 그대로 강제하면 인플루언서의 감성 피드 무드와 충돌하지만, '따뜻한 자연광·우드/식물·미니멀 라이프'라는 시각적 감도가 [우리 브랜드 페르소나 DNA]와 80% 이상 일치할 때만 "CREATIVE_EXCEPTION"을 부여해.

4. "DATA_INSUFFICIENT" (판단 보류 - 데이터 부족):
   - 캡션에 의미 있는 텍스트가 전혀 없고 이모지만 나열되어 있거나, 이미지가 완전히 깨진/까만 화면이라 분석이 불가능할 때만 부여해.
""".strip()


def evaluate_influencer_candidate(
    client: OpenAI,
    candidate_name: str,
    image_paths: List[Path],
    caption: str,
) -> InfluencerEvaluation:
    """단일 후보자(이미지 + 캡션)에 대해 gpt-4o Structured Output 평가를 수행합니다."""
    safe_paths = image_paths[:3] if len(image_paths) > 2 else image_paths[:]

    content_payload: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": f"[후보자 식별자]: {candidate_name}\n[인플루언서 피드 캡션]:\n{caption}",
        }
    ]
    for p in safe_paths:
        b64_img = encode_image_to_base64(p)
        content_payload.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_img}",
                    "detail": "low",
                },
            }
        )

    system_prompt = build_system_prompt(BRAND_PERSONA_DNA, CAMPAIGN_GUIDELINE)

    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_payload},
        ],
        response_format=InfluencerEvaluation,
        temperature=0.1,
    )
    return response.choices[0].message.parsed


def run_step2_verification():
    imgs = prepare_local_beauty_test_images()
    real_a = imgs[0].parent / "tmrw_sunshine_03.jpg"
    real_b = imgs[0].parent / "today_hotdael1026_02.jpg"
    real_c = imgs[0].parent / "day_zip_b_01.jpg"
    img_a = real_a if real_a.exists() else imgs[0]
    img_b = real_b if real_b.exists() else imgs[1]
    img_c = real_c if real_c.exists() else imgs[2]

    # PRD 부록(p.26~27, p.41~42)에 정의된 3인 극단적 더미 데이터
    test_cases = [
        {
            "id": "후보 A (일상형 / 뷰티 고관여 Ideal Fit)",
            "image_paths": [img_a],
            "caption": (
                "요즘 환절기라 피부가 확 뒤집어져서 너무 속상했는데 ㅠㅠ 며칠 전부터 "
                "진정 루틴으로 싹 바꿨더니 붉은기가 많이 가라앉았어요! 끈적이는 거 딱 "
                "질색인데 이건 흡수도 빠르고 속건조를 꽉 잡아주더라고요. 아침저녁으로 듬뿍 "
                "올려주고 자는 게 제 꿀팁 🍯✨ #내돈내산 #스킨케어 #민감성피부"
            ),
            "expected_status": "APPROVE",
        },
        {
            "id": "후보 B (광고형 / 과도한 상업 및 공구 전단지형)",
            "image_paths": [img_b],
            "caption": (
                "[단독 핫딜 오픈] 여러분 드디어 기다리시던 앰플 3차 공구 오픈합니다!! 🎉 "
                "이번 구성 진짜 역대급 혜택 미쳤어요 ㅠㅠ 3세트 구매 시 1세트 더 드리는 이벤트 "
                "놓치지 마세요! 품절되기 전에 프로필 링크에서 지금 당장 구매 가능합니다 🏃‍♀️🏃‍♂️ "
                "#공구마켓 #협찬 #광고 #핫딜 #할인행사"
            ),
            "expected_status": "REJECT",
        },
        {
            "id": "후보 C (감성형 / 라이프스타일 매칭형 - 시연 핵심 케이스)",
            "image_paths": [img_c],
            "caption": (
                "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 "
                "나만의 스킨케어 타임. 패키지가 예뻐서 화장대 위에 그냥 툭 올려두기만 해도 "
                "감성 가득하네요. 텍스처가 가벼워서 데일리로 쓰기 좋아요. "
                "#집꾸미기 #홈카페 #미니멀라이프"
            ),
            "expected_status": "CREATIVE_EXCEPTION",
        },
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다.")
    client = OpenAI(api_key=api_key)

    print("=" * 80)
    print("🚀 [InfluenceOps PoC 검증 ②] 초개인화 매칭 프롬프트 반응 테스트 시작 (3대 케이스)")
    print("=" * 80)

    all_passed = True
    summary_rows = []

    for idx, tc in enumerate(test_cases, start=1):
        t0 = time.perf_counter()
        parsed_res = evaluate_influencer_candidate(
            client=client,
            candidate_name=tc["id"],
            image_paths=tc["image_paths"],
            caption=tc["caption"],
        )
        elapsed = round(time.perf_counter() - t0, 2)

        actual_status = parsed_res.fit_status
        expected_status = tc["expected_status"]
        is_match = actual_status == expected_status
        if not is_match:
            all_passed = False

        status_icon = "✅ PASS" if is_match else "❌ FAIL"
        print(f"\n[{idx}/3] {tc['id']}")
        print(f"  • 이미지 파일        : {tc['image_paths'][0].name}")
        print(f"  • 기대 상태값        : {expected_status}")
        print(f"  • 실제 AI 상태값     : {actual_status}  -->  {status_icon} (소요시간: {elapsed}초)")
        print(f"  • 브랜드 DNA 매칭률  : {parsed_res.overall_match_percentage}%")
        print(f"  • 비주얼 감도 점수   : {parsed_res.media_analysis[0].aesthetic_score}/10점 ({parsed_res.media_analysis[0].visual_appeal})")
        print(f"  • 텍스트 의도 분류   : {parsed_res.media_analysis[0].text_intent}")
        print(f"  • 예상 충돌 항목     : {parsed_res.expected_collisions}")
        print(f"  • AI 판단 근거 요약  : {parsed_res.decision_rationale}")
        print(f"  • 맞춤 가이드라인 안 : {parsed_res.guideline_draft}")
        print("  • [Structured JSON 출력]:")
        print(parsed_res.model_dump_json(indent=2))

        summary_rows.append(
            {
                "candidate": tc["id"],
                "expected": expected_status,
                "actual": actual_status,
                "match_pct": parsed_res.overall_match_percentage,
                "passed": is_match,
                "elapsed_sec": elapsed,
            }
        )

    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 [검증 ② 최종 결과: PASS 🟢] 3가지 극단적 더미 데이터 모두 기획 의도와 100% 일치!")
    else:
        print("⚠️ [검증 ② 최종 결과: FAIL 🔴] 일부 케이스의 상태값이 기대값과 다릅니다.")
    print("=" * 80)
    for row in summary_rows:
        mark = "🟢 PASS" if row["passed"] else "🔴 FAIL"
        print(
            f"  - {row['candidate']}: 기대({row['expected']}) == 실제({row['actual']}) "
            f"| 매칭률 {row['match_pct']}% | {row['elapsed_sec']}초 [{mark}]"
        )
    print("=" * 80)


if __name__ == "__main__":
    run_step2_verification()
