FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libgomp1 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
ARG INSTALL_MINERU=true
RUN if [ "$INSTALL_MINERU" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra pdf_ocr --extra pdf_mineru; \
    else \
        uv sync --frozen --no-dev --no-install-project --extra pdf_ocr; \
    fi

COPY app ./app
COPY src ./src
COPY scripts ./scripts
COPY langgraph.json ./langgraph.json
RUN uv pip install --no-deps -e . \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/.tmp \
    && chown -R appuser:appuser /app

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
