#!/bin/bash
# run.sh — Music-to-MV v2 命令行入口
# 用法: ./run.sh --theme "童年" [选项...]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 加载 .env（如果存在）
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# 检查 Python
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查依赖
$PYTHON -c "import yaml, jinja2" 2>/dev/null || {
    echo "📥 安装依赖..."
    pip install pyyaml jinja2
}

# 运行
exec $PYTHON -m src.main "$@"
