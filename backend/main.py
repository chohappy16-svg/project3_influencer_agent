"""
[InfluenceOps] backend/main.py
==============================================================================
FastAPI 메인 서버 엔트리포인트 및 DB 초기화 스크립트

역할:
  1. 서버 시작 시 데이터베이스 5대 핵심 테이블 자동 점검 및 생성
  2. 스키마 확장에 따른 신규 컬럼 무중단 안전 마이그레이션 (ALTER TABLE)
  3. 프론트엔드(Vite) 연동을 위한 CORS 설정
  4. 도메인별 API 라우터 등록 (인증/브랜드DNA, 캠페인/분석)
==============================================================================
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

import models
from database import ACTIVE_DB_MODE, SQLALCHEMY_DATABASE_URL, engine, get_db
from routers import auth, campaigns

# 1. ORM 메타데이터 기반 기본 테이블 생성
models.Base.metadata.create_all(bind=engine)

# 2. 기존 DB와의 호환성을 위한 신규 컬럼 무중단 자동 추가 (안전 검사 후 반영)
try:
    _insp = inspect(engine)
    with engine.begin() as _conn:
        if "campaigns" in _insp.get_table_names():
            _camp_cols = [c["name"] for c in _insp.get_columns("campaigns")]
            if "preferred_format" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN preferred_format VARCHAR(30) DEFAULT 'MIXED'"))
            if "status" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN status VARCHAR(30) DEFAULT 'READY'"))
            if "start_date" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN start_date VARCHAR(20)"))
            if "end_date" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN end_date VARCHAR(20)"))
            if "is_deleted" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
            if "deleted_at" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN deleted_at TIMESTAMP"))
            if "product_url" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN product_url VARCHAR(500)"))
            if "product_image_url" not in _camp_cols:
                _conn.execute(text("ALTER TABLE campaigns ADD COLUMN product_image_url VARCHAR(500)"))
        if "influencer_results" in _insp.get_table_names():
            _res_cols = [c["name"] for c in _insp.get_columns("influencer_results")]
            if "primary_format" not in _res_cols:
                _conn.execute(text("ALTER TABLE influencer_results ADD COLUMN primary_format VARCHAR(30) DEFAULT 'FEED'"))
except Exception as _mig_err:
    print("DB 마이그레이션 확인 알림:", _mig_err)

app = FastAPI(
    title="InfluenceOps API",
    description="브랜드 인플루언서 섭외 의사결정 지원 SaaS 백엔드 API (스마트 매칭 검증 시스템)",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(campaigns.results_router)

# 2. React(Vite) 프론트엔드 연동을 위한 CORS 허용 (로컬 개발 및 EC2 공인 IP 원활한 접속 지원)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://16.178.177.137:5173",
    ],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    """기본 헬스체크 및 PostgreSQL 5대 테이블 생성 확인 엔드포인트"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    return {
        "status": "ok",
        "message": "InfluenceOps 백엔드 및 PostgreSQL 연결 완료!",
        "active_db_mode": ACTIVE_DB_MODE,
        "created_tables": table_names,
        "table_count": len(table_names),
    }


@app.get("/api/db-status")
def check_database_status(db: Session = Depends(get_db)):
    """PostgreSQL 연결 상태 및 5대 핵심 테이블(users, brand_dnas, campaigns, influencer_results, token_usages) 검증"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected_5 = ["users", "brand_dnas", "campaigns", "influencer_results", "token_usages"]
    missing = [t for t in expected_5 if t not in tables]

    return {
        "connected": True,
        "active_db_mode": ACTIVE_DB_MODE,
        "expected_5_tables": expected_5,
        "actual_tables_in_db": tables,
        "all_5_ready": len(missing) == 0,
        "missing_tables": missing,
    }
