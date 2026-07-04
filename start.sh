#!/bin/bash
# ===========================================================================
# 知识图谱系统一键管理脚本
# 用法:
#   ./start.sh          # 启动全部服务（默认）
#   ./start.sh start    # 同上
#   ./start.sh stop     # 停止全部服务
#   ./start.sh restart  # 重启
#   ./start.sh status   # 查看运行状态
#
# 启动顺序: llama-server(:8000) → 后端 FastAPI(:3000) → 前端 Vite(:5173)
# 日志:    logs/{llm,backend,frontend}.log
# PID:     .run/{llm,backend,frontend}.pid
# ===========================================================================
set -u

PROJECT_DIR="/home/honi/AI/class_AI_deploy_and_apply"
LLAMA_SERVER="/home/honi/llama.cpp/build/bin/llama-server"
PYTHON="/home/honi/miniconda3/envs/AI/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.run"

MODEL_DIR="$PROJECT_DIR/model/gemma-4-12b-uncensored"
MAIN_MODEL="$MODEL_DIR/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"
DRAFT_MODEL="$MODEL_DIR/mtp-gemma-4-12B-it.gguf"
MODEL_ALIAS="gemma-4-12b-uncensored"

mkdir -p "$LOG_DIR" "$PID_DIR"

# ---------- 工具函数 ----------
is_running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

# 等待端口可达；$1=健康检查URL $2=pidfile $3=名称 $4=最大重试次数
wait_ready() {
    local url="$1" pidfile="$2" name="$3" tries="$4"
    for _ in $(seq 1 "$tries"); do
        curl -s "$url" >/dev/null 2>&1 && return 0
        kill -0 "$(cat "$pidfile")" 2>/dev/null || { echo "✗ $name 进程已退出，见日志"; return 1; }
        sleep 2
    done
    echo "✗ $name 启动超时，见日志"
    return 1
}

# 连同子进程一起停掉（前端 npm→vite 会派生子进程）
kill_tree() {
    local pid="$1"
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
}

# ---------- 启动各项 ----------
start_llm() {
    if is_running "$PID_DIR/llm.pid"; then echo "✓ llama-server 已在运行"; return 0; fi
    echo "▶ 启动 llama-server (端口 8000, MTP 投机解码)..."
    nohup "$LLAMA_SERVER" \
        -m "$MAIN_MODEL" \
        -md "$DRAFT_MODEL" --spec-type draft-mtp \
        --alias "$MODEL_ALIAS" \
        --host 127.0.0.1 --port 8000 \
        --ctx-size 16384 --n-gpu-layers 99 -fa on \
        > "$LOG_DIR/llm.log" 2>&1 &
    echo $! > "$PID_DIR/llm.pid"
    wait_ready "http://127.0.0.1:8000/health" "$PID_DIR/llm.pid" "llama-server" 60 \
        && echo "✓ llama-server 就绪" || return 1
}

start_backend() {
    if is_running "$PID_DIR/backend.pid"; then echo "✓ 后端已在运行"; return 0; fi
    echo "▶ 启动 FastAPI 后端 (端口 3000)..."
    cd "$PROJECT_DIR"
    nohup "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 3000 \
        > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
    wait_ready "http://127.0.0.1:3000/api/health" "$PID_DIR/backend.pid" "后端" 30 \
        && echo "✓ 后端就绪" || return 1
}

start_frontend() {
    if is_running "$PID_DIR/frontend.pid"; then echo "✓ 前端已在运行"; return 0; fi
    cd "$PROJECT_DIR/frontend" || return 1
    if [ ! -d node_modules ]; then
        echo "▶ 首次运行，安装前端依赖..."
        npm install || { echo "✗ 依赖安装失败"; return 1; }
    fi
    echo "▶ 启动前端 (端口 5173)..."
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    echo "✓ 前端启动中 → http://127.0.0.1:5173"
}

start_all() {
    start_llm || return 1
    start_backend || return 1
    start_frontend || return 1
    echo ""
    echo "🎉 全部启动完成 → http://127.0.0.1:5173"
    echo "   日志: tail -f $LOG_DIR/{llm,backend,frontend}.log"
}

stop_all() {
    for name in frontend backend llm; do
        f="$PID_DIR/$name.pid"
        if is_running "$f"; then
            kill_tree "$(cat "$f")"
            rm -f "$f"
            echo "○ 已停止 $name"
        fi
    done
    # 兜底：按进程名清理游离进程（llama 可能是手动 run.sh 启动的，不在 pidfile 里）
    pkill -f "llama-server" 2>/dev/null && echo "○ 兜底停止 llama-server"
    pkill -f "uvicorn main:app" 2>/dev/null && echo "○ 兜底停止后端"
    pkill -f "vite" 2>/dev/null && echo "○ 兜底停止前端"
    sleep 2
}

show_status() {
    for name in llm backend frontend; do
        f="$PID_DIR/$name.pid"
        if is_running "$f"; then
            echo "● $name 运行中 (pid $(cat "$f"))"
        else
            echo "○ $name 未运行"
        fi
    done
}

# ---------- 入口 ----------
case "${1:-start}" in
    start)   start_all ;;
    stop)    stop_all ;;
    restart) stop_all; sleep 2; start_all ;;
    status)  show_status ;;
    *) echo "用法: $0 {start|stop|restart|status}"; exit 1 ;;
esac
