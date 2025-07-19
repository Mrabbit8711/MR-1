FROM python:3.10-slim

WORKDIR /app

# 1) 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) 소스 코드 복사
COPY . .
RUN echo "=== /app 디렉터리 목록 시작 ===" && ls -R /app && echo "=== /app 디렉터리 목록 끝 ==="

# 3) 헬스체크용 포트 노출
EXPOSE 8080

# 4) 컨테이너 시작 명령
CMD ["python", "bot.py"]
