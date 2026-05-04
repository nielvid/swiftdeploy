FROM python:3.12-alpine

RUN adduser -D -u 1001 appuser

WORKDIR /app
COPY app/main.py .

RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

USER appuser

ENV APP_PORT=3000 \
    MODE=stable \
    APP_VERSION=1.0.0

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${APP_PORT}/healthz || exit 1

CMD ["python", "main.py"]
