"""
[InfluenceOps Phase 1 - PoC 기술 검증 ①]
검증 항목: ① Base64 인코딩 및 멀티모달 전송 (gpt-4o Vision API)

1. 무엇을 테스트하는가? (Test)
   - 로컬 PC에 저장된 뷰티 인플루언서 테스트 이미지 파일(3종: 일상 피부결/제형 컷, 과도한 광고 전단지 컷, 감성 라이프스타일 컷)을
     텍스트 형태의 Base64 암호문으로 정상 변환하여 Vision LLM(gpt-4o)에게 누락 없이 전송하는지 테스트합니다.
2. 왜 해야 하는가? (Why)
   - 멀티모달 AI 서비스(InfluenceOps)의 기본 전제인 로컬 -> RAM Base64 인코딩 -> Vision LLM 전송 파이프라인이
     에러 없이 수립되었는지 확인하기 위함입니다.
3. 통과 여부 기준 (Success Criteria)
   - 이미지 전송 과정에서 파이썬 FileNotFoundError나 인코딩(UTF-8/Base64) 에러 없이
     gpt-4o API 호출이 정상 성공(HTTP 200 & 유효 응답 수신)해야 합니다.
"""

import base64
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# Windows 터미널 한글/이모지 출력 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# .env 환경변수 로드 (c:\workAI\work9\.env)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env") or load_dotenv(BASE_DIR / ".env")

POC_IMAGE_DIR = BASE_DIR / "poc_images"


def prepare_local_beauty_test_images() -> List[Path]:
    """
    로컬 PC(c:\\workAI\\work9\\poc_images)에 기획안(PRD) 기준 테스트용 뷰티 이미지 3종을 준비합니다.
    (PIL/Pillow로 각 시나리오의 시각적 특징이 명확한 로컬 JPG 이미지를 생성하여 FileNotFoundError를 원천 방지합니다.)
    """
    POC_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    img_a = POC_IMAGE_DIR / "beauty_case_A_natural_glow.jpg"
    img_b = POC_IMAGE_DIR / "beauty_case_B_hard_sell_promo.jpg"
    img_c = POC_IMAGE_DIR / "beauty_case_C_minimal_aesthetic.jpg"

    try:
        from PIL import Image, ImageDraw, ImageFilter

        # [사진 1 - 후보 A] 따뜻한 자연광 + 맑은 수분 앰플 제형/피부결 무드 컷
        if not img_a.exists():
            im = Image.new("RGB", (640, 640), (246, 238, 230))
            draw = ImageDraw.Draw(im)
            # 따뜻한 자연광 그라데이션 & 수분 앰플 물방울 표현
            for y in range(640):
                r = min(255, 240 + int(12 * (1 - y / 640)))
                g = min(255, 228 + int(15 * (1 - y / 640)))
                b = min(255, 218 + int(18 * (1 - y / 640)))
                draw.line([(0, y), (640, y)], fill=(r, g, b))
            # 앰플 병 실루엣 & 수분 드롭
            draw.rounded_rectangle([230, 180, 410, 490], radius=32, fill=(215, 238, 248), outline=(160, 200, 220), width=4)
            draw.rectangle([285, 110, 355, 180], fill=(245, 245, 245), outline=(180, 180, 180), width=3)
            draw.ellipse([430, 340, 510, 420], fill=(200, 235, 250), outline=(150, 210, 240), width=3)
            draw.text((195, 535), "Natural Glow Hydrating Ampoule", fill=(90, 80, 70))
            im = im.filter(ImageFilter.SMOOTH)
            im.save(img_a, "JPEG", quality=92)

        # [사진 2 - 후보 B] 과도한 상업/전단지형 (고채도 배경 + 자극적 할인 텍스트 오버레이)
        if not img_b.exists():
            im = Image.new("RGB", (640, 640), (255, 45, 45))
            draw = ImageDraw.Draw(im)
            draw.rectangle([20, 20, 620, 620], outline=(255, 235, 0), width=12)
            draw.rectangle([50, 60, 590, 190], fill=(255, 235, 0))
            draw.text((95, 105), "HOT DEAL!! 70% SALE EVENT!!", fill=(220, 0, 0))
            draw.rectangle([70, 240, 570, 380], fill=(255, 255, 255))
            draw.text((110, 295), "BUY 3 GET 1 FREE! HURRY UP!", fill=(0, 0, 0))
            draw.rectangle([120, 430, 520, 550], fill=(0, 0, 0))
            draw.text((170, 475), "SOLD OUT SOON - CLICK LINK", fill=(255, 255, 0))
            im.save(img_b, "JPEG", quality=92)

        # [사진 3 - 후보 C] 화장품 노출 없는 감성 인테리어/우드톤/식물/햇살 컷
        if not img_c.exists():
            im = Image.new("RGB", (640, 640), (242, 239, 232))
            draw = ImageDraw.Draw(im)
            # 창문 채광 그림자
            draw.polygon([(0, 0), (420, 0), (640, 360), (640, 640), (180, 640)], fill=(252, 249, 242))
            # 우드 테이블
            draw.rectangle([0, 420, 640, 640], fill=(198, 166, 132))
            # 커피잔 & 화분 오브제
            draw.ellipse([180, 350, 310, 460], fill=(250, 248, 245), outline=(170, 160, 150), width=4)
            draw.ellipse([205, 370, 285, 435], fill=(130, 90, 60))
            draw.rounded_rectangle([390, 270, 490, 440], radius=16, fill=(215, 205, 190))
            draw.ellipse([360, 170, 460, 290], fill=(115, 155, 110))
            draw.ellipse([420, 150, 520, 270], fill=(95, 140, 95))
            draw.text((185, 520), "Sunday Morning Sunlight & Coffee", fill=(245, 240, 230))
            im.save(img_c, "JPEG", quality=92)

    except Exception as e:
        print(f"[경고] PIL 이미지 생성 중 예외 발생 ({e}), 기존 work9/image 폴더 이미지를 대체 활용합니다.")
        fallback_dir = BASE_DIR / "image"
        return [
            fallback_dir / "withpet.jpg",
            fallback_dir / "desk.jpg",
            fallback_dir / "road.jpg",
        ]

    return [img_a, img_b, img_c]


def encode_image_to_base64(image_path: str | Path) -> str:
    """
    [PRD 3.2 & 4.2] 로컬 이미지를 디스크에 재저장하지 않고 RAM에서 읽어
    UTF-8 Base64 문자열로 인코딩합니다.
    """
    path_obj = Path(image_path)
    if not path_obj.exists() or not path_obj.is_file():
        raise FileNotFoundError(f"로컬 이미지 파일을 찾을 수 없습니다: {path_obj}")

    with open(path_obj, "rb") as image_file:
        raw_bytes = image_file.read()
        if not raw_bytes:
            raise ValueError(f"이미지 파일이 비어 있습니다(0 byte): {path_obj}")
        b64_str = base64.b64encode(raw_bytes).decode("utf-8")

    # 디코딩 무결성 검증 (손상 없이 역변환 가능한지 확인)
    decoded_check = base64.b64decode(b64_str.encode("utf-8"))
    if len(decoded_check) != len(raw_bytes):
        raise ValueError("Base64 인코딩/디코딩 무결성 검증 실패")

    return b64_str


def test_step1_base64_and_multimodal_transmission(image_paths: List[Path]) -> Dict[str, Any]:
    """
    [검증 ① 실행 함수]
    1) 로컬 파일 존재 확인 (FileNotFoundError 방어)
    2) Base64 인코딩 무결성 테스트 (Encoding Error 방어)
    3) OpenAI Vision LLM (gpt-4o) 멀티모달 전송 및 응답 수신 테스트
    """
    print("=" * 76)
    print("🚀 [InfluenceOps PoC 검증 ①] Base64 인코딩 및 멀티모달(gpt-4o) 전송 테스트 시작")
    print("=" * 76)

    # 1. 로컬 이미지 Base64 인코딩 검증
    encoded_payload_items = []
    encoding_report = []

    # PRD 방어 로직: 만약 미디어가 2장 이하일 때도 IndexError 없이 안전하게 슬라이싱 처리
    safe_image_paths = image_paths[:3] if len(image_paths) > 2 else image_paths[:]

    for idx, img_path in enumerate(safe_image_paths, start=1):
        b64_str = encode_image_to_base64(img_path)
        file_size_kb = round(img_path.stat().st_size / 1024, 2)
        b64_len = len(b64_str)

        print(f"  ✅ [이미지 #{idx} 인코딩 성공] 파일명: {img_path.name}")
        print(f"     - 경로: {img_path}")
        print(f"     - 원본 크기: {file_size_kb} KB -> Base64 문자열 길이: {b64_len:,} chars")
        print(f"     - Base64 앞 40자 샘플: {b64_str[:40]}...")

        encoding_report.append(
            {
                "index": idx,
                "file_name": img_path.name,
                "file_size_kb": file_size_kb,
                "base64_length": b64_len,
            }
        )
        encoded_payload_items.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_str}",
                    "detail": "low",  # PoC 토큰 비용 최적화 및 고속 전송
                },
            }
        )

    # 2. Vision LLM (gpt-4o) 멀티모달 API 전송 테스트
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다.")

    client = OpenAI(api_key=api_key)

    content_payload = [
        {
            "type": "text",
            "text": (
                "아래 전송된 3장의 Base64 이미지가 각각 어떤 비주얼/색감/특징을 가지고 있는지 "
                "번호별로 한 줄씩 간단히 요약해 주세요. (멀티모달 수신 확인용)"
            ),
        },
        *encoded_payload_items,
    ]

    print("\n⏳ Vision LLM (gpt-4o-2024-08-06)로 Base64 이미지 3장 멀티모달 전송 중...")
    start_time = time.perf_counter()

    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "너는 InfluenceOps의 뷰티 비주얼 검수 AI 에이전트야. 전송받은 이미지가 정상적으로 보이는지 각 이미지의 시각적 특징을 간결하게 설명해.",
            },
            {
                "role": "user",
                "content": content_payload,
            },
        ],
        max_tokens=300,
        temperature=0.2,
    )

    elapsed_sec = round(time.perf_counter() - start_time, 2)
    ai_reply = response.choices[0].message.content.strip()
    usage = response.usage

    print("\n" + "=" * 76)
    print("🎉 [검증 ① 통과 결과: PASS 🟢] FileNotFoundError / 인코딩 에러 0건, API 호출 성공!")
    print("=" * 76)
    print(f"• 호출 모델        : {response.model}")
    print(f"• 전송 이미지 수   : {len(safe_image_paths)}장 (Base64 인코딩 전송 완료)")
    print(f"• 응답 소요 시간   : {elapsed_sec}초 (목표: 5.0초 이내)")
    print(f"• 토큰 사용량      : 총 {usage.total_tokens} tokens (Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens})")
    print("-" * 76)
    print("[Vision LLM이 실제로 눈으로 읽은 이미지 3장 판독 응답]:")
    print(ai_reply)
    print("=" * 76)

    return {
        "success": True,
        "model": response.model,
        "image_count": len(safe_image_paths),
        "elapsed_seconds": elapsed_sec,
        "total_tokens": usage.total_tokens,
        "encoding_report": encoding_report,
        "ai_reply": ai_reply,
    }


if __name__ == "__main__":
    test_imgs = prepare_local_beauty_test_images()
    test_step1_base64_and_multimodal_transmission(test_imgs)

