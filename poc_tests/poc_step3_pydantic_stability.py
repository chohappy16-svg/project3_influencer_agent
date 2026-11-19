"""
[InfluenceOps Phase 1 - PoC 기술 검증 ③]
검증 항목: ③ Pydantic 스키마 강제 및 출력 안정성 (10회 연속 호출 100% 검증)

1. 무엇을 테스트하는가? (Test)
   - OpenAI API 호출 시 Pydantic 모델(InfluencerEvaluation)을 response_format으로 지정하여,
     응답이 항상 정해진 구조화된 JSON(Structured Output)으로 떨어지는지 테스트합니다.
2. 왜 해야 하는가? (Why)
   - LLM이 자유 서술형(줄글)이나 마크다운 잡음이 섞인 텍스트로 답변할 경우,
     추후 웹 프론트엔드(Streamlit/React) 및 PostgreSQL DB 적재 시 JSON 파싱 에러(앱 다운)가 발생하므로
     이를 원천 차단하기 위함입니다.
3. 통과 여부 기준 (Success Criteria)
   - 터미널에서 API를 10번 연속 호출했을 때, 포맷 에러(ValidationError, JSONDecodeError, Key 누락) 없이
     10번 모두 Pydantic 스키마 형태의 유효한 JSON을 100%(10/10) 반환해야 합니다.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from poc_step1_base64_multimodal import prepare_local_beauty_test_images
from poc_step2_prompt_matching import (
    InfluencerEvaluation,
    evaluate_influencer_candidate,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")

TOTAL_RUNS = 10


def run_step3_10x_pydantic_stability_test() -> Dict[str, Any]:
    imgs = prepare_local_beauty_test_images()
    img_a, img_b, img_c = imgs[0], imgs[1], imgs[2]

    # 10회 연속 호출에 사용할 시나리오 풀 (후보 A, B, C 순환)
    scenarios = [
        {
            "label": "Case A (뷰티 고관여 일상형)",
            "images": [img_a],
            "caption": "요즘 환절기라 피부가 뒤집어져서 진정 루틴으로 바꿨더니 붉은기가 가라앉았어요! 흡수도 빠르고 속건조를 잡아주네요 🍯✨ #내돈내산 #스킨케어 #민감성피부",
        },
        {
            "label": "Case B (과도한 상업/공구형)",
            "images": [img_b],
            "caption": "[단독 핫딜 오픈] 앰플 3차 공구 오픈합니다!! 🎉 3세트 구매 시 1세트 더! 품절 전 프로필 링크에서 당장 구매 가능 #공구마켓 #협찬 #핫딜",
        },
        {
            "label": "Case C (감성 라이프스타일형)",
            "images": [img_c],
            "caption": "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 스킨케어 타임. 화장대 위에 올려두기만 해도 감성 가득해요 #집꾸미기 #홈카페 #미니멀라이프",
        },
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다.")
    client = OpenAI(api_key=api_key)

    print("=" * 84)
    print(f"🚀 [InfluenceOps PoC 검증 ③] Pydantic 스키마 강제 및 10회 연속 호출 출력 안정성 테스트 시작")
    print("=" * 84)

    success_count = 0
    format_error_count = 0
    latencies: List[float] = []
    run_logs: List[Dict[str, Any]] = []

    REQUIRED_KEYS = {
        "media_analysis",
        "overall_match_percentage",
        "fit_status",
        "expected_collisions",
        "decision_rationale",
        "guideline_draft",
    }

    for i in range(1, TOTAL_RUNS + 1):
        sc = scenarios[(i - 1) % len(scenarios)]
        t0 = time.perf_counter()

        try:
            # 1) OpenAI Structured Output 호출 (response_format=InfluencerEvaluation)
            parsed_obj = evaluate_influencer_candidate(
                client=client,
                candidate_name=f"Run #{i} - {sc['label']}",
                image_paths=sc["images"],
                caption=sc["caption"],
            )
            elapsed = round(time.perf_counter() - t0, 2)
            latencies.append(elapsed)

            # 2) Pydantic 인스턴스 타입 검증
            if not isinstance(parsed_obj, InfluencerEvaluation):
                raise TypeError(f"반환 객체가 InfluencerEvaluation 타입이 아닙니다: {type(parsed_obj)}")

            # 3) JSON 직렬화 및 역직렬화(재검증) 무결성 확인
            json_str = parsed_obj.model_dump_json()
            raw_dict = json.loads(json_str)
            re_validated = InfluencerEvaluation.model_validate_json(json_str)

            # 4) 필수 키 누락 여부 확인
            missing_keys = REQUIRED_KEYS - set(raw_dict.keys())
            if missing_keys:
                raise KeyError(f"필수 스키마 키 누락: {missing_keys}")

            success_count += 1
            print(
                f"  ✅ [{i:02d}/{TOTAL_RUNS:02d}회차 성공] {sc['label']:<25} | "
                f"fit_status={re_validated.fit_status:<18} | "
                f"match={re_validated.overall_match_percentage:>3}% | "
                f"스키마 무결성=OK | 소요시간={elapsed:.2f}s"
            )
            run_logs.append(
                {
                    "run": i,
                    "scenario": sc["label"],
                    "fit_status": re_validated.fit_status,
                    "match_pct": re_validated.overall_match_percentage,
                    "elapsed_sec": elapsed,
                    "schema_valid": True,
                }
            )

        except (ValidationError, json.JSONDecodeError, TypeError, KeyError, Exception) as err:
            elapsed = round(time.perf_counter() - t0, 2)
            format_error_count += 1
            print(f"  ❌ [{i:02d}/{TOTAL_RUNS:02d}회차 실패] 포맷/스키마 에러 발생: {err}")
            run_logs.append(
                {
                    "run": i,
                    "scenario": sc["label"],
                    "error": str(err),
                    "elapsed_sec": elapsed,
                    "schema_valid": False,
                }
            )

    success_rate = round((success_count / TOTAL_RUNS) * 100, 1)
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0

    print("\n" + "=" * 84)
    if success_count == TOTAL_RUNS and format_error_count == 0:
        print(
            f"🎉 [검증 ③ 최종 결과: PASS 🟢] {TOTAL_RUNS}회 연속 호출 중 {success_count}회 성공 "
            f"(성공률 {success_rate}%, 포맷 에러 {format_error_count}건)"
        )
    else:
        print(
            f"⚠️ [검증 ③ 최종 결과: FAIL 🔴] {TOTAL_RUNS}회 중 {success_count}회 성공 "
            f"(포맷 에러 {format_error_count}건 발생)"
        )
    print("=" * 84)
    print(f"• 총 연속 호출 횟수      : {TOTAL_RUNS}회")
    print(f"• 스키마 검증 통과 횟수  : {success_count}회 ({success_rate}%)")
    print(f"• 포맷/파싱 에러 건수    : {format_error_count}건 (목표: 0건)")
    print(f"• 평균 E2E 응답 지연시간 : {avg_latency}초 (최소 {min_latency}초 ~ 최대 {max_latency}초 / 목표: 평균 5.0초 이내)")
    print("=" * 84)

    return {
        "total_runs": TOTAL_RUNS,
        "success_count": success_count,
        "format_error_count": format_error_count,
        "success_rate_pct": success_rate,
        "avg_latency_sec": avg_latency,
        "logs": run_logs,
    }


if __name__ == "__main__":
    run_step3_10x_pydantic_stability_test()

