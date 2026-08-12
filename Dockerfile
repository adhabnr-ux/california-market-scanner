FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MARKET_SCANNER_OUTPUT_DIR=/app/artifacts

RUN groupadd --system scanner \
    && useradd --system --gid scanner --create-home scanner

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY config/ ./config/
COPY src/ ./src/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

RUN mkdir -p /app/artifacts && chown scanner:scanner /app/artifacts
USER scanner

ENTRYPOINT ["market-scanner"]
CMD ["scan", "--provider", "alpaca", "--output-dir", "/app/artifacts"]
