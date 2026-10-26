#!/bin/bash
# FTSM-RAG 全栈启动器（host 模式：5 个进程直接跑在本机）
# 由 launchd / osascript 调用，避免 WorkBuddy 沙箱回收后台子进程。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
mkdir -p .runtime
STATE=".runtime/stack_state"

log()  { printf '[stack_up] %s\n' "$*"; }
fail() { printf '[stack_up] FAIL %s\n' "$*" >&2; echo "FAIL: $*" >"$STATE"; exit 1; }

# ── 1. 载入 .env，并翻译成 Java 侧期望的变量名 ────────────────────────────────
# 关键坑：Spring 只读**进程环境**，不读 .env；而 .env 用的是无前缀的 MYSQL_HOST。
# 此前脚本一个变量都不导出，Java 于是全部回落到 application.yml 的默认值
# （root/ftsm123456），在 .env 里改了密码也不生效——现象是"进程起来了但连不上库"，
# 日志里只有一行 connection refused。同理 FTSM_SESSION_SECRET / ADMIN_API_KEY
# 不导出的话，网关会用开发默认密钥、admin 路由直接 500。
[ -f .env ] || fail "缺少 .env（可从 .env.example 复制）"
set -a
# shellcheck disable=SC1091
. ./.env
set +a

export FTSM_MYSQL_HOST="${FTSM_MYSQL_HOST:-${MYSQL_HOST:-127.0.0.1}}"
export FTSM_MYSQL_PORT="${FTSM_MYSQL_PORT:-${MYSQL_PORT:-3306}}"
export FTSM_MYSQL_USER="${FTSM_MYSQL_USER:-${MYSQL_USER:-root}}"
export FTSM_MYSQL_PASSWORD="${FTSM_MYSQL_PASSWORD:-${MYSQL_PASSWORD:-}}"
export FTSM_RABBITMQ_HOST="${FTSM_RABBITMQ_HOST:-127.0.0.1}"
export FTSM_RABBITMQ_PORT="${FTSM_RABBITMQ_PORT:-5672}"
export FTSM_RABBITMQ_USER="${FTSM_RABBITMQ_USER:-guest}"
export FTSM_RABBITMQ_PASSWORD="${FTSM_RABBITMQ_PASSWORD:-guest}"
export FTSM_SESSION_SECRET="${FTSM_SESSION_SECRET:-dev-only-secret-change-me}"
export ADMIN_API_KEY="${ADMIN_API_KEY:-}"

[ "$FTSM_SESSION_SECRET" = "dev-only-secret-change-me" ] && \
  log "WARN FTSM_SESSION_SECRET 未设置，网关/用户服务使用开发默认密钥（演示可用，勿对外）"
[ -z "$ADMIN_API_KEY" ] && \
  log "WARN ADMIN_API_KEY 为空 —— /api/knowledge/update 会返回 500（爬虫/管理员刷新不可用）"

# 兼容 host 模式：.env 里 GOOGLE_APPLICATION_CREDENTIALS 指向容器内路径 /ftsm/.gcp/...
# 本机不存在该路径，需回落到仓库内的 .gcp/
if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  if [ -f "$ROOT/.gcp/application_default_credentials.json" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/.gcp/application_default_credentials.json"
    log "已把 GOOGLE_APPLICATION_CREDENTIALS 回落到 $ROOT/.gcp/application_default_credentials.json"
  fi
fi

# ── 2. 预检：缺件当场报错，而不是让用户干等 2 分钟后看到 PARTIAL ──────────────
for j in ftsm-user ftsm-conversation ftsm-knowledge ftsm-gateway; do
  [ -f "ftsm-java/$j/target/$j-0.1.0.jar" ] || \
    fail "缺少构建产物 ftsm-java/$j/target/$j-0.1.0.jar（先执行 mvn -f ftsm-java/pom.xml package -DskipTests）"
done
[ -x .venv/bin/python ] || fail "缺少 .venv（python3 -m venv .venv && .venv/bin/pip install -r requirements.txt）"

if ! command -v docker >/dev/null 2>&1; then
  log "WARN 未找到 docker —— 若本机没有 MySQL/RabbitMQ，Java 服务将启动失败"
elif ! docker info >/dev/null 2>&1; then
  log "WARN Docker 守护进程未运行 —— 无法启动 docker-compose 里的 MySQL/RabbitMQ"
fi

# MySQL 不可用 = 3 个 Java 服务起不来（Hikari 默认 fail-fast）；
# MQ 不可用只是降级（Python 侧会自动重连并在必要时退回本地训练线程）。
mysql_ok=0
if nc -z 127.0.0.1 "${FTSM_MYSQL_PORT}" 2>/dev/null; then mysql_ok=1; fi
mq_ok=0
if nc -z 127.0.0.1 "${FTSM_RABBITMQ_PORT}" 2>/dev/null; then mq_ok=1; fi
[ "$mysql_ok" -eq 0 ] && log "WARN MySQL ${FTSM_MYSQL_HOST}:${FTSM_MYSQL_PORT} 不可达 —— ftsm-user/conversation/knowledge 会启动失败"
[ "$mq_ok" -eq 0 ] && log "WARN RabbitMQ ${FTSM_RABBITMQ_HOST}:${FTSM_RABBITMQ_PORT} 不可达 —— 索引将退回本机训练线程（功能可用，质量看板无数据）"

RJ="$(/usr/libexec/java_home -v 17)/bin/java"
PY="$ROOT/.venv/bin/python"

# ── 3. 停掉上一轮实例 ─────────────────────────────────────────────────────────
pkill -f "ftsm-.*-0.1.0.jar" 2>/dev/null
pkill -f "uvicorn web_app:app" 2>/dev/null
sleep 1

# ── 4. 启动 5 个服务 ─────────────────────────────────────────────────────────
nohup "$RJ" -Xms64m -Xmx256m -jar ftsm-java/ftsm-user/target/ftsm-user-0.1.0.jar --server.port=8101 --server.address=127.0.0.1 > .runtime/user.log 2>&1 &
nohup "$RJ" -Xms64m -Xmx256m -jar ftsm-java/ftsm-conversation/target/ftsm-conversation-0.1.0.jar --server.port=8102 --server.address=127.0.0.1 > .runtime/conversation.log 2>&1 &
nohup "$RJ" -Xms64m -Xmx384m -jar ftsm-java/ftsm-knowledge/target/ftsm-knowledge-0.1.0.jar --server.port=8103 --server.address=127.0.0.1 > .runtime/knowledge.log 2>&1 &
nohup "$RJ" -Xms64m -Xmx256m -jar ftsm-java/ftsm-gateway/target/ftsm-gateway-0.1.0.jar --server.port=8080 --server.address=127.0.0.1 > .runtime/gateway.log 2>&1 &
FTSM_MQ_ENABLED=1 nohup "$PY" -m uvicorn web_app:app --host 127.0.0.1 --port 8104 > .runtime/rag.log 2>&1 &

# ── 5. 就绪探测：按服务打真实路由，并打印 HTTP 码 ─────────────────────────────
# 此前一律 curl "http://127.0.0.1:$p/"，靠退出码判断"端口开着"。这既看不出
# 哪个服务没起来，也区分不了 404（路由不存在）和 200（真的可用）。
probe() { # <名称> <端口> <路径>
  local code
  code=$(curl -s --noproxy 127.0.0.1 -o /dev/null -w '%{http_code}' -m 3 \
         "http://127.0.0.1:$2$3" 2>/dev/null)
  printf '  %-14s :%s  %-28s -> %s\n' "$1" "$2" "$3" "${code:-000}"
  [ -n "$code" ] && [ "$code" != "000" ]
}

for _ in $(seq 1 30); do
  ok=0
  for spec in "user 8101 /api/auth/me" \
              "conversation 8102 /api/conversations" \
              "knowledge 8103 /api/knowledge/stats" \
              "rag 8104 /api/kb/stats" \
              "gateway 8080 /api/kb/stats"; do
    # shellcheck disable=SC2086
    set -- $spec
    probe "$1" "$2" "$3" >/dev/null 2>&1 && ok=$((ok + 1))
  done
  [ "$ok" -eq 5 ] && break
  sleep 4
done

log "就绪探测结果（HTTP 非 000 即视为该进程在服务请求）："
ready=0
for spec in "user 8101 /api/auth/me:401" \
            "conversation 8102 /api/conversations:401" \
            "knowledge 8103 /api/knowledge/stats:200" \
            "rag 8104 /api/kb/stats:200" \
            "gateway 8080 /api/kb/stats:200"; do
  svc_path="${spec%%:*}"; want="${spec##*:}"
  # shellcheck disable=SC2086
  set -- $svc_path
  out=$(probe "$1" "$2" "$3")
  echo "$out"
  code=$(printf '%s' "$out" | sed -n 's/.*-> //p')
  [ "$code" = "$want" ] && ready=$((ready + 1))
done

if [ "$ready" -eq 5 ]; then
  echo "ALL_UP" >"$STATE"
  log "全部 5 个服务就绪（期望 HTTP 码均匹配）"
  # 顺手把 RAG 的真实状态打出来：精排是否生效一眼可见（欠费/未装模型时会 active=false）
  stats=$(curl -s --noproxy 127.0.0.1 -m 5 "http://127.0.0.1:8104/api/kb/stats" 2>/dev/null)
  [ -n "$stats" ] && log "RAG 状态: $stats"
  exit 0
fi

echo "PARTIAL ready=$ready/5" >"$STATE"
log "有服务未就绪（$ready/5）。排查顺序："
log "  1) .runtime/*.log 里的首个 ERROR/Caused by"
log "  2) MySQL 是否可达（Java 服务 fail-fast）"
log "  3) 是否已 mvn package 出 jar"
exit 1
