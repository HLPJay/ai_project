#!/bin/bash
# burn_subtitle.sh - 烧录硬字幕到视频
# 用法: ./burn_subtitle.sh -p <项目目录> -i <输入视频> -s <字幕文件> -o <输出视频> [选项]
#
# 示例:
#   ./burn_subtitle.sh -p ~/mv/童年_20260424 -i output/final.mp4 -s audio/song.srt -o output/tiktok.mp4
#   ./burn_subtitle.sh -p ~/mv/童年_20260424 -i output/final.mp4 -s audio/song.srt -o output/vertical.mp4 --wide

set -e

FFMPEG="${FFMPEG:-ffmpeg}"
FONT="Microsoft YaHei"
SIZE=32
MARGINV=20
WIDE=false

usage() {
    echo "用法: $0 -p <项目目录> -i <输入> -s <字幕> -o <输出> [选项]"
    echo ""
    echo "必填:"
    echo "  -p <项目目录>   项目根目录"
    echo "  -i <输入视频>   输入文件（相对于项目目录）"
    echo "  -s <字幕文件>   SRT 文件（相对于项目目录）"
    echo "  -o <输出视频>   输出文件（相对于项目目录）"
    echo ""
    echo "选项:"
    echo "  --font <名称>   字体名称 (默认: Microsoft YaHei)"
    echo "  --size <pt>     字号 (默认: 32)"
    echo "  --mv <px>       底部边距 (默认: 20)"
    echo "  --wide          生成 9:16 竖屏版"
    echo "  -f <ffmpeg>     ffmpeg 路径"
    echo "  -h              显示帮助"
    exit 1
}

opts=$(getopt -o p:i:s:o:f:h -l font:,size:,mv:,wide --name "$0" -- "$@")
eval set -- "$opts"

while true; do
    case "$1" in
        -p) PROJECT_DIR="$2"; shift 2;;
        -i) INPUT_REL="$2"; shift 2;;
        -s) SRT_REL="$2"; shift 2;;
        -o) OUTPUT_REL="$2"; shift 2;;
        --font) FONT="$2"; shift 2;;
        --size) SIZE="$2"; shift 2;;
        --mv) MARGINV="$2"; shift 2;;
        --wide) WIDE=true; shift;;
        -f) FFMPEG="$2"; shift 2;;
        -h) usage;;
        --) shift; break;;
        *) usage;;
    esac
done

if [ -z "$PROJECT_DIR" ] || [ -z "$INPUT_REL" ] || [ -z "$SRT_REL" ] || [ -z "$OUTPUT_REL" ]; then
    usage
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/status_funcs.sh"

METADATA_DIR="$PROJECT_DIR/metadata"
mkdir -p "$METADATA_DIR"

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" >> "$METADATA_DIR/steps.log"
}

update_status "burn" "running" "starting..."
log_step "[burn] starting..."

INPUT="$PROJECT_DIR/$INPUT_REL"
SRT="$PROJECT_DIR/$SRT_REL"
OUTPUT="$PROJECT_DIR/$OUTPUT_REL"

mkdir -p "$(dirname "$OUTPUT")"

STYLE="FontName=$FONT,FontSize=$SIZE,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=$MARGINV"

if [ "$WIDE" = "true" ]; then
    # 9:16 竖屏: 先缩放再 pad
    update_status "burn" "running" "rendering 9:16 vertical with subtitles..."
    log_step "[burn] rendering 9:16 vertical..."
    $FFMPEG -y \
        -i "$INPUT" \
        -vf "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,subtitles=$SRT:force_style='$STYLE'" \
        -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
        -c:a copy \
        "$OUTPUT" 2>/dev/null
else
    # 16:9 横屏
    update_status "burn" "running" "rendering 16:9 with subtitles..."
    log_step "[burn] rendering 16:9..."
    $FFMPEG -y \
        -i "$INPUT" \
        -vf "subtitles=$SRT:force_style='$STYLE'" \
        -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
        -c:a copy \
        "$OUTPUT" 2>/dev/null
fi

if [ -f "$OUTPUT" ]; then
    SIZE=$(du -h "$OUTPUT" | cut -f1)
    update_status "burn" "completed" "$OUTPUT ($SIZE)"
    log_step "[burn] completed: $OUTPUT ($SIZE)"
    echo "✅ 字幕烧录完成: $OUTPUT ($SIZE)"
else
    update_status "burn" "failed" "render failed"
    log_step "[burn] FAILED: render failed"
    echo "❌ 字幕烧录失败"
    exit 1
fi
