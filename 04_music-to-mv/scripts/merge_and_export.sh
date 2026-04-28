#!/bin/bash
# merge_and_export.sh - Steps ⑨-⑪: 合并音视频 + 导出 TikTok 版本
# 用法: ./merge_and_export.sh <项目目录>
#
# 修复:
#   - SRT 路径用 Python 转义（解决空格/special chars 问题）
#   - ffmpeg 错误检测（不再被 || true 吞掉）
#   - temp/ 保留到 export 完成后
#
# 输入: {project_dir}/clips/seg*_scene_kb.mp4  (Ken Burns 片段)
#       {project_dir}/audio/song.mp3
#       {project_dir}/audio/song.srt
# 输出: {project_dir}/output/final.mp4
#       {project_dir}/output/tiktok.mp4
#       {project_dir}/output/vertical.mp4

set -e

PROJECT_DIR="${1:-}"

[ -z "$PROJECT_DIR" ] && echo "❌ 用法: $0 <项目目录>" && exit 1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"   # 加载 API Token 配置
source "$SCRIPT_DIR/status_funcs.sh"

FFMPEG="${FFMPEG:-ffmpeg}"
FFPROBE="${FFPROBE:-ffprobe}"

AUDIO_DIR="$PROJECT_DIR/audio"
TEMP_DIR="$PROJECT_DIR/temp"
OUTPUT_DIR="$PROJECT_DIR/output"
METADATA_DIR="$PROJECT_DIR/metadata"

mkdir -p "$OUTPUT_DIR"

log_step() { echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1" >> "$METADATA_DIR/steps.log"; }

check_interrupt() {
    local f="$PROJECT_DIR/metadata/interrupt.json"
    [ -f "$f" ] || return 1
    local stop=$(python3 -c "
import json, sys
try:
    d = json.load(open('$f'))
    print(str(d.get('stop', False)).lower())
except Exception:
    print('ERROR')
" 2>&1)
    # 若 Python 执行失败（文件损坏等），跳过打断检查，不阻塞执行
    [ "$stop" = "true" ] || [ "$stop" = "ERROR" ] || [ "$stop" = "false" ] || return 1
    [ "$stop" = "true" ] || return 1
    python3 -c "import json; d=json.load(open('$f')); d['stop']=False; json.dump(d,open('$f','w'))"
    return 0
}

# ═══════════════════════════════════════════════════════════════
# Step ⑨: 拼接视频
# ═══════════════════════════════════════════════════════════════
check_interrupt || { update_status "⑨ concat" "interrupted"; exit 0; }
update_status "⑨ concat" "running" "..."
log_step "[⑨ concat] starting..."

export CLIPS_DIR="$PROJECT_DIR/clips"
export CONCAT_LIST="$TEMP_DIR/concat_list.txt"
export VIDEO_RAW="$TEMP_DIR/video_raw.mp4"

# 收集 clips，用 Python 写 concat list（避免 shell 路径转义问题）
python3 << 'PYEOF'
import os, glob

clips_dir = os.environ.get('CLIPS_DIR', '')
concat_list = os.environ.get('CONCAT_LIST', '')

pattern = os.path.join(clips_dir, '*_scene_kb.mp4')
clips = sorted(glob.glob(pattern))

with open(concat_list, 'w', encoding='utf-8') as f:
    for clip in clips:
        # ffmpeg concat 需要相对路径或绝对路径，单引号包裹
        abs_path = os.path.abspath(clip)
        f.write(f"file '{abs_path}'\n")

print(f'Written {len(clips)} clips to {concat_list}')
PYEOF

CLIP_COUNT=$(grep -c "^file '" "$CONCAT_LIST" 2>/dev/null || echo 0)
if [ "$CLIP_COUNT" -eq 0 ]; then
    update_status "⑨ concat" "failed" "no clips found"
    log_step "[⑨ concat] FAILED: no clips in $CLIPS_DIR"
    echo "❌ 没有找到 KB 片段: $CLIPS_DIR/*_scene_kb.mp4"
    exit 1
fi

log_step "[⑨ concat] concatenating $CLIP_COUNT clips..."

check_interrupt || { update_status "⑨ concat" "interrupted"; exit 0; }
update_status "⑨ concat" "running" "ffmpeg concat..."
log_step "[⑨ concat] running ffmpeg concat..."

# 用 Python 执行 ffmpeg（更可靠的错误捕获）
python3 -c "
import subprocess, os, sys

cmd = [
    '$FFMPEG', '-y',
    '-f', 'concat', '-safe', '0',
    '-i', '$CONCAT_LIST',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-pix_fmt', 'yuv420p',
    '$VIDEO_RAW'
]

with open('$METADATA_DIR/ffmpeg.log', 'a') as log:
    log.write(f'[⑨ concat] {\" \".join(cmd)}\\n')
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.stdout:
        log.write(proc.stdout.decode("utf-8", errors="replace"))

if proc.returncode != 0:
    print(f'FFmpeg failed with code {proc.returncode}', file=sys.stderr)
    sys.exit(proc.returncode)
print('concat done')
"

if [ ! -f "$VIDEO_RAW" ]; then
    update_status "⑨ concat" "failed" "ffmpeg concat failed"
    log_step "[⑨ concat] FAILED"
    exit 1
fi

RAW_SIZE=$(du -h "$VIDEO_RAW" | cut -f1)
RAW_DURATION=$($FFPROBE -v error -show_entries format=duration -of csv=p=0 "$VIDEO_RAW" 2>/dev/null | cut -d. -f1 || echo "0")

update_status "⑨ concat" "completed" "video_raw.mp4 (${RAW_SIZE}, ${RAW_DURATION}s)"
log_step "[⑨ concat] completed: ${RAW_SIZE}, ${RAW_DURATION}s"
echo "✅ ⑨ 完成: video_raw.mp4 ($RAW_SIZE, ${RAW_DURATION}s)"

# ═══════════════════════════════════════════════════════════════
# Step ⑩: 合并音视频 + 字幕
# ═══════════════════════════════════════════════════════════════
check_interrupt || { update_status "⑩ merge" "interrupted"; exit 0; }
update_status "⑩ merge" "running" "..."
log_step "[⑩ merge] starting..."

AUDIO_FILE="$AUDIO_DIR/song.mp3"
SRT_FILE="$AUDIO_DIR/song.srt"
FINAL_OUTPUT="$OUTPUT_DIR/final.mp4"

check_interrupt || { update_status "⑩ merge" "interrupted"; exit 0; }

log_step "[⑩ merge] merging video+audio${SRT_FILE:+ + subtitles}..."

python3 -c "
import subprocess, os, sys

inputs = ['$VIDEO_RAW', '$AUDIO_FILE']
if '$SRT_FILE' and os.path.exists('$SRT_FILE'):
    inputs.append('$SRT_FILE')

cmd = ['$FFMPEG', '-y'] + ['-i', inputs[0]] + ['-i', inputs[1]]
if len(inputs) > 2:
    cmd += ['-i', inputs[2]]
    cmd += ['-c:v', 'copy', '-c:a', 'aac', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=chi']
else:
    cmd += ['-c:v', 'copy', '-c:a', 'aac']
cmd += ['-c:v', 'copy', '-c:a', 'aac', '$FINAL_OUTPUT']

with open('$METADATA_DIR/ffmpeg.log', 'a') as log:
    log.write(f'[⑩ merge] {\" \".join(cmd)}\\n')
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.stdout:
        log.write(proc.stdout.decode("utf-8", errors="replace"))

if proc.returncode != 0:
    print(f'FFmpeg merge failed with code {proc.returncode}', file=sys.stderr)
    sys.exit(proc.returncode)
print('merge done')
"

if [ ! -f "$FINAL_OUTPUT" ]; then
    update_status "⑩ merge" "failed" "ffmpeg merge failed"
    log_step "[⑩ merge] FAILED"
    exit 1
fi

FINAL_SIZE=$(du -h "$FINAL_OUTPUT" | cut -f1)
FINAL_DURATION=$($FFPROBE -v error -show_entries format=duration -of csv=p=0 "$FINAL_OUTPUT" 2>/dev/null | cut -d. -f1 || echo "0")

update_status "⑩ merge" "completed" "final.mp4 (${FINAL_SIZE}, ${FINAL_DURATION}s)"
log_step "[⑩ merge] completed: ${FINAL_SIZE}, ${FINAL_DURATION}s"
echo "✅ ⑩ 完成: final.mp4 ($FINAL_SIZE, ${FINAL_DURATION}s)"

# ═══════════════════════════════════════════════════════════════
# Step ⑪: 导出 TikTok 版本
# ═══════════════════════════════════════════════════════════════
check_interrupt || { update_status "⑪ export" "interrupted"; exit 0; }
update_status "⑪ export" "running" "..."
log_step "[⑪ export] starting..."

FONT_NAME="Microsoft YaHei"
FONT_SIZE=32
STYLE="FontName=$FONT_NAME,FontSize=$FONT_SIZE,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=20"

# 用 Python 安全构建 ffmpeg 命令（SRT 路径转义）
export SRT_FILE FINAL_OUTPUT OUTPUT_DIR METADATA_DIR FFMPEG STYLE
python3 << 'PYEOF'
import subprocess, os, sys

srt_file = os.environ.get('SRT_FILE', '')
final_output = os.environ.get('FINAL_OUTPUT', '')
output_dir = os.environ.get('OUTPUT_DIR', '')
metadata_dir = os.environ.get('METADATA_DIR', '')

# ── Tiktok (burn subtitles) ──
log_path = os.path.join(metadata_dir, 'ffmpeg.log')
tiktok_output = os.path.join(output_dir, 'tiktok.mp4')

if srt_file and os.path.exists(srt_file):
    # 用 Python subprocess 执行（自动处理路径编码）
    cmd = [
        os.environ.get('FFMPEG', 'ffmpeg'), '-y',
        '-i', final_output,
        '-vf', f"subtitles='{srt_file}':force_style='{os.environ.get('STYLE', '')}'",
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'copy',
        tiktok_output
    ]
    with open(log_path, 'a') as log:
        log.write(f"[⑪ export] tiktok: {' '.join(cmd)}\n")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.stdout:
        log.write(proc.stdout.decode("utf-8", errors="replace"))
    if proc.returncode != 0:
        print(f'tiktok burn failed: {proc.returncode}', file=sys.stderr)
else:
    import shutil
    shutil.copy(final_output, tiktok_output)

# ── Vertical ──
vertical_output = os.path.join(output_dir, 'vertical.mp4')
cmd2 = [
    os.environ.get('FFMPEG', 'ffmpeg'), '-y',
    '-i', tiktok_output,
    '-vf', 'scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
    '-c:a', 'copy',
    vertical_output
]
with open(log_path, 'a') as log:
    log.write(f"[⑪ export] vertical: {' '.join(cmd2)}\n")
    proc = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.stdout:
        log.write(proc.stdout.decode("utf-8", errors="replace"))
if proc.returncode != 0:
    print(f'vertical failed: {proc.returncode}', file=sys.stderr)

print('export done')
PYEOF

if [ ! -f "$OUTPUT_DIR/tiktok.mp4" ]; then
    update_status "⑪ export" "failed" "tiktok generation failed"
    log_step "[⑪ export] FAILED"
    exit 1
fi

TIKTOK_SIZE=$(du -h "$OUTPUT_DIR/tiktok.mp4" | cut -f1)
VERTICAL_SIZE=$(du -h "$OUTPUT_DIR/vertical.mp4" | cut -f1)

update_status "⑪ export" "completed" "tiktok (${TIKTOK_SIZE}), vertical (${VERTICAL_SIZE})"
notify_telegram "✅ MV 制作完成！横屏 tiktok.mp4 (${TIKTOK_SIZE})，竖屏 vertical.mp4 (${VERTICAL_SIZE})"
log_step "[⑪ export] completed: tiktok=${TIKTOK_SIZE}, vertical=${VERTICAL_SIZE}"
echo "✅ ⑪ 完成: tiktok.mp4 ($TIKTOK_SIZE), vertical.mp4 ($VERTICAL_SIZE)"

# ═══════════════════════════════════════════════════════════════
# 质量报告
# ═══════════════════════════════════════════════════════════════
python3 -c "
import json, os

project_dir = '$PROJECT_DIR'
info_path = project_dir + '/metadata/info.json'
report_path = project_dir + '/metadata/quality_report.json'

with open(info_path, 'r', encoding='utf-8') as f:
    info = json.load(f)

alignment = info.get('alignment', {})
aligned = alignment.get('aligned_lines', 0)
total = alignment.get('total_lyrics_lines', 0)
rate = round(aligned / total * 100) if total > 0 else 0

song_path = project_dir + '/audio/song.mp3'
song_size = os.path.getsize(song_path) / 1024 / 1024 if os.path.exists(song_path) else 0

final_path = project_dir + '/output/final.mp4'
final_size = os.path.getsize(final_path) / 1024 / 1024 if os.path.exists(final_path) else 0

images_count = len([f for f in os.listdir(project_dir + '/images') if f.endswith('.png')])
clips_count = len([f for f in os.listdir(project_dir + '/clips') if f.endswith('.mp4')])
scenes_path = project_dir + '/metadata/scenes.json'
scene_count = 0
if os.path.exists(scenes_path):
    with open(scenes_path, 'r') as f:
        scene_count = len(json.load(f))

report = {
    'song_title': info.get('song_title', 'N/A'),
    'theme': info.get('theme', ''),
    'alignment_rate': f'{aligned}/{total} ({rate}%)',
    'audio_duration_sec': info.get('audio_duration_sec', 0),
    'audio_size_mb': round(song_size, 1),
    'final_mv_size_mb': round(final_size, 1),
    'images_count': images_count,
    'clips_count': clips_count,
    'scene_count': scene_count,
    'generated_at': info.get('created_at', '')
}

with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print()
print('=' * 50)
print('📊 MV 质量报告')
print('=' * 50)
print(f'  歌曲: {report[\"song_title\"]}')
print(f'  主题: {report[\"theme\"]}')
print(f'  歌词对齐率: {report[\"alignment_rate\"]}')
print(f'  场景数: {report[\"scene_count\"]}')
print(f'  音频时长: {report[\"audio_duration_sec\"]}s')
print(f'  最终 MV: {report[\"final_mv_size_mb\"]}MB')
print(f'  场景图: {report[\"images_count\"]} 张')
print(f'  KB 片段: {report[\"clips_count\"]} 个')
print('=' * 50)
"

# ═══════════════════════════════════════════════════════════════
# 清理 temp/
# ═══════════════════════════════════════════════════════════════
rm -f "$TEMP_DIR/concat_list.txt" "$TEMP_DIR/video_raw.mp4"
log_step "temp/ cleanup done"

log_step "=========================================="
log_step "合并+导出完成！"
log_step "最终文件: $OUTPUT_DIR/final.mp4"
echo ""
echo "✅ 合并+导出完成！"
echo "   最终文件: $OUTPUT_DIR/final.mp4"
# ═══════════════════════════════════════════════════════════════
# 生成 LLM 完整报告
# ═══════════════════════════════════════════════════════════════
echo ""
echo "📊 生成 LLM 完整报告..."
python3 "$SCRIPT_DIR/generate_llm_report.py" "$PROJECT_DIR" --output "$OUTPUT_DIR/llm_report.html"
