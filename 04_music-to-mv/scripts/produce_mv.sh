#!/bin/bash
# produce_mv.sh - Steps 4-8: 分析SRT → 生图 → Ken Burns 视频
# 用法: ./produce_mv.sh <项目目录> [--step N]
#
# 选项:
#   --step N    只执行指定步骤（4=base, 5=scenes, 8=KB），其他跳过
#
# 核心改进（相比旧版本）:
#   - Step 0: 调用 analyze_srt.py 分析歌词结构 → scenes.json
#   - Step 4: 读取 base_char.json 做角色 prompt（不再硬编码）
#   - Steps 5-7: 场景数 = scenes.json 动态数量（不是固定7个）
#   - Step 8: KB 时长 = scenes.json 中每段的实际 duration
#
# 输入: {project_dir}/metadata/info.json
#       {project_dir}/audio/song.srt
#       {project_dir}/audio/lyrics.txt
# 输出: images/*.png, clips/*_kb.mp4

# 加载统一配置（API URL / Model / Token）
# 如果 config.sh 存在则 source（自动从 .env 读取 Token）
if [ -f "$(dirname "$0")/config.sh" ]; then
    source "$(dirname "$0")/config.sh"
fi

set -e

PROJECT_DIR=""
TARGET_STEP=""

while [ -n "$1" ]; do
    case "$1" in
        --step) TARGET_STEP="$2"; shift 2 ;;
        -*) shift ;;
        *) PROJECT_DIR="$1"; shift ;;
    esac
done

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ 用法: $0 <项目目录> [--step N]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/status_funcs.sh"

# 检查图片 API token（根据 provider）
IMG_PROVIDER="${IMAGE_API_PROVIDER:-alibaba}"
case "$IMG_PROVIDER" in
    alibaba)   [ -z "${ALIBABA_TOKEN:-}" ]   && echo "❌ ALIBABA_TOKEN 未设置（IMAGE_API_PROVIDER=alibaba）"   && exit 1 ;;
    dall-e)    [ -z "${OPENAI_TOKEN:-}" ]     && echo "❌ OPENAI_TOKEN 未设置（IMAGE_API_PROVIDER=dall-e）"    && exit 1 ;;
    pollinations) ;;  # 免费，无需 token
    minimax)  [ -z "${MINIMAX_TOKEN:-}" ]    && echo "❌ MINIMAX_TOKEN 未设置（IMAGE_API_PROVIDER=minimax）"   && exit 1 ;;
esac

FFMPEG="${FFMPEG:-ffmpeg}"
FFPROBE="${FFPROBE:-ffprobe}"

AUDIO_DIR="$PROJECT_DIR/audio"
IMAGES_DIR="$PROJECT_DIR/images"
CLIPS_DIR="$PROJECT_DIR/clips"
TEMP_DIR="$PROJECT_DIR/temp"
OUTPUT_DIR="$PROJECT_DIR/output"
METADATA_DIR="$PROJECT_DIR/metadata"
SCENES_JSON="$METADATA_DIR/scenes.json"
BASE_CHAR_JSON="$METADATA_DIR/base_char.json"

mkdir -p "$IMAGES_DIR" "$CLIPS_DIR" "$TEMP_DIR" "$OUTPUT_DIR"

log_step() { echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" >> "$METADATA_DIR/steps.log"; }

# ── 中断检查 ─────────────────────────────────────────────────
# check_interrupt() and interrupt_stop() are provided by status_funcs.sh
# (sourced below) — no local shadowing needed

# ═══════════════════════════════════════════════════════════════
# Step 0: 分析 SRT（必须优先执行）
# ═══════════════════════════════════════════════════════════════
if [ "$TARGET_STEP" = "" ] || [ "$TARGET_STEP" = "0" ]; then
    if [ -f "$SCENES_JSON" ] && python3 -c "
import json
s=json.load(open('$SCENES_JSON'))
exit(0 if isinstance(s,list) and len(s)>0 else 1)
" 2>/dev/null; then
        echo "✅ Step 0 跳过: scenes.json 已存在"
    else
        check_interrupt || { echo "⚠️ 中断"; exit 0; }
        update_status "0 analyze" "running" "running analyze_srt.py..."
        log_step "[0 analyze] running analyze_srt.py..."
        if python3 "$SCRIPT_DIR/analyze_srt.py" "$PROJECT_DIR" 2>&1; then
            update_status "0 analyze" "completed" "scenes.json ready"
            log_step "[0 analyze] completed"
        else
            update_status "0 analyze" "failed" "analyze_srt.py failed"
            log_step "[0 analyze] FAILED"
            exit 1
        fi
    fi
fi

# 加载场景配置
SCENE_COUNT=$(python3 -c "
import json
s=json.load(open('$SCENES_JSON'))
print(len(s))
" 2>/dev/null || echo "0")

if [ "$SCENE_COUNT" -eq 0 ]; then
    echo "❌ scenes.json 无效，请先运行 Step 0"
    exit 1
fi

# 读取全局风格参数（给所有后续步骤使用）
STYLE_NAME=$(python3 -c "
import json; print(json.load(open('$METADATA_DIR/info.json')).get('style',''))
" 2>/dev/null)
API_STYLE=$(python3 -c "
import sys; sys.path.insert(0,'$SCRIPT_DIR'); from style_map import get_api_style; print(get_api_style('${STYLE_NAME:-动漫风}'))
" 2>/dev/null)
NEG_PROMPT=$(python3 -c "
import sys; sys.path.insert(0,'$SCRIPT_DIR'); from style_map import get_negative_prompt; print(get_negative_prompt('${STYLE_NAME:-动漫风}'))
" 2>/dev/null)
SEED=$(python3 -c "
import json; print(json.load(open('$METADATA_DIR/info.json')).get('image_seed', 0))
" 2>/dev/null)
export IMAGE_SEED="$SEED"
log_step "[init] seed=$SEED"
log_step "[global] style=$STYLE_NAME api_style=$API_STYLE"

# ═══════════════════════════════════════════════════════════════
# Step 4: 生成基础角色图
# ═══════════════════════════════════════════════════════════════
if [ "$TARGET_STEP" != "" ] && [ "$TARGET_STEP" != "4" ]; then
    echo "⏭️ 跳过 Step 4（--step=$TARGET_STEP）"
else
    # 检查 base_char.json
    if [ ! -f "$BASE_CHAR_JSON" ]; then
        python3 "$SCRIPT_DIR/analyze_srt.py" "$PROJECT_DIR" > /dev/null 2>&1
    fi

    if [ -f "$IMAGES_DIR/base_character.png" ] && \
       [ $(stat -c%s "$IMAGES_DIR/base_character.png" 2>/dev/null || echo 0) -gt 1000 ]; then
        update_status "④ base" "completed" "base_character.png (exists)"
        log_step "[④ base] skipped: already exists"
        echo "⏭️ ④ 跳过: base_character.png 已存在"
    else
        check_interrupt || { update_status "④ base" "interrupted"; exit 0; }
        update_status "④ base" "running" "..."
        log_step "[④ base] starting..."

        # 从 base_char.json 读取角色描述
        CHAR_PROMPT=$(python3 -c "
import json, os
try:
    d=json.load(open('$BASE_CHAR_JSON'))
    print(d.get('prompt',''))
except Exception: pass
" 2>/dev/null)

        # 读取风格配置（使用公共 style_map）
        ART_STYLE=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from style_map import ART_STYLES
import json
s=json.load(open('$METADATA_DIR/info.json')).get('style','')
print(ART_STYLES.get(s, 'illustration style, soft warm colors, heartwarming'))
" 2>/dev/null)

        SONG_TITLE=$(python3 -c "
import json; print(json.load(open('$METADATA_DIR/info.json')).get('song_title',''))
" 2>/dev/null)

        # 读取主题
        THEME_NAME=$(python3 -c "
import json; print(json.load(open('$METADATA_DIR/info.json')).get('theme',''))
" 2>/dev/null)

        # 构造图片 prompt（不再写死 spring）
        FULL_PROMPT=$(python3 -c "
import json, os

char_prompt = '''$CHAR_PROMPT'''
art_style = '''$ART_STYLE'''
song_title = '''$SONG_TITLE'''
theme = '''$THEME_NAME'''

scene_context = f'representing the song \"{song_title}\" with a {theme} theme' if theme else f'representing the song \"{song_title}\"'
prompt = f'{char_prompt}, in a scene {scene_context}, {art_style}'
print(prompt)
" 2>/dev/null)

        # 调用通用图片生成脚本（传递 API style + negative prompt）
        python3 "$SCRIPT_DIR/call_image_api.py" "$FULL_PROMPT" "$IMAGES_DIR/base_character.png" --style "$API_STYLE" --negative "$NEG_PROMPT"
        if [ -f "$IMAGES_DIR/base_character.png" ] && [ $(stat -c%s "$IMAGES_DIR/base_character.png" 2>/dev/null || echo 0) -gt 1000 ]; then
            SZ=$(du -h "$IMAGES_DIR/base_character.png" | cut -f1)
            update_status "④ base" "completed" "base_character.png ($SZ)"
            log_step "[④ base] completed: $SZ"
            echo "✅ ④ 完成: base_character.png ($SZ)"
        else
            update_status "④ base" "failed" "download failed"
            log_step "[④ base] FAILED: download"
            exit 1
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════════
# Steps 5-7: 生成场景图（并行 Python）
# ═══════════════════════════════════════════════════════════════
if [ "$TARGET_STEP" != "" ] && [ "$TARGET_STEP" != "5" ] && [ "$TARGET_STEP" != "6" ] && [ "$TARGET_STEP" != "7" ]; then
    echo "⏭️ 跳过 Steps 5-7（--step=$TARGET_STEP）"
else
    update_status "⑤-⑦ images" "running" "starting..."
    log_step "[⑤-⑦ images] starting..."

    # 传递 API style + negative 到 generate_scene_imgs.py（通过 env）
    export IMAGE_STYLE="$API_STYLE"
    export IMAGE_NEGATIVE="$NEG_PROMPT"
    PY_EXIT=0
    python3 "$SCRIPT_DIR/generate_scene_imgs.py" "$PROJECT_DIR" -j 4 || PY_EXIT=$?
    if [ $PY_EXIT -eq 0 ]; then
        update_status "⑤-⑦ images" "completed" "done"
        log_step "[⑤-⑦ images] completed"
        echo "✅ ⑤-⑦ 完成"
    else
        update_status "⑤-⑦ images" "failed" "parallel generation failed"
        log_step "[⑤-⑦ images] FAILED"
        exit 1
    fi
fi

# ═══════════════════════════════════════════════════════════════
# Step 8: Ken Burns（动态时长）
# ═══════════════════════════════════════════════════════════════
# Step ⑧: Ken Burns 视频（Python 脚本，支持变体 crossfade）
# ═══════════════════════════════════════════════════════════════
if [ "$TARGET_STEP" != "" ] && [ "$TARGET_STEP" != "8" ]; then
    echo "⏭️ 跳过 Step 8（--step=$TARGET_STEP）"
else
    update_status "⑧ kb" "running" "starting..."
    log_step "[⑧ kb] starting..."

    # 调用 Python KB 生成脚本（支持变体图 crossfade）
    python3 "$SCRIPT_DIR/generate_kb_video.py" "$PROJECT_DIR" 2>&1 | tee -a "$METADATA_DIR/ffmpeg.log"
    PY_EXIT=$?

    if [ $PY_EXIT -eq 0 ]; then
        KB_COUNT=$(ls -1 "$CLIPS_DIR"/*_scene_kb.mp4 2>/dev/null | wc -l)
        update_status "⑧ kb" "completed" "${KB_COUNT} clips"
        log_step "[⑧ kb] completed: $KB_COUNT clips"
        echo "✅ ⑧ 完成: $KB_COUNT clips"
    else
        update_status "⑧ kb" "failed" "KB generation failed"
        log_step "[⑧ kb] FAILED"
        exit 1
    fi
fi

# ═══════════════════════════════════════════════════════════════
# 完成
# ═══════════════════════════════════════════════════════════════
log_step "=========================================="
log_step "produce_mv.sh 完成（④-⑧）"
log_step "下一步: ./merge_and_export.sh $PROJECT_DIR"
echo ""
echo "✅ produce_mv.sh 完成（④-⑧）"
# ═══════════════════════════════════════════════════════════════
# LLM 日志归档（按日期分类，减少小文件碎片）
ARC_COUNT=$(python3 "$SCRIPT_DIR/archive_llm_logs.py" "$PROJECT_DIR" 2>/dev/null || echo "0")
log_step "LLM logs archived ($ARC_COUNT files)"

