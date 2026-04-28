#!/bin/bash
# align_lyrics.sh - Step 3: 歌词时间轴对齐
# 用法: ./align_lyrics.sh <项目目录>
#
# 正确流程:
#   ① 人声分离（Demucs）→ ② Whisper 转写 → ③ 两遍对齐 → ④ 后处理修正 → ⑤ 生成 SRT
#
# 输入: {项目目录}/audio/song.mp3, {项目目录}/audio/lyrics.txt
# 输出: {项目目录}/audio/song.srt

set -e

PROJECT_DIR="${1:-}"
ALIGN_MODE="auto"      # auto | manual
MANUAL_SRT=""        # path to manually provided SRT file

while [ -n "$1" ]; do
    case "$1" in
        --align-mode)
            ALIGN_MODE="$2"; shift 2 ;;
        --srt-file)
            MANUAL_SRT="$2"; shift 2 ;;
        -*) shift ;;
        *) PROJECT_DIR="$1"; shift ;;
    esac
done

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ 用法: $0 <项目目录> [--align-mode auto|manual] [--srt-file <path>]"
    echo ""
    echo "  --align-mode auto   全自动：Demucs人声分离 + Whisper转写 + 对齐（默认）"
    echo "  --align-mode manual 手动模式：跳过ASR，直接用提供的 SRT 文件（不做对齐）"
    echo "  --srt-file <path>   配合 --align-mode manual 使用，指定SRT文件路径"
    echo ""
    echo "示例："
    echo "  $0 ~/mv/项目名                  # 全自动"
        echo "  $0 ~/mv/项目名 --align-mode manual --srt-file /tmp/lyrics.srt"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/status_funcs.sh"

AUDIO_DIR="$PROJECT_DIR/audio"
AUDIO_FILE="$AUDIO_DIR/song.mp3"
LYRICS_FILE="$AUDIO_DIR/lyrics.txt"
OUTPUT_SRT="$AUDIO_DIR/song.srt"
TEMP_DIR="$PROJECT_DIR/temp"

if [ ! -f "$AUDIO_FILE" ]; then
    echo "❌ 音频文件不存在: $AUDIO_FILE"
    echo "   请先执行 Step ② 生成音乐"
    exit 1
fi

if [ ! -f "$LYRICS_FILE" ]; then
    echo "❌ 歌词文件不存在: $LYRICS_FILE"
    exit 1
fi

mkdir -p "$TEMP_DIR"

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [③ align] $1" >> "$PROJECT_DIR/metadata/steps.log"
}

# ============================================================
# 子步骤 1: 检查打断
# ============================================================
check_interrupt || { update_status "③ align" "interrupted" "stopped by user"; exit 0; }

update_status "③ align" "running" "starting..."
log_step "starting"

# ============================================================
# 子步骤 2: 人声分离（Demucs）
# ============================================================
check_interrupt || { update_status "③ align" "interrupted" "stopped by user"; exit 0; }

VOCAL_FILE=""
DEMUCS_DONE=""

if [ "$ALIGN_MODE" = "manual" ]; then
    # ── 手动模式：跳过 ASR，直接复制指定的 SRT 文件 ──
    if [ -z "$MANUAL_SRT" ]; then
        echo "❌ --align-mode manual 需要配合 --srt-file 指定 SRT 文件路径"
        exit 1
    fi
    if [ ! -f "$MANUAL_SRT" ] || [ ! -s "$MANUAL_SRT" ]; then
        echo "❌ SRT 文件不存在或为空：$MANUAL_SRT"
        exit 1
    fi
    echo "⏭️ [③ align] 跳过 Demucs/Whisper（--align-mode manual）"
    echo "   复制手动 SRT：$MANUAL_SRT → $OUTPUT_SRT"
    cp "$MANUAL_SRT" "$OUTPUT_SRT"
    log_step "[③ align] manual mode: using provided SRT"
    echo "✅ SRT 准备完成，跳过对齐"
    # 直接跳到完成
    update_status "③ align" "completed" "manual SRT (no alignment)"
    echo ""
    echo "=================================================="
    echo "✅ ③ 对齐完成（手动模式）"
    echo "=================================================="
    exit 0
else
if command -v demucs > /dev/null 2>&1; then
    update_status "③ align" "running" "vocal separation with Demucs..."
    log_step "Demucs vocal separation starting..."

    DEMUCS_OUT="$TEMP_DIR/demucs_out"
    mkdir -p "$DEMUCS_OUT"

    # 用 --two-stems vocals 只分离人声，最快
    if demucs --two-stems vocals \
        -o "$DEMUCS_OUT" \
        --device cpu \
        "$AUDIO_FILE" > "$TEMP_DIR/demucs.log" 2>&1; then

        # 查找分离后的人声文件
        # Demucs 输出路径: {out}/{model}/{stem}/{filename}/vocals.wav
        BASENAME=$(basename "$AUDIO_FILE" .mp3)
        CANDIDATE="$DEMUCS_OUT/htdemucs/separated/${BASENAME}/vocals.wav"

        if [ -f "$CANDIDATE" ]; then
            VOCAL_FILE="$CANDIDATE"
            DEMUCS_DONE="yes"
            log_step "Demucs done: vocals extracted"
            echo "🔊 人声分离完成: $VOCAL_FILE"
        fi
    else
        log_step "Demucs failed, fallback to original audio"
        echo "⚠️ Demucs 失败，使用原始音频"
    fi
else
    log_step "Demucs not available, using original audio"
    echo "ℹ️ Demucs 未安装，使用原始音频直接转写"
fi

# 若无人声分离，使用原始音频
[ -z "$VOCAL_FILE" ] && VOCAL_FILE="$AUDIO_FILE"

# ============================================================
# 子步骤 3: Whisper 转写
# ============================================================
check_interrupt || { update_status "③ align" "interrupted" "stopped by user"; exit 0; }

update_status "③ align" "running" "Whisper transcribing..."
log_step "Whisper transcription starting..."

WHISPER_JSON="$TEMP_DIR/song.json"

# 计算音频文件 hash（用人声文件）
AUDIO_HASH=$(md5sum "$VOCAL_FILE" 2>/dev/null | cut -d' ' -f1 \
    || sha1sum "$VOCAL_FILE" 2>/dev/null | cut -d' ' -f1 \
    || echo "nohash")

CACHED_HASH=$(python3 -c "
import json, sys
try:
    with open('$WHISPER_JSON') as f: d=json.load(f)
    print(d.get('_source_hash',''))
except Exception: pass
" 2>/dev/null)

if [ -f "$WHISPER_JSON" ] && [ -s "$WHISPER_JSON" ] && \
   [ "$AUDIO_HASH" = "$CACHED_HASH" ] && [ "$CACHED_HASH" != "nohash" ]; then
    log_step "Whisper cache hit (hash=$AUDIO_HASH), skipping"
    echo "⏭️ Whisper 转写跳过（缓存有效）"
else
    [ -f "$WHISPER_JSON" ] && log_step "Whisper cache miss, re-transcribing..."

    # 尝试 small 模型，若 OOM 则 fallback 到 base
    if ! whisper "$VOCAL_FILE" \
        --model small \
        --language zh \
        --output_format json \
        --output_dir "$TEMP_DIR" \
        --verbose False > "$TEMP_DIR/whisper.log" 2>&1; then

        log_step "Whisper small failed, trying base model..."
        echo "⚠️ Whisper small OOM，尝试 base 模型..."

        if ! whisper "$VOCAL_FILE" \
            --model base \
            --language zh \
            --output_format json \
            --output_dir "$TEMP_DIR" \
            --verbose False > "$TEMP_DIR/whisper_base.log" 2>&1; then
            update_status "③ align" "failed" "Whisper transcription failed"
            log_step "FAILED: Whisper transcription failed"
            echo "❌ Whisper 转写失败（small 和 base 均失败），详见 whisper 日志"
            exit 1
        fi
    fi

    if [ ! -f "$WHISPER_JSON" ]; then
        update_status "③ align" "failed" "Whisper output not found"
        log_step "FAILED: song.json not found"
        echo "❌ Whisper 未生成输出文件"
        exit 1
    fi

    # 写入 source hash
    python3 -c "
import json
with open('$WHISPER_JSON') as f: d=json.load(f)
d['_source_hash']='$AUDIO_HASH'
with open('$WHISPER_JSON','w') as f: json.dump(d, f, ensure_ascii=False)
" 2>/dev/null || true
fi

update_status "③ align" "running" "Whisper transcription completed"
log_step "Whisper transcription completed"
fi


# ============================================================
# 子步骤 4: 解析 + 两遍对齐 + 后处理修正 + 生成 SRT
# ============================================================
check_interrupt || { update_status "③ align" "interrupted" "stopped by user"; exit 0; }

update_status "③ align" "running" "aligning lyrics to timestamps..."
log_step "alignment starting..."

ALIGN_RESULT=$(PROJECT_DIR_V="$PROJECT_DIR" python3 - << 'PYEOF'
import json
import re
from difflib import SequenceMatcher
import os

PROJECT_DIR = os.environ['PROJECT_DIR_V']
AUDIO_DIR = PROJECT_DIR + '/audio'
TEMP_DIR = PROJECT_DIR + '/temp'
OUTPUT_SRT = AUDIO_DIR + '/song.srt'
WHISPER_JSON = TEMP_DIR + '/song.json'

# ── 读取歌词 ────────────────────────────────────────────────
with open(AUDIO_DIR + '/lyrics.txt', 'r', encoding='utf-8') as f:
    lyrics_lines = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith('## ')
    ]
# 去掉 [Intro] [Verse] 等段落标记
clean_lyrics = [
    line for line in lyrics_lines
    if not re.match(r'^\[.+\]$', line)
]

# ── 读取 Whisper 识别结果 ───────────────────────────────────
with open(WHISPER_JSON, 'r', encoding='utf-8') as f:
    whisper_data = json.load(f)

whisper_segments = whisper_data.get('segments', [])
asr_entries = [(seg['start'], seg['end'], seg['text'].strip()) for seg in whisper_segments]

# ── 相似度函数 ───────────────────────────────────────────────
def similarity(a, b):
    a = re.sub(r'[^\w\s]', '', a.lower())
    b = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def chinese_overlap(a, b):
    ca = set(re.findall(r'[\u4e00-\u9fff]', a))
    cb = set(re.findall(r'[\u4e00-\u9fff]', b))
    return len(ca & cb) / len(ca) if ca else 0

def score_pair(text, lyric):
    return max(similarity(text, lyric), chinese_overlap(text, lyric) * 1.2)

# ── 两遍对齐算法 ────────────────────────────────────────────
M, N = len(clean_lyrics), len(asr_entries)
THRESHOLD1 = 0.25   # 第一遍阈值
THRESHOLD2 = 0.20   # 第二遍阈值（更宽松）

lyric_assigned = [False] * M
asr_assigned = [False] * N
alignments = {}   # lyric_idx -> (start, end, total_score, count)

# ── 第一遍：顺序贪心匹配 ────────────────────────────────────
lyric_idx = 0
for i, (start, end, text) in enumerate(asr_entries):
    if lyric_idx >= M:
        break
    if len(text) < 2:
        continue

    best_score = 0
    best_li = -1
    for j in range(lyric_idx, min(lyric_idx + 8, M)):
        if lyric_assigned[j]:
            continue
        s = score_pair(text, clean_lyrics[j])
        if s > best_score:
            best_score = s
            best_li = j

    if best_score >= THRESHOLD1 and best_li >= 0:
        if best_li in alignments:
            a = alignments[best_li]
            alignments[best_li] = (a[0], end, a[2] + best_score, a[3] + 1)
        else:
            alignments[best_li] = (start, end, best_score, 1)
        lyric_assigned[best_li] = True
        asr_assigned[i] = True
        lyric_idx = best_li + 1

# ── 第二遍：补漏未匹配的歌词 ────────────────────────────────
unassigned_asr = [(i, asr_entries[i][0], asr_entries[i][1], asr_entries[i][2])
                   for i in range(N) if not asr_assigned[i]]

for j in range(M):
    if lyric_assigned[j]:
        continue
    best_score = 0
    best_entry = None
    for _, start, end, text in unassigned_asr:
        s = score_pair(text, clean_lyrics[j])
        if s > best_score:
            best_score = s
            best_entry = (start, end)
    if best_score >= THRESHOLD2 and best_entry:
        start, end = best_entry
        if j in alignments:
            a = alignments[j]
            alignments[j] = (a[0], end, a[2] + best_score, a[3] + 1)
        else:
            alignments[j] = (start, end, best_score, 1)
        lyric_assigned[j] = True

# ── 后处理修正 ──────────────────────────────────────────────
# 修正1: 若第1行歌词未匹配，分配第一个有效 ASR 片段时间
if not lyric_assigned[0]:
    for i, (start, end, text) in enumerate(asr_entries):
        if len(text) >= 2:
            alignments[0] = (start, end, 0.0, 0)
            lyric_assigned[0] = True
            log_msg = f"post-fix: line 1 assigned to first ASR segment ({start:.2f}s)"
            print(log_msg, file=open(TEMP_DIR + '/steps.log', 'a'))
            break

# 修正2: 填充跳行（连续未匹配的歌词行，分配平均间隔时间）
for j in range(1, M):
    if not lyric_assigned[j]:
        # 找前后已分配的歌词行
        prev_li = -1
        next_li = -1
        for k in range(j-1, -1, -1):
            if lyric_assigned[k]:
                prev_li = k
                break
        for k in range(j+1, M):
            if lyric_assigned[k]:
                next_li = k
                break

        if prev_li >= 0 and next_li >= 0:
            prev_start, prev_end = alignments[prev_li][0], alignments[prev_li][1]
            next_start, _ = alignments[next_li][0], alignments[next_li][1]
            # 均分插值
            gap = (next_start - prev_end) / (next_li - prev_li + 1)
            fill_start = prev_end + gap * (j - prev_li)
            fill_end = fill_start + (prev_end - prev_start)  # 用前一行的时长
            alignments[j] = (fill_start, fill_end, 0.0, 0)
            lyric_assigned[j] = True
            print(f"post-fix: line {j+1} interpolated to {fill_start:.2f}s", file=open(TEMP_DIR + '/steps.log', 'a'))

# ── 生成 SRT ────────────────────────────────────────────────
def fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    sec = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

srt_parts = []
for li in sorted(alignments.keys()):
    start, end, _, _ = alignments[li]
    srt_parts.append(f"{len(srt_parts)+1}\n{fmt_time(start)} --> {fmt_time(end)}\n{clean_lyrics[li]}\n\n")

with open(OUTPUT_SRT, 'w', encoding='utf-8') as f:
    f.write("".join(srt_parts))

matched = sum(1 for li in range(M) if li in alignments)
print(f"ALIGNED|{matched}|{M}|{len(srt_parts)}")
PYEOF
)

ALIGNED_COUNT=$(echo "$ALIGN_RESULT" | grep "^ALIGNED" | cut -d'|' -f2)
TOTAL=$(echo "$ALIGN_RESULT" | grep "^ALIGNED" | cut -d'|' -f3)
SRT_ENTRIES=$(echo "$ALIGN_RESULT" | grep "^ALIGNED" | cut -d'|' -f4)

# 打印后处理信息（若有）
echo "$ALIGN_RESULT" | grep -v "^ALIGNED" | while read -r line; do
    echo "   $line"
done

update_status "③ align" "running" "alignment completed"
log_step "alignment completed"

# ============================================================
# 子步骤 5: 更新 info.json（修复 heredoc 注入风险）
# ============================================================
check_interrupt || { update_status "③ align" "interrupted" "stopped by user"; exit 0; }

update_status "③ align" "running" "updating metadata..."

PROJECT_DIR_V="$PROJECT_DIR" ALIGNED_V="$ALIGNED_COUNT" TOTAL_V="$TOTAL" SRT_V="$SRT_ENTRIES" \
    python3 - << 'PYEOF'
import json, os

info_path = os.environ['PROJECT_DIR_V'] + '/metadata/info.json'
aligned_count = int(os.environ['ALIGNED_V'])
total = int(os.environ['TOTAL_V'])
srt_entries = int(os.environ['SRT_V'])

with open(info_path, 'r', encoding='utf-8') as f:
    info = json.load(f)

info['alignment'] = {
    'aligned_lines': aligned_count,
    'total_lyrics_lines': total,
    'srt_entries': srt_entries
}

with open(info_path, 'w', encoding='utf-8') as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
PYEOF

# ============================================================
# 完成
# ============================================================
update_status "③ align" "completed" "${ALIGNED_COUNT}/${TOTAL} lines aligned"
log_step "completed: ${ALIGNED_COUNT}/${TOTAL} lines aligned"
echo "✅ 对齐完成: ${ALIGNED_COUNT}/${TOTAL} 行已对齐"
