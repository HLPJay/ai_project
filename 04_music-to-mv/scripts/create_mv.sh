#!/bin/bash
# create_mv.sh — MV 流水线统一入口
#
# 用法:
#   create_mv.sh --theme <主题> [--style <风格>] [--music-style <音乐风格>] [--mood <情绪>] \
#                [--language <语言>] [--reference <参考>] [--notify]
#   create_mv.sh <项目目录> --phase align|produce|export
#
# 分阶段模式:
#   --phase init     创建项目 + Step①②（歌词+音乐），完成后暂停
#   --phase align    执行 Step③（歌词对齐），需要 info.json 有 align_mode
#   --phase produce  执行 Step④-⑧（生图+Ken Burns）
#   --phase export   执行 Step⑨-⑪（合成+导出）
#
# 全自动模式（不暂停，仅用于测试）:
#   create_mv.sh --theme <主题> --auto [--align-mode auto|manual]
#
# 暂停点检查:
#   每次执行前检查 info.json 中的 user_approved 标记。
#   若标记不存在，脚本输出提示并退出，避免 Agent 跳过用户交互。

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${HOME}/.openclaw/workspace/mv"

# ── 参数变量 ──────────────────────────────────────────
THEME=""
STYLE="国风"
MUSIC_STYLE="流行"
MOOD="温柔"
LANGUAGE="中文"
REFERENCE=""
NOTIFICATIONS=""
PROJECT_DIR=""
PHASE=""
AUTO_MODE=""
ALIGN_MODE=""

show_usage() {
    echo "用法:"
    echo "  $0 --theme <主题> [选项...]"
    echo "     创建新项目"
    echo ""
    echo "  $0 <项目目录> --phase <init|align|produce|export>"
    echo "     从指定阶段继续"
    echo ""
    echo "选项:"
    echo "  --style <风格>         画面风格（默认：国风）"
    echo "  --music-style <风格>   音乐风格（默认：流行）"
    echo "  --mood <情绪>          情绪基调（默认：温柔）"
    echo "  --language <语言>       歌词语言（默认：中文）"
    echo "  --reference <参考>      参考描述/角色设定"
    echo "  --notify               完成时 Telegram 通知"
    echo "  --auto                 全自动模式（跳过用户确认暂停）"
    echo "  --align-mode <模式>    对齐方式：auto(默认) / manual"
    echo "  --srt-file <路径>      手动模式时的 SRT 文件路径"
    echo ""
    echo "示例:"
    echo "  $0 --theme 春天 --style 水彩插画风 --mood 宁静"
    echo "  $0 --theme 战争 --auto --align-mode manual"
    echo "  $0 ~/mv/战争_20260425_031726 --phase align"
}

# ── 解析参数 ──────────────────────────────────────────
while [ -n "$1" ]; do
    case "$1" in
        --help|-h)
            show_usage; exit 0 ;;
        --theme)
            THEME="$2"; shift 2 ;;
        --style)
            STYLE="$2"; shift 2 ;;
        --music-style)
            MUSIC_STYLE="$2"; shift 2 ;;
        --mood)
            MOOD="$2"; shift 2 ;;
        --language)
            LANGUAGE="$2"; shift 2 ;;
        --reference)
            REFERENCE="$2"; shift 2 ;;
        --notify)
            NOTIFICATIONS="true"; shift ;;
        --phase)
            PHASE="$2"; shift 2 ;;
        --auto)
            AUTO_MODE="true"; shift ;;
        --align-mode)
            ALIGN_MODE="$2"; shift 2 ;;
        --srt-file)
            SRT_FILE="$2"; shift 2 ;;
        *)
            if [ -z "$PROJECT_DIR" ] && [ -d "$1" 2>/dev/null ] && echo "$1" | grep -q "^${WORKSPACE_ROOT}"; then
                PROJECT_DIR="$1"
            else
                echo "⚠️ 未知参数或无效路径: $1"
                show_usage
                exit 1
            fi
            shift ;;
    esac
done

# ── 阶段一：创建新项目 ────────────────────────────────
if [ -z "$PHASE" ] && [ -n "$THEME" ]; then
    # 全自动模式：--auto 等价于 --phase init + 自动设置标记
    PHASE="init"
fi

if [ "$PHASE" = "init" ] || [ "$PHASE" = "" ]; then
    if [ -z "$THEME" ]; then
        echo "❌ 缺少 --theme 参数"
        show_usage
        exit 1
    fi

    # 调用 init_project.sh 创建项目目录
    PROJECT_DIR=$("$SCRIPT_DIR/init_project.sh" "$THEME" \
        --style "$STYLE" \
        --music-style "$MUSIC_STYLE" \
        --mood "$MOOD" \
        --language "$LANGUAGE" \
        --reference "$REFERENCE" \
        ${NOTIFICATIONS:+--notify} \
        2>&1 | grep -E "^${WORKSPACE_ROOT}/" | tail -1)

    if [ -z "$PROJECT_DIR" ]; then
        # fallback: 用命名规则找
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        SAFE_NAME=$(echo "$THEME" | sed 's/[^a-zA-Z0-9\u4e00-\u9fa5_-]//g')
        PROJECT_DIR="${WORKSPACE_ROOT}/${SAFE_NAME}_${TIMESTAMP}"
    fi

    # 生成歌词
    echo "📝 [Step ①] 生成歌词..."
    "$SCRIPT_DIR/generate_lyrics.sh" "$PROJECT_DIR"

    # 生成音乐
    echo "🎵 [Step ②] 生成音乐..."
    "$SCRIPT_DIR/generate_music.sh" "$PROJECT_DIR"

    # 读取歌曲信息用于展示
    SONG_TITLE=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(d.get('song_title', '未知'))
" 2>/dev/null || echo "未知")
    AUDIO_SIZE=$(du -h "$PROJECT_DIR/audio/song.mp3" 2>/dev/null | cut -f1 || echo "?")
    AUDIO_DUR=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(int(d.get('audio_duration_sec', 0)))
" 2>/dev/null || echo "?")

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ 创作完成！"
    echo "   歌曲：${SONG_TITLE}"
    echo "   时长：${AUDIO_DUR}s"
    echo "   文件：${AUDIO_SIZE}"
    echo "   目录：${PROJECT_DIR}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 暂停点：写入 info.json 标记等待用户确认
    python3 -c "
import json
path = '$PROJECT_DIR/metadata/info.json'
with open(path) as f:
    d = json.load(f)
d['pause_step2'] = True
d['step2_pending_approval'] = True
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
"

    # 全自动模式：自动设置 approval
    if [ "$AUTO_MODE" = "true" ]; then
        python3 -c "
import json
path = '$PROJECT_DIR/metadata/info.json'
with open(path) as f:
    d = json.load(f)
d['pause_step2'] = False
d['step2_pending_approval'] = False
d['step2_approved'] = True
d['align_mode'] = '${ALIGN_MODE:-auto}'
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
"
        echo "⏩ 自动模式：跳过 Step② 确认点"
        PHASE="align_ready"
    else
        # 输出暂停信息（Agent 必须读取此信息并询问用户）
        echo ""
        echo "⏸️ [PAUSE] Step①② 完成，等待用户确认是否继续。"
        echo ""
        echo "Agent 操作指引："
        echo "  1. 告知用户创作已完成（歌曲信息如上）"
        echo "  2. 询问：\"是否继续后续步骤？\""
        echo "  3. 选项：继续 / 暂停查看歌词"
        echo "  4. 如选择继续，询问对齐方式 A/B/C"
        echo ""
        echo "用户确认后，执行："
        echo "  $0 \"$PROJECT_DIR\" --phase align"
        echo ""
        exit 0  # 正常退出，等待 Agent 交互后再继续
    fi
fi

# ── 阶段二：对齐 ─────────────────────────────────────
if [ "$PHASE" = "align" ] || [ "$PHASE" = "align_ready" ]; then
    if [ -z "$PROJECT_DIR" ]; then
        echo "❌ 需要指定项目目录"
        exit 1
    fi

    # 暂停点检查：必须有 step2_approved
    APPROVED=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(str(d.get('step2_approved', False)).lower())
" 2>/dev/null)

    if [ "$APPROVED" != "true" ] && [ "$PHASE" != "align_ready" ]; then
        echo "⛔ [BLOCK] 用户尚未确认继续。"
        echo "   请先询问用户，设置 step2_approved=true 后再试。"
        echo ""
        echo "   手动绕过："
        echo "   python3 -c \"import json; d=json.load(open('${PROJECT_DIR}/metadata/info.json')); d['step2_approved']=True; d['align_mode']='auto'; json.dump(d, open('${PROJECT_DIR}/metadata/info.json','w'), indent=2)\""
        exit 1
    fi

    # 读取对齐模式
    if [ -z "$ALIGN_MODE" ]; then
        ALIGN_MODE=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(d.get('align_mode', 'auto'))
" 2>/dev/null || echo "auto")
    fi

    SRT_FLAG=""
    if [ "$ALIGN_MODE" = "manual" ]; then
        SRT_FILE=$(python3 -c "
import json
with open('$PROJECT_DIR/metadata/info.json') as f:
    d = json.load(f)
print(d.get('manual_srt_file', ''))
" 2>/dev/null || echo "")
        if [ -n "$SRT_FILE" ]; then
            SRT_FLAG="--srt-file $SRT_FILE"
        fi
    fi

    echo "🔗 [Step ③] 歌词对齐（模式: $ALIGN_MODE）..."
    "$SCRIPT_DIR/align_lyrics.sh" "$PROJECT_DIR" --align-mode "$ALIGN_MODE" $SRT_FLAG

    # 对齐完成后，如果下一阶段也是 auto 就不暂停
    if [ "$AUTO_MODE" != "true" ] && [ -z "$PHASE" ]; then
        echo ""
        echo "⏸️ [INFO] Step③ 完成。继续执行生图..."
    fi

    # 如果只有 --phase align，就停在这里
    if [ "$PHASE" = "align" ] && [ "$AUTO_MODE" != "true" ]; then
        echo ""
        echo "✅ Step③ 对齐完成。继续执行："
        echo "  $0 \"$PROJECT_DIR\" --phase produce"
        exit 0
    fi

    # 进入生图（自动）
    PHASE="produce"
fi

# ── 阶段三：生图 + Ken Burns ─────────────────────────
if [ "$PHASE" = "produce" ] || [ "$PHASE" = "align_ready" ]; then
    # 处理从 align_ready 过来的未赋值情况
    if [ "$PHASE" = "align_ready" ]; then
        PHASE="produce"
    fi

    if [ -z "$PROJECT_DIR" ]; then
        echo "❌ 需要指定项目目录"
        exit 1
    fi

    echo "🎨 [Step ④-⑧] 生成角色图 + 场景图 + Ken Burns..."
    "$SCRIPT_DIR/produce_mv.sh" "$PROJECT_DIR"

    echo ""
    echo "✅ 生图完成。合成导出..."
    PHASE="export"
fi

# ── 阶段四：合成导出 ─────────────────────────────────
if [ "$PHASE" = "export" ]; then
    if [ -z "$PROJECT_DIR" ]; then
        echo "❌ 需要指定项目目录"
        exit 1
    fi

    echo "🎬 [Step ⑨-⑪] 合成视频 + 导出..."
    "$SCRIPT_DIR/merge_and_export.sh" "$PROJECT_DIR"

    # 检查输出
    FINAL="${PROJECT_DIR}/output/final.mp4"
    if [ -f "$FINAL" ]; then
        SIZE=$(du -h "$FINAL" | cut -f1)
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🎉 MV 制作完成！"
        echo "   输出目录: ${PROJECT_DIR}/output/"
        echo "   final.mp4: ${SIZE}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        # 生成 LLM 日志汇总报告（HTML + 更新 info.json）
        REPORT_HTML="${PROJECT_DIR}/metadata/llm_report.html"
        LOG_SUMMARY=$(PROJECT_DIR="$PROJECT_DIR" SCRIPT_DIR="$SCRIPT_DIR" python3 - <<- PYREPORT
import json, os, sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from analyze_llm_logs import analyze_project, STEP_LABELS, STEP_ORDER
    proj = '$PROJECT_DIR'
    by_step = analyze_project(proj)
    if by_step:
        total_calls = sum(v['count'] for v in by_step.values())
        total_tokens = sum(v['tokens'] for v in by_step.values())
        models = set()
        for v in by_step.values():
            models.update(v['models'])
        model_list = ','.join(sorted(models))
        lines = []
        lines.append('## 🤖 LLM 交互日志')
        lines.append(f"""**日志文件**: `{proj}/metadata/llm_calls/` | **汇总报告**: `{proj}/metadata/llm_report.html`")
        lines.append('')
        lines.append('| 步骤 | 调用次数 | 模型 | 估算token | 错误 |')
        lines.append('|------|---------|------|-----------|------|')
        for step in STEP_ORDER:
            if step not in by_step:
                continue
            v = by_step[step]
            label = STEP_LABELS.get(step, step)
            models_s = ','.join(sorted(v['models']))[:20]
            err_s = str(v['errors']) if v['errors'] > 0 else '-'
            tok_s = f"{v['tokens']:.0f}"
            lines.append(f'| {label} | {v["count"]} | {models_s} | {tok_s} | {err_s} |')
        lines.append('')
        lines.append(f'**合计**: {total_calls} 次调用 | ~{total_tokens:.0f} token | 模型: {model_list}')
        print('\n'.join(lines))
    else:
        print('**LLM 日志**: 无记录（可能未开启日志）')
except Exception as e:
    print(f'**LLM 日志**: 生成失败 ({e})')
PYREPORT
        )

        # 生成 HTML 报告（独立脚本）
        python3 - <<- PYHTML
import json, sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from collections import defaultdict
    proj = '$PROJECT_DIR'
    log_dir = Path(proj) / 'metadata' / 'llm_calls'
    all_records = []
    for f in sorted(log_dir.glob('*.jsonl')):
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line: continue
                try: all_records.append(json.loads(line))
                except: pass
    archive_dir = log_dir / 'archive' / '2026-04'
    if archive_dir.exists():
        for f in sorted(archive_dir.glob('*.jsonl')):
            with open(f, encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line: continue
                    try: all_records.append(json.loads(line))
                    except: pass
    all_records.sort(key=lambda x: x.get('timestamp', ''))
    STEP_LABELS = {'lyrics':'🎵 歌词','music':'🎶 音乐','scene_desc_batch':'🤖 批量场景','scene_desc_single':'🔹 单场景','variant_desc_batch':'🤖 批量变体','variant_desc_single':'🔹 单变体','scene_img':'🖼️ 图片'}
    STEP_ORDER = ['lyrics','music','scene_desc_batch','scene_desc_single','variant_desc_batch','variant_desc_single','scene_img']
    by_step = defaultdict(list)
    for r in all_records:
        if r.get('step') != 'test_step':
            by_step[r.get('step','?')].append(r)
    def esc(s):
        if s is None: return ''
        return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    def tag(step):
        m = {'lyrics':'tag-lyrics','music':'tag-music'}
        for k in m:
            if k in step: return m[k]
        return 'tag-scene'
    html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>LLM 日志 — {proj.split("/")[-1]}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,sans-serif;background:#0f0f1a;color:#e0e0e0;padding:24px}}
h1{{color:#fff;margin-bottom:4px}}.sub{{color:#666;font-size:13px;margin-bottom:20px}}
.stat{{display:flex;gap:14px;margin-bottom:24px}}.s{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:8px;padding:10px 16px}}
.s .n{{font-size:22px;font-weight:700;color:#7eb8ff}}.s .l{{font-size:11px;color:#888;margin-top:3px}}
.filter{{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}}
.btn{{background:#1e1e32;border:1px solid #2a2a4a;color:#888;padding:5px 14px;border-radius:6px;font-size:12px;cursor:pointer}}
.btn:hover{{border-color:#3a6aaa;color:#a0c4ff}}.btn.active{{background:#1e3a6a;border-color:#3a6aaa;color:#a0c4ff}}
.section{{margin-bottom:40px}}.section h2{{color:#a0c4ff;font-size:14px;border-bottom:1px solid #2a2a4a;padding:8px 0;margin-bottom:14px}}
.record{{background:#13132a;border:1px solid #1e1e38;border-radius:10px;margin-bottom:14px;overflow:hidden}}
.record-header{{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1a1a30;cursor:pointer}}
.record-header:hover{{background:#1e1e3a}}.toggle{{color:#7eb8ff;font-size:12px;width:14px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px}}
.tag-lyrics{{background:#1a3a2a;color:#7eb8ff}}.tag-music{{background:#2a1a3a;color:#c5a0ff}}
.tag-scene{{background:#1a2a3a;color:#a0d4ff}}.tag-img{{background:#2a2a1a;color:#ffc87e}}
.model{{font-size:12px;color:#7eb8ff;font-weight:600}}.meta{{font-size:11px;color:#444;margin-left:auto}}
.record-body{{padding:0 14px 12px;display:none}}.record-body.open{{display:block}}
.field{{margin-top:12px}}.field-label{{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}}
.field-value{{font-size:12px;color:#c5d4f0;line-height:1.6;background:#0d0d1e;border:1px solid #1a1a30;border-radius:6px;padding:8px 10px}}
.prompt-full{{white-space:pre-wrap;word-break:break-all;margin:0;font-family:inherit;color:#b8d0f0}}
.copy-btn{{background:#1e3a6a;border:1px solid #2a5a9a;color:#a0c4ff;padding:3px 10px;border-radius:4px;font-size:10px;cursor:pointer;margin-bottom:6px}}
.copy-btn:hover{{background:#2a5a9a}}.err{{color:#e55;font-size:11px}}
.resp-text{{white-space:pre-wrap;word-break:break-all;font-size:11px;color:#8bce8b;max-height:200px;overflow-y:auto}}
</style></head><body>
<h1>🎬 LLM 完整 Prompt 日志 — {proj.split("/")[-1]}</h1>
<div class="sub">{len(all_records)} 条记录 | 点击每条展开查看完整内容</div>
<div class="stat">
<div class="s"><div class="n">{len(all_records)}</div><div class="l">总调用</div></div>
<div class="s"><div class="n">{len(by_step)}</div><div class="l">类型</div></div>
</div>
<div class="filter">
<button class="btn active" onclick="showAll(this)">全部</button>
'''
    for step in STEP_ORDER:
        if step not in by_step: continue
        html += f'<button class="btn" onclick="showSection(\'{step}\',this)">{STEP_LABELS.get(step,step)} ({len(by_step[step])})</button>\n'
    html += '</div>\n'
    for step in STEP_ORDER:
        if step not in by_step: continue
        recs = by_step[step]
        label = STEP_LABELS.get(step,step)
        tc = tag(step)
        html += f'<div class="section" id="sec-{step}"><h2>{label} — {len(recs)} 条 <span style="color:#8bce8b;font-size:11px">✓ 完整无省略</span></h2>\n'
        for i, r in enumerate(recs):
            ts = r.get('timestamp','')[:19]
            model = esc(r.get('model','-'))
            prompt_str = str(r.get('prompt','') or '')
            resp_raw = r.get('response')
            resp_str = json.dumps(resp_raw,ensure_ascii=False,indent=2) if isinstance(resp_raw,(dict,list)) else str(resp_raw or '')
            err_str = esc(r.get('error',''))
            rid = f'rec-{step}-{i}'
            html += f'''<div class="record" id="{rid}">
<div class="record-header" onclick="toggleRecord('{rid}')">
<span class="toggle">▶</span><span class="tag {tc}">{esc(label)}</span>
<span class="model">{model}</span>
<span class="meta">{ts} | prompt {len(prompt_str)} chars | response {len(resp_str)} chars</span>
</div>
<div class="record-body" id="{rid}-body">
<div class="field"><div class="field-label">📝 完整 Prompt</div>
<div class="field-value"><button class="copy-btn" onclick="event.stopPropagation();copyText('{rid}-prompt')">复制 Prompt</button>
<pre class="prompt-full" id="{rid}-prompt">{esc(prompt_str)}</pre></div></div>
<div class="field"><div class="field-label">📦 完整 Response</div>
<div class="field-value"><div class="resp-text">{esc(resp_str)}</div></div></div>
'''
            if err_str: html += f'<div class="field"><div class="field-label">❌ 错误</div><div class="field-value"><span class="err">{err_str}</span></div></div>\n'
            extra = r.get('extra',{})
            if extra and isinstance(extra,dict): html += f'<div class="field"><div class="field-label">📊 Extra</div><div class="field-value"><pre class="prompt-full" style="font-size:11px">{esc(json.dumps(extra,ensure_ascii=False))}</pre></div></div>\n'
            html += '</div></div>\n'
        html += '</div>\n'
    html += '''<script>
function toggleRecord(id){var b=document.getElementById(id+'-body');var t=document.querySelector('#'+id+' .toggle');if(b.classList.contains('open')){b.classList.remove('open');t.textContent='▶'}else{b.classList.add('open');t.textContent='▼'}}
function showSection(name,btn){document.querySelectorAll('.section').forEach(s=>s.style.display='none');document.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.getElementById('sec-'+name).style.display='block'}
function showAll(btn){document.querySelectorAll('.section').forEach(s=>s.style.display='block');document.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active')}
function copyText(id){var el=document.getElementById(id);if(!el)return;navigator.clipboard.writeText(el.textContent||el.innerText).then(function(){var btns=document.querySelectorAll('.copy-btn');btns.forEach(function(b){b.textContent='复制 Prompt'});event.target.textContent='已复制!';setTimeout(function(){event.target.textContent='复制 Prompt'},1500)}).catch(function(){})}
</script></body></html>'''
    out = Path('$PROJECT_DIR/metadata/llm_report.html')
    out.write_text(html, encoding='utf-8')
    print(f'✅ LLM 日志报告已生成: {out}')
except Exception as e:
    print(f'⚠️  HTML报告生成失败: {e}')
PYHTML

        # 更新 info.json 记录报告路径
        python3 -c "
import json
path = '$PROJECT_DIR/metadata/info.json'
with open(path) as f:
    d = json.load(f)
d['llm_report_path'] = '${PROJECT_DIR}/metadata/llm_report.html'
d['llm_log_dir'] = '${PROJECT_DIR}/metadata/llm_calls/'
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
" 2>/dev/null

        echo "$LOG_SUMMARY"
        echo ""
        echo "📋 LLM 日志报告: ${PROJECT_DIR}/metadata/llm_report.html"
        echo ""
        # 清理暂停标记
        python3 -c "
import json
path = '$PROJECT_DIR/metadata/info.json'
with open(path) as f:
    d = json.load(f)
d['pause_step2'] = False
d['step2_pending_approval'] = False
d['steps_completed'] = list(set(d.get('steps_completed', []) + ['all']))
with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
" 2>/dev/null || true
    else
        echo "⚠️ 导出可能未完成，请检查输出目录"
    fi
fi
