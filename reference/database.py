# =====================================================================
# [1105 2교시 필기] database.py : SQLAlchemy 엔진(커넥션 풀 내장) 및 Session 관리
# =====================================================================
# ★ 수업 필기 오타 교정 포인트:
#   - `from sqlalchemy.orm import DeclrativeBase` -> `DeclarativeBase`
#   - `locallhost:3306/shop?charset=ut8mb4`       -> `localhost:3306/shop?charset=utf8mb4`
#   - `SessionalLocal = sessionmaker(...)`        -> `SessionLocal = sessionmaker(...)`
# =====================================================================

import os
import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 루트 폴더(.env)에서 DB 접속 정보 로드
ROOT_ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(ROOT_ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_NAME = os.getenv("DB_NAME", "shop")


def _build_engine():
    """
    MySQL 서버가 실행 중이면 `mysql+pymysql://...` 엔진(pool_size=5, max_overflow=10)을 생성하고,
    로컬 MySQL 접속이 안 될 때는 실습이 멈추지 않도록 SQLite 호환 엔진으로 자동 전환합니다.
    """
    candidate_passwords = [DB_PASSWORD, "1234", "abcd1234", "root", ""]
    seen = set()
    unique_candidates = [p for p in candidate_passwords if not (p in seen or seen.add(p))]

    for pw in unique_candidates:
        try:
            conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=pw,
                charset="utf8mb4",
                connect_timeout=2,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;")
                conn.commit()

            mysql_url = f"mysql+pymysql://{DB_USER}:{pw}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
            eng = create_engine(
                mysql_url,
                echo=True,          # 실제 실행되는 SQL 쿼리를 콘솔에 출력
                pool_size=5,        # 기본 커넥션 풀 크기 (5개)
                max_overflow=10,    # 풀 초과 시 추가로 생성 가능한 최대 연결 수 (+10개 = 최대 15개)
                pool_pre_ping=True, # 연결이 끊어졌는지 미리 확인(ping) 후 자동 재연결
            )
            return eng, mysql_url, "mysql+pymysql"
        except Exception:
            continue

    # 로컬 MySQL 미실행 시 SQLite 파일 DB로 자동 전환 (SQLAlchemy ORM 코드는 100% 동일하게 동작!)
    sqlite_path = os.path.join(os.path.dirname(__file__), "sqlalchemy_test.db")
    sqlite_url = f"sqlite:///{sqlite_path}"
    eng = create_engine(
        sqlite_url,
        echo=True,  # 실제 생성되는 SQL 로그 출력
        connect_args={"check_same_thread": False},
    )
    return eng, sqlite_url, "sqlite (ORM 호환 모드)"


# 1. Engine 생성 (내부적으로 커넥션 풀 관리)
engine, DATABASE_URL, ACTIVE_ORM_ENGINE = _build_engine()

# 2. 세션 팩토리 생성 (매 요청마다 동일한 설정으로 Session 객체를 찍어내는 공장)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# 3. 모든 ORM 모델이 상속받을 기본 클래스 (SQLAlchemy 2.0 방식)
class Base(DeclarativeBase):
    pass


# 4. FastAPI Depends(get_db)용 의존성 주입 제너레이터 함수
def get_db():
    """
    [동작 순서]
    1) API 요청이 들어오면 db = SessionLocal()로 세션을 생성
    2) yield db에서 API 함수(예: get_users)에 세션을 전달하고 잠시 대기
    3) API 함수 실행이 끝나면 finally 블록으로 돌아와 db.close()로 세션을 닫음(풀에 반납)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

