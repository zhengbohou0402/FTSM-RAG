#!/bin/bash
# FTSM-RAG stack in a single Docker container (host processes get reaped by
# the WorkBuddy sandbox, so everything runs inside Docker instead).
# - Base: eclipse-temurin:17-jre-jammy (JDK17 preinstalled) + python3.10 via apt
# - All 5 services run on 127.0.0.1 inside the container => gateway routes work as-is
# - MySQL/RabbitMQ reached via docker DNS on ftsm-rag_default network
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="ftsm-stack"
NET="ftsm-rag_default"

log() { echo "[stack-docker] $*"; }

docker rm -f "$NAME" >/dev/null 2>&1 || true

log "starting container"
docker run -d --name "$NAME" --network "$NET" \
  -p 8080:8080 -p 127.0.0.1:8101:8101 -p 127.0.0.1:8102:8102 -p 127.0.0.1:8103:8103 -p 127.0.0.1:8104:8104 \
  -v "$ROOT":/ftsm -w /ftsm \
  eclipse-temurin:17-jre-jammy sleep infinity

log "installing python (apt)"
docker exec "$NAME" bash -c "apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv curl >/dev/null 2>&1"

log "creating venv + installing python deps (tuna mirror)"
docker exec "$NAME" bash -c "python3 -m venv /opt/venv && /opt/venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn[standard] python-multipart Jinja2 PyYAML python-dotenv httpx dashscope langchain langchain-community langchain-core langchain-chroma langchain-text-splitters langgraph langchain-google-vertexai google-auth chromadb numpy rank-bm25 aio-pika pypdf requests beautifulsoup4 opencc-python-reimplemented pillow"

log "starting services"
# stale queue guard: if doc.index.request.queue was ever declared WITHOUT
# x-message-ttl (e.g. by an aio-pika consumer), Java's declaration with TTL
# fails with 406 PRECONDITION_FAILED. Delete it so Java re-declares first.
docker exec "$NAME" bash -c "curl -s -u guest:guest -X DELETE 'http://ftsm-rabbitmq:15672/api/queues/%2F/doc.index.request.queue' -o /dev/null" || true
docker exec -d "$NAME" bash -c '
  export FTSM_MYSQL_HOST=ftsm-mysql FTSM_RABBITMQ_HOST=ftsm-rabbitmq
  export FTSM_RABBITMQ_URL=amqp://guest:guest@ftsm-rabbitmq:5672/ FTSM_MQ_ENABLED=1
  export PATH=/opt/venv/bin:$PATH
  cd /ftsm
  java -Xms64m -Xmx256m -jar ftsm-java/ftsm-user/target/ftsm-user-0.1.0.jar --server.port=8101 > /ftsm/.runtime/c-user.log 2>&1 &
  java -Xms64m -Xmx256m -jar ftsm-java/ftsm-conversation/target/ftsm-conversation-0.1.0.jar --server.port=8102 > /ftsm/.runtime/c-conversation.log 2>&1 &
  java -Xms64m -Xmx384m -jar ftsm-java/ftsm-knowledge/target/ftsm-knowledge-0.1.0.jar --server.port=8103 > /ftsm/.runtime/c-knowledge.log 2>&1 &
  java -Xms64m -Xmx256m -jar ftsm-java/ftsm-gateway/target/ftsm-gateway-0.1.0.jar --server.port=8080 > /ftsm/.runtime/c-gateway.log 2>&1 &
  uvicorn web_app:app --host 0.0.0.0 --port 8104 > /ftsm/.runtime/c-rag.log 2>&1 &
  wait'

log "probing readiness (up to 150s)"
for i in $(seq 1 30); do
  ok=0
  for p in 8101 8102 8103 8104 8080; do
    curl -s --noproxy 127.0.0.1 -o /dev/null -m 2 "http://127.0.0.1:$p/" && ok=$((ok+1))
  done
  [ "$ok" -eq 5 ] && log "ALL_UP" && echo ALL_UP > "$ROOT/.runtime/stack_state" && exit 0
  sleep 5
done
echo "PARTIAL ok=$ok" > "$ROOT/.runtime/stack_state"
log "TIMEOUT ok=$ok"
exit 1
