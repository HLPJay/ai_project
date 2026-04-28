#!/bin/bash
# init_project.sh - 初始化 MV 项目目录结构
# 用法: ./init_project.sh <主题> [--style <画面风格>] [--music-style <音乐风格>] [--mood <情绪基调>] [--language <语言>] [--reference <参考>] [--notify]
#
# 示例:
#   ./init_project.sh "春天"
#   ./init_project.sh "春天" --style "写实摄影风" --music-style "民谣" --mood "温柔" --language "中文" --notify
#
# 选项:
#   --style <风格>         画面风格（动漫风/国风/写实摄影风/水彩插画风/像素游戏风/电影感写实风/极简几何风/浮世绘和风/复古胶片风/漫画美式涂鸦风/蒸汽朋克风/赛博朋克风）
#   --music-style <风格>   音乐风格（流行/说唱/民谣/电子/摇滚/古典/爵士/HipHop/R&B/中国风/新世纪NewAge/EDM舞曲/乡村Country/朋克Punk）
#   --mood <基调>          情绪基调（欢快/温柔/史诗/忧伤/热血/梦幻/浪漫/怀旧/希望/暗黑/宁静/慵懒/清新/叛逆/孤独/悬疑/魔幻）
#   --language <语言>       歌词语言（中文 / 英文 / 双语）
#   --reference <参考>      参考描述（可选）
#   --notify                完成后通过 Telegram 发送进度通知（需先由 Agent 询问用户确认）
#
# 输出: 创建项目目录及所有子目录，返回项目路径

set -e

# ── 前置依赖检查（在创建任何目录之前）────────────────────────
_PREFLIGHT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$_PREFLIGHT_DIR/preflight.sh" || exit 1

PROJECT_NAME=""
WORKSPACE_ROOT="${HOME}/.openclaw/workspace/mv"
NOTIFICATIONS=""
STYLE=""
MUSIC_STYLE=""
MOOD=""
LANGUAGE=""
REFERENCE=""
NEXT_ARG=""

# 解析参数
NEXT_ARG=""
for arg in "$@"; do
    if [ -n "$NEXT_ARG" ]; then
        case "$NEXT_ARG" in
            style) STYLE="$arg" ;;
            music_style) MUSIC_STYLE="$arg" ;;
            mood) MOOD="$arg" ;;
            language) LANGUAGE="$arg" ;;
            reference) REFERENCE="$arg" ;;
        esac
        NEXT_ARG=""
    else
        case "$arg" in
            --notify) NOTIFICATIONS="true" ;;
            --style) NEXT_ARG="style" ;;
            --music-style) NEXT_ARG="music_style" ;;
            --mood) NEXT_ARG="mood" ;;
            --language) NEXT_ARG="language" ;;
            --reference) NEXT_ARG="reference" ;;
            -*) ;;
            *) PROJECT_NAME="$arg" ;;
        esac
    fi
done

if [ -z "$PROJECT_NAME" ]; then
    echo "❌ 用法: $0 <主题> [--style <画面风格>] [--music-style <音乐风格>] [--mood <情绪基调>] [--language <语言>] [--reference <参考>] [--notify]"
    exit 1
fi

# 默认值
[ -z "$STYLE" ] && STYLE="动漫风"
[ -z "$MUSIC_STYLE" ] && MUSIC_STYLE="流行"
[ -z "$MOOD" ] && MOOD="欢快"
[ -z "$LANGUAGE" ] && LANGUAGE="中文"

# ============================================================
# 前置检查：磁盘空间（至少需要 1GB）
# ============================================================
if [ -d "$WORKSPACE_ROOT" ]; then
    AVAILABLE_KB=$(df -k "$WORKSPACE_ROOT" | tail -1 | awk '{print $4}')
    if [ "${AVAILABLE_KB:-0}" -lt 1048576 ]; then
        echo "❌ 磁盘空间不足（可用 ${AVAILABLE_KB}KB，需要 >1GB）"
        exit 1
    fi
fi

# ============================================================
# 清理旧项目（已禁用，用户手动管理）
# ============================================================
# 不再自动清理旧项目，用户自行决定删除哪些。

# 生成目录名: 用 Python 处理 Unicode，非ASCII/非字母数字字符转下划线
SAFE_NAME=$(python3 -c "
import re, sys
name = sys.argv[1]
safe = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_-]', '_', name)
print(safe)
" "$PROJECT_NAME")

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="${WORKSPACE_ROOT}/${SAFE_NAME}_${TIMESTAMP}"

# 创建目录结构
mkdir -p "$PROJECT_DIR"/{metadata,audio,images,clips,temp,output}

# 写入 metadata/info.json
NOTIFY_FIELD="false"
if [ "$NOTIFICATIONS" = "true" ]; then
    NOTIFY_FIELD="true"
fi

# 用 Python 写 info.json，避免变量展开导致的 JSON 注入
PY_TMP=$(mktemp /tmp/init_info_XXXXXX.py)
PROJECT_DIR_V="$PROJECT_DIR" PROJECT_NAME_V="$PROJECT_NAME" SAFE_NAME_V="$SAFE_NAME" \
    WORKSPACE_ROOT_V="$WORKSPACE_ROOT" NOTIFY_FIELD_V="$NOTIFY_FIELD" \
    STYLE_V="$STYLE" MUSIC_STYLE_V="$MUSIC_STYLE" MOOD_V="$MOOD" \
    LANGUAGE_V="$LANGUAGE" REFERENCE_V="$REFERENCE" \
    python3 - << 'PYJSON'
import json, os, subprocess
info = {
    "project_name": os.environ['PROJECT_NAME_V'],
    "theme": os.environ['PROJECT_NAME_V'],
    "safe_name": os.environ['SAFE_NAME_V'],
    "created_at": subprocess.run(['date', '+%Y-%m-%dT%H:%M:%S%z'],
                                capture_output=True, text=True).stdout.strip(),
    "workspace_root": os.environ['WORKSPACE_ROOT_V'],
    "notifications": os.environ['NOTIFY_FIELD_V'] == 'true',
    "style": os.environ['STYLE_V'],
    "music_style": os.environ['MUSIC_STYLE_V'],
    "mood": os.environ['MOOD_V'],
    "language": os.environ['LANGUAGE_V'],
    "reference": os.environ['REFERENCE_V'],
    "image_seed": __import__('random').randint(0, 2147483646),
    "steps_completed": [],
    "config": {
        "resolution": "1280x720",
        "fps": 25,
        "kb_duration_sec": 27,
        "kb_fade_sec": 2,
        "subtitle_font": "Microsoft YaHei",
        "subtitle_size": 32
    }
}
Path = __import__('pathlib').Path
(info_path := Path(os.environ['PROJECT_DIR_V']) / 'metadata' / 'info.json').write_text(
    json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
PYJSON

# 写入初始 steps.log
cat > "$PROJECT_DIR/metadata/steps.log" << EOF
[$(date +%Y-%m-%d\ %H:%M:%S)] Project initialized: $PROJECT_NAME
[$(date +%Y-%m-%d\ %H:%M:%S)] Directory: $PROJECT_DIR
[$(date +%Y-%m-%d\ %H:%M:%S)] Style: $STYLE, Music: $MUSIC_STYLE, Mood: $MOOD, Language: $LANGUAGE
[$(date +%Y-%m-%d\ %H:%M:%S)] Notifications: $NOTIFY_FIELD
EOF

# 初始化 status.json 和 interrupt.json
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"   # 加载 API Token 配置
source "$SCRIPT_DIR/status_funcs.sh"

init_status_json "$SAFE_NAME"
init_interrupt_json

echo "$PROJECT_DIR"
