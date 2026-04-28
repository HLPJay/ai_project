#!/bin/bash
# generate_music.sh - Step 2: 生成音乐
# 用法: ./generate_music.sh <项目目录>
#
# 输入: {项目目录}/audio/lyrics.txt
# 输出: {项目目录}/audio/song.mp3

set -e

# ── 清理函数（Ctrl+C 时也要删除临时文件）────────────────────────────────────
_music_cleanup() {
    [ -n "$_MUSIC_LYRICS_TMP" ] && rm -f "$_MUSIC_LYRICS_TMP"
}
trap _music_cleanup EXIT

PROJECT_DIR="${1:-}"

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ 用法: $0 <项目目录>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"   # 加载 API Token 配置
source "$SCRIPT_DIR/status_funcs.sh"

TOKEN="${MINIMAX_TOKEN:-}"
if [ -z "$TOKEN" ]; then
    echo "❌ MINIMAX_TOKEN 环境变量未设置"
    exit 1
fi

AUDIO_DIR="$PROJECT_DIR/audio"
LYRICS_FILE="$AUDIO_DIR/lyrics.txt"
OUTPUT_FILE="$AUDIO_DIR/song.mp3"

if [ ! -f "$LYRICS_FILE" ]; then
    echo "❌ 歌词文件不存在: $LYRICS_FILE"
    echo "   请先执行 Step ① 生成歌词"
    exit 1
fi

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [② music] $1" >> "$PROJECT_DIR/metadata/steps.log"
}

# ============================================================
# 子步骤 2: 读取 info.json（一次读取获取所有字段）
# ============================================================
check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

update_status "② music" "running" "reading metadata..."
log_step "starting"

INFO_JSON=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json', 'r') as f:
    info = json.load(f)
print(json.dumps({
    'theme': info.get('theme', ''),
    'song_title': info.get('song_title', ''),
    'style': info.get('style', ''),
    'music_style': info.get('music_style', ''),
    'mood': info.get('mood', ''),
    'language': info.get('language', ''),
    'reference': info.get('reference', ''),
    'style_tags': ','.join(info.get('style_tags', [])) if isinstance(info.get('style_tags'), list) else str(info.get('style_tags', ''))
}, ensure_ascii=False))
")

THEME=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['theme'])")
SONG_TITLE=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['song_title'])")
STYLE=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['style'])")
MUSIC_STYLE=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['music_style'])")
MUSIC_DETAIL=$(python3 -c "import sys; sys.path.insert(0,'$SCRIPT_DIR'); from style_map import get_music_prompt_details; print(get_music_prompt_details('$MUSIC_STYLE'))" 2>/dev/null || echo "")
if [ -n "$MUSIC_STYLE" ] && [ -z "$MUSIC_DETAIL" ]; then
    echo "   ⚠️ 警告: 音乐风格 '$MUSIC_STYLE' 不在 style_map.py 的 MUSIC_PROMPT_DETAILS 中，编曲细节为空，请检查拼写是否正确"
fi
MOOD=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['mood'])")
LANGUAGE=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['language'])")
REFERENCE=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['reference'])")
STYLE_TAGS=$(echo "$INFO_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['style_tags'])")

# MUSIC_PROMPT="${SONG_TITLE}，${STYLE_TAGS}，${MUSIC_STYLE}，${MOOD}，${LANGUAGE}，${REFERENCE}，${THEME}"
# [ -n "$MUSIC_DETAIL" ] && MUSIC_PROMPT="${MUSIC_PROMPT}。编曲：${MUSIC_DETAIL}"

# ============================================================
# 👇👇👇 这里是【音乐提示词增强】核心优化 👇👇👇
# ============================================================
MUSIC_PROMPT=""

[ -n "$SONG_TITLE" ] && MUSIC_PROMPT+="歌曲名：$SONG_TITLE，"
[ -n "$MOOD" ] && MUSIC_PROMPT+="情绪：$MOOD，"
[ -n "$MUSIC_STYLE" ] && MUSIC_PROMPT+="音乐风格：$MUSIC_STYLE，"
[ -n "$STYLE_TAGS" ] && MUSIC_PROMPT+="风格标签：$STYLE_TAGS，"
[ -n "$LANGUAGE" ] && MUSIC_PROMPT+="演唱语言：$LANGUAGE，"
[ -n "$THEME" ] && MUSIC_PROMPT+="主题：$THEME，"
[ -n "$REFERENCE" ] && MUSIC_PROMPT+="参考风格：$REFERENCE，"

# 追加专业音乐生成指令（关键增强）
MUSIC_PROMPT+="旋律流畅自然，节奏清晰，副歌抓耳，主歌舒缓，强弱层次分明，"
MUSIC_PROMPT+="人声清晰贴合歌词，编曲简洁不杂乱，适合儿童/治愈系MV背景音乐，"
MUSIC_PROMPT+="完整歌曲结构：主歌1 → 副歌 → 主歌2 → 副歌 → 尾奏"

# 追加编曲细节（来自 style_map）
[ -n "$MUSIC_DETAIL" ] && MUSIC_PROMPT+="，$MUSIC_DETAIL"

# ============================================================
# 👆👆👆 提示词增强结束 👆👆👆
# ============================================================

# ============================================================
# 子步骤 3: 读取歌词并预处理
# ============================================================
check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

update_status "② music" "running" "reading lyrics..."
log_step "reading lyrics from $LYRICS_FILE"

# 预处理歌词（去注释行，保留段落标记）
LYRICS=$(grep -v '^## ' "$LYRICS_FILE" | grep -v '^#' | grep -v '^$' | paste -sd ' ' -)

if [ -z "$LYRICS" ]; then
    update_status "② music" "failed" "lyrics file is empty"
    log_step "FAILED: lyrics file is empty"
    echo "❌ 歌词文件内容为空"
    exit 1
fi

# ============================================================
# 子步骤 3: 调用 API（带重试）
# ============================================================
check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

update_status "② music" "running" "calling music_generation API..."
log_step "calling MiniMax music_generation API (prompt: $MUSIC_PROMPT)..."

MAX_RETRIES=3
DELAY=2
ATTEMPT=1

while true; do
    # ★ 每次迭代前检查打断
    check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

    # 将歌词写入临时文件，用 env var 传参，避免特殊字符破坏 Python/JSON 结构
    _MUSIC_LYRICS_TMP=$(mktemp "${TMPDIR:-/tmp}/music_lyrics_XXXXXX.txt")
    printf '%s' "$LYRICS" > "$_MUSIC_LYRICS_TMP"
    _MUSIC_PAYLOAD=$(PROMPT_V="$MUSIC_PROMPT" LYRICS_TMP_V="$_MUSIC_LYRICS_TMP" \
        python3 - << 'PYEOF'
import json, os
with open(os.environ['LYRICS_TMP_V'], 'r', encoding='utf-8') as f:
    lyrics = f.read()
d = {
    'model': 'music-2.6',
    'prompt': os.environ['PROMPT_V'],
    'lyrics': lyrics,
    'is_instrumental': False
}
print(json.dumps(d, ensure_ascii=False))
PYEOF
)
    rm -f "$_MUSIC_LYRICS_TMP"
    RESPONSE=$(curl -s --noproxy '*' \
        --max-time 120 \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -X POST "https://api.minimaxi.com/v1/music_generation" \
        -d "$_MUSIC_PAYLOAD") \
        || { EXIT=$?; update_status "② music" "failed" "curl failed (exit $EXIT)"; log_step "FAILED: curl exit $EXIT"; exit 1; }
    if [ -z "$RESPONSE" ]; then
        update_status "② music" "failed" "empty API response"; log_step "FAILED: empty API response"; exit 1
    fi
    API_STATUS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('base_resp', {}).get('status_code', -1))
except:
    print(-1)
" 2>/dev/null)

    if [ "$API_STATUS" = "0" ] && echo "$RESPONSE" | grep -q "data"; then
        update_status "② music" "running" "API call succeeded"
        log_step "API call succeeded"
        # ── LLM 日志记录 ───────────────────────────────
        # ── LLM 日志记录（通过临时文件传递 RESPONSE，避免 heredoc 变量不可达） ──
        # ── LLM 日志记录（通过临时文件传递 RESPONSE，避免 heredoc 变量不可达） ──
        _MUSIC_RESP_TMP=$(mktemp "${TMPDIR:-/tmp}/music_resp_XXXXXX.json")
        printf '%s' "$RESPONSE" > "$_MUSIC_RESP_TMP"
        SCRIPT_DIR_V="$SCRIPT_DIR" PROJECT_DIR="$PROJECT_DIR" _MUSIC_RESP_TMP="$_MUSIC_RESP_TMP" _MUSIC_PAYLOAD="$_MUSIC_PAYLOAD" python3 - << 'PYEOF'
import json, os, sys
resp_file = os.environ.get('_MUSIC_RESP_TMP', '')
project_dir = os.environ.get('PROJECT_DIR', '')
script_dir = os.environ.get('SCRIPT_DIR_V', '/home/hlp/.openclaw/skills/music-to-mv/scripts')
try:
    sys.path.insert(0, script_dir)
    with open(resp_file, 'r', encoding='utf-8') as f:
        resp = f.read()
    from llm_logger import log_llm
    payload_str = os.environ.get('_MUSIC_PAYLOAD', '')
    try:
        payload = json.loads(payload_str)
        prompt_text = payload.get('prompt', '')
        lyrics_preview = payload.get('lyrics', '')[:100]
    except:
        prompt_text = payload_str
        lyrics_preview = ''
    try:
        resp_data = json.loads(resp)
        audio_hex_len = len(resp_data.get('data', {}).get('audio', ''))
        resp_summary = {'audio_hex_length': audio_hex_len}
    except:
        resp_summary = {'raw': resp[:200]}
    log_llm(project_dir, "music", "MiniMax-music_generation",
            prompt_text,
            resp_summary)
except ImportError:
    print("⚠️ llm_logger 未安装，跳过音乐日志记录")
except Exception as e:
    print(f"⚠️ 音乐 LLM 日志写入失败: {e}")
PYEOF
        rm -f "$_MUSIC_RESP_TMP"
        break
    fi

    if [ $ATTEMPT -ge $MAX_RETRIES ]; then
        ERROR_MSG=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('base_resp', {}).get('status_msg', 'Unknown'))
except:
    print('API failed after $MAX_RETRIES attempts')
" 2>/dev/null)
        update_status "② music" "failed" "$ERROR_MSG"
        log_step "FAILED: $ERROR_MSG"
        echo "❌ 音乐生成失败: $ERROR_MSG"
        exit 1
    fi

    update_status "② music" "running" "API failed, retry ${ATTEMPT}/${MAX_RETRIES} in ${DELAY}s..."
    log_step "API failed (attempt $ATTEMPT/$MAX_RETRIES), retrying in ${DELAY}s..."

    # ★ 把 sleep 改为短间隔轮询，每秒检查一次打断
    REMAINING=$DELAY
    while [ $REMAINING -gt 0 ]; do
        check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }
        sleep 1
        REMAINING=$((REMAINING - 1))
    done

    DELAY=$((DELAY * 2))
    ATTEMPT=$((ATTEMPT + 1))
done

# ============================================================
# 子步骤 4: 解码并保存音频
# ============================================================
check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

update_status "② music" "running" "decoding audio..."
log_step "decoding hex to MP3..."

AUDIO_HEX=$(echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('data', {}).get('audio', ''))
" 2>/dev/null)

if [ -z "$AUDIO_HEX" ]; then
    update_status "② music" "failed" "no audio data in API response"
    log_step "FAILED: no audio data in response"
    echo "❌ API 响应中无音频数据"
    exit 1
fi

echo "$AUDIO_HEX" | python3 -c "
import sys
hex_data = sys.stdin.read().strip()
audio_bytes = bytes.fromhex(hex_data)
with open('$OUTPUT_FILE', 'wb') as f:
    f.write(audio_bytes)
size_mb = len(audio_bytes) / 1024 / 1024
print(f'SAVED|{size_mb:.1f}')
"

FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

# ============================================================
# 子步骤 5: 获取时长并更新 info.json
# ============================================================
check_interrupt || { update_status "② music" "interrupted" "stopped by user"; exit 0; }

update_status "② music" "running" "updating metadata..."
log_step "updating info.json..."

ffprobe_cmd=$(command -v ffprobe || echo "")
if [ -n "$ffprobe_cmd" ]; then
    DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT_FILE" 2>/dev/null | cut -d. -f1 || echo "0")
else
    DURATION="0"
fi

PY_TMP=$(mktemp /tmp/update_music_info_XXXXXX.py)
PROJECT_DIR_V="$PROJECT_DIR" DURATION_V="$DURATION" \
    python3 - << 'PYEOF'
import json, os

info_path = os.environ['PROJECT_DIR_V'] + '/metadata/info.json'
duration = int(os.environ['DURATION_V']) if os.environ['DURATION_V'] else 0

with open(info_path, 'r', encoding='utf-8') as f:
    info = json.load(f)

info['audio_duration_sec'] = duration

with open(info_path, 'w', encoding='utf-8') as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
PYEOF

# ============================================================
# 完成
# ============================================================
update_status "② music" "completed" "${FILE_SIZE}, ${DURATION}s"
notify_telegram "🎵 音乐生成完成：${SONG_TITLE}（${FILE_SIZE}，${DURATION}s）"
log_step "completed: ${FILE_SIZE}, ${DURATION}s"
echo "✅ 音乐生成完成: ${FILE_SIZE}, ${DURATION}s"
