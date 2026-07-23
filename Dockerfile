# Python image for report-aggregator API (default) and CLI (command override).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends diffutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Editable install keeps sources under /app/src so mappings/ resolve at /app/mappings.
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY mappings/ mappings/

RUN pip install --no-cache-dir -e ".[api]" \
    && mkdir -p /data/workspaces \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data/workspaces

USER appuser

ENV REPORT_AGGREGATOR_API_HOST=0.0.0.0 \
    REPORT_AGGREGATOR_API_PORT=8000 \
    REPORT_AGGREGATOR_WORKSPACE=/data/workspaces \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["report-aggregator-api"]
