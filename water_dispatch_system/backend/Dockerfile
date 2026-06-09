FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
RUN pip install --no-cache-dir --prefix=/install gunicorn==21.2.0

FROM python:3.11-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app/ ./app/
COPY config.yaml ./app/config.yaml

COPY gunicorn_conf.py .

RUN mkdir -p /app/frontend && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-c", "gunicorn_conf.py"]
