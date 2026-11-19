"""
[InfluenceOps 실사 이미지(tmrw_sunshine_01~06) 기반 PoC ② 정밀 검증 스크립트]
====================================================================================
1. 넣어주신 실제 사진 6장(tmrw_sunshine_01.jpg ~ 06.jpg) 각각의 비주얼 속성을 AI가
   어떻게 판독하는지 확인합니다.
2. 팀장님 가이드(더미 데이터 1, 2, 3)의 후보 A / B / C 시나리오에 실사 이미지를 주입하여
   APPROVE / REJECT / CREATIVE_EXCEPTION 및 핵심 판정 사유가 정확히 출력되는지 검증합니다.
====================================================================================
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from dotenv import load_dotenv
from openai import OpenAI

from poc_step1_base64_multimodal import POC_IMAGE_DIR, encode_image_to_base64, prepare_local_beauty_test_images
from poc_step2_prompt_matching import (
    BRAND_PERSONA_DNA,
    CAMPAIGN_GUIDELINE,
    InfluencerEvaluation,
    build_system_prompt,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")


def evaluate_post(
    client: OpenAI,
    system_prompt: str,
    candidate_title: str,
    image_paths: List[Path],
    caption: str,
) -> InfluencerEvaluation:
    content_payload: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"[검증 대상]: {candidate_title}\n"
                f"[첨부 이미지 파일명]: {[p.name for p in image_paths]}\n"
                f"[인플루언서 캡션 텍스트]:\n\"{caption}\"\n\n"
                "첨부된 이미지들과 캡션 텍스트를 [데이터 1: 브랜드 페르소나 DNA] 및 "
                "[데이터 2: 퍼포먼스팀 캠페인 가이드라인]과 대조하여 InfluencerEvaluation JSON으로 판정해."
            ),
        }
    ]

    for p in image_paths:
        b64_img = encode_image_to_base64(p)
        mime_type = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        content_payload.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64_img}",
                    "detail": "low",
                },
            }
        )

    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_payload},
        ],
        response_format=InfluencerEvaluation,
        temperature=0.0,
    )
    return response.choices[0].message.parsed


def run_tmrw_sunshine_verification() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    system_prompt = build_system_prompt(BRAND_PERSONA_DNA, CAMPAIGN_GUIDELINE)

    # tmrw_sunshine_01 ~ 06 경로 확인 (후보 A 실사)
    tmrw_imgs = [POC_IMAGE_DIR / f"tmrw_sunshine_0{i}.jpg" for i in range(1, 7)]
    # today_hotdael1026_01 ~ 03 경로 확인 (후보 B 실사)
    hotdeal_imgs = [
        POC_IMAGE_DIR / "today_hotdael1026_01.jpg",
        POC_IMAGE_DIR / "today_hotdael1026_02.jpg",
        POC_IMAGE_DIR / "today_hotdael1026_03.png",
    ]
    # day_zip_b_01 ~ 05 경로 확인 (후보 C 실사)
    dayzip_imgs = [POC_IMAGE_DIR / f"day_zip_b_0{i}.jpg" for i in range(1, 6)]

    for p in tmrw_imgs + hotdeal_imgs + dayzip_imgs:
        if not p.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")

    print("=" * 88)
    print("📸 [100% 실사 검증] 후보 A(tmrw_sunshine) + 후보 B(today_hotdael1026) + 후보 C(day_zip_b)")
    print("=" * 88)

    test_scenarios = [
        {
            "id": "후보 A (뷰티 고관여 일상형 - 실사 tmrw_sunshine_03 피부결 셀카 + 04 정면 + 05 제형)",
            "images": [tmrw_imgs[2], tmrw_imgs[3], tmrw_imgs[4]],
            "caption": (
                "요즘 환절기라 피부가 확 뒤집어져서 너무 속상했는데 ㅠㅠ 며칠 전부터 "
                "진정 루틴으로 싹 바꿨더니 붉은기가 많이 가라앉았어요! 끈적이는 거 딱 "
                "질색인데 이건 흡수도 빠르고 속건조를 꽉 잡아주더라고요. 아침저녁으로 듬뿍 "
                "올려주고 자는 게 제 꿀팁 🍯✨ #내돈내산 #스킨케어 #민감성피부"
            ),
            "expected": "APPROVE",
        },
        {
            "id": "후보 B (광고/전단지형 - 실사 today_hotdael1026_01~03 3장 투입)",
            "images": hotdeal_imgs,
            "caption": (
                "[단독 핫딜 오픈] 여러분 드디어 기다리시던 앰플 3차 공구 오픈합니다!! 🎉 "
                "이번 구성 진짜 역대급 혜택 미쳤어요 ㅠㅠ 3세트 구매 시 1세트 더 드리는 이벤트 "
                "놓치지 마세요! 품절되기 전에 프로필 링크에서 지금 당장 구매 가능합니다 🏃‍♀️🏃‍♂️ "
                "#공구마켓 #협찬 #광고 #핫딜 #할인행사"
            ),
            "expected": "REJECT",
        },
        {
            "id": "후보 C-3장종합 (감성 라이프스타일형 - 실사 day_zip_b_01 창가햇살찻잔 + 03 꽃화병 + 04 우드톤찬장)",
            "images": [dayzip_imgs[0], dayzip_imgs[2], dayzip_imgs[3]],
            "caption": (
                "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 "
                "나만의 스킨케어 타임. 패키지가 예뻐서 화장대 위에 그냥 툭 올려두기만 해도 "
                "감성 가득하네요. 텍스처가 가벼워서 데일리로 쓰기 좋아요. "
                "#집꾸미기 #홈카페 #미니멀라이프"
            ),
            "expected": "CREATIVE_EXCEPTION",
        },
        {
            "id": "후보 C-단일컷 (감성 라이프스타일형 - 실사 day_zip_b_01 '창가 햇살·화분·찻잔' 단독 투입)",
            "images": [dayzip_imgs[0]],
            "caption": (
                "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 "
                "나만의 스킨케어 타임. 패키지가 예뻐서 화장대 위에 그냥 툭 올려두기만 해도 "
                "감성 가득하네요. 텍스처가 가벼워서 데일리로 쓰기 좋아요. "
                "#집꾸미기 #홈카페 #미니멀라이프"
            ),
            "expected": "CREATIVE_EXCEPTION",
        },
    ]

    for idx, sc in enumerate(test_scenarios, start=1):
        start_t = time.perf_counter()
        res = evaluate_post(client, system_prompt, sc["id"], sc["images"], sc["caption"])
        elapsed = round(time.perf_counter() - start_t, 2)
        matched = res.fit_status == sc["expected"]

        print(f"\n[{idx}/{len(test_scenarios)}] {sc['id']}")
        print(f"  • 투입 이미지        : {[p.name for p in sc['images']]}")
        print(f"  • 기대 상태값        : {sc['expected']}")
        print(f"  • AI 실제 판정값     : {res.fit_status} ({'✅ 정확히 일치' if matched else '❌ 불일치'})")
        print(f"  • 종합 매칭률        : {res.overall_match_percentage}%")
        print(f"  • 프레임별 시각 판독 : {[f'{m.visual_appeal}/{m.texture_rendering}({m.aesthetic_score}점)' for m in res.media_analysis]}")
        print(f"  • 예상 충돌 지점     : {res.expected_collisions}")
        print(f"  • AI 판정 사유       : {res.decision_rationale}")
        print(f"  • 맞춤형 가이드라인  : {res.guideline_draft}")
        print(f"  • 소요 시간          : {elapsed}초")


if __name__ == "__main__":
    run_tmrw_sunshine_verification()

