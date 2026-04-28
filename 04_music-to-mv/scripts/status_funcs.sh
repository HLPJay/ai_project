#!/bin/bash
# status_funcs.sh - 统一的流水线状态追踪函数库
# 所有步骤脚本必须 source 此文件
#
# 函数：
#   update_status <step_label> <status> <detail>
#   check_interrupt
#   init_status_json
#   clear_interrupt

# ============================================================
# update_status — 更新 status.json 中指定步骤的状态
# 用法: update_status "① lyrics" "running" "calling API..."
# ============================================================
update_status() {
    local step="$1"
    local status="$2"
    local detail="$3"
    local status_file="$PROJECT_DIR/metadata/status.json"

    if [ -z "$PROJECT_DIR" ] || [ ! -f "$status_file" ]; then
        return
    fi

    python3 - << PYEOF
import json
from datetime import datetime

status_file = "$status_file"
step = "$step"
status = "$status"
detail = "$detail"

try:
    with open(status_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {"pipeline": {}, "last_updated": None}

data["pipeline"][step] = {
    "status": status,
    "detail": detail,
    "updated_at": datetime.now().isoformat()
}
data["last_updated"] = datetime.now().isoformat()

with open(status_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PYEOF

    # stdout 输出，供日志和 Control UI 轮询感知
    case "$status" in
        running)    echo "🔄 [$step] $detail" ;;
        completed)  echo "✅ [$step] $detail" ;;
        failed)     echo "❌ [$step] $detail" ;;
        interrupted) echo "⚠️  [$step] interrupted: $detail" ;;
    esac
}

# ============================================================
# check_interrupt — 检查用户是否发送了打断信号
# 返回: 0=未打断, 1=已打断（脚本应退出）
# ============================================================
check_interrupt() {
    local interrupt_file="$PROJECT_DIR/metadata/interrupt.json"

    if [ -z "$PROJECT_DIR" ] || [ ! -f "$interrupt_file" ]; then
        return 0
    fi

    local stop
    stop=$(python3 -c "
import json, sys
try:
    with open('$interrupt_file', 'r') as f:
        d = json.load(f)
    print('True' if d.get('stop', False) else 'False')
except:
    print('False')
" 2>/dev/null)

    if [ "$stop" = "True" ]; then
        # 清除打断标记，防止重复触发
        python3 -c "
import json
with open('$interrupt_file', 'r') as f:
    d = json.load(f)
d['stop'] = False
d['cleared_at'] = '$(date -u +%Y-%m-%dT%H:%M:%S+08:00)'
with open('$interrupt_file', 'w') as f:
    json.dump(d, f, ensure_ascii=False)
" 2>/dev/null
        return 1
    fi

    return 0
}

# ============================================================
# init_status_json — 初始化 status.json 模板
# 用法: init_status_json <project_name>
# ============================================================
init_status_json() {
    local project_name="$1"
    local status_file="$PROJECT_DIR/metadata/status.json"

    python3 - << PYEOF
import json
from datetime import datetime

status_file = "$status_file"
project_name = "$project_name"

data = {
    "project": project_name,
    "pipeline": {
        "① lyrics":    {"status": "pending", "detail": "", "updated_at": None},
        "② music":     {"status": "pending", "detail": "", "updated_at": None},
        "③ align":     {"status": "pending", "detail": "", "updated_at": None},
        "④ base":      {"status": "pending", "detail": "", "updated_at": None},
        "⑤-⑦ images": {"status": "pending", "detail": "", "updated_at": None},
        "⑧ kb":        {"status": "pending", "detail": "", "updated_at": None},
        "⑨ concat":    {"status": "pending", "detail": "", "updated_at": None},
        "⑩ merge":     {"status": "pending", "detail": "", "updated_at": None},
        "⑪ export":   {"status": "pending", "detail": "", "updated_at": None}
    },
    "last_updated": datetime.now().isoformat()
}

with open(status_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PYEOF
}

# ============================================================
# notify_telegram — 发送 Telegram 进度通知
# 条件: info.json 中 notifications=true 时才发送
# 用法: notify_telegram "🎵 音乐生成完成：童年小纸飞机"
# ============================================================
notify_telegram() {
    local message="$1"

    # 检查开关
    if [ -z "$PROJECT_DIR" ]; then
        return
    fi

    local enabled
    enabled=$(python3 -c "
import json, sys
try:
    with open('$PROJECT_DIR/metadata/info.json', 'r') as f:
        info = json.load(f)
    print('true' if info.get('notifications', False) else 'false')
except:
    print('false')
" 2>/dev/null)

    if [ "$enabled" != "true" ]; then
        return
    fi

    # 发送 Telegram
    curl -s --noproxy '*' \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=$message" \
        -d "parse_mode=HTML" \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        > /dev/null 2>&1
}

# ============================================================
# init_interrupt_json — 初始化 interrupt.json
# ============================================================
init_interrupt_json() {
    local interrupt_file="$PROJECT_DIR/metadata/interrupt.json"
    # 通过 env var 传路径，保持单引号 heredoc 避免 Python 代码中意外展开
    INIT_INTERRUPT_FILE="$interrupt_file" python3 - << 'PYEOF'
import json, os
interrupt_file = os.environ['INIT_INTERRUPT_FILE']
data = {"stop": False, "requested_at": None, "cleared_at": None}
with open(interrupt_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PYEOF
}
