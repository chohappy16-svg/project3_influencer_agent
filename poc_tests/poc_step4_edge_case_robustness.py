"""
[InfluenceOps Phase 1 - PoC 기술 검증 ④]
검증 항목: ④ 엣지 케이스 방어 로직 (Robustness)

1. 무엇을 테스트하는가? (Test)
   - 이모지로만 도배된 텍스트("☕️🌿✨🤍"), 완전한 새까만 화면 이미지(black screen),
     바이트가 깨진 손상 이미지 파일(corrupted file), 그리고 LLM 안전 필터 거절(Safety Refusal) 상황을
     주입하여 예외 상황에 대응하는지 테스트합니다.
2. 왜 해야 하는가? (Why)
   - 실제 서비스 운영 중 비정상적인 유저 입력이나 불량 데이터 유입으로 인해
     파이썬 백엔드 서버(FastAPI)가 다운(500 Internal Server Error)되는 것을 원천 차단하기 위함입니다.
3. 통과 여부 기준 (Success Criteria)
   - 모든 비정상/극단적 입력에 대해 서버(코드)가 뻗지 않고(Unhandled Exception 0건),
     사전에 정의한 예외 상태값(DATA_INSUFFICIENT, UNANALYZABLE)을 100% 정확히 반환해야 합니다.
"""

import io
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, UnidentifiedImageError

from poc_step1_base64_multimodal import (
    POC_IMAGE_DIR,
    encode_image_to_base64,
    prepare_local_beauty_test_images,
)
from poc_step2_prompt_matching import (
    BRAND_PERSONA_DNA,
    CAMPAIGN_GUIDELINE,
    InfluencerEvaluation,
    MediaIntentAnalysis,
    build_system_prompt,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")


def prepare_edge_case_test_files() -> Dict[str, Path]:
    """
    엣지 케이스 검증을 위한 특수 로컬 이미지 파일들을 생성합니다:
    1) edge_black_screen.jpg : 피사체를 전혀 식별할 수 없는 완전한 새까만 화면 (RGB 0, 0, 0)
    2) edge_corrupted_file.jpg : 파일 확장자는 .jpg이지만 내부 바이트가 손상된 깨진 파일
    """
    POC_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    normal_imgs = prepare_local_beauty_test_images()

    # 1) 완전한 새까만 화면 이미지 생성
    black_img_path = POC_IMAGE_DIR / "edge_black_screen.jpg"
    black_im = Image.new("RGB", (512, 512), (0, 0, 0))
    black_im.save(black_img_path, "JPEG", quality=85)

    # 2) 깨진(손상된) 이미지 파일 생성
    corrupted_img_path = POC_IMAGE_DIR / "edge_corrupted_file.jpg"
    with open(corrupted_img_path, "wb") as f:
        f.write(b"NOT_A_VALID_JPEG_HEADER_\x00\xff\xd8\xff_CORRUPTED_BYTES_DATA")

    return {
        "normal_aesthetic": normal_imgs[2],
        "black_screen": black_img_path,
        "corrupted_file": corrupted_img_path,
    }


def is_text_meaningful(caption: str) -> bool:
    """
    캡션에서 이모지·특수문자·공백을 제거한 뒤 실제 한글/영문/숫자 글자가 최소 2자 이상 존재하는지 검사합니다.
    (예: "☕️🌿✨🤍" -> 의미 있는 텍스트 없음 -> False)
    """
    if not caption or not caption.strip():
        return False
    meaningful_chars = re.findall(r"[가-힣a-zA-Z0-9]", caption)
    return len(meaningful_chars) >= 2


def validate_and_inspect_image(image_path: Path) -> Dict[str, Any]:
    """
    로컬 이미지 파일을 RAM에서 열어 손상 여부(Corrupted)와 완전 흑백/암전 화면(Black Screen) 여부를 사전 진단합니다.
    """
    if not image_path.exists() or not image_path.is_file():
        return {"valid": False, "reason": "FILE_NOT_FOUND"}

    try:
        raw_bytes = image_path.read_bytes()
        if len(raw_bytes) < 100:
            return {"valid": False, "reason": "CORRUPTED_OR_TOO_SMALL"}

        with Image.open(io.BytesIO(raw_bytes)) as im:
            im_rgb = im.convert("RGB")
            extrema = im_rgb.getextrema()  # ((R_min, R_max), (G_min, G_max), (B_min, B_max))
            max_pixel_val = max(channel[1] for channel in extrema)
            if max_pixel_val <= 5:
                return {"valid": True, "is_black_screen": True, "reason": "ALL_BLACK_IMAGE"}

        return {"valid": True, "is_black_screen": False, "reason": "OK"}
    except (UnidentifiedImageError, OSError, Exception) as e:
        return {"valid": False, "reason": f"CORRUPTED_IMAGE ({type(e).__name__})"}


def build_safe_fallback_evaluation(reason_msg: str, frame_count: int = 1) -> InfluencerEvaluation:
    """
    깨진 이미지 파일, 텍스트 부재, 또는 LLM 안전 필터 거절(Safety Refusal) 발생 시
    500 에러 대신 프론트엔드/DB가 안전하게 처리할 수 있는 표준 예외 스키마(UNANALYZABLE / DATA_INSUFFICIENT)를 생성합니다.
    """
    unanalyzable_frame = MediaIntentAnalysis(
        aesthetic_score=1,
        texture_rendering="UNANALYZABLE",
        lifestyle_context="UNANALYZABLE",
        text_intent="UNANALYZABLE",
        visual_appeal="UNANALYZABLE",
    )
    return InfluencerEvaluation(
        media_analysis=[unanalyzable_frame for _ in range(max(1, frame_count))],
        overall_match_percentage=0,
        fit_status="DATA_INSUFFICIENT",
        expected_collisions=["분석 불가 미디어 또는 텍스트 데이터 부족 (마케터 수동 확인 요망)"],
        decision_rationale=reason_msg[:500],
        guideline_draft="데이터 부족 또는 이미지 판독 불가 상태이므로 마케터님의 수동 피드 확인 후 가이드라인 작성을 권장합니다.",
    )


def evaluate_with_edge_case_defense(
    client: OpenAI,
    case_name: str,
    image_paths: List[Path],
    caption: str,
    simulate_safety_refusal: bool = False,
) -> InfluencerEvaluation:
    """
    [PRD 3.3, 6.A.3 & p.23~24 실무 방어 엔진]
    1) 방어 1 (IndexError 방지): 미디어 배열이 2장 이하일 때도 안전하게 슬라이싱
    2) 방어 2 (깨진 이미지 차단): 손상된 이미지 파일 유입 시 OpenAI API 400 에러 발생 전 UNANALYZABLE 스키마 즉시 반환
    3) 방어 3 (이모지 도배 / 암전 화면 프롬프트 + 사후 검증): Vision LLM 호출 및 Safety Refusal 방어
    """
    # 방어 1: 2장 이하 배열 슬라이싱 안전 처리
    safe_paths = image_paths[:3] if len(image_paths) > 2 else image_paths[:]
    if not safe_paths:
        return build_safe_fallback_evaluation("입력된 이미지가 없습니다 (DATA_INSUFFICIENT).", 1)

    # 방어 2: 로컬 이미지 파일 무결성(깨진 파일 여부) 사전 검사
    has_black_screen = False
    for p in safe_paths:
        img_check = validate_and_inspect_image(p)
        if not img_check["valid"]:
            return build_safe_fallback_evaluation(
                f"[방어 로직 작동 - {img_check['reason']}] 깨지거나 손상된 이미지 파일({p.name})이 감지되어 서버 다운을 방지하고 UNANALYZABLE / DATA_INSUFFICIENT 상태를 반환합니다.",
                frame_count=len(safe_paths),
            )
        if img_check.get("is_black_screen"):
            has_black_screen = True

    text_ok = is_text_meaningful(caption)

    # 방어 3: LLM Safety Refusal 시뮬레이션 (PRD p.23~24 피부 클로즈업/오프숄더 NSFW 오해 거절 대응 검증)
    if simulate_safety_refusal:
        return build_safe_fallback_evaluation(
            "[AI 안전 필터로 인해 판독 불가 (마케터 수동 검증 요망)] OpenAI Safety Refusal 응답이 감지되어 앱 크래시를 차단하고 예외 스키마를 반환했습니다.",
            frame_count=len(safe_paths),
        )

    # Vision LLM에게 엣지 케이스도 분석하도록 전달하되, 시스템 프롬프트에 UNANALYZABLE / DATA_INSUFFICIENT 규칙을 명확히 주입
    edge_defense_prompt = (
        build_system_prompt(BRAND_PERSONA_DNA, CAMPAIGN_GUIDELINE)
        + """

[엣지 케이스 강제 방어 규칙 (매우 중요)]
- 만약 캡션 텍스트가 이모지("☕️🌿✨🤍" 등)로만 도배되어 의미 있는 글이 없거나 빈 문자열이면:
  반드시 fit_status="DATA_INSUFFICIENT"로 설정하고, text_intent="UNANALYZABLE" (또는 "NONE")로 설정해!
- 만약 전송된 이미지가 완전히 새까만 화면(암전)이거나 피사체를 전혀 알아볼 수 없는 이미지라면:
  반드시 해당 프레임의 texture_rendering="UNANALYZABLE", lifestyle_context="UNANALYZABLE", visual_appeal="UNANALYZABLE", aesthetic_score=1 로 설정하고, 최종 fit_status="DATA_INSUFFICIENT"로 반환해!
"""
    )

    content_payload: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": f"[케이스]: {case_name}\n[인플루언서 피드 캡션]:\n{caption}",
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

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": edge_defense_prompt},
                {"role": "user", "content": content_payload},
            ],
            response_format=InfluencerEvaluation,
            temperature=0.0,
        )
        msg = response.choices[0].message

        # OpenAI Safety Refusal 실제 발생 시 방어
        if getattr(msg, "refusal", None):
            return build_safe_fallback_evaluation(
                f"AI 안전 필터로 인해 판독 불가 (마케터 수동 검증 요망): {msg.refusal}",
                frame_count=len(safe_paths),
            )

        parsed: InfluencerEvaluation = msg.parsed

        # 사후 가드레일(Post-Validation Guardrail): 이모지 도배나 완전 암전 이미지일 때 상태값 100% 보장
        if not text_ok or has_black_screen:
            parsed.fit_status = "DATA_INSUFFICIENT"
            if has_black_screen:
                for frame in parsed.media_analysis:
                    frame.texture_rendering = "UNANALYZABLE"
                    frame.visual_appeal = "UNANALYZABLE"
                    frame.lifestyle_context = "UNANALYZABLE"
            if not text_ok:
                for frame in parsed.media_analysis:
                    if frame.text_intent not in ("NONE", "UNANALYZABLE"):
                        frame.text_intent = "UNANALYZABLE"

        return parsed

    except Exception as api_err:
        # 어떤 API/네트워크/파싱 에러가 발생해도 500 에러로 서버가 죽지 않고 예외 스키마 반환
        return build_safe_fallback_evaluation(
            f"[시스템 예외 방어 작동] 비정상 입력 처리 중 예외 포착({type(api_err).__name__}): 마케터 수동 검증 요망",
            frame_count=len(safe_paths),
        )


def run_step4_edge_case_verification():
    files = prepare_edge_case_test_files()

    edge_cases = [
        {
            "id": "엣지 케이스 1: 이모지로만 도배된 텍스트 (PRD p.14 '☕️🌿✨🤍')",
            "images": [files["normal_aesthetic"]],
            "caption": "☕️🌿✨🤍",
            "simulate_refusal": False,
            "expect_fit_status": "DATA_INSUFFICIENT",
            "expect_unanalyzable_or_none": True,
        },
        {
            "id": "엣지 케이스 2: 완전한 새까만 화면 이미지 (Black Screen) + 빈 텍스트",
            "images": [files["black_screen"]],
            "caption": "🖤",
            "simulate_refusal": False,
            "expect_fit_status": "DATA_INSUFFICIENT",
            "expect_unanalyzable_or_none": True,
        },
        {
            "id": "엣지 케이스 3: 바이트가 손상된 깨진 이미지 파일 (Corrupted JPEG)",
            "images": [files["corrupted_file"]],
            "caption": "오늘의 스킨케어 루틴 공유해요!",
            "simulate_refusal": False,
            "expect_fit_status": "DATA_INSUFFICIENT",
            "expect_unanalyzable_or_none": True,
        },
        {
            "id": "엣지 케이스 4: LLM 안전 필터 거절 (Safety Refusal) & 2장 이하 배열 방어",
            "images": [files["normal_aesthetic"], files["black_screen"]],  # 2장짜리 캐러셀 (IndexError 방어 검증 포함)
            "caption": "피부 질감 초근접 클로즈업 컷 테스트",
            "simulate_refusal": True,
            "expect_fit_status": "DATA_INSUFFICIENT",
            "expect_unanalyzable_or_none": True,
        },
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다.")
    client = OpenAI(api_key=api_key)

    print("=" * 84)
    print("🚀 [InfluenceOps PoC 검증 ④] 엣지 케이스 방어 로직 (Robustness) 테스트 시작")
    print("=" * 84)

    all_passed = True
    results_summary = []

    for idx, ec in enumerate(edge_cases, start=1):
        t0 = time.perf_counter()
        res = evaluate_with_edge_case_defense(
            client=client,
            case_name=ec["id"],
            image_paths=ec["images"],
            caption=ec["caption"],
            simulate_safety_refusal=ec["simulate_refusal"],
        )
        elapsed = round(time.perf_counter() - t0, 2)

        frame0 = res.media_analysis[0]
        has_unanalyzable = (
            "UNANALYZABLE"
            in (
                frame0.texture_rendering,
                frame0.lifestyle_context,
                frame0.text_intent,
                frame0.visual_appeal,
            )
            or frame0.text_intent == "NONE"
        )
        status_ok = res.fit_status == ec["expect_fit_status"]
        case_passed = status_ok and has_unanalyzable
        if not case_passed:
            all_passed = False

        badge = "✅ PASS (서버 정상 방어)" if case_passed else "❌ FAIL"
        print(f"\n[{idx}/4] {ec['id']}")
        print(f"  • 입력 이미지        : {[p.name for p in ec['images']]}")
        print(f"  • 입력 캡션          : {repr(ec['caption'])}")
        print(f"  • 반환 fit_status    : {res.fit_status} (기대값: {ec['expect_fit_status']})")
        print(
            f"  • 프레임 예외 상태값 : texture={frame0.texture_rendering}, "
            f"visual={frame0.visual_appeal}, text_intent={frame0.text_intent}"
        )
        print(f"  • 방어 사유 요약     : {res.decision_rationale}")
        print(f"  • 판정 결과          : {badge} (소요시간: {elapsed}초)")
        print("  • [Structured JSON 출력]:")
        print(res.model_dump_json(indent=2))

        results_summary.append(
            {
                "case": ec["id"],
                "fit_status": res.fit_status,
                "texture": frame0.texture_rendering,
                "visual": frame0.visual_appeal,
                "text_intent": frame0.text_intent,
                "passed": case_passed,
                "elapsed_sec": elapsed,
            }
        )

    print("\n" + "=" * 84)
    if all_passed:
        print(
            "🎉 [검증 ④ 최종 결과: PASS 🟢] 500 에러 0건! 모든 엣지 케이스에서 DATA_INSUFFICIENT / UNANALYZABLE 100% 반환!"
        )
    else:
        print("⚠️ [검증 ④ 최종 결과: FAIL 🔴] 일부 엣지 케이스 방어 실패")
    print("=" * 84)
    for r in results_summary:
        mark = "🟢 PASS" if r["passed"] else "🔴 FAIL"
        print(
            f"  - {r['case']}: fit_status={r['fit_status']} | "
            f"texture={r['texture']} | text_intent={r['text_intent']} | {r['elapsed_sec']}초 [{mark}]"
        )
    print("=" * 84)


if __name__ == "__main__":
    run_step4_edge_case_verification()
