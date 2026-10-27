#!/usr/bin/env bash
#
# Paper Agent 本地启动脚本
#
#   ./start.sh                  启动 PostgreSQL、Redis、后端、解析/邮件 worker 与前端（首次安装并迁移）
#   ./start.sh --backend-only   启动后端服务及 PostgreSQL、Redis、解析/邮件 worker，不启动前端
#   ./start.sh --frontend-only  只启动前端（需后端已在别处运行）
#   ./start.sh --no-install     跳过 uv sync / pnpm install
#   ./start.sh --skip-db        不启动 PostgreSQL（使用已有数据库；后端仍启动本机 Redis）
#   ./start.sh --with-storage   同时启动对象存储（RustFS，S3 兼容）
#                               backend/.env 里 STORAGE_BACKEND=s3 时会自动启动
#
# 环境变量：BACKEND_PORT（默认 8000）、AGENT_SERVICE_PORT（默认 8001）、FRONTEND_PORT（默认 5173）、
#          BACKEND_HOST / AGENT_SERVICE_HOST / FRONTEND_HOST（默认 127.0.0.1）
#
# Ctrl-C 会同时停止前后端；日志同时写入 .var/logs/。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.var/logs"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
AGENT_SERVICE_HOST="${AGENT_SERVICE_HOST:-127.0.0.1}"
AGENT_SERVICE_PORT="${AGENT_SERVICE_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# 宿主机端口：compose 与 backend/.env 必须一致，否则会连到别的 checkout 的库。
# 载入仓库根 .env（若存在），它记录本工作树选定的端口与数据库地址。
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
STORAGE_PORT="${STORAGE_PORT:-9000}"
DATABASE_URL_DEFAULT="postgresql+psycopg://paper_agent:paper_agent_dev@127.0.0.1:${POSTGRES_PORT}/paper_agent"
TEST_DATABASE_URL_DEFAULT="postgresql+psycopg://paper_agent:paper_agent_dev@127.0.0.1:${POSTGRES_PORT}/paper_agent_test"
REDIS_URL_DEFAULT="redis://127.0.0.1:${REDIS_PORT}/0"

START_DB=1
START_BACKEND=1
START_FRONTEND=1
START_STORAGE=0
DO_INSTALL=1

BACKEND_PID=""
WORKER_PID=""
MAIL_WORKER_PID=""
AGENT_SERVICE_PID=""
FRONTEND_PID=""
TAIL_PIDS=()

# --- 输出 -------------------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"
  RED="$(printf '\033[31m')"; GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"; BLUE="$(printf '\033[34m')"; RESET="$(printf '\033[0m')"
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi

step() { printf '%s==>%s %s\n' "$BLUE" "$RESET" "$1"; }
ok()   { printf '%s  ✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '%s  !%s %s\n' "$YELLOW" "$RESET" "$1"; }
fail() { printf '%s  ✗%s %s\n' "$RED" "$RESET" "$1" >&2; }
die()  { fail "$1"; exit 1; }

usage() {
  sed -n '/^# Paper Agent 本地启动脚本/,/^# Ctrl-C/p' "${BASH_SOURCE[0]}" \
    | sed 's/^# \{0,1\}//'
}

# --- 参数 -------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-only)  START_FRONTEND=0 ;;
    --frontend-only) START_BACKEND=0; START_DB=0 ;;
    --no-install)    DO_INSTALL=0 ;;
    --skip-db)       START_DB=0 ;;
    --with-storage)   START_STORAGE=1 ;;
    -h|--help)       usage; exit 0 ;;
    *) die "未知参数：$1（使用 --help 查看用法）" ;;
  esac
  shift
done

# --- 清理 -------------------------------------------------------------------
# 递归终止进程树：pnpm/uv 会再派生 vite 与 uvicorn worker，只杀父进程不可靠。
kill_tree() {
  local pid="$1" sig="${2:-TERM}" child
  [[ -z "$pid" ]] && return 0
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child" "$sig"
  done
  kill "-$sig" "$pid" 2>/dev/null || true
}

cleanup() {
  local exit_status=$?
  trap - INT TERM EXIT
  echo
  step "正在停止服务…"
  for pid in "${TAIL_PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  # 注：bash 仍可能打印 "Terminated: 15" 作业提示，这是 shell 行为；
  # 曾尝试用 disown 消除，但会让脚本收不到 Ctrl-C，故保留提示、保证能停干净。
  {
    kill_tree "$FRONTEND_PID" TERM
    kill_tree "$BACKEND_PID" TERM
    kill_tree "$WORKER_PID" TERM
    kill_tree "$MAIL_WORKER_PID" TERM
    kill_tree "$AGENT_SERVICE_PID" TERM
  } 2>/dev/null
  # 等待子进程真正退出，避免端口被占用
  for _ in $(seq 1 20); do
    local alive=0
    [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null && alive=1
    [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null && alive=1
    [[ -n "$WORKER_PID" ]] && kill -0 "$WORKER_PID" 2>/dev/null && alive=1
    [[ -n "$MAIL_WORKER_PID" ]] && kill -0 "$MAIL_WORKER_PID" 2>/dev/null && alive=1
    [[ -n "$AGENT_SERVICE_PID" ]] && kill -0 "$AGENT_SERVICE_PID" 2>/dev/null && alive=1
    [[ "$alive" -eq 1 ]] || break
    sleep 0.25
  done
  {
    kill_tree "$FRONTEND_PID" KILL
    kill_tree "$BACKEND_PID" KILL
    kill_tree "$WORKER_PID" KILL
    kill_tree "$MAIL_WORKER_PID" KILL
    kill_tree "$AGENT_SERVICE_PID" KILL
    # 回收子进程，让 bash 的作业表清理干净
    for pid in "${TAIL_PIDS[@]:-}" "$FRONTEND_PID" "$BACKEND_PID" "$WORKER_PID" "$MAIL_WORKER_PID" "$AGENT_SERVICE_PID"; do
      [[ -n "$pid" ]] && wait "$pid"
    done
  } 2>/dev/null || true
  ok "已停止"
  exit "$exit_status"
}
trap cleanup INT TERM EXIT

check_port_free() {
  local port="$1" name="$2" listeners
  listeners="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$listeners" ]]; then
    die "$name 端口 $port 已被占用（PID：$(echo "$listeners" | tr '\n' ' ')）；请停止原服务或更换端口后重试，不会自动终止已有进程"
  fi
}

wait_for_http() {
  local url="$1" name="$2" tries="${3:-60}" pid="${4:-}" i
  local probe_args=(--noproxy '*' -fsS --max-time 2)
  # 监听所有网卡时，仍通过回环地址探测；本地请求不经过系统代理。
  url="${url/http:\/\/0.0.0.0:/http:\/\/127.0.0.1:}"
  for ((i = 1; i <= tries; i++)); do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      fail "$name 进程已退出，停止等待健康检查"
      return 1
    fi
    if (( (i - 1) % 10 == 0 )); then
      step "等待${name}就绪（检查 ${i}/${tries}）"
    fi
    if curl "${probe_args[@]}" "$url" >/dev/null 2>&1; then
      if [[ -z "$pid" ]] || kill -0 "$pid" 2>/dev/null; then
        return 0
      fi
      fail "$name 进程已退出，停止等待健康检查"
      return 1
    fi
    sleep 0.5
  done
  return 1
}

wait_for_tcp() {
  local host="$1" port="$2" pid="$3" i
  [[ "$host" == "0.0.0.0" ]] && host="127.0.0.1"
  for ((i = 1; i <= 60; i++)); do
    kill -0 "$pid" 2>/dev/null || return 1
    (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 1
}

require() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1${2:+（$2）}"
}

mkdir -p "$LOG_DIR"

# --- 依赖检查 ---------------------------------------------------------------
step "检查本地依赖"
require uv "https://docs.astral.sh/uv/"
require curl
require lsof
[[ "$START_FRONTEND" -eq 1 ]] && require pnpm "https://pnpm.io/"
[[ "$START_DB" -eq 1 || "$START_BACKEND" -eq 1 ]] && require docker "https://orbstack.dev/"
ok "uv $(uv --version | awk '{print $2}')"
[[ "$START_FRONTEND" -eq 1 ]] && ok "pnpm $(pnpm --version)"
echo

# 在安装依赖、迁移与写入服务日志之前拒绝重复启动，保留旧日志供排查。
if [[ "$START_BACKEND" -eq 1 ]]; then
  check_port_free "$BACKEND_PORT" "后端"
  check_port_free "$AGENT_SERVICE_PORT" "AgentScope 服务"
  [[ "$BACKEND_PORT" != "$AGENT_SERVICE_PORT" ]] || die "后端与 AgentScope 服务不能使用相同端口"
fi
if [[ "$START_FRONTEND" -eq 1 ]]; then
  check_port_free "$FRONTEND_PORT" "前端"
  if [[ "$START_BACKEND" -eq 1 ]]; then
    [[ "$FRONTEND_PORT" != "$BACKEND_PORT" && "$FRONTEND_PORT" != "$AGENT_SERVICE_PORT" ]] \
      || die "前端与后端服务不能使用相同端口"
  fi
fi

# --- Docker 依赖 ------------------------------------------------------------
if [[ "$START_DB" -eq 1 || "$START_BACKEND" -eq 1 ]]; then
  step "检查 Docker / OrbStack"
  if ! docker info >/dev/null 2>&1; then
    if command -v orb >/dev/null 2>&1; then
      warn "Docker 守护进程未运行，尝试 orb start"
      orb start >/dev/null 2>&1 || true
    fi
    for _ in $(seq 1 30); do
      docker info >/dev/null 2>&1 && break
      sleep 1
    done
    docker info >/dev/null 2>&1 || die "Docker 守护进程不可用，请先启动 OrbStack"
  fi

fi

# --- 数据库 -----------------------------------------------------------------
if [[ "$START_DB" -eq 1 ]]; then
  step "启动 PostgreSQL"
  (cd "$ROOT_DIR" && docker compose up -d postgres) >/dev/null
  for _ in $(seq 1 40); do
    if (cd "$ROOT_DIR" && docker compose exec -T postgres \
        pg_isready -U paper_agent -d paper_agent) >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  (cd "$ROOT_DIR" && docker compose exec -T postgres \
      pg_isready -U paper_agent -d paper_agent) >/dev/null 2>&1 \
    || die "PostgreSQL 未就绪，请查看 docker compose logs postgres"
  if [[ "$START_BACKEND" -eq 1 ]]; then
    (cd "$ROOT_DIR" && docker compose exec -T postgres \
      psql -U paper_agent -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'paper_agent_as'" \
      | grep -qx 1) || \
      (cd "$ROOT_DIR" && docker compose exec -T postgres \
        psql -U paper_agent -d postgres -c 'CREATE DATABASE paper_agent_as') >/dev/null
  fi
  ok "PostgreSQL 已就绪（localhost:${POSTGRES_PORT}）"
  echo
fi

# --- Redis ------------------------------------------------------------------
if [[ "$START_BACKEND" -eq 1 ]]; then
  step "启动 Redis"
  (cd "$ROOT_DIR" && docker compose up -d redis) >/dev/null
  for _ in $(seq 1 40); do
    [[ "$(cd "$ROOT_DIR" && docker compose exec -T redis redis-cli ping 2>/dev/null)" == "PONG" ]] && break
    sleep 0.5
  done
  [[ "$(cd "$ROOT_DIR" && docker compose exec -T redis redis-cli ping 2>/dev/null)" == "PONG" ]] \
    || die "Redis 未就绪，请查看 docker compose logs redis"
  if command -v redis-cli >/dev/null 2>&1; then
    compose_run_id="$(cd "$ROOT_DIR" && docker compose exec -T redis redis-cli INFO server | sed -n 's/^run_id://p' | tr -d '\r')"
    host_run_id="$(redis-cli -p "$REDIS_PORT" INFO server 2>/dev/null | sed -n 's/^run_id://p' | tr -d '\r')"
    [[ -n "$compose_run_id" && "$compose_run_id" == "$host_run_id" ]] \
      || die "Redis 不是 Compose 实例，请停止占用 ${REDIS_PORT} 的其他进程"
  fi
  ok "Redis 已就绪"
  echo
fi

# --- 对象存储（可选）--------------------------------------------------------
# STORAGE_BACKEND=s3 时后端需要 S3 兼容服务；本地默认是 RustFS 容器。
if [[ "$START_BACKEND" -eq 1 && -f "$BACKEND_DIR/.env" ]] \
   && grep -qE '^STORAGE_BACKEND=s3' "$BACKEND_DIR/.env"; then
  START_STORAGE=1
fi

if [[ "$START_STORAGE" -eq 1 ]]; then
  step "启动对象存储（RustFS）"
  (cd "$ROOT_DIR" && docker compose --profile storage up -d storage) >/dev/null
  if wait_for_http "http://127.0.0.1:9000/health" "storage" 60; then
    ok "对象存储已就绪（http://127.0.0.1:9000，控制台 http://127.0.0.1:9001）"
  else
    warn "对象存储未在预期时间内就绪，可稍后再看：docker compose logs storage"
  fi
  echo
fi

# --- 后端 -------------------------------------------------------------------
if [[ "$START_BACKEND" -eq 1 ]]; then
  step "准备后端"
  cd "$BACKEND_DIR"

  if [[ ! -f .env ]]; then
    cp .env.example .env
    # 端口来自仓库根 .env（或默认值），保证与 compose 一致。
    sed -i.bak \
      -e "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL_DEFAULT}|" \
      -e "s|^TEST_DATABASE_URL=.*|TEST_DATABASE_URL=${TEST_DATABASE_URL_DEFAULT}|" \
      -e "s|^REDIS_URL=.*|REDIS_URL=${REDIS_URL_DEFAULT}|" \
      .env && rm -f .env.bak
    warn "已从 .env.example 生成 backend/.env，请按需修改 Provider 配置"
  fi

  if ! grep -q '^AGENT_INTERNAL_KEY=.' .env; then
    require openssl
    printf '\nAGENT_INTERNAL_KEY=%s\n' "$(openssl rand -hex 32)" >>.env
    ok "已生成服务间检索密钥"
  fi
  export BUSINESS_API_URL="${BUSINESS_API_URL:-http://127.0.0.1:$BACKEND_PORT}"
  AGENT_SERVICE_INTERNAL_HOST="$AGENT_SERVICE_HOST"
  [[ "$AGENT_SERVICE_INTERNAL_HOST" == "0.0.0.0" ]] && AGENT_SERVICE_INTERNAL_HOST="127.0.0.1"
  export AGENT_SERVICE_URL="${AGENT_SERVICE_URL:-http://$AGENT_SERVICE_INTERNAL_HOST:$AGENT_SERVICE_PORT}"

  if [[ "$DO_INSTALL" -eq 1 ]]; then
    uv sync --quiet
  fi
  ok "Python 依赖已就绪"

  if ! grep -q '^CREDENTIAL_MASTER_KEY=.' .env; then
    [[ "$START_DB" -eq 1 ]] || die "使用外部数据库时必须手动配置 CREDENTIAL_MASTER_KEY"
    credentials="$(cd "$ROOT_DIR" && docker compose exec -T postgres \
      psql -U paper_agent -d paper_agent_as -tAc "SELECT count(*) FROM credentials" 2>/dev/null || true)"
    [[ -z "$credentials" || "$credentials" == "0" ]] \
      || die "已有凭据，请恢复原 CREDENTIAL_MASTER_KEY"
    require openssl
    printf '\nCREDENTIAL_MASTER_KEY=%s\n' "$(openssl rand -hex 32)" >>.env
    chmod 600 .env
    ok "已生成 Credential 主密钥；请安全备份 backend/.env"
  fi

  uv run alembic upgrade head >/dev/null
  ok "数据库迁移已应用到 head"
  echo

  step "启动后端 http://$BACKEND_HOST:$BACKEND_PORT"
  uv run uvicorn app.main:app \
    --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload \
    >"$LOG_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!

  if wait_for_http "http://$BACKEND_HOST:$BACKEND_PORT/health" "后端" 60 "$BACKEND_PID"; then
    ok "后端已就绪（API 文档 /docs）"
  else
    fail "后端启动失败，日志末尾："
    tail -n 20 "$LOG_DIR/backend.log" >&2
    exit 1
  fi
  echo

  step "启动文献解析 worker"
  uv run python -m app.literature_support.importing.worker >"$LOG_DIR/worker.log" 2>&1 &
  WORKER_PID=$!
  sleep 0.5
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    fail "解析 worker 启动失败，日志末尾："
    tail -n 20 "$LOG_DIR/worker.log" >&2
    exit 1
  fi
  ok "解析 worker 已启动"
  echo

  step "启动邮件投递 worker"
  uv run python -m app.platform.mail_worker >"$LOG_DIR/mail-worker.log" 2>&1 &
  MAIL_WORKER_PID=$!
  sleep 0.5
  if ! kill -0 "$MAIL_WORKER_PID" 2>/dev/null; then
    fail "邮件 worker 启动失败，请查看 .var/logs/mail-worker.log"
    exit 1
  fi
  ok "邮件 worker 已启动"
  echo

  step "启动 AgentScope 服务 http://$AGENT_SERVICE_HOST:$AGENT_SERVICE_PORT"
  uv run uvicorn agent_service.main:app \
    --host "$AGENT_SERVICE_HOST" --port "$AGENT_SERVICE_PORT" --reload \
    >"$LOG_DIR/agent-service.log" 2>&1 &
  AGENT_SERVICE_PID=$!
  if ! wait_for_tcp "$AGENT_SERVICE_HOST" "$AGENT_SERVICE_PORT" "$AGENT_SERVICE_PID"; then
    fail "AgentScope 服务启动失败，日志末尾："
    tail -n 20 "$LOG_DIR/agent-service.log" >&2
    exit 1
  fi
  ok "AgentScope 服务 TCP 已就绪（不代表已验证登录态或完整业务健康）"
  echo
fi

# --- 前端 -------------------------------------------------------------------
if [[ "$START_FRONTEND" -eq 1 ]]; then
  step "准备前端"
  cd "$FRONTEND_DIR"

  if [[ "$DO_INSTALL" -eq 1 || ! -d node_modules ]]; then
    pnpm install --silent
  fi
  ok "Node 依赖已就绪"
  echo

  step "启动前端 http://$FRONTEND_HOST:$FRONTEND_PORT"
  pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort \
    >"$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!

  if wait_for_http "http://$FRONTEND_HOST:$FRONTEND_PORT/" "前端" 60 "$FRONTEND_PID"; then
    ok "前端已就绪"
  else
    fail "前端启动失败，日志末尾："
    tail -n 20 "$LOG_DIR/frontend.log" >&2
    exit 1
  fi
  echo
fi

# --- 汇总 -------------------------------------------------------------------
cd "$ROOT_DIR"
printf '%s%s 服务已启动%s\n' "$BOLD" "$GREEN" "$RESET"
[[ "$START_FRONTEND" -eq 1 ]] && printf '  %s前端%s   http://%s:%s\n' "$BOLD" "$RESET" "$FRONTEND_HOST" "$FRONTEND_PORT"
[[ "$START_BACKEND" -eq 1 ]] && printf '  %sAgentScope%s http://%s:%s\n' "$BOLD" "$RESET" "$AGENT_SERVICE_HOST" "$AGENT_SERVICE_PORT"
[[ "$START_BACKEND" -eq 1 ]] && printf '  %s后端%s   http://%s:%s  %s(文档 /docs)%s\n' \
  "$BOLD" "$RESET" "$BACKEND_HOST" "$BACKEND_PORT" "$DIM" "$RESET"
[[ "$START_BACKEND" -eq 1 ]] && printf '  %s解析 / 邮件 worker%s   独立进程\n' "$BOLD" "$RESET"
printf '  %s日志%s   %s\n' "$BOLD" "$RESET" "$LOG_DIR"
printf '%s按 Ctrl-C 停止全部服务%s\n\n' "$DIM" "$RESET"

# 实时跟随日志（带前缀），直到收到信号。
# 用进程替换而不是管道：$! 拿到的是 tail 的 PID，kill 它即可让前缀循环自然退出。
# 前缀用 bash 的 printf 逐行写（sed/awk 在非终端下会块缓冲，导致日志迟迟不出现）。
if [[ "$START_BACKEND" -eq 1 ]]; then
  tail -n 0 -f "$LOG_DIR/backend.log" > >(while IFS= read -r line; do printf '[backend] %s\n' "$line"; done) &
  TAIL_PIDS+=($!)
  tail -n 0 -f "$LOG_DIR/worker.log" > >(while IFS= read -r line; do printf '[worker] %s\n' "$line"; done) &
  TAIL_PIDS+=($!)
  tail -n 0 -f "$LOG_DIR/mail-worker.log" > >(while IFS= read -r line; do printf '[mail-worker] %s\n' "$line"; done) &
  TAIL_PIDS+=($!)
  tail -n 0 -f "$LOG_DIR/agent-service.log" > >(while IFS= read -r line; do printf '[agent-service] %s\n' "$line"; done) &
  TAIL_PIDS+=($!)
fi
if [[ "$START_FRONTEND" -eq 1 ]]; then
  tail -n 0 -f "$LOG_DIR/frontend.log" > >(while IFS= read -r line; do printf '[frontend] %s\n' "$line"; done) &
  TAIL_PIDS+=($!)
fi

# Bash 3.2 没有 wait -n；轮询服务进程，任一退出都触发统一 cleanup。
while true; do
  for pid in "$BACKEND_PID" "$WORKER_PID" "$MAIL_WORKER_PID" "$AGENT_SERVICE_PID" "$FRONTEND_PID"; do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      die "服务进程已退出（PID：$pid），请查看 $LOG_DIR 中对应日志"
    fi
  done
  sleep 1
done
