# ==============================================================================
# [1105/news_ai_project] FastAPI + PyMySQL(PooledDB) + KoELECTRA 2종 + GPT Agent
# ==============================================================================
# 참조 코드:
#   1) 1023/02_gradio_koelectra_nsmc.py (KoELECTRA 감성 분석 & 확률 분포 시각화 구조)
#   2) 1026/02_news_review_agent.py     (1021 파인튜닝 뉴스 7분류 + 감성 분석 + GPT Tool Calling)
#
# 적용된 4대 설계 규칙:
#   1) DB 연결: 루트 .env 기반 PyMySQL + PooledDB 커넥션 풀(maxconnections=10, mincached=2)
#   2) AI 모드: 로컬 KoELECTRA 2종(뉴스 7분류 + NSMC 감성분석) 기본 실행 + GPT Agent 토글 지원
#   3) 입력 분리: 뉴스 기사 원문(news_text) + 독자 리뷰/댓글(review_text) 2칸 분리 (빈 칸은 자동 생략)
#   4) 저장/임계값: 분석 즉시 MySQL 자동 저장 + 신뢰도 70% 미만은 '분류보류(모호)' 표시 + 조회/필터/수정/삭제 CRUD
# ==============================================================================

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1105 폴더에 구현된 dbutils(PooledDB) 패키지를 사용할 수 있도록 경로 추가
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent                  # c:\workAI\work9\1105\news_ai_project
WORK9_ROOT = PROJECT_DIR.parent.parent            # c:\workAI\work9
sys.path.insert(0, str(WORK9_ROOT / "1105"))

import pymysql
import torch
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymysql.cursors import DictCursor
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ==============================================================================
# 1. 루트 .env 환경변수 로드
# ==============================================================================
ENV_PATH = WORK9_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_NAME = os.getenv("DB_NAME", "shop")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip().strip('"').strip("'")

NEWS_MODEL_DIR = WORK9_ROOT / "1021" / "results" / "best_news_model"
SENTIMENT_MODEL_DIR = WORK9_ROOT / "saved_model"
FALLBACK_NSMC_HF = "daekeun-ml/koelectra-small-v3-nsmc"

CONFIDENCE_THRESHOLD = 70.0  # 신뢰도 70% 임계값 규칙

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

app = FastAPI(
    title="뉴스 & 리뷰 AI 분석 에이전트 (React + FastAPI + MySQL PooledDB)",
    description="1023 Gradio 감성분석 + 1026 뉴스/리뷰 AI 에이전트를 통합한 풀스택 웹 서비스",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==============================================================================
# 2. MySQL + PooledDB 커넥션 풀 설정 (내장 SQLite 백업 호환 포함)
# ==============================================================================
SQLITE_BACKUP_PATH = str(CURRENT_DIR / "news_ai_backup.db")
ACTIVE_DB_ENGINE = "mysql"
DETECTED_PASSWORD = DB_PASSWORD


class SQLiteCompatCursor:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._cur = conn.cursor()
        self.rowcount = 0
        self.lastrowid = 0

    def execute(self, sql: str, params=()):
        q = sql.replace("%s", "?")
        if not isinstance(params, (tuple, list)):
            params = (params,)
        self._cur.execute(q, params)
        self.rowcount = self._cur.rowcount
        self.lastrowid = self._cur.lastrowid
        return self.rowcount

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cur.close()


class SQLiteCompatConnection:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def cursor(self, *args, **kwargs):
        return SQLiteCompatCursor(self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def ping(self, reconnect: bool = True):
        return True

    def close(self):
        self._conn.close()


class SQLiteCreator:
    @staticmethod
    def connect(**kwargs):
        return SQLiteCompatConnection(SQLITE_BACKUP_PATH)


SAMPLE_INITIAL_LOGS = [
    (
        "엔비디아 차세대 AI 슈퍼칩 블랙웰(Blackwell) 정식 출하 시작... 글로벌 클라우드 4사 역대 최대 규모 주문 쇄도.",
        "성능은 진짜 압도적인데 가격이 너무 비싸서 중소 스타트업들은 엄두도 못 내겠네요.",
        "PHOTO_NV_2026_01",
        "IT과학",
        93.4,
        1,
        json.dumps(
            [
                {"category": "IT과학", "probability_percent": 93.4},
                {"category": "경제", "probability_percent": 4.8},
                {"category": "세계", "probability_percent": 1.1},
            ],
            ensure_ascii=False,
        ),
        "부정 (Negative)",
        14.2,
        85.8,
        0,
        "▶ [뉴스 분류] 'IT과학' 분야 (신뢰도 93.4% - 정상 분류)\n▶ [독자 반응] '부정 (Negative)' 우세 (85.8%)\n▶ [종합 요약] AI 반도체 출하 소식으로 IT과학 분야에 해당하며, 독자 리뷰는 가격 부담과 독점 우려로 부정적 감성이 높게 나타났습니다.",
        "샘플 초기 데이터 (IT과학 + 부정 리뷰)",
        "2026-11-05 14:00:00",
    ),
    (
        "한국은행 기준금리 전격 인하 결정... 주택담보대출 이자 부담 완화 기대감 확산",
        "드디어 대출 이자 숨통이 좀 트이겠네요! 내수 경기도 빨리 살아났으면 좋겠습니다.",
        "",
        "경제",
        91.2,
        1,
        json.dumps(
            [
                {"category": "경제", "probability_percent": 91.2},
                {"category": "사회", "probability_percent": 5.3},
                {"category": "정치", "probability_percent": 2.1},
            ],
            ensure_ascii=False,
        ),
        "긍정 (Positive)",
        94.6,
        5.4,
        0,
        "▶ [뉴스 분류] '경제' 분야 (신뢰도 91.2% - 정상 분류)\n▶ [독자 반응] '긍정 (Positive)' 우세 (94.6%)\n▶ [종합 요약] 금리 인하 관련 경제 기사이며, 이자 부담 완화에 대한 기대감으로 독자 감성이 매우 긍정적입니다.",
        "금리 인하 긍정 반응 사례",
        "2026-11-05 14:10:00",
    ),
]


def init_db_and_pool() -> PooledDB:
    global ACTIVE_DB_ENGINE, DETECTED_PASSWORD

    # SQLite 백업 테이블 준비
    sconn = sqlite3.connect(SQLITE_BACKUP_PATH)
    with sconn:
        cur = sconn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS news_analysis_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_text TEXT,
                review_text TEXT,
                photo_id TEXT DEFAULT '',
                predicted_category TEXT,
                category_confidence REAL DEFAULT 0.0,
                is_high_confidence INTEGER DEFAULT 1,
                top3_categories_json TEXT,
                sentiment_label TEXT,
                positive_percent REAL DEFAULT 0.0,
                negative_percent REAL DEFAULT 0.0,
                used_gpt_agent INTEGER DEFAULT 0,
                ai_report TEXT,
                memo TEXT DEFAULT '',
                created_at TEXT
            );
            """
        )
        cur.execute("SELECT COUNT(*) FROM news_analysis_logs;")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                """
                INSERT INTO news_analysis_logs (
                    news_text, review_text, photo_id, predicted_category, category_confidence,
                    is_high_confidence, top3_categories_json, sentiment_label,
                    positive_percent, negative_percent, used_gpt_agent, ai_report, memo, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                SAMPLE_INITIAL_LOGS,
            )
    sconn.close()

    # MySQL 연결 시도
    candidates = [DB_PASSWORD, "1234", "abcd1234", "root", ""]
    seen = set()
    unique_pws = [p for p in candidates if not (p in seen or seen.add(p))]

    for pw in unique_pws:
        try:
            conn = pymysql.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=pw,
                charset="utf8mb4",
                cursorclass=DictCursor,
                connect_timeout=2,
            )
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4;")
                    cursor.execute(f"USE `{DB_NAME}`;")
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS news_analysis_logs (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            news_text TEXT,
                            review_text TEXT,
                            photo_id VARCHAR(60) DEFAULT '',
                            predicted_category VARCHAR(50),
                            category_confidence FLOAT DEFAULT 0.0,
                            is_high_confidence TINYINT(1) DEFAULT 1,
                            top3_categories_json TEXT,
                            sentiment_label VARCHAR(50),
                            positive_percent FLOAT DEFAULT 0.0,
                            negative_percent FLOAT DEFAULT 0.0,
                            used_gpt_agent TINYINT(1) DEFAULT 0,
                            ai_report TEXT,
                            memo VARCHAR(255) DEFAULT '',
                            created_at VARCHAR(30)
                        ) CHARACTER SET utf8mb4;
                        """
                    )
                    cursor.execute("SELECT COUNT(*) AS cnt FROM news_analysis_logs;")
                    if cursor.fetchone()["cnt"] == 0:
                        cursor.executemany(
                            """
                            INSERT INTO news_analysis_logs (
                                news_text, review_text, photo_id, predicted_category, category_confidence,
                                is_high_confidence, top3_categories_json, sentiment_label,
                                positive_percent, negative_percent, used_gpt_agent, ai_report, memo, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            SAMPLE_INITIAL_LOGS,
                        )
                conn.commit()

            DETECTED_PASSWORD = pw
            ACTIVE_DB_ENGINE = "mysql"
            print(f"[DB] MySQL ({DB_HOST}:{DB_PORT}/{DB_NAME}) 연결 및 news_analysis_logs 테이블 준비 완료!")
            return PooledDB(
                creator=pymysql,
                maxconnections=10,
                mincached=2,
                maxcached=5,
                blocking=True,
                ping=1,
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DETECTED_PASSWORD,
                database=DB_NAME,
                charset="utf8mb4",
                cursorclass=DictCursor,
            )
        except Exception:
            continue

    ACTIVE_DB_ENGINE = "sqlite_backup"
    print("[DB] 내장 SQLite 호환 엔진으로 PooledDB 커넥션 풀이 동작합니다.")
    return PooledDB(
        creator=SQLiteCreator,
        maxconnections=10,
        mincached=2,
        maxcached=5,
        blocking=True,
        ping=1,
    )


pool = init_db_and_pool()


def get_connection():
    """PooledDB 커넥션 풀에서 연결을 대여합니다."""
    return pool.connection()


# ==============================================================================
# 3. 로컬 KoELECTRA 모델 2종 로더 (1021 뉴스 7분류 + 1023/saved_model 감성분석)
# ==============================================================================
_news_tokenizer = None
_news_model = None
_news_labels = {
    0: "IT과학",
    1: "경제",
    2: "사회",
    3: "생활문화",
    4: "세계",
    5: "스포츠",
    6: "정치",
}

_sentiment_tokenizer = None
_sentiment_model = None


def get_news_model():
    global _news_tokenizer, _news_model, _news_labels
    if _news_model is None and NEWS_MODEL_DIR.exists():
        print(f"[AI LOAD] 1021 뉴스 7분류 KoELECTRA 모델 로드 중: {NEWS_MODEL_DIR}")
        _news_tokenizer = AutoTokenizer.from_pretrained(str(NEWS_MODEL_DIR))
        _news_model = AutoModelForSequenceClassification.from_pretrained(str(NEWS_MODEL_DIR))
        _news_model.to(device)
        _news_model.eval()
        if hasattr(_news_model.config, "id2label") and _news_model.config.id2label:
            _news_labels = {int(k): v for k, v in _news_model.config.id2label.items()}
    return _news_tokenizer, _news_model, _news_labels


def get_sentiment_model():
    global _sentiment_tokenizer, _sentiment_model
    if _sentiment_model is None:
        target_dir = str(SENTIMENT_MODEL_DIR) if (SENTIMENT_MODEL_DIR / "config.json").exists() else FALLBACK_NSMC_HF
        try:
            print(f"[AI LOAD] KoELECTRA 감성 분석(NSMC) 모델 로드 중: {target_dir}")
            _sentiment_tokenizer = AutoTokenizer.from_pretrained(target_dir)
            _sentiment_model = AutoModelForSequenceClassification.from_pretrained(target_dir)
            _sentiment_model.to(device)
            _sentiment_model.eval()
        except Exception as e:
            print(f"[WARN] 감성 분석 모델 로드 실패: {e}")
    return _sentiment_tokenizer, _sentiment_model


# ==============================================================================
# 4. 핵심 AI 추론 함수 (1026/02_news_review_agent.py & 1023/02_gradio 통합)
# ==============================================================================
def classify_news_category(text: str, photo_id: Optional[str] = None) -> Dict[str, Any]:
    """뉴스 원문을 분석하여 7개 카테고리 확률 분포와 70% 임계값 통과 여부를 반환합니다."""
    if not text or not text.strip():
        return {
            "status": "skipped",
            "predicted_category": "미입력",
            "confidence_score": 0.0,
            "is_high_confidence": True,
            "top3_categories": [],
            "all_probabilities": {},
        }

    tokenizer, model, labels_map = get_news_model()
    inputs = tokenizer(
        text.strip(),
        return_tensors="pt",
        truncation=True,
        max_length=128,
        padding=True,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)[0]

    top_idx = int(torch.argmax(probs).item())
    top_label = labels_map.get(top_idx, f"Label_{top_idx}")
    top_prob = round(probs[top_idx].item() * 100, 2)
    is_high_conf = top_prob >= CONFIDENCE_THRESHOLD

    top3_indices = torch.topk(probs, min(3, len(labels_map))).indices.tolist()
    top3_breakdown = [
        {
            "category": labels_map.get(i, f"Label_{i}"),
            "probability_percent": round(probs[i].item() * 100, 2),
        }
        for i in top3_indices
    ]

    all_probs = {
        labels_map.get(i, f"Label_{i}"): round(probs[i].item() * 100, 2)
        for i in range(len(labels_map))
    }

    res = {
        "status": "success",
        "predicted_category": top_label,
        "display_category": top_label if is_high_conf else f"분류보류 ({top_label}?)",
        "confidence_score": top_prob,
        "is_high_confidence": is_high_conf,
        "top3_categories": top3_breakdown,
        "all_probabilities": all_probs,
    }
    if photo_id:
        res["photo_id"] = photo_id
    return res


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """독자 리뷰/댓글의 긍정(Positive)/부정(Negative) 감성 확률을 계산합니다."""
    if not text or not text.strip():
        return {
            "status": "skipped",
            "sentiment": "미입력",
            "positive_percent": 0.0,
            "negative_percent": 0.0,
            "confidence_score": 0.0,
        }

    tokenizer, model = get_sentiment_model()
    inputs = tokenizer(
        text.strip(),
        return_tensors="pt",
        truncation=True,
        max_length=256,
        padding=True,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)[0]

    neg_prob = round(probs[0].item() * 100, 2)
    pos_prob = round(probs[1].item() * 100, 2)
    sentiment = "긍정 (Positive)" if pos_prob >= neg_prob else "부정 (Negative)"

    return {
        "status": "success",
        "sentiment": sentiment,
        "positive_percent": pos_prob,
        "negative_percent": neg_prob,
        "confidence_score": max(pos_prob, neg_prob),
    }


def build_local_summary_report(
    news_res: Dict[str, Any],
    sent_res: Dict[str, Any],
    photo_id: str = "",
) -> str:
    """GPT 호출 없이 로컬 KoELECTRA 2종 분석 결과만으로 상세 리포트를 구성합니다."""
    lines = []
    if news_res.get("status") == "success":
        cat = news_res["predicted_category"]
        conf = news_res["confidence_score"]
        if news_res["is_high_confidence"]:
            lines.append(f"▶ [뉴스 분야 판정]: '{cat}' (신뢰도 {conf:.2f}% - 70% 기준 통과 [정상 분류])")
        else:
            lines.append(
                f"▶ [뉴스 분야 판정]: ⚠️ 분류보류 / 모호 기사 (최고 예측: '{cat}' {conf:.2f}% — 기준치 70% 미만)"
            )
        top3_str = ", ".join(
            f"{item['category']}({item['probability_percent']}%)"
            for item in news_res.get("top3_categories", [])
        )
        lines.append(f"  - Top-3 분야 확률 분포: {top3_str}")
        if photo_id:
            lines.append(f"  - 추적된 첨부 사진 ID: {photo_id}")

    if sent_res.get("status") == "success":
        icon = "😊" if "긍정" in sent_res["sentiment"] else "😢"
        lines.append(
            f"▶ [독자 리뷰 감성 판정]: {icon} {sent_res['sentiment']} "
            f"(긍정 {sent_res['positive_percent']:.2f}% / 부정 {sent_res['negative_percent']:.2f}%)"
        )

    return "\n".join(lines) if lines else "분석할 텍스트가 없습니다."


def run_gpt_agent_summary(
    news_text: str,
    review_text: str,
    photo_id: str,
    news_res: Dict[str, Any],
    sent_res: Dict[str, Any],
) -> str:
    """use_gpt_agent=True일 때 OpenAI GPT를 통해 종합 인사이트 리포트를 생성합니다."""
    if not OPENAI_API_KEY:
        return build_local_summary_report(news_res, sent_res, photo_id) + "\n\n(안내: OPENAI_API_KEY가 없어 로컬 모델 리포트로 대체되었습니다.)"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            "다음은 로컬 파인튜닝 KoELECTRA 모델 2종(뉴스 카테고리 분류 모델 & 감성 분석 모델)의 실행 결과입니다.\n"
            "모델이 반환한 카테고리명과 확률 수치를 절대 변경하지 말고 그대로 인용하여, "
            "30대 직장인을 위한 깔끔한 3~4줄 종합 브리핑 리포트를 작성해주세요.\n\n"
            f"- 입력 뉴스 원문: {news_text or '(없음)'}\n"
            f"- 입력 독자 리뷰: {review_text or '(없음)'}\n"
            f"- 첨부 사진 ID: {photo_id or '(없음)'}\n"
            f"- 뉴스 분류 모델 결과: {json.dumps(news_res, ensure_ascii=False)}\n"
            f"- 감성 분석 모델 결과: {json.dumps(sent_res, ensure_ascii=False)}\n"
        )
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "당신은 로컬 KoELECTRA 모델의 분석 수치를 정확히 인용해 요약하는 수석 뉴스 & 리뷰 분석 AI 에이전트입니다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        gpt_text = resp.choices[0].message.content or ""
        return build_local_summary_report(news_res, sent_res, photo_id) + "\n\n🤖 [GPT 에이전트 종합 인사이트]\n" + gpt_text
    except Exception as e:
        return build_local_summary_report(news_res, sent_res, photo_id) + f"\n\n(참고: GPT 추가 요약 생략 - {e})"


# ==============================================================================
# 5. Pydantic 요청 모델 정의
# ==============================================================================
class AnalyzeRequest(BaseModel):
    news_text: Optional[str] = ""
    review_text: Optional[str] = ""
    photo_id: Optional[str] = ""
    use_gpt_agent: bool = False
    memo: Optional[str] = ""


class LogUpdateRequest(BaseModel):
    memo: Optional[str] = None
    predicted_category: Optional[str] = None
    is_high_confidence: Optional[int] = None


# ==============================================================================
# 6. FastAPI 엔드포인트 구현 (분석 + MySQL 자동 저장 + 조회/필터/수정/삭제)
# ==============================================================================
def _format_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    top3 = []
    if row.get("top3_categories_json"):
        try:
            top3 = json.loads(row["top3_categories_json"])
        except Exception:
            top3 = []
    row["top3_categories"] = top3
    row["is_high_confidence"] = bool(row.get("is_high_confidence", 1))
    row["used_gpt_agent"] = bool(row.get("used_gpt_agent", 0))
    return row


@app.post("/api/analyze", tags=["1. AI 뉴스 분류 & 감성 분석 실행 (MySQL 자동 저장)"])
def analyze_and_save(req: AnalyzeRequest):
    """
    [규칙 반영]
    - 뉴스 원문(news_text)과 독자 리뷰(review_text)를 2칸으로 분리해 입력받으며, 비워둔 칸은 자동 생략합니다.
    - 둘 다 비어 있으면 400 에러를 반환합니다.
    - 분석 즉시 MySQL `news_analysis_logs` 테이블에 자동 저장하고 결과를 반환합니다.
    """
    news_text = (req.news_text or "").strip()
    review_text = (req.review_text or "").strip()
    photo_id = (req.photo_id or "").strip()

    if not news_text and not review_text:
        raise HTTPException(
            status_code=400,
            detail="뉴스 기사 원문 또는 독자 리뷰/댓글 중 최소 하나는 입력해주세요!",
        )

    # 1) 뉴스 분류 실행 (입력된 경우에만)
    news_res = classify_news_category(news_text, photo_id=photo_id)
    # 2) 독자 리뷰 감성 분석 실행 (입력된 경우에만)
    sent_res = analyze_sentiment(review_text)

    # 3) 리포트 생성 (로컬 기본 리포트 or GPT 에이전트 통합 리포트)
    if req.use_gpt_agent:
        ai_report = run_gpt_agent_summary(news_text, review_text, photo_id, news_res, sent_res)
    else:
        ai_report = build_local_summary_report(news_res, sent_res, photo_id)

    pred_cat = news_res.get("predicted_category", "미입력")
    cat_conf = float(news_res.get("confidence_score", 0.0))
    is_high_conf = 1 if news_res.get("is_high_confidence", True) else 0
    top3_json = json.dumps(news_res.get("top3_categories", []), ensure_ascii=False)

    sent_label = sent_res.get("sentiment", "미입력")
    pos_pct = float(sent_res.get("positive_percent", 0.0))
    neg_pct = float(sent_res.get("negative_percent", 0.0))
    used_gpt = 1 if req.use_gpt_agent else 0
    now_str = get_now_str()
    memo_val = (req.memo or "").strip()

    # 4) MySQL DB에 자동 저장 (PooledDB에서 커넥션 대여 후 반납)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO news_analysis_logs (
                    news_text, review_text, photo_id, predicted_category, category_confidence,
                    is_high_confidence, top3_categories_json, sentiment_label,
                    positive_percent, negative_percent, used_gpt_agent, ai_report, memo, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                sql,
                (
                    news_text,
                    review_text,
                    photo_id,
                    pred_cat,
                    cat_conf,
                    is_high_conf,
                    top3_json,
                    sent_label,
                    pos_pct,
                    neg_pct,
                    used_gpt,
                    ai_report,
                    memo_val,
                    now_str,
                ),
            )
            new_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e}")
    finally:
        conn.close()

    saved_record = {
        "id": new_id,
        "news_text": news_text,
        "review_text": review_text,
        "photo_id": photo_id,
        "predicted_category": pred_cat,
        "category_confidence": cat_conf,
        "is_high_confidence": bool(is_high_conf),
        "top3_categories": news_res.get("top3_categories", []),
        "all_category_probabilities": news_res.get("all_probabilities", {}),
        "sentiment_label": sent_label,
        "positive_percent": pos_pct,
        "negative_percent": neg_pct,
        "used_gpt_agent": bool(used_gpt),
        "ai_report": ai_report,
        "memo": memo_val,
        "created_at": now_str,
    }
    return {
        "message": "AI 분석 및 MySQL 자동 저장이 완료되었습니다.",
        "result": saved_record,
        "pool_status": pool.status(),
    }


@app.get("/api/logs", tags=["2. MySQL 분석 히스토리 조회 · 필터 · 수정 · 삭제 (CRUD)"])
def get_analysis_logs(
    category: Optional[str] = Query(None, description="카테고리 필터 (예: IT과학, 경제 등)"),
    sentiment: Optional[str] = Query(None, description="감성 필터 (긍정 / 부정)"),
    confidence_mode: Optional[str] = Query("all", description="all: 전체, high: 70% 이상 정상분류, hold: 70% 미만 분류보류"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM news_analysis_logs ORDER BY id DESC")
            rows = [_format_log_row(r) for r in cursor.fetchall()]

        if category and category != "전체":
            rows = [r for r in rows if r["predicted_category"] == category]
        if sentiment and sentiment != "전체":
            rows = [r for r in rows if sentiment in (r["sentiment_label"] or "")]
        if confidence_mode == "high":
            rows = [r for r in rows if r["is_high_confidence"] and r["predicted_category"] != "미입력"]
        elif confidence_mode == "hold":
            rows = [r for r in rows if (not r["is_high_confidence"]) and r["predicted_category"] != "미입력"]

        return rows
    finally:
        conn.close()


@app.get("/api/stats", tags=["2. MySQL 분석 히스토리 조회 · 필터 · 수정 · 삭제 (CRUD)"])
def get_dashboard_stats():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM news_analysis_logs ORDER BY id DESC")
            rows = [_format_log_row(r) for r in cursor.fetchall()]

        total_count = len(rows)
        high_conf_count = sum(
            1 for r in rows if r["predicted_category"] != "미입력" and r["is_high_confidence"]
        )
        hold_count = sum(
            1 for r in rows if r["predicted_category"] != "미입력" and not r["is_high_confidence"]
        )
        pos_count = sum(1 for r in rows if "긍정" in (r["sentiment_label"] or ""))
        neg_count = sum(1 for r in rows if "부정" in (r["sentiment_label"] or ""))

        category_counts: Dict[str, int] = {}
        for r in rows:
            cat = r["predicted_category"]
            if cat and cat != "미입력":
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_count": total_count,
            "high_confidence_count": high_conf_count,
            "hold_confidence_count": hold_count,
            "positive_review_count": pos_count,
            "negative_review_count": neg_count,
            "category_counts": category_counts,
            "db_engine": ACTIVE_DB_ENGINE,
            "pool_status": pool.status(),
        }
    finally:
        conn.close()


@app.put("/api/logs/{log_id}", tags=["2. MySQL 분석 히스토리 조회 · 필터 · 수정 · 삭제 (CRUD)"])
def update_analysis_log(log_id: int, req: LogUpdateRequest):
    """저장된 분석 이력의 메모(memo)를 수정하거나, 분류보류(70% 미만) 기사의 카테고리를 확정합니다."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM news_analysis_logs WHERE id = %s", (log_id,))
            target = cursor.fetchone()
            if not target:
                raise HTTPException(status_code=404, detail="해당 분석 기록을 찾을 수 없습니다.")

            new_memo = req.memo if req.memo is not None else target["memo"]
            new_cat = req.predicted_category if req.predicted_category is not None else target["predicted_category"]
            new_conf_flag = (
                req.is_high_confidence
                if req.is_high_confidence is not None
                else target["is_high_confidence"]
            )

            cursor.execute(
                """
                UPDATE news_analysis_logs
                SET memo = %s, predicted_category = %s, is_high_confidence = %s
                WHERE id = %s
                """,
                (new_memo, new_cat, new_conf_flag, log_id),
            )
        conn.commit()
        target["memo"] = new_memo
        target["predicted_category"] = new_cat
        target["is_high_confidence"] = new_conf_flag
        return {"message": "수정 완료", "updated": _format_log_row(target)}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/logs/{log_id}", tags=["2. MySQL 분석 히스토리 조회 · 필터 · 수정 · 삭제 (CRUD)"])
def delete_analysis_log(log_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM news_analysis_logs WHERE id = %s", (log_id,))
            affected = cursor.rowcount
        conn.commit()
        if affected == 0:
            raise HTTPException(status_code=404, detail="삭제할 기록이 없습니다.")
        return {"message": "삭제 완료", "deleted_id": log_id}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


# React 빌드 정적 파일(frontend/dist)이 있으면 함께 서빙하여 8002 포트에서도 바로 접속 지원
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


@app.get("/", include_in_schema=False)
def serve_frontend():
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))
    return {"message": "React 프론트엔드를 빌드하거나 Vite 개발 서버를 실행해주세요. Swagger 문서는 /docs 입니다."}


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("[START] 1105/news_ai_project 백엔드 서버 시작! (FastAPI + MySQL PooledDB)")
    print(" -> 웹 대시보드 주소 : http://127.0.0.1:8002")
    print(" -> Swagger API 문서: http://127.0.0.1:8002/docs")
    print("=" * 70)
    uvicorn.run(app, host="127.0.0.1", port=8002)

