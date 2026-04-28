#!/bin/bash
# generate_lyrics.sh - Step 1: 生成歌词
# 用法: ./generate_lyrics.sh <项目目录>
#
# theme 从项目目录的 metadata/info.json 中读取
# 输入: 无
# 输出: {项目目录}/audio/lyrics.txt

set -e

# ── 清理函数（Ctrl+C 时也要删除临时文件）────────────────────────────────────
_tmp_files="$_LYRICS_TMP $PY_TMP"
_cleanup() {
    rm -f $_tmp_files 2>/dev/null
}
trap _cleanup EXIT

PROJECT_DIR="${1:-}"

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ 用法: $0 <项目目录>"
    exit 1
fi

# 从 info.json 读取 theme
THEME=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(d.get('theme', ''))
" 2>/dev/null)

if [ -z "$THEME" ]; then
    echo "❌ 无法从 $PROJECT_DIR/metadata/info.json 读取 theme"
    echo "   请先运行 init_project.sh 创建项目"
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
mkdir -p "$AUDIO_DIR"

# 读取所有偏好参数（从 info.json），用 shlex.quote 确保每个值 shell 安全
eval "$(INFO_DIR="$PROJECT_DIR" python3 - << 'PYEOF'
import json, shlex, os
with open(os.environ['INFO_DIR'] + '/metadata/info.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
for key, var in [('style','STYLE'),('music_style','MUSIC_STYLE'),
                 ('mood','MOOD'),('language','LANGUAGE'),('reference','REFERENCE')]:
    print(f"{var}={shlex.quote(d.get(key, ''))}")
PYEOF
)"

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [① lyrics] $1" >> "$PROJECT_DIR/metadata/steps.log"
}

# ============================================================
# 子步骤 1: 检查打断
# ============================================================
check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

update_status "① lyrics" "running" "starting..."
log_step "starting"

# ============================================================
# 子步骤 2: 调用 API（带重试 + 轮询打断）
# ============================================================
check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

update_status "① lyrics" "running" "calling API..."
log_step "calling MiniMax lyrics_generation API..."

MAX_RETRIES=3
DELAY=2
ATTEMPT=1

while true; do
    # ★ 每次迭代前检查打断
    check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

    # 用 Python 构建 payload，避免含特殊字符时破坏 JSON 结构
    _PAYLOAD=$(THEME_V="$THEME" STYLE_V="$STYLE" MUSIC_V="$MUSIC_STYLE" \
        MOOD_V="$MOOD" LANG_V="$LANGUAGE" REF_V="$REFERENCE" \
        python3 - << 'PYEOF'
import json, os
# parts = [os.environ[k] for k in ('THEME_V','STYLE_V','MUSIC_V','MOOD_V','LANG_V','REF_V') if os.environ[k]]
# print(json.dumps({"mode": "write_full_song", "prompt": "，".join(parts)}, ensure_ascii=False))

# 读取用户自定义全部参数
theme = os.environ.get('THEME_V', '')
style = os.environ.get('STYLE_V', '')
music_style = os.environ.get('MUSIC_V', '')
mood = os.environ.get('MOOD_V', '')
lang = os.environ.get('LANG_V', '')
ref = os.environ.get('REF_V', '')

prompt_parts = []
if theme:
    prompt_parts.append(f"创作主题：{theme}")
if style:
    prompt_parts.append(f"整体艺术风格：{style}")
if music_style:
    prompt_parts.append(f"音乐曲风：{music_style}")
if mood:
    prompt_parts.append(f"整体情绪氛围：{mood}")
if lang:
    prompt_parts.append(f"创作语言：{lang}")
if ref:
    prompt_parts.append(f"参考创作风格：{ref}")

# 通用硬性规范（无场景偏向，全风格通用）
prompt_parts.append("严格遵循标准流行歌曲结构：主歌1、副歌、主歌2、副歌、收尾段落")
prompt_parts.append("句式长短均衡，韵律协调，押韵自然，语句通顺适合演唱")
prompt_parts.append("紧扣核心主题，意境统一，逻辑连贯，无杂乱无关内容")
prompt_parts.append("副歌段落强化记忆点，段落划分清晰，层次分明")

final_prompt = "，".join([p for p in prompt_parts if p])

print(json.dumps({
    "mode": "write_full_song",
    "prompt": final_prompt
}, ensure_ascii=False))

PYEOF
)
    RESPONSE=$(curl -s --noproxy '*' \
        --max-time 60 \
        --request POST \
        --url "https://api.minimaxi.com/v1/lyrics_generation" \
        --header "Authorization: Bearer $TOKEN" \
        --header "Content-Type: application/json" \
        --data "$_PAYLOAD") \
        || { EXIT=$?; update_status "① lyrics" "failed" "curl failed (exit $EXIT)"; log_step "FAILED: curl exit $EXIT"; exit 1; }

    # 检查 API 响应
    if [ -z "$RESPONSE" ]; then
        update_status "① lyrics" "failed" "empty API response"; log_step "FAILED: empty API response"; exit 1
    fi
    API_STATUS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('base_resp', {}).get('status_code', -1))
except:
    print(-1)
" 2>/dev/null)

    if [ "$API_STATUS" = "0" ] && [ -n "$RESPONSE" ]; then
        update_status "① lyrics" "running" "API call succeeded"
        log_step "API call succeeded"
        # ── LLM 日志记录 ───────────────────────────────
        # ── LLM 日志记录（通过临时文件传递 RESPONSE，避免 heredoc 变量不可达） ──
        _LYRICS_RESP_TMP=$(mktemp "${TMPDIR:-/tmp}/lyrics_resp_XXXXXX.json")
        printf '%s' "$RESPONSE" > "$_LYRICS_RESP_TMP"
        PROJECT_DIR="$PROJECT_DIR" SCRIPT_DIR="$SCRIPT_DIR" _LYRICS_RESP_TMP="$_LYRICS_RESP_TMP" _PAYLOAD="$_PAYLOAD" \
            python3 - << 'PYEOF'
import json, os, sys
resp_file = os.environ.get('_LYRICS_RESP_TMP', '')
project_dir = os.environ.get('PROJECT_DIR', '')
script_dir = os.environ.get('SCRIPT_DIR', '/home/hlp/.openclaw/skills/music-to-mv/scripts')
try:
    sys.path.insert(0, script_dir)
    with open(resp_file, 'r', encoding='utf-8') as f:
        resp = f.read()
    from llm_logger import log_llm
    payload_str = os.environ.get('_PAYLOAD', '')
    try:
        payload = json.loads(payload_str)
        prompt_text = payload.get('prompt', '')
    except:
        prompt_text = payload_str
    try:
        resp_data = json.loads(resp)
        resp_summary = {
            'song_title': resp_data.get('song_title', ''),
            'style_tags': resp_data.get('style_tags', ''),
            'lyrics_length': len(resp_data.get('lyrics', '')),
        }
    except:
        resp_summary = {'raw': resp[:200]}
    log_llm(project_dir, "lyrics", "MiniMax-lyrics_generation", prompt_text, resp_summary)
except ImportError:
    print("⚠️ llm_logger 未安装，跳过歌词日志记录")
except Exception as e:
    print(f"⚠️ 歌词 LLM 日志写入失败: {e}")
PYEOF
        rm -f "$_LYRICS_RESP_TMP"
        break
    fi

    if [ $ATTEMPT -ge $MAX_RETRIES ]; then
        ERROR_MSG=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('base_resp', {}).get('status_msg', 'Unknown error'))
except:
    print('API call failed after $MAX_RETRIES attempts')
" 2>/dev/null)
        update_status "① lyrics" "failed" "$ERROR_MSG"
        log_step "FAILED: $ERROR_MSG"
        echo "❌ 歌词生成失败: $ERROR_MSG"
        exit 1
    fi

    update_status "① lyrics" "running" "API call failed, retry ${ATTEMPT}/${MAX_RETRIES} in ${DELAY}s..."
    log_step "API call failed (attempt $ATTEMPT/$MAX_RETRIES), retrying in ${DELAY}s..."

    # ★ 把 sleep 改为短间隔轮询，每秒检查一次打断
    REMAINING=$DELAY
    while [ $REMAINING -gt 0 ]; do
        check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }
        sleep 1
        REMAINING=$((REMAINING - 1))
    done

    DELAY=$((DELAY * 2))
    ATTEMPT=$((ATTEMPT + 1))
done

# ============================================================
# 子步骤 3: 解析响应
# ============================================================
check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

update_status "① lyrics" "running" "parsing response..."
log_step "parsing API response..."

PARSED=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(json.dumps({
        'title': d.get('song_title', 'Untitled'),
        'tags': d.get('style_tags', ''),
        'lyrics': d.get('lyrics', '')
    }, ensure_ascii=False))
except Exception as e:
    print('PARSE_ERROR:' + str(e))
" 2>/dev/null)

if echo "$PARSED" | grep -q "PARSE_ERROR:"; then
    ERROR_MSG=$(echo "$PARSED" | sed 's/PARSE_ERROR://')
    update_status "① lyrics" "failed" "Invalid API response: $ERROR_MSG"
    log_step "FAILED: Invalid API response: $ERROR_MSG"
    echo "❌ 响应解析失败: $ERROR_MSG"
    exit 1
fi

SONG_TITLE=$(echo "$PARSED" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])")
STYLE_TAGS=$(echo "$PARSED" | python3 -c "import sys,json; print(json.load(sys.stdin)['tags'])")
LYRICS=$(echo "$PARSED" | python3 -c "import sys,json; print(json.load(sys.stdin)['lyrics'])")

# ============================================================
# 子步骤 4: 写入 lyrics.txt（防止变量展开）
# ============================================================
check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

update_status "① lyrics" "running" "writing lyrics.txt..."
log_step "writing lyrics.txt..."

LYRICS_FILE="$AUDIO_DIR/lyrics.txt"

# 将歌词内容写入临时文件，再通过 env var 传递元数据，避免特殊字符破坏 shell
_LYRICS_TMP=$(mktemp "${TMPDIR:-/tmp}/lyrics_XXXXXX.txt")
printf '%s' "$LYRICS" > "$_LYRICS_TMP"

SONG_TITLE_V="$SONG_TITLE" STYLE_TAGS_V="$STYLE_TAGS" \
    THEME_V="$THEME" LYRICS_FILE_V="$LYRICS_FILE" LYRICS_TMP_V="$_LYRICS_TMP" \
    python3 - << 'PYEOF'
import os
title      = os.environ['SONG_TITLE_V']
tags       = os.environ['STYLE_TAGS_V']
theme      = os.environ['THEME_V']
lyrics_dst = os.environ['LYRICS_FILE_V']
with open(os.environ['LYRICS_TMP_V'], 'r', encoding='utf-8') as f:
    lyrics = f.read()
with open(lyrics_dst, 'w', encoding='utf-8') as f:
    f.write(f"## {title}\n")
    f.write(f"## Tags: {tags}\n")
    f.write(f"## Theme: {theme}\n")
    f.write("## Generated by MiniMax Lyrics Generation API\n\n")
    f.write(lyrics)
PYEOF
rm -f "$_LYRICS_TMP"

# ============================================================
# 子步骤 5: 更新 info.json
# ============================================================
check_interrupt || { update_status "① lyrics" "interrupted" "stopped by user"; exit 0; }

update_status "① lyrics" "running" "updating metadata..."
log_step "updating info.json..."

# Write to temp file to avoid heredoc sys.argv issue
PY_TMP=$(mktemp /tmp/update_info_XXXXXX.py)
PROJECT_DIR_V="$PROJECT_DIR" SONG_TITLE_V="$SONG_TITLE" STYLE_TAGS_V="$STYLE_TAGS" THEME_V="$THEME" \
    python3 - << 'PYEOF'
import json, os

info_path = os.environ['PROJECT_DIR_V'] + '/metadata/info.json'
song_title = os.environ['SONG_TITLE_V']
style_tags = os.environ['STYLE_TAGS_V']
theme = os.environ['THEME_V']

with open(info_path, 'r', encoding='utf-8') as f:
    info = json.load(f)

info['song_title'] = song_title
info['style_tags'] = style_tags.split(',') if style_tags else []
info['theme'] = theme

with open(info_path, 'w', encoding='utf-8') as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
PYEOF

# ============================================================
# 完成
# ============================================================
update_status "① lyrics" "completed" "title='$SONG_TITLE', tags='$STYLE_TAGS'"
log_step "completed: title='$SONG_TITLE', tags='$STYLE_TAGS'"
echo "✅ 歌词生成完成: $SONG_TITLE"
