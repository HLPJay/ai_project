# music-to-mv 统一配置
# 所有脚本通过 source 此文件获取 API 配置
#
# 使用方式：
#   source "$(dirname "$0")/config.sh"
#
# 环境变量优先级（从高到低）：
#   1. 当前 shell 已设置的环境变量（最高）
#   2. .env 文件（若有）
#   3. 默认值（hardcoded fallback）
#
# 切换图片 provider：
#   IMAGE_API_PROVIDER=pollinations source config.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# ── 保存 shell 已有变量（防止被 .env 覆盖）─────────────────
# 这些变量如果在调用前已设置，.env 不会覆盖它们
_SAVED_API_PROVIDER="${IMAGE_API_PROVIDER:-}"

# ── 加载 .env（若存在）─────────────────────────────────────
if [ -f "$SKILL_DIR/.env" ]; then
    set -a  # 后续赋值自动导出
    source "$SKILL_DIR/.env"
    set +a
fi

# ── 恢复调用者设置的变量（优先级最高）──────────────────────
[ -n "$_SAVED_API_PROVIDER" ] && IMAGE_API_PROVIDER="$_SAVED_API_PROVIDER"
unset _SAVED_API_PROVIDER

# ── MiniMax API ─────────────────────────────────────────────
export MINIMAX_API_HOST="${MINIMAX_API_HOST:-https://api.minimaxi.com}"
export MINIMAX_API_URL="${MINIMAX_API_URL:-${MINIMAX_API_HOST}/v1/image_generation}"

# ── MiniMax LLM API（文本生成，OpenAI 兼容格式）───────────
export LLM_API_URL="${LLM_API_URL:-https://api.minimaxi.com/v1/chat/completions}"
export LLM_MODEL="${LLM_MODEL:-MiniMax-M2.7}"

# ── 图片生成配置 ────────────────────────────────────────────
export IMAGE_API_PROVIDER="${IMAGE_API_PROVIDER:-minimax}"

# 各 provider 的 endpoint 和 model
export IMAGE_API_URL_MINIMAX="${IMAGE_API_URL_MINIMAX:-${MINIMAX_API_HOST}/v1/image_generation}"
export IMAGE_MODEL_MINIMAX="${IMAGE_MODEL_MINIMAX:-image-01}"

export IMAGE_API_URL_POLLINATIONS="${IMAGE_API_URL_POLLINATIONS:-https://image.pollinations.ai}"
export IMAGE_MODEL_POLLINATIONS="${IMAGE_MODEL_POLLINATIONS:-flux}"

export IMAGE_API_URL_ALIBABA="${IMAGE_API_URL_ALIBABA:-https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis}"
export IMAGE_MODEL_ALIBABA="${IMAGE_MODEL_ALIBABA:-wan2.2-t2i-plus}"

export IMAGE_API_URL_DALLE="${IMAGE_API_URL_DALLE:-https://api.openai.com/v1/images/generations}"
export IMAGE_MODEL_DALLE="${IMAGE_MODEL_DALLE:-dall-e-3}"

# ── 当前生效的图片 API（根据 provider 选择）─────────────────
case "$IMAGE_API_PROVIDER" in
    minimax)
        export IMAGE_API_URL="${IMAGE_API_URL:-${IMAGE_API_URL_MINIMAX}}"
        export IMAGE_MODEL="${IMAGE_MODEL:-${IMAGE_MODEL_MINIMAX}}"
        ;;
    pollinations)
        export IMAGE_API_URL="${IMAGE_API_URL:-${IMAGE_API_URL_POLLINATIONS}}"
        export IMAGE_MODEL="${IMAGE_MODEL:-${IMAGE_MODEL_POLLINATIONS}}"
        ;;
    dall-e)
        export IMAGE_API_URL="${IMAGE_API_URL:-${IMAGE_API_URL_DALLE}}"
        export IMAGE_MODEL="${IMAGE_MODEL:-${IMAGE_MODEL_DALLE}}"
        ;;
    alibaba)
        export IMAGE_API_URL="${IMAGE_API_URL:-${IMAGE_API_URL_ALIBABA}}"
        export IMAGE_MODEL="${IMAGE_MODEL:-${IMAGE_MODEL_ALIBABA}}"
        ;;
    *)
        echo "Unknown IMAGE_API_PROVIDER: $IMAGE_API_PROVIDER" >&2
        ;;
esac
