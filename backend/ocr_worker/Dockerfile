# syntax=docker/dockerfile:1.7
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1

WORKDIR /app

COPY ocr_worker/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install \
      --prefer-binary \
      --retries 5 \
      --timeout 180 \
      --index-url "${PIP_INDEX_URL}" \
      -r requirements.txt

COPY ocr_worker ./ocr_worker

CMD ["celery", "-A", "ocr_worker.celery_app.celery_app", "worker", "--loglevel=info", "--concurrency=1", "-Q", "ocr"]
