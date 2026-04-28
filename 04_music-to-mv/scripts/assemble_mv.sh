#!/bin/bash
# assemble_mv.sh - 拼接视频片段（带黑场过渡）
# 用法: ./assemble_mv.sh -p <项目目录> -o <输出文件> [-t <转场秒数>] [-r <分辨率>]
#
# 示例:
#   ./assemble_mv.sh -p ~/mv/童年_20260424 -o output/assembled.mp4
#   ./assemble_mv.sh -p ~/mv/童年_20260424 -o output/assembled.mp4 -t 2 -r 1920x1080

set -e

FFMPEG="${FFMPEG:-ffmpeg}"
FFPROBE="${FFPROBE:-ffprobe}"
TRANSITION=1
RESOLUTION="1280x720"
OUTPUT=""
PROJECT_DIR=""

usage() {
    echo "用法: $0 -p <项目目录> -o <输出文件> [选项]"
    echo ""
    echo "必填:"
    echo "  -p <项目目录>   项目根目录"
    echo "  -o <输出文件>   输出文件路径（相对于项目目录）"
    echo ""
    echo "选项:"
    echo "  -t <秒数>       黑场转场时长 (默认: 1)"
    echo "  -r <分辨率>     输出分辨率 (默认: 1280x720)"
    echo "  -f <ffmpeg>     ffmpeg 路径 (默认: ffmpeg)"
    echo "  -h              显示帮助"
    exit 1
}

while getopts "p:o:t:r:f:h" opt; do
    case $opt in
        p) PROJECT_DIR="$OPTARG";;
        o) OUTPUT="$OPTARG";;
        t) TRANSITION="$OPTARG";;
        r) RESOLUTION="$OPTARG";;
        f) FFMPEG="$OPTARG";;
        h) usage;;
        ?) usage;;
    esac
done

if [ -z "$PROJECT_DIR" ] || [ -z "$OUTPUT" ]; then
    usage
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/status_funcs.sh"

METADATA_DIR="$PROJECT_DIR/metadata"
mkdir -p "$METADATA_DIR"

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" >> "$METADATA_DIR/steps.log"
}

update_status "assemble" "running" "starting..."
log_step "[assemble] starting..."

# 解析分辨率
WIDTH=$(echo "$RESOLUTION" | cut -d'x' -f1)
HEIGHT=$(echo "$RESOLUTION" | cut -d'x' -f2)

WORKDIR="$PROJECT_DIR"
FULL_OUTPUT="$WORKDIR/$OUTPUT"

mkdir -p "$(dirname "$FULL_OUTPUT")"

# 生成黑场过渡片段
BLACK_FILE="$WORKDIR/temp/black_${TRANSITION}s.mp4"
mkdir -p "$WORKDIR/temp"
$FFMPEG -y -f lavfi -i "color=black:s=${RESOLUTION}:d=$TRANSITION" \
    -vf "fps=25" -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
    "$BLACK_FILE" 2>/dev/null

# 收集所有 KB 片段并排序
CLIPS=$(ls -1 "$WORKDIR"/clips/*_kb.mp4 2>/dev/null | sort)

if [ -z "$CLIPS" ]; then
    update_status "assemble" "failed" "no KB clips found"
    log_step "[assemble] FAILED: no KB clips found"
    echo "❌ 未找到 KB 视频片段: $WORKDIR/clips/*_kb.mp4"
    exit 1
fi

# 构建 concat 列表：片段 + 黑场 + 片段 + 黑场...
CONCAT_LIST="$WORKDIR/temp/concat_list_assemble.txt"

# 用 mapfile 读入数组，避免管道子 shell 导致 idx 计数器失效
mapfile -t CLIPS_ARRAY < <(ls -1 "$WORKDIR"/clips/*_kb.mp4 2>/dev/null | sort)
total=${#CLIPS_ARRAY[@]}

> "$CONCAT_LIST"
for idx in "${!CLIPS_ARRAY[@]}"; do
    clip="${CLIPS_ARRAY[$idx]}"
    # 用相对路径（相对于 WORKDIR/temp/），便于项目迁移后仍能工作
    rel="${clip#$WORKDIR/}"   # 去掉 WORKDIR 前缀得到 clips/xxx.mp4
    echo "file '$rel'" >> "$CONCAT_LIST"
    if [ "$idx" -lt $((total - 1)) ]; then
        echo "file 'black_${TRANSITION}s.mp4'" >> "$CONCAT_LIST"
    fi
done

# 拼接
update_status "assemble" "running" "concatenating clips..."
log_step "[assemble] concatenating..."

$FFMPEG -y -f concat -safe 0 -i "$CONCAT_LIST" \
    -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p \
    "$FULL_OUTPUT" 2>/dev/null

if [ -f "$FULL_OUTPUT" ]; then
    SIZE=$(du -h "$FULL_OUTPUT" | cut -f1)
    DURATION=$($FFPROBE -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 "$FULL_OUTPUT" 2>/dev/null \
        | cut -d. -f1 || echo "0")
    update_status "assemble" "completed" "$FULL_OUTPUT ($SIZE, $DURATION)"
    log_step "[assemble] completed: $FULL_OUTPUT ($SIZE, $DURATION)"
    echo "✅ 拼接完成: $FULL_OUTPUT ($SIZE, $DURATION)"
else
    update_status "assemble" "failed" "concat failed"
    log_step "[assemble] FAILED: concat failed"
    echo "❌ 拼接失败"
    exit 1
fi
