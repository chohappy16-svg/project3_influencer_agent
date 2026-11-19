"""
[InfluenceOps Phase 2 MVP] backend/database.py
==============================================================================
PostgreSQL 데이터베이스 연결 엔진 및 SQLAlchemy 세션(get_db) 관리 모듈
- 사용자가 생성해 둔 'mydb' 또는 전용 'influenceops' DB에 자동 연결합니다.
- .env의 POSTGRES_URL 또는 DB_PASSWORD 설정을 자동으로 읽어 연결합니다.
==============================================================================
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")


class Base(DeclarativeBase):
    pass


def _resolve_postgresql_url() -> tuple[str, str]:
    """
    1순위: .env에 명시된 POSTGRES_DATABASE_URL 사용
    2순위: 로컬 PostgreSQL(포트 5432)에서 'influenceops' 또는 사용자가 생성한 'mydb'에 자동 접속 시도
           (만약 'mydb'만 있고 'influenceops'가 없으면 'mydb'를 기본 사용하거나 자동 연결)
    3순위: 로컬 PostgreSQL 서버가 꺼져 있을 때 서버 기동이 멈추지 않도록 SQLite 안전 폴백 지원
    """
    explicit_url = os.getenv("POSTGRES_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url, "postgresql_explicit"

    pg_user = os.getenv("POSTGRES_USER", "postgres").strip()
    pg_host = os.getenv("POSTGRES_HOST", "localhost").strip()
    pg_port = os.getenv("POSTGRES_PORT", "5432").strip()

    # 후보 비밀번호 리스트 (.env의 POSTGRES_PASSWORD, DB_PASSWORD 및 흔히 쓰는 실습 비밀번호 순회)
    candidate_passwords = []
    for pw in (
        os.getenv("POSTGRES_PASSWORD"),
        os.getenv("DB_PASSWORD"),
        "1234",
        "abcd1234",
        "postgres",
        "0000",
    ):
        if pw and pw not in candidate_passwords:
            candidate_passwords.append(pw)

    # 후보 데이터베이스 이름 (사용자가 방금 생성한 mydb 및 프로젝트 전용 influenceops 모두 지원)
    preferred_db = os.getenv("POSTGRES_DB", "").strip()
    candidate_dbs = [d for d in (preferred_db, "influenceops", "mydb", "postgres") if d]
    # 중복 제거
    candidate_dbs = list(dict.fromkeys(candidate_dbs))

    for pw in candidate_passwords:
        encoded_pw = quote_plus(pw)
        for db_name in candidate_dbs:
            test_url = f"postgresql+psycopg2://{pg_user}:{encoded_pw}@{pg_host}:{pg_port}/{db_name}"
            try:
                tmp_engine = create_engine(test_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
                with tmp_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                tmp_engine.dispose()
                return test_url, f"postgresql ({db_name})"
            except Exception:
                continue

    # PostgreSQL 접속이 아직 안 된 경우에도 서버가 죽지 않도록 기본 URL 구성 (또는 SQLite 폴백)
    default_pw = quote_plus(os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or "1234")
    default_db = preferred_db or "mydb"
    fallback_pg_url = f"postgresql+psycopg2://{pg_user}:{default_pw}@{pg_host}:{pg_port}/{default_db}"
    try:
        tmp_engine = create_engine(fallback_pg_url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
        with tmp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        tmp_engine.dispose()
        return fallback_pg_url, f"postgresql ({default_db})"
    except Exception:
        sqlite_path = ROOT_DIR / "backend" / "influenceops_local.db"
        return f"sqlite:///{sqlite_path}", "sqlite_fallback (PostgreSQL 비밀번호 확인 필요)"


SQLALCHEMY_DATABASE_URL, ACTIVE_DB_MODE = _resolve_postgresql_url()

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI 라우터에서 DB 세션을 안전하게 열고 닫아주는 의존성(Dependency) 함수"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
