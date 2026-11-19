# 1. Base Image: Python 3.10 경량화 버전 사용
FROM python:3.10-slim

# 2. 필수 시스템 패키지 설치 (C 컴파일러 및 psycopg2 빌드 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 의존성 파일 복사 및 설치 (캐싱 활용)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# 5. 백엔드 소스코드 복사
COPY backend /app/backend

# 6. 작업 디렉토리를 backend 폴더로 이동 (main:app 실행 위치)
WORKDIR /app/backend

# 7. 서비스 포트 오픈
EXPOSE 8000

# 8. 컨테이너 시작 시 uvicorn 서버 구동
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
