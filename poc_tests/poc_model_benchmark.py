"""
[InfluenceOps LLM 모델 선정 벤치마크 테스트]
====================================================================================
후보 A(일상형: APPROVE), 후보 B(광고형: REJECT), 후보 C(감성형: CREATIVE_EXCEPTION)
3가지 표준 더미 데이터셋(이미지 + 캡션)을 동일한 프롬프트와 Pydantic 스키마로
4개 멀티모달 LLM 모델에 주입하여 아래 지표를 정량·정성 비교합니다.

[비교 지표]
1. 판정 정확도 (Accuracy): 후보 A/B/C 기획 의도 정답 일치율 (3/3 만점)
2. 스키마 및 제약 준수율 (Validation): Pydantic JSON 파싱 & 점수(1~10)/글자 수(<=500자) 준수
3. 응답 속도 (Latency): 후보 1명당 평균 분석 시간(초) — 목표 5.0초 이내
4. 토큰 사용량 및 비용 효율 (Cost): 1명당 평균 토큰 및 1,000명 분석 시 예상 API 비용(원)
5. 카피라이팅 품질 (Guideline Quality): 후보 C(감성형)에 대한 맞춤형 역제안 가이드라인 문장력
====================================================================================
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

from poc_step1_base64_multimodal import encode_image_to_base64, prepare_local_beauty_test_images
from poc_step2_prompt_matching import (
    BRAND_PERSONA_DNA,
    CAMPAIGN_GUIDELINE,
    InfluencerEvaluation,
    build_system_prompt,
)


def build_dummy_candidates(imgs: List[Path]) -> List[Dict[str, Any]]:
    img_a, img_b, img_c = imgs[0], imgs[1], imgs[2]
    return [
        {
            "id": "CASE_A",
            "name": "후보 A (일상형 / 뷰티 고관여 Ideal Fit)",
            "persona_desc": "내돈내산 스킨케어 루틴 공유, 피부 광채 및 진정 팁 중심",
            "image_path": img_a,
            "caption": (
                "요즘 환절기라 피부가 확 뒤집어져서 너무 속상했는데 ㅠㅠ 며칠 전부터 "
                "진정 루틴으로 싹 바꿨더니 붉은기가 많이 가라앉았어요! 끈적이는 거 딱 "
                "질색인데 이건 흡수도 빠르고 속건조를 꽉 잡아주더라고요. 아침저녁으로 듬뿍 "
                "올려주고 자는 게 제 꿀팁 🍯✨ #내돈내산 #스킨케어 #민감성피부"
            ),
            "expected_fit_status": "APPROVE",
        },
        {
            "id": "CASE_B",
            "name": "후보 B (광고형 / 과도한 상업 및 공구 전단지형)",
            "persona_desc": "단독 핫딜 오픈, 과장된 세일 배너 및 프로필 구매 링크 유도 중심",
            "image_path": img_b,
            "caption": (
                "[단독 핫딜 오픈] 여러분 드디어 기다리시던 앰플 3차 공구 오픈합니다!! 🎉 "
                "이번 구성 진짜 역대급 혜택 미쳤어요 ㅠㅠ 3세트 구매 시 1세트 더 드리는 이벤트 "
                "놓치지 마세요! 품절되기 전에 프로필 링크에서 지금 당장 구매 가능합니다 🏃‍♀️🏃‍♂️ "
                "#공구마켓 #협찬 #광고 #핫딜 #할인행사"
            ),
            "expected_fit_status": "REJECT",
        },
        {
            "id": "CASE_C",
            "name": "후보 C (감성형 / 라이프스타일 매칭형 - 시연 핵심 케이스)",
            "persona_desc": "자연광 우드 톤 미니멀 홈카페 감성, 비주얼 무드 최상이나 직접적 효능 키워드 부재",
            "image_path": img_c,
            "caption": (
                "Sunday morning vibe ☕️🌿 여유로운 주말 아침, 따뜻한 햇살 아래서 즐기는 "
                "나만의 스킨케어 타임. 패키지가 예뻐서 화장대 위에 그냥 툭 올려두기만 해도 "
                "감성 가득하네요. 텍스처가 가벼워서 데일리로 쓰기 좋아요. "
                "#집꾸미기 #홈카페 #미니멀라이프"
            ),
            "expected_fit_status": "CREATIVE_EXCEPTION",
        },
    ]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")

# 모델별 1M 토큰당 단가표 (USD 기준, 1 USD = 1,400 KRW 환산)
MODEL_PRICING_PER_1M: Dict[str, Dict[str, float]] = {
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "google/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "anthropic/claude-3.7-sonnet": {"input": 3.00, "output": 15.00},
}


def evaluate_candidate_with_openai_parse(
    client: OpenAI,
    model_id: str,
    system_prompt: str,
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """OpenAI Structured Outputs (beta.chat.completions.parse) 기반 후보 평가"""
    b64_img = encode_image_to_base64(candidate["image_path"])
    user_text = (
        f"[검증 대상 인플루언서: {candidate['name']}]\n"
        f"- 계정/게시물 특성: {candidate['persona_desc']}\n"
        f"- 게시물 캡션 텍스트:\n\"{candidate['caption']}\"\n\n"
        "첨부된 이미지와 캡션 텍스트를 종합 분석하여 InfluencerEvaluation 스키마로 판정 결과를 반환하세요."
    )

    start_time = time.perf_counter()
    response = client.beta.chat.completions.parse(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_img}",
                            "detail": "low",
                        },
                    },
                ],
            },
        ],
        response_format=InfluencerEvaluation,
        temperature=0.0,
    )
    elapsed = round(time.perf_counter() - start_time, 2)
    parsed: InfluencerEvaluation = response.choices[0].message.parsed

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0

    return {
        "parsed": parsed,
        "elapsed": elapsed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def evaluate_candidate_with_json_prompt(
    client: OpenAI,
    model_id: str,
    system_prompt: str,
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """OpenRouter 경유 모델(Gemini / Claude 등)을 위한 JSON 스키마 프롬프트 + Pydantic 검증"""
    b64_img = encode_image_to_base64(candidate["image_path"])
    schema_json = json.dumps(InfluencerEvaluation.model_json_schema(), ensure_ascii=False)
    strict_json_instruction = (
        "\n\n[출력 포맷 절대 규칙]\n"
        "반드시 마크다운 코드블록(```json) 없이 순수 JSON 객체만 출력하세요. "
        f"따라야 할 JSON Schema는 다음과 같습니다:\n{schema_json}"
    )
    user_text = (
        f"[검증 대상 인플루언서: {candidate['name']}]\n"
        f"- 계정/게시물 특성: {candidate['persona_desc']}\n"
        f"- 게시물 캡션 텍스트:\n\"{candidate['caption']}\"\n\n"
        "첨부된 이미지와 캡션 텍스트를 종합 분석하여 지정된 JSON 포맷으로만 응답하세요."
    )

    start_time = time.perf_counter()
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt + strict_json_instruction},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_img}",
                            "detail": "low",
                        },
                    },
                ],
            },
        ],
        temperature=0.0,
        max_tokens=900,
    )
    elapsed = round(time.perf_counter() - start_time, 2)
    raw_content = (response.choices[0].message.content or "").strip()
    if raw_content.startswith("```"):
        raw_content = raw_content.strip("`")
        if raw_content.lower().startswith("json"):
            raw_content = raw_content[4:].strip()

    parsed = InfluencerEvaluation.model_validate_json(raw_content)
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0

    return {
        "parsed": parsed,
        "elapsed": elapsed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def probe_openrouter_model(or_client: Optional[OpenAI], model_id: str) -> bool:
    """OpenRouter API 키로 해당 모델 호출이 가능한지 사전 점검"""
    if or_client is None:
        return False
    try:
        resp = or_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5,
        )
        return bool(resp.choices)
    except Exception as e:
        print(f"  ℹ️ OpenRouter [{model_id}] 호출 불가 ({type(e).__name__}: {str(e)[:80]}) -> OpenAI 최신 모델로 대체합니다.")
        return False


def run_benchmark() -> None:
    print("=" * 90)
    print("🚀 [InfluenceOps] 4대 멀티모달 LLM 모델 정량·정성 비교 벤치마크 시작")
    print("=" * 90)

    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openai_key:
        print("❌ OPENAI_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)

    oa_client = OpenAI(api_key=openai_key)
    or_client = (
        OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
        if openrouter_key
        else None
    )

    image_paths = prepare_local_beauty_test_images()
    candidates = build_dummy_candidates(image_paths)
    system_prompt = build_system_prompt(BRAND_PERSONA_DNA, CAMPAIGN_GUIDELINE)

    # 테스트할 4개 모델 라인업 구성 (OpenRouter 가능 시 포함, 아니면 OpenAI 4대 Vision 라인업으로 완주)
    model_lineup: List[Dict[str, Any]] = [
        {
            "label": "① GPT-4o (현재 메인)",
            "model_id": "gpt-4o-2024-08-06",
            "client": oa_client,
            "mode": "openai_parse",
        },
        {
            "label": "② GPT-4o-mini (초경량 가성비)",
            "model_id": "gpt-4o-mini",
            "client": oa_client,
            "mode": "openai_parse",
        },
    ]

    print("\n🔍 외부 모델(Gemini / Claude) API 연결 상태 사전 점검 중...")
    if probe_openrouter_model(or_client, "google/gemini-2.5-flash"):
        model_lineup.append(
            {
                "label": "③ Gemini 2.5 Flash (Google)",
                "model_id": "google/gemini-2.5-flash",
                "client": or_client,
                "mode": "json_prompt",
            }
        )
    else:
        model_lineup.append(
            {
                "label": "③ GPT-4.1 (차세대 플래그십)",
                "model_id": "gpt-4.1",
                "client": oa_client,
                "mode": "openai_parse",
            }
        )

    if probe_openrouter_model(or_client, "anthropic/claude-3.7-sonnet"):
        model_lineup.append(
            {
                "label": "④ Claude 3.7 Sonnet (Anthropic)",
                "model_id": "anthropic/claude-3.7-sonnet",
                "client": or_client,
                "mode": "json_prompt",
            }
        )
    else:
        model_lineup.append(
            {
                "label": "④ GPT-4.1-mini (차세대 밸런스형)",
                "model_id": "gpt-4.1-mini",
                "client": oa_client,
                "mode": "openai_parse",
            }
        )

    benchmark_summary: List[Dict[str, Any]] = []

    for m_info in model_lineup:
        label = m_info["label"]
        model_id = m_info["model_id"]
        client = m_info["client"]
        mode = m_info["mode"]

        print("\n" + "-" * 90)
        print(f"🧪 모델 테스트 중: {label} (model='{model_id}')")
        print("-" * 90)

        correct_count = 0
        schema_valid_count = 0
        latencies: List[float] = []
        total_in_tokens = 0
        total_out_tokens = 0
        case_outputs: Dict[str, Any] = {}

        for cand in candidates:
            expected = cand["expected_fit_status"]
            try:
                if mode == "openai_parse":
                    res = evaluate_candidate_with_openai_parse(client, model_id, system_prompt, cand)
                else:
                    res = evaluate_candidate_with_json_prompt(client, model_id, system_prompt, cand)

                parsed: InfluencerEvaluation = res["parsed"]
                actual = parsed.fit_status
                is_correct = actual == expected
                if is_correct:
                    correct_count += 1

                # 제약 조건 준수 여부
                scores_ok = all(1 <= f.aesthetic_score <= 10 for f in parsed.media_analysis)
                match_ok = 0 <= parsed.overall_match_percentage <= 100
                len_ok = len(parsed.decision_rationale) <= 500 and len(parsed.guideline_draft) <= 500
                if scores_ok and match_ok and len_ok:
                    schema_valid_count += 1

                latencies.append(res["elapsed"])
                total_in_tokens += res["prompt_tokens"]
                total_out_tokens += res["completion_tokens"]

                case_outputs[cand["id"]] = {
                    "expected": expected,
                    "actual": actual,
                    "match_pct": parsed.overall_match_percentage,
                    "score": [f.aesthetic_score for f in parsed.media_analysis],
                    "rationale": parsed.decision_rationale,
                    "guideline": parsed.guideline_draft,
                    "elapsed": res["elapsed"],
                    "correct": is_correct,
                }

                mark = "✅ 일치" if is_correct else "❌ 불일치"
                print(
                    f"  • [{cand['id']}] 기대값={expected} | 실제값={actual} ({mark}) | "
                    f"매칭률={parsed.overall_match_percentage}% | 미학점수={[f.aesthetic_score for f in parsed.media_analysis]} | "
                    f"{res['elapsed']}초"
                )
            except Exception as e:
                print(f"  ❌ [{cand['id']}] 에러 발생: {type(e).__name__}: {e}")
                case_outputs[cand["id"]] = {
                    "expected": expected,
                    "actual": f"ERROR ({type(e).__name__})",
                    "match_pct": 0,
                    "score": [],
                    "rationale": str(e),
                    "guideline": "",
                    "elapsed": 0.0,
                    "correct": False,
                }

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        avg_in = total_in_tokens / 3.0
        avg_out = total_out_tokens / 3.0
        pricing = MODEL_PRICING_PER_1M.get(model_id, {"input": 2.50, "output": 10.00})
        cost_per_call_usd = (avg_in / 1_000_000) * pricing["input"] + (avg_out / 1_000_000) * pricing["output"]
        cost_per_1000_krw = round(cost_per_call_usd * 1000 * 1400, 0)

        benchmark_summary.append(
            {
                "label": label,
                "model_id": model_id,
                "correct_count": correct_count,
                "schema_valid_count": schema_valid_count,
                "avg_latency": avg_latency,
                "avg_in_tokens": int(avg_in),
                "avg_out_tokens": int(avg_out),
                "cost_per_call_krw": round(cost_per_call_usd * 1400, 2),
                "cost_per_1000_krw": int(cost_per_1000_krw),
                "cases": case_outputs,
            }
        )

    print("\n" + "=" * 90)
    print("📊 [최종 비교 리포트] 4개 모델 정량·정성 평가 요약")
    print("=" * 90)
    for b in benchmark_summary:
        c_a = b["cases"].get("CASE_A", {}).get("actual", "-")
        c_b = b["cases"].get("CASE_B", {}).get("actual", "-")
        c_c = b["cases"].get("CASE_C", {}).get("actual", "-")
        print(
            f"■ {b['label']} ({b['model_id']})\n"
            f"  - 정답 일치율 : {b['correct_count']} / 3 (후보A={c_a}, 후보B={c_b}, 후보C={c_c})\n"
            f"  - 스키마 준수 : {b['schema_valid_count']} / 3 (100% 여부)\n"
            f"  - 평균 속도   : {b['avg_latency']}초 / 건 (평균 입력 {b['avg_in_tokens']} tok, 출력 {b['avg_out_tokens']} tok)\n"
            f"  - 예상 비용   : 건당 약 {b['cost_per_call_krw']}원 (1,000명 분석 시 약 {b['cost_per_1000_krw']:,}원)\n"
            f"  - [후보C 판정사유] : {b['cases'].get('CASE_C', {}).get('rationale', '')}\n"
            f"  - [후보C 가이드라인]: {b['cases'].get('CASE_C', {}).get('guideline', '')}"
        )
        print("-" * 90)


if __name__ == "__main__":
    run_benchmark()
