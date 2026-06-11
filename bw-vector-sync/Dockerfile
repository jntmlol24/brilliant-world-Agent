# 多阶段构建：builder 编译 proto，slim runtime 仅含运行所需
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-dev

COPY proto/ ./proto/
RUN mkdir -p src/bw_vector_sync/proto_gen \
    && protoc --python_out=src/bw_vector_sync/proto_gen -I proto proto/*.proto \
    && touch src/bw_vector_sync/proto_gen/__init__.py \
    && find src/bw_vector_sync/proto_gen -name "*.py" -exec sed -i 's/^import dual_write_event_pb2/from . import dual_write_event_pb2/' {} \;

COPY src/ ./src/

# ---- runtime ----
FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /build/src ./src
COPY --from=builder /build/proto ./proto

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8080/health',timeout=2).status_code==200 else 1)"]

CMD ["python", "-m", "bw_vector_sync.main"]
