# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG PIP_INDEX_URL="https://pypi.org/simple"
ARG PIP_EXTRA_INDEX_URL="https://pypi.org/simple"
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

COPY requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=60 \
    --index-url "$PIP_INDEX_URL" \
    --extra-index-url "$PIP_EXTRA_INDEX_URL" \
    -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "webhook_app:app", "--host", "0.0.0.0", "--port", "8000"]
