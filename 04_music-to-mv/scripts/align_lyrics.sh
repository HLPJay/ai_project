#!/bin/bash
# align_lyrics.sh - Step 3: 姝岃瘝鏃堕棿杞村榻?
# 鐢ㄦ硶: ./align_lyrics.sh <椤圭洰鐩綍>
#
# 姝ｇ‘娴佺▼:
#   鈶?浜哄０鍒嗙锛圖emucs锛夆啋 鈶?Whisper 杞啓 鈫?鈶?涓ら亶瀵归綈 鈫?鈶?鍚庡鐞嗕慨姝?鈫?鈶?鐢熸垚 SRT
#
# 杈撳叆: {椤圭洰鐩綍}/audio/song.mp3, {椤圭洰鐩綍}/audio/lyrics.txt
# 杈撳嚭: {椤圭洰鐩綍}/audio/song.srt

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
    echo "鉂?鐢ㄦ硶: $0 <椤圭洰鐩綍> [--align-mode auto|manual] [--srt-file <path>]"
    echo ""
    echo "  --align-mode auto   鍏ㄨ嚜鍔細Demucs浜哄０鍒嗙 + Whisper杞啓 + 瀵归綈锛堥粯璁わ級"
    echo "  --align-mode manual 鎵嬪姩妯″紡锛氳烦杩嘇SR锛岀洿鎺ョ敤鎻愪緵鐨?SRT 鏂囦欢锛堜笉鍋氬榻愶級"
    echo "  --srt-file <path>   閰嶅悎 --align-mode manual 浣跨敤锛屾寚瀹歋RT鏂囦欢璺緞"
    echo ""
    echo "绀轰緥锛?
    echo "  $0 ~/mv/椤圭洰鍚?                 # 鍏ㄨ嚜鍔?
        echo "  $0 ~/mv/椤圭洰鍚?--align-mode manual --srt-file /tmp/lyrics.srt"
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
    echo "鉂?闊抽鏂囦欢涓嶅瓨鍦? $AUDIO_FILE"
    echo "   璇峰厛鎵ц Step 鈶?鐢熸垚闊充箰"
    exit 1
fi

if [ ! -f "$LYRICS_FILE" ]; then
    echo "鉂?姝岃瘝鏂囦欢涓嶅瓨鍦? $LYRICS_FILE"
    exit 1
fi

mkdir -p "$TEMP_DIR"

log_step() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] [鈶?align] $1" >> "$PROJECT_DIR/metadata/steps.log"
}

# ============================================================
# 瀛愭楠?1: 妫€鏌ユ墦鏂?
# ============================================================
check_interrupt || { update_status "鈶?align" "interrupted" "stopped by user"; exit 0; }

update_status "鈶?align" "running" "starting..."
log_step "starting"

# ============================================================
# 瀛愭楠?2: 浜哄０鍒嗙锛圖emucs锛?
# ============================================================
check_interrupt || { update_status "鈶?align" "interrupted" "stopped by user"; exit 0; }

VOCAL_FILE=""
DEMUCS_DONE=""

if [ "$ALIGN_MODE" = "manual" ]; then
    # 鈹€鈹€ 鎵嬪姩妯″紡锛氳烦杩?ASR锛岀洿鎺ュ鍒舵寚瀹氱殑 SRT 鏂囦欢 鈹€鈹€
    if [ -z "$MANUAL_SRT" ]; then
        echo "鉂?--align-mode manual 闇€瑕侀厤鍚?--srt-file 鎸囧畾 SRT 鏂囦欢璺緞"
        exit 1
    fi
    if [ ! -f "$MANUAL_SRT" ] || [ ! -s "$MANUAL_SRT" ]; then
        echo "鉂?SRT 鏂囦欢涓嶅瓨鍦ㄦ垨涓虹┖锛?MANUAL_SRT"
        exit 1
    fi
    echo "鈴笍 [鈶?align] 璺宠繃 Demucs/Whisper锛?-align-mode manual锛?
    echo "   澶嶅埗鎵嬪姩 SRT锛?MANUAL_SRT 鈫?$OUTPUT_SRT"
    cp "$MANUAL_SRT" "$OUTPUT_SRT"
    log_step "[鈶?align] manual mode: using provided SRT"
    echo "鉁?SRT 鍑嗗瀹屾垚锛岃烦杩囧榻?
    # 鐩存帴璺冲埌瀹屾垚
    update_status "鈶?align" "completed" "manual SRT (no alignment)"
    echo ""
    echo "=================================================="
    echo "鉁?鈶?瀵归綈瀹屾垚锛堟墜鍔ㄦā寮忥級"
    echo "=================================================="
    exit 0
else
if command -v demucs > /dev/null 2>&1; then
    update_status "鈶?align" "running" "vocal separation with Demucs..."
    log_step "Demucs vocal separation starting..."

    DEMUCS_OUT="$TEMP_DIR/demucs_out"
    mkdir -p "$DEMUCS_OUT"

    # 鐢?--two-stems vocals 鍙垎绂讳汉澹帮紝鏈€蹇?
    if demucs --two-stems vocals \
        -o "$DEMUCS_OUT" \
        --device cpu \
        "$AUDIO_FILE" > "$TEMP_DIR/demucs.log" 2>&1; then

        # 鏌ユ壘鍒嗙鍚庣殑浜哄０鏂囦欢
        # Demucs 杈撳嚭璺緞: {out}/{model}/{stem}/{filename}/vocals.wav
        BASENAME=$(basename "$AUDIO_FILE" .mp3)
        CANDIDATE="$DEMUCS_OUT/htdemucs/separated/${BASENAME}/vocals.wav"

        if [ -f "$CANDIDATE" ]; then
            VOCAL_FILE="$CANDIDATE"
            DEMUCS_DONE="yes"
            log_step "Demucs done: vocals extracted"
            echo "馃攰 浜哄０鍒嗙瀹屾垚: $VOCAL_FILE"
        fi
    else
        log_step "Demucs failed, fallback to original audio"
        echo "鈿狅笍 Demucs 澶辫触锛屼娇鐢ㄥ師濮嬮煶棰?
    fi
else
    log_step "Demucs not available, using original audio"
    echo "鈩癸笍 Demucs 鏈畨瑁咃紝浣跨敤鍘熷闊抽鐩存帴杞啓"
fi

# 鑻ユ棤浜哄０鍒嗙锛屼娇鐢ㄥ師濮嬮煶棰?
[ -z "$VOCAL_FILE" ] && VOCAL_FILE="$AUDIO_FILE"

# ============================================================
# 瀛愭楠?3: Whisper 杞啓
# ============================================================
check_interrupt || { update_status "鈶?align" "interrupted" "stopped by user"; exit 0; }

update_status "鈶?align" "running" "Whisper transcribing..."
log_step "Whisper transcription starting..."

WHISPER_JSON="$TEMP_DIR/song.json"

# 璁＄畻闊抽鏂囦欢 hash锛堢敤浜哄０鏂囦欢锛?
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
    echo "鈴笍 Whisper 杞啓璺宠繃锛堢紦瀛樻湁鏁堬級"
else
    [ -f "$WHISPER_JSON" ] && log_step "Whisper cache miss, re-transcribing..."

    # 灏濊瘯 small 妯″瀷锛岃嫢 OOM 鍒?fallback 鍒?base
    if ! whisper "$VOCAL_FILE" \
        --model small \
        --language zh \
        --output_format json \
        --output_dir "$TEMP_DIR" \
        --verbose False > "$TEMP_DIR/whisper.log" 2>&1; then

        log_step "Whisper small failed, trying base model..."
        echo "鈿狅笍 Whisper small OOM锛屽皾璇?base 妯″瀷..."

        if ! whisper "$VOCAL_FILE" \
            --model base \
            --language zh \
            --output_format json \
            --output_dir "$TEMP_DIR" \
            --verbose False > "$TEMP_DIR/whisper_base.log" 2>&1; then
            update_status "鈶?align" "failed" "Whisper transcription failed"
            log_step "FAILED: Whisper transcription failed"
            echo "鉂?Whisper 杞啓澶辫触锛坰mall 鍜?base 鍧囧け璐ワ級锛岃瑙?whisper 鏃ュ織"
            exit 1
        fi
    fi

    if [ ! -f "$WHISPER_JSON" ]; then
        update_status "鈶?align" "failed" "Whisper output not found"
        log_step "FAILED: song.json not found"
        echo "鉂?Whisper 鏈敓鎴愯緭鍑烘枃浠?
        exit 1
    fi

    # 鍐欏叆 source hash
    python3 -c "
import json
with open('$WHISPER_JSON') as f: d=json.load(f)
d['_source_hash']='$AUDIO_HASH'
with open('$WHISPER_JSON','w') as f: json.dump(d, f, ensure_ascii=False)
" 2>/dev/null || true
fi

update_status "鈶?align" "running" "Whisper transcription completed"
log_step "Whisper transcription completed"
fi


# ============================================================
# 瀛愭楠?4: 瑙ｆ瀽 + 涓ら亶瀵归綈 + 鍚庡鐞嗕慨姝?+ 鐢熸垚 SRT
# ============================================================
check_interrupt || { update_status "鈶?align" "interrupted" "stopped by user"; exit 0; }

update_status "鈶?align" "running" "aligning lyrics to timestamps..."
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

# 鈹€鈹€ 璇诲彇姝岃瘝 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
with open(AUDIO_DIR + '/lyrics.txt', 'r', encoding='utf-8') as f:
    lyrics_lines = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith('## ')
    ]
# 鍘绘帀 [Intro] [Verse] 绛夋钀芥爣璁?
clean_lyrics = [
    line for line in lyrics_lines
    if not re.match(r'^\[.+\]$', line)
]

# 鈹€鈹€ 璇诲彇 Whisper 璇嗗埆缁撴灉 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
with open(WHISPER_JSON, 'r', encoding='utf-8') as f:
    whisper_data = json.load(f)

whisper_segments = whisper_data.get('segments', [])
asr_entries = [(seg['start'], seg['end'], seg['text'].strip()) for seg in whisper_segments]

# 鈹€鈹€ 鐩镐技搴﹀嚱鏁?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

# 鈹€鈹€ 涓ら亶瀵归綈绠楁硶 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
M, N = len(clean_lyrics), len(asr_entries)
THRESHOLD1 = 0.25   # 绗竴閬嶉槇鍊?
THRESHOLD2 = 0.20   # 绗簩閬嶉槇鍊硷紙鏇村鏉撅級

lyric_assigned = [False] * M
asr_assigned = [False] * N
alignments = {}   # lyric_idx -> (start, end, total_score, count)

# 鈹€鈹€ 绗竴閬嶏細椤哄簭璐績鍖归厤 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

# 鈹€鈹€ 绗簩閬嶏細琛ユ紡鏈尮閰嶇殑姝岃瘝 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

# 鈹€鈹€ 鍚庡鐞嗕慨姝?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 淇1: 鑻ョ1琛屾瓕璇嶆湭鍖归厤锛屽垎閰嶇涓€涓湁鏁?ASR 鐗囨鏃堕棿
if not lyric_assigned[0]:
    for i, (start, end, text) in enumerate(asr_entries):
        if len(text) >= 2:
            alignments[0] = (start, end, 0.0, 0)
            lyric_assigned[0] = True
            log_msg = f"post-fix: line 1 assigned to first ASR segment ({start:.2f}s)"
            print(log_msg, file=open(TEMP_DIR + '/steps.log', 'a'))
            break

# 淇2: 濉厖璺宠锛堣繛缁湭鍖归厤鐨勬瓕璇嶈锛屽垎閰嶅钩鍧囬棿闅旀椂闂达級
for j in range(1, M):
    if not lyric_assigned[j]:
        # 鎵惧墠鍚庡凡鍒嗛厤鐨勬瓕璇嶈
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
            # 鍧囧垎鎻掑€?
            gap = (next_start - prev_end) / (next_li - prev_li + 1)
            fill_start = prev_end + gap * (j - prev_li)
            fill_end = fill_start + (prev_end - prev_start)  # 鐢ㄥ墠涓€琛岀殑鏃堕暱
            alignments[j] = (fill_start, fill_end, 0.0, 0)
            lyric_assigned[j] = True
            print(f"post-fix: line {j+1} interpolated to {fill_start:.2f}s", file=open(TEMP_DIR + '/steps.log', 'a'))

# 鈹€鈹€ 鐢熸垚 SRT 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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

# 鎵撳嵃鍚庡鐞嗕俊鎭紙鑻ユ湁锛?
echo "$ALIGN_RESULT" | grep -v "^ALIGNED" | while read -r line; do
    echo "   $line"
done

update_status "鈶?align" "running" "alignment completed"
log_step "alignment completed"

# ============================================================
# 瀛愭楠?5: 鏇存柊 info.json锛堜慨澶?heredoc 娉ㄥ叆椋庨櫓锛?
# ============================================================
check_interrupt || { update_status "鈶?align" "interrupted" "stopped by user"; exit 0; }

update_status "鈶?align" "running" "updating metadata..."

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
# 瀹屾垚
# ============================================================
update_status "鈶?align" "completed" "${ALIGNED_COUNT}/${TOTAL} lines aligned"
log_step "completed: ${ALIGNED_COUNT}/${TOTAL} lines aligned"
echo "鉁?瀵归綈瀹屾垚: ${ALIGNED_COUNT}/${TOTAL} 琛屽凡瀵归綈"
