"""
[InfluenceOps Phase 2 MVP] backend/schemas.py
==============================================================================
Pydantic v2 입출력 스키마 및 환각(Hallucination) 통제 AI Structured Output 스키마 정의
- 피부 타입, 가족/반려동물 노출 등 미확인 정보에 대한 'UNKNOWN(파악 불가)' 강제 처리 반영
==============================================================================
"""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field


# ==============================================================================
# 1. AI Structured Output 스키마 (UNKNOWN 환각 통제 포함)
# ==============================================================================
class FrameAnalysisItem(BaseModel):
    aesthetic_score: int = Field(..., ge=1, le=10, description="1~10점 비주얼 감도 점수")
    texture_rendering: Literal["NATURAL_GLOW", "MODERATE_EDIT", "HEAVY_FILTER", "UNANALYZABLE"]
    lifestyle_context: Literal["BEAUTY_HIGH_INVOLVEMENT", "DAILY_CASUAL", "IRRELEVANT", "UNANALYZABLE"]
    scene_type_kr: str = Field(..., max_length=30, description="구체적 촬영 연출 형태 한글 요약")


class InfluencerAIOutputSchema(BaseModel):
    """투트랙 AI 라우팅(1차 Gemini Flash / 2차 GPT-4o) 공통 Structured Output 스키마"""

    overall_match_percentage: int = Field(..., ge=0, le=100, description="종합 매칭률 (0~100%)")
    fit_status: Literal["APPROVE", "CREATIVE_EXCEPTION", "REVIEW_NEEDED", "REJECT", "DATA_INSUFFICIENT"]
    one_line_verdict: str = Field(..., min_length=5, max_length=90, description="리스트 뷰에 표시할 1줄 핵심 판정 요약")

    # 환각(Hallucination) 통제 필드 — 게시물에서 명확히 확인되지 않으면 반드시 'UNKNOWN' 반환
    skin_type: Literal["DRY", "OILY", "COMBINATION", "SENSITIVE", "ACNE_PRONE", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="캡션·영상에서 명시적으로 확인된 피부 타입 (미확인 시 추측 금지, 반드시 UNKNOWN)",
    )
    family_pet_exposure: Literal["BABY_KIDS", "PET_COMPANION", "BOTH", "NONE_VISIBLE", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="영유아·자녀 또는 반려동물 노출 여부 (미확인 시 반드시 UNKNOWN)",
    )
    communication_authenticity: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"] = Field(
        default="UNKNOWN",
        description="팔로워 소통 및 리뷰 진정성 수준 (단순 전단지/봇은 LOW, 미확인 시 UNKNOWN)",
    )

    expected_collisions: List[str] = Field(default_factory=list)
    rationale_bullets: List[str] = Field(..., min_length=1, max_length=4)
    media_analysis: List[FrameAnalysisItem] = Field(..., min_length=1)


# ==============================================================================
# 2. Auth / BrandDNA / Campaign / Batch API 요청·응답 스키마
# ==============================================================================
class UserSignupRequest(BaseModel):
    email: EmailStr = Field(..., examples=["marketer@influenceops.ai"])
    password: str = Field(..., min_length=4, examples=["password1234"])
    company_name: Optional[str] = Field(default="클린뷰티 랩", examples=["클린뷰티 랩"])
    brand_url: str = Field(..., examples=["https://www.innisfree.com"])


class UserSignupResponse(BaseModel):
    message: str
    user_id: int
    email: str
    company_name: Optional[str] = None
    brand_url: str
    brand_dna: str


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., examples=["marketer@influenceops.ai"])
    password: str = Field(..., examples=["password1234"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    company_name: Optional[str] = None
    brand_dna_summary: Optional[str] = None


class UserRead(BaseModel):
    id: int
    email: str
    company_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserMeResponse(BaseModel):
    user_id: int
    email: str
    company_name: Optional[str] = None
    brand_url: Optional[str] = None
    brand_dna_summary: Optional[str] = None


class BrandDnaUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    brand_url: str
    full_dna_text: Optional[str] = None
    re_extract: bool = False


class BrandDnaResponse(BaseModel):
    message: str
    user_id: int
    company_name: Optional[str] = None
    brand_url: str
    brand_dna_summary: str


class BrandDNACreate(BaseModel):
    brand_name: str
    brand_url: Optional[str] = None
    target_audience: Optional[str] = None
    visual_mood: Optional[str] = None
    core_selling_point: Optional[str] = None
    full_dna_text: str


class CampaignCreate(BaseModel):
    title: str = Field(..., examples=["순한 수분 앰플 1차 캠페인"])
    product_name: Optional[str] = Field(default="저자극 시카 수분 앰플", examples=["저자극 시카 수분 앰플"])
    product_url: Optional[str] = Field(default=None, examples=["https://brand.com/products/cica-ampoule"])
    product_image_url: Optional[str] = Field(default=None, examples=["https://brand.com/images/cica-ampoule.jpg"])
    preferred_format: str = Field(default="MIXED", examples=["REELS"])
    status: str = Field(default="READY", examples=["READY"])
    start_date: Optional[str] = Field(default=None, examples=["2026-11-19"])
    end_date: Optional[str] = Field(default=None, examples=["2026-12-19"])
    campaign_appeal: str = Field(
        default=(
            "1. 제품 패키지 정면 노출 1컷 이상 필수\n"
            "2. 앰플 제형이 흐르는 영상/컷 1개 포함\n"
            "3. '피부 장벽 개선', '수분 광채' 키워드 삽입\n"
            "4. 맑은 자연광 및 과도한 필터/광고 전단지 배제\n"
            "5. 필수 해시태그 삽입 (#수분앰플 #클린뷰티)"
        ),
        examples=["1. 맑은 자연광 피부결 표현\n2. 과도한 필터 지양\n3. 제품 제형 컷 포함"],
    )
    brand_dna_id: Optional[int] = Field(default=None, examples=[1])


class CampaignUpdate(BaseModel):
    title: Optional[str] = None
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    product_image_url: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CampaignResponse(BaseModel):
    id: int
    user_id: int
    brand_dna_id: Optional[int] = None
    title: str
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    product_image_url: Optional[str] = None
    preferred_format: Optional[str] = "MIXED"
    status: Optional[str] = "READY"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_deleted: Optional[bool] = False
    deleted_at: Optional[datetime] = None
    campaign_appeal: str
    total_candidates: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InfluencerResultItem(BaseModel):
    id: int
    campaign_id: int
    instagram_id: str
    full_name: Optional[str] = None
    followers_count: int = 0
    posts_count: int = 0
    engagement_rate: float = 0.0
    influencer_tier: Optional[str] = None
    primary_format: Optional[str] = "FEED"
    recommended_fee: Optional[str] = None
    overall_match_percentage: int
    fit_status: str
    approval_state: str
    skin_type: str
    family_pet_exposure: str
    communication_authenticity: str
    one_line_verdict: Optional[str] = None
    rationale_bullets: List[str] = Field(default_factory=list)
    thumbnails: List[str] = Field(default_factory=list)
    track_stage_completed: Optional[str] = None

    class Config:
        from_attributes = True


class TokenUsageSummary(BaseModel):
    track1_gemini_calls: int
    track1_rejected_count: int
    track2_gpt4o_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_krw: float
    estimated_gpt4o_only_cost_krw: float
    cost_saving_percentage: float


class BatchUploadResponse(BaseModel):
    message: str
    campaign_id: int
    campaign_title: str
    total_uploaded: int
    cost_summary: TokenUsageSummary
    results: List[InfluencerResultItem]


class ApprovalStateUpdate(BaseModel):
    approval_state: Literal["PENDING", "APPROVED", "SKIPPED"]


class CompareCandidateItem(BaseModel):
    id: int
    campaign_id: int
    instagram_id: str
    full_name: Optional[str] = None
    followers_count: int = 0
    posts_count: int = 0
    engagement_rate: float = 0.0
    influencer_tier: Optional[str] = None
    primary_format: Optional[str] = "FEED"
    recommended_fee: Optional[str] = None
    overall_match_percentage: int
    fit_status: str
    approval_state: str
    skin_type: str
    family_pet_exposure: str
    communication_authenticity: str
    one_line_verdict: Optional[str] = None
    rationale_bullets: List[str] = Field(default_factory=list)
    media_analysis: List[dict] = Field(default_factory=list)
    thumbnails: List[str] = Field(default_factory=list)


class CompareResponse(BaseModel):
    campaign_id: int
    campaign_title: str
    compared_count: int
    candidates: List[CompareCandidateItem]


class DecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "PENDING"] = Field(..., examples=["APPROVED"])


class DecisionResponse(BaseModel):
    message: str
    result_id: int
    instagram_id: str
    approval_state: str
    campaign_id: int
    campaign_cumulative_cost_krw: float
    campaign_total_tokens: int
