#!/bin/bash
# list_projects.sh - 列出所有 MV 项目及其流水线状态
# 用法: ./list_projects.sh [--failed] [--json]
#
# 选项:
#   --failed   只显示包含 failed/interrupted 步骤的项目
#   --json     输出 JSON 格式（供脚本解析）

WORKSPACE_ROOT="${HOME}/.openclaw/workspace/mv"
FILTER_FAILED=false
OUTPUT_JSON=false

for arg in "$@"; do
    case $arg in
        --failed) FILTER_FAILED=true ;;
        --json)   OUTPUT_JSON=true ;;
    esac
done

if [ ! -d "$WORKSPACE_ROOT" ]; then
    if $OUTPUT_JSON; then
        echo "[]"
    else
        echo "暂无项目（工作目录: $WORKSPACE_ROOT）"
    fi
    exit 0
fi

# 收集所有项目信息
PROJECTS_JSON="[]"

count=0
for project_dir in "$WORKSPACE_ROOT"/*/; do
    [ -d "$project_dir" ] || continue

    project_name=$(basename "$project_dir")
    status_file="$project_dir/metadata/status.json"
    info_file="$project_dir/metadata/info.json"

    project_info=$(python3 - << PYEOF 2>/dev/null
import json, os, sys

project_dir = "$project_dir"
status_file = "$status_file"
info_file   = "$info_file"

result = {
    "name": "$project_name",
    "path": project_dir,
    "theme": "",
    "created_at": "",
    "overall": "unknown",
    "completed": 0,
    "total": 0,
    "failed_steps": [],
    "interrupted_steps": [],
    "running_steps": [],
}

# 读取 info.json
try:
    with open(info_file) as f:
        info = json.load(f)
    result["theme"] = info.get("project_name", "")
    result["created_at"] = info.get("created_at", "")
except Exception: pass

# 读取 status.json
try:
    with open(status_file) as f:
        d = json.load(f)
    steps = d.get("pipeline", {})
    result["total"] = len(steps)
    result["completed"] = sum(1 for v in steps.values() if v["status"] == "completed")
    result["failed_steps"] = [k for k, v in steps.items() if v["status"] == "failed"]
    result["interrupted_steps"] = [k for k, v in steps.items() if v["status"] == "interrupted"]
    result["running_steps"] = [k for k, v in steps.items() if v["status"] == "running"]

    if result["failed_steps"]:
        result["overall"] = "failed"
    elif result["interrupted_steps"]:
        result["overall"] = "interrupted"
    elif result["running_steps"]:
        result["overall"] = "running"
    elif result["completed"] == result["total"] and result["total"] > 0:
        result["overall"] = "completed"
    else:
        result["overall"] = "pending"
except Exception: pass

print(json.dumps(result, ensure_ascii=False))
PYEOF
)

    [ -z "$project_info" ] && continue

    # 过滤失败/中断项目
    if $FILTER_FAILED; then
        overall=$(echo "$project_info" | python3 -c "import json,sys; print(json.load(sys.stdin)['overall'])" 2>/dev/null)
        [[ "$overall" != "failed" && "$overall" != "interrupted" ]] && continue
    fi

    PROJECTS_JSON=$(python3 - << PYEOF 2>/dev/null
import json, sys
existing = $PROJECTS_JSON
new_item = $project_info
existing.append(new_item)
print(json.dumps(existing, ensure_ascii=False))
PYEOF
)
    count=$((count + 1))
done

# ── 输出 ──────────────────────────────────────────────────────
if $OUTPUT_JSON; then
    echo "$PROJECTS_JSON"
    exit 0
fi

echo "📁 MV 项目列表  ($WORKSPACE_ROOT)"
echo "══════════════════════════════════════════════════════════════"

if [ $count -eq 0 ]; then
    echo "  （暂无项目）"
else
    python3 - << PYEOF
import json
projects = $PROJECTS_JSON

icons = {
    "completed":   "✅",
    "failed":      "❌",
    "interrupted": "⏸ ",
    "running":     "🔄",
    "pending":     "⏳",
    "unknown":     "❓",
}

for i, p in enumerate(projects, 1):
    icon = icons.get(p["overall"], "❓")
    created = p["created_at"][:10] if p.get("created_at") else "unknown date"
    theme = p.get("theme") or p["name"]

    print(f"  [{i}] {icon}  {theme}  ({created})")

    comp = p["completed"]
    total = p["total"]
    print(f"       进度: {comp}/{total} 步骤完成")

    if p["failed_steps"]:
        print(f"       ❌ 失败于: {', '.join(p['failed_steps'])}")
    if p["interrupted_steps"]:
        print(f"       ⏸  中断于: {', '.join(p['interrupted_steps'])}")

    print(f"       路径: {p['path']}")
    print()
PYEOF
fi

echo "══════════════════════════════════════════════════════════════"
echo "恢复失败项目: 参见 SKILL.md → Resume Failed Pipeline"
