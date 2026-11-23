"""
[InfluenceOps] backend/models.py
==============================================================================
인플루언서 섭외 의사결정 지원 SaaS 핵심 데이터베이스 모델 정의 (SQLAlchemy ORM)

핵심 테이블 구조:
  1. users              — 마케터 계정 (비밀번호 Bcrypt 단방향 해시 암호화 저장)
  2. brand_dnas         — 브랜드 자사몰 기반 자동 추출 및 설정된 브랜드 페르소나/가이드라인
  3. campaigns          — 협찬 캠페인 정보 (대상 제품, 희망 포맷, 진행 기간, 상태, 5대 가이드라인)
  4. influencer_results — 인플루언서별 프로필, 피드 분석, 매칭률, 적합도 판정, 예상 원고료, 승인 상태
  5. token_usages       — 분석 단계별(1차 선별 / 2차 정밀 분석) AI 토큰 소모량 및 비용 통계
==============================================================================
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """1. 마케터 회원 계정 모델"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    company_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계 정의
    brand_dnas = relationship("BrandDNA", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    token_usages = relationship("TokenUsage", back_populates="user")


class BrandDNA(Base):
    """
    2. 브랜드 페르소나 및 가이드라인 모델
    - 브랜드 자사몰 웹페이지에서 추출한 톤앤매너, 타깃 고객, 소구점을 영구 저장하여
      새로운 캠페인 생성 및 인플루언서 매칭 평가 시 일관된 기준으로 활용합니다.
    """

    __tablename__ = "brand_dnas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_name = Column(String(120), nullable=False)
    brand_url = Column(String(500), nullable=True)
    target_audience = Column(Text, nullable=True)
    visual_mood = Column(Text, nullable=True)
    core_selling_point = Column(Text, nullable=True)
    full_dna_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="brand_dnas")
    campaigns = relationship("Campaign", back_populates="brand_dna")


class Campaign(Base):
    """
    3. 협찬 캠페인 정보 모델
    - 제품 정보, 희망 콘텐츠 포맷(릴스/피드/혼합), 기간(D-Day), 진행 상태(준비/진행중/완료),
      소프트 딜리트(휴지통 30일 보관), 5대 평가 가이드라인을 관리합니다.
    """

    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_dna_id = Column(Integer, ForeignKey("brand_dnas.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    product_name = Column(String(150), nullable=True)
    product_url = Column(String(500), nullable=True)          # 제품 공식 판매/홍보 링크
    product_image_url = Column(String(500), nullable=True)    # 대표 썸네일 이미지 URL (자동 추출 또는 직접 지정)
    preferred_format = Column(String(30), default="MIXED")    # 희망 포맷: MIXED(자유) | REELS(릴스) | FEED(피드)
    status = Column(String(30), default="READY", index=True)  # 상태: READY(준비/분석) | IN_PROGRESS(진행 중) | COMPLETED(종료)
    start_date = Column(String(20), nullable=True)            # 시작일 (YYYY-MM-DD)
    end_date = Column(String(20), nullable=True)              # 종료일 (YYYY-MM-DD)
    is_sourcing_completed = Column(Boolean, default=False, index=True) # 섭외 완료/마감 여부 (False: 섭외 진행 중, True: 섭외 완료)
    is_deleted = Column(Boolean, default=False, index=True)   # 휴지통 이동 여부 (소프트 딜리트)
    deleted_at = Column(DateTime(timezone=True), nullable=True) # 삭제 시각 (30일 경과 시 자동 영구 삭제 대상)
    campaign_appeal = Column(Text, nullable=False)            # 5대 가이드라인 텍스트
    total_candidates = Column(Integer, default=0)             # 등록된 후보 수
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="campaigns")
    brand_dna = relationship("BrandDNA", back_populates="campaigns")
    influencer_results = relationship(
        "InfluencerResult",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    token_usages = relationship("TokenUsage", back_populates="campaign")


class InfluencerResult(Base):
    """
    4. 인플루언서 분석 결과 및 의사결정 상태 모델
    - 프로필 정보, 활동 지표, 주력 포맷(릴스/피드), 매칭 점수, 적합도 판정, 시장 기준 예상 원고료,
      마케터의 최종 승인 여부(PENDING / APPROVED)를 저장합니다.
    """

    __tablename__ = "influencer_results"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    instagram_id = Column(String(100), index=True, nullable=False)
    full_name = Column(String(150), nullable=True)
    followers_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    influencer_tier = Column(String(80), nullable=True)       # 메가 / 매크로 / 마이크로 / 나노
    primary_format = Column(String(30), default="FEED")       # 🎬 REELS | 📷 FEED | 🎬+📷 HYBRID
    recommended_fee = Column(String(80), nullable=True)       # 시장 기준 예상 원고료

    # 브랜드 적합도 매칭률 점수 (0 ~ 100%)
    overall_match_percentage = Column(Integer, default=0, index=True)

    # 종합 적합도 판정: APPROVE(적합) / CREATIVE_EXCEPTION(예외추천) / REVIEW_NEEDED(검토필요) / REJECT(부적합) / DATA_INSUFFICIENT(판독불가)
    fit_status = Column(String(40), default="PENDING", index=True)

    # 마케터 최종 의사결정 상태: PENDING(검토 대기) -> APPROVED(선정/승인 완료)
    approval_state = Column(String(30), default="PENDING", index=True)

    # 인플루언서 프로필 분석 항목 (게시물 근거가 없을 경우 'UNKNOWN'으로 저장되어 환각 방지)
    skin_type = Column(String(40), default="UNKNOWN")
    family_pet_exposure = Column(String(40), default="UNKNOWN")
    communication_authenticity = Column(String(40), default="UNKNOWN")

    one_line_verdict = Column(Text, nullable=True)            # 한 줄 핵심 판정 코멘트
    rationale_json = Column(Text, nullable=True)              # 판정 근거 불릿 포인트 JSON
    media_analysis_json = Column(Text, nullable=True)         # 피드별 분석 결과 JSON
    thumbnails_json = Column(Text, nullable=True)             # 최근 피드 썸네일 이미지 목록 JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    campaign = relationship("Campaign", back_populates="influencer_results")


class TokenUsage(Base):
    """
    5. 단계별 AI 분석 토큰 소모량 및 비용 추적 모델
    - 1차 선별과 2차 정밀 분석 단계의 모델별 사용량과 비용 절감 통계를 집계합니다.
    """

    __tablename__ = "token_usages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    instagram_id = Column(String(100), nullable=True)
    track_stage = Column(String(40), nullable=False)          # 1단계 선별(TRACK_1_SCREENING) / 2단계 정밀(TRACK_2_DEEP_EVAL)
    model_name = Column(String(80), nullable=False)           # 실제 호출된 AI 모델 식별자
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    estimated_cost_krw = Column(Float, default=0.0)
    latency_sec = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="token_usages")
    campaign = relationship("Campaign", back_populates="token_usages")

    user = relationship("User", back_populates="token_usages")
    campaign = relationship("Campaign", back_populates="token_usages")
