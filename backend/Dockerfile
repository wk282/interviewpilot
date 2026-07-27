# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The default mirror is optimized for deployments in mainland China. It can
# be overridden at build time with --build-arg PIP_INDEX_URL=...
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install \
      --prefer-binary \
      --retries 5 \
      --timeout 120 \
      --index-url "${PIP_INDEX_URL}" \
      -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "run_server:app", "--host", "0.0.0.0", "--port", "8000"]
