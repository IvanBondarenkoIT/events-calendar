FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    TZ=Asia/Tbilisi \
    IDEMPOTENCY_PATH=/app/data/alert_state.json

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
  && ln -snf /usr/share/zoneinfo/Asia/Tbilisi /etc/localtime \
  && echo Asia/Tbilisi > /etc/timezone \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY src /app/src
COPY data /app/data
COPY ["Nini calendar TG.txt", "/app/Nini calendar TG.txt"]
COPY *.xlsx /app/

RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "dec_calendar", "check-config"]
