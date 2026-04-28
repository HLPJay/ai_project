#!/bin/bash
# preflight.sh - Pipeline 前置依赖检查
# 用法: ./preflight.sh
# 在 init_project.sh 启动时自动调用，也可手动运行

ERRORS=()
WARNINGS=()

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"   # 加载 API Token 配置

check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# ── 必须项 ──────────────────────────────────────────────────
check_cmd python3 || ERRORS+=("python3 未安装")
check_cmd curl    || ERRORS+=("curl 未安装")
check_cmd ffmpeg  || ERRORS+=("ffmpeg 未安装  →  sudo apt install ffmpeg  /  brew install ffmpeg")
check_cmd ffprobe || ERRORS+=("ffprobe 未安装（随 ffmpeg 一起安装）")

# ── 图片 API Token 检查（根据 provider）──────────────────────
IMG_PROVIDER="${IMAGE_API_PROVIDER:-alibaba}"
case "$IMG_PROVIDER" in
    minimax)
        [ -z "${MINIMAX_TOKEN:-}" ] && ERRORS+=("MINIMAX_TOKEN 未设置  →  export MINIMAX_TOKEN=your_token\n   获取地址: https://www.minimaxi.com/user-center/basic-information/interface-key") ;;
    alibaba)
        [ -z "${ALIBABA_TOKEN:-}" ] && ERRORS+=("ALIBABA_TOKEN 未设置  →  export ALIBABA_TOKEN=your_token\n   获取地址: https://dashscope.console.aliyun.com") ;;
    dall-e)
        [ -z "${OPENAI_TOKEN:-}" ] && ERRORS+=("OPENAI_TOKEN 未设置  →  export OPENAI_TOKEN=your_token\n   获取地址: https://platform.openai.com") ;;
    pollinations) ;;  # 免费，无需 token
    *) ERRORS+=("未知的 IMAGE_API_PROVIDER: $IMG_PROVIDER（可选: minimax/alibaba/dall-e/pollinations）") ;;
esac

# DeepSeek Token（场景描述生成）
[ -z "${DEEPSEEK_TOKEN:-}" ] && ERRORS+=("DEEPSEEK_TOKEN 未设置  →  export DEEPSEEK_TOKEN=your_token\n   获取地址: https://platform.deepseek.com")

# whisper 可以是 CLI 或 Python 模块
if ! check_cmd whisper; then
    python3 -c "import whisper" 2>/dev/null \
        || ERRORS+=("whisper 未安装  →  pip install openai-whisper")
fi

# Demucs 检查（可选，vocal separation 用）
if ! python3 -c "import demucs" 2>/dev/null; then
    WARNINGS+=("Demucs 未安装，人声分离将被跳过  →  pip install demucs --break-system-packages")
fi

# openai-whisper 包检查
if ! python3 -c "import openai.whisper" 2>/dev/null && ! python3 -c "import whisper" 2>/dev/null; then
    ERRORS+=("openai-whisper 未安装  →  pip install openai-whisper")
fi

# ── 可选项（警告，不阻断）──────────────────────────────────
# 检测 Microsoft YaHei 字体（字幕渲染）
_font_found=false
if check_cmd fc-list; then
    fc-list 2>/dev/null | grep -qi "yahei\|微软雅黑" && _font_found=true
fi
# Windows/WSL 路径兜底
for _p in \
    "/mnt/c/Windows/Fonts/msyh.ttc" \
    "/usr/share/fonts/truetype/msttcorefonts/msyh.ttc" \
    "${WINDIR:-}/Fonts/msyh.ttc"
do
    [ -f "$_p" ] && _font_found=true && break
done
$_font_found || WARNINGS+=("未检测到 Microsoft YaHei 字体，字幕将使用系统默认字体
   安装: sudo apt install fonts-wqy-zenhei  （中文备用字体）")

# ── 输出结果 ─────────────────────────────────────────────────
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "⚠️  前置检查警告："
    for w in "${WARNINGS[@]}"; do
        echo "   • $w"
    done
    echo ""
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "❌ 前置检查失败，缺少以下依赖："
    for e in "${ERRORS[@]}"; do
        echo "   • $e"
    done
    exit 1
fi

echo "✅ 前置检查通过"
