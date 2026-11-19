# 1단계: 빌드 환경 (Node.js 18)
FROM node:18-alpine AS build

WORKDIR /app

# package.json 및 package-lock.json 복사 후 설치 (캐시 최적화)
COPY frontend/package*.json ./
RUN npm install

# 프론트엔드 소스코드 전체 복사 및 프로덕션 번들 빌드
COPY frontend/ ./
RUN npm run build

# 2단계: 프로덕션 서빙 환경 (Nginx 초경량 웹서버)
FROM nginx:alpine

# Vite 빌드 산출물(dist)을 Nginx 기본 서빙 경로로 복사
COPY --from=build /app/dist /usr/share/nginx/html

# SPA 라우팅(HTML5 History Mode)을 위한 Nginx 설정
RUN echo 'server { \
    listen 80; \
    server_name localhost; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html index.htm; \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
