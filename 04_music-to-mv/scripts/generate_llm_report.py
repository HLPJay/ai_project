#!/usr/bin/env python3
"""
generate_llm_report.py — 生成 LLM 交互完整 HTML 报告
读取 metadata/llm_calls/ 目录下所有 JSONL 文件，生成交互式 HTML 报告

用法:
    python3 generate_llm_report.py <项目目录> [--output <输出路径>]
"""

import json, os, sys, html
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# ── HTML 模板 ─────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 20px 24px; }
h1 { color: #fff; margin-bottom: 4px; }
.sub { color: #666; font-size: 13px; margin-bottom: 20px; }
.stat { display: flex; gap: 14px; margin-bottom: 24px; flex-wrap: wrap; }
.s { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 8px; padding: 10px 16px; }
.s .n { font-size: 22px; font-weight: 700; color: #7eb8ff; }
.s .l { font-size: 11px; color: #888; margin-top: 3px; }
.filter { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; align-items: center; }
.filter-label { color: #555; font-size: 12px; margin-right: 4px; }
.btn { background: #1e1e32; border: 1px solid #2a2a4a; color: #888; padding: 5px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: #3a6aaa; color: #a0c4ff; }
.btn.active { background: #1e3a6a; border-color: #3a6aaa; color: #a0c4ff; }
.section { margin-bottom: 40px; }
.section h2 { color: #a0c4ff; font-size: 14px; border-bottom: 1px solid #2a2a4a; padding: 8px 0; margin-bottom: 14px; }
.record { background: #13132a; border: 1px solid #1e1e38; border-radius: 10px; margin-bottom: 14px; overflow: hidden; }
.record-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: #1a1a30; cursor: pointer; }
.record-header:hover { background: #1e1e3a; }
.toggle { color: #7eb8ff; font-size: 12px; width: 14px; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; }
.tag-lyrics { background: #1a3a2a; color: #7eb8ff; }
.tag-music { background: #2a1a3a; color: #c5a0ff; }
.tag-scene { background: #1a2a3a; color: #a0d4ff; }
.tag-img { background: #2a2a1a; color: #ffc87e; }
.tag-analyze { background: #3a1a2a; color: #ff9eb8; }
.tag-unknown { background: #2a2a2a; color: #aaa; }
.model { font-size: 12px; color: #7eb8ff; font-weight: 600; }
.meta { font-size: 11px; color: #444; margin-left: auto; }
.record-body { padding: 0 14px 12px; display: none; }
.record-body.open { display: block; }
.field { margin-top: 12px; }
.field-label { font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
.field-value { font-size: 12px; color: #c5d4f0; line-height: 1.6; background: #0d0d1e; border: 1px solid #1a1a30; border-radius: 6px; padding: 8px 10px; }
.prompt-full { white-space: pre-wrap; word-break: break-all; margin: 0; font-family: inherit; color: #b8d0f0; }
.copy-btn { background: #1e3a6a; border: 1px solid #2a5a9a; color: #a0c4ff; padding: 3px 10px; border-radius: 4px; font-size: 10px; cursor: pointer; }
.copy-btn:hover { background: #2a5a9a; }
.err { color: #e55; font-size: 11px; }
.resp-text { white-space: pre-wrap; word-break: break-all; font-size: 11px; color: #8bce8b; max-height: 200px; overflow-y: auto; }
.full-badge { background: #2a3a1a; color: #8bce8b; padding: 2px 8px; border-radius: 4px; font-size: 10px; margin-left: 8px; }
.fail-badge { background: #3a1a1a; color: #e55; padding: 2px 8px; border-radius: 4px; font-size: 10px; margin-left: 8px; }
"""

JS = """
function toggleRecord(id) {
    var body = document.getElementById(id + '-body');
    var all = document.querySelectorAll('.record-body');
    all.forEach(function(el) { if (el.id !== id + '-body') el.classList.remove('open'); });
    body.classList.toggle('open');
}
function showSection(name, btn) {
    var secs = document.querySelectorAll('.section');
    secs.forEach(function(s) { s.style.display = 'none'; });
    var target = document.getElementById('sec-' + name);
    if (target) target.style.display = 'block';
    document.querySelectorAll('.btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
}
function showAll(btn) {
    document.querySelectorAll('.section').forEach(function(s) { s.style.display = 'block'; });
    document.querySelectorAll('.btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
}
function copyText(id) {
    var el = document.getElementById(id);
    if (el) {
        var text = el.textContent || el.innerText;
        navigator.clipboard.writeText(text).then(function() { alert('已复制'); });
    }
}
function showAllBtns() {
    var allBtn = document.querySelector('.filter .btn');
    if (allBtn) showAll(allBtn);
}
window.onload = showAllBtns;
"""

STEP_TAGS = {
    'lyrics': ('🎵 歌词生成', 'tag-lyrics'),
    'music': ('🎵 音乐生成', 'tag-music'),
    'scene_desc': ('🎨 场景描述', 'tag-scene'),
    'scene_img': ('🖼️ 场景图片', 'tag-img'),
    'variant_desc': ('🔄 变体描述', 'tag-scene'),
    'base_char': ('👤 角色图', 'tag-img'),
    'analyze': ('🤖 场景分析', 'tag-analyze'),
    'unknown': ('❓ 未知', 'tag-unknown'),
}

def get_step_tag(step):
    for key, (label, cls) in STEP_TAGS.items():
        if key in step.lower():
            return label, cls
    return STEP_TAGS['unknown']

def count_tokens(text):
    """粗略估算 token 数（中文字符 ≈ 2token，英文 ≈ 0.25token）"""
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    english = len([c for c in text if c.isascii()])
    # 中文字符 ≈ 2.5 token（MiniMax 上限约 3），英文 ≈ 0.25 token
    return chinese * 2.5 + english * 0.25

def truncate(s, maxlen=200):
    s = str(s) if s is not None else ''
    if len(s) <= maxlen:
        return s
    return s[:maxlen] + '...'

def format_bytes(size):
    if size is None:
        return ''
    if isinstance(size, dict):
        size = size.get('size', 0)
    if isinstance(size, int):
        return f'{size//1024}KB'
    return str(size)

def build_record(entry, index):
    step = entry.get('step', 'unknown')
    model = entry.get('model', 'unknown')
    timestamp = entry.get('timestamp', '')
    prompt = entry.get('prompt', '')
    response = entry.get('response')
    error = entry.get('error')
    extra = entry.get('extra', {})

    tag_label, tag_cls = get_step_tag(step)
    rid = f"rec-{index}"

    # prompt 长度
    prompt_chars = len(str(prompt)) if prompt else 0
    prompt_tokens = int(count_tokens(str(prompt)))

    # response 信息
    if response is not None:
        if isinstance(response, dict):
            resp_info = f"response {len(str(response))} chars"
        else:
            resp_info = f"response {len(str(response))} chars"
    elif error:
        resp_info = '❌ 失败'
    else:
        resp_info = 'response 0 chars'

    meta = f"{timestamp} &nbsp;|&nbsp; prompt {prompt_chars} chars &nbsp;|&nbsp; ~{prompt_tokens} tokens &nbsp;|&nbsp; {resp_info}"

    prompt_html = html.escape(str(prompt)) if prompt else '(empty)'
    # response 展示
    if error:
        resp_html = f'<div class="field"><div class="field-label">❌ 错误</div><div class="field-value"><span class="err">{html.escape(str(error))}</span></div></div>'
    elif response is not None:
        resp_str = json.dumps(response, ensure_ascii=False, indent=2) if isinstance(response, (dict, list)) else str(response)
        resp_html = f'''<div class="field">
            <div class="field-label">📦 完整 Response / 结果</div>
            <div class="field-value"><div class="resp-text">{html.escape(truncate(resp_str, 2000))}</div></div>
        </div>'''
    else:
        resp_html = ''

    # extra 信息（sid 等）
    extra_html = ''
    if extra:
        extra_parts = [f"{k}={v}" for k, v in extra.items() if v]
        if extra_parts:
            extra_html = f'<div class="field"><div class="field-label">📋 附加信息</div><div class="field-value" style="font-size:11px;color:#888;">{" | ".join(extra_parts)}</div></div>'

    badge = '<span class="fail-badge">❌ 失败</span>' if error else ''

    return f"""
<div class="record" id="{rid}">
  <div class="record-header" onclick="toggleRecord('{rid}')">
    <span class="toggle">▶</span>
    <span class="tag {tag_cls}">{tag_label}</span>
    <span class="model">{html.escape(model)}</span>
    <span class="meta">{meta}</span>
    {badge}
  </div>
  <div class="record-body" id="{rid}-body">
    <div class="field">
      <div class="field-label">📝 完整 Prompt（全部内容）</div>
      <div class="field-value">
        <button class="copy-btn" onclick="event.stopPropagation(); copyText('{rid}-prompt')">复制 Prompt</button>
        <pre class="prompt-full" id="{rid}-prompt">{prompt_html}</pre>
      </div>
    </div>
    {resp_html}
    {extra_html}
  </div>
</div>"""

def generate_report(project_dir, output_path=None):
    proj = Path(project_dir)
    llm_dir = proj / 'metadata' / 'llm_calls'
    info_path = proj / 'metadata' / 'info.json'
    scenes_path = proj / 'metadata' / 'scenes.json'

    # 读取项目信息
    project_name = proj.name
    song_title = ''
    theme = ''
    if info_path.exists():
        info = json.loads(info_path.read_text())
        song_title = info.get('song_title', '')
        theme = info.get('theme', '')

    scenes_count = 0
    if scenes_path.exists():
        scenes = json.loads(scenes_path.read_text())
        scenes_count = len(scenes)

    # 读取所有 JSONL 文件
    records = []
    if llm_dir.exists():
        for fpath in sorted(llm_dir.glob('*.jsonl')):
            with open(fpath, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        records.append(entry)
                    except:
                        pass

    # 统计
    total = len(records)
    providers = set(r.get('model', 'unknown') for r in records)
    total_tokens = sum(int(count_tokens(str(r.get('prompt', '')))) for r in records)

    # 按 step 分组
    step_groups = defaultdict(list)
    for i, rec in enumerate(records):
        step = rec.get('step', 'unknown')
        # 标准化 step 名称（去掉 _batch / _single 后缀）
        step_key = step
        for suffix in ['_batch', '_single']:
            if step.endswith(suffix):
                step_key = step[:-len(suffix)]
        step_groups[step_key].append(i)

    # 排序 step_keys 为固定顺序
    step_order = ['lyrics', 'music', 'analyze', 'scene_desc', 'variant_desc', 'base_char', 'scene_img']
    sorted_steps = sorted(step_groups.keys(), key=lambda x: step_order.index(x) if x in step_order else 99)

    # 生成 section HTML
    sections_html = ''
    for step_key in sorted_steps:
        indices = step_groups[step_key]
        tag_label, tag_cls = get_step_tag(step_key)
        badge = '<span class="full-badge">✓ 完整无省略</span>'
        failed = any(records[i].get('error') for i in indices)
        if failed:
            badge = '<span class="fail-badge">⚠️ 部分失败</span>'
        sections_html += f'''
<div class="section" id="sec-{step_key}">
  <h2>{tag_label} — {len(indices)} 条（点击每条查看完整 Prompt）{badge}</h2>
'''
        for idx in indices:
            sections_html += build_record(records[idx], idx) + '\n'
        sections_html += '</div>\n'

    # 生成过滤器按钮
    filter_btns = f'<span class="filter-label">按类型：</span><button class="btn active" onclick="showAll(this)">全部</button>'
    for step_key in sorted_steps:
        count = len(step_groups[step_key])
        tag_label, _ = get_step_tag(step_key)
        filter_btns += f'<button class="btn" onclick="showSection(\'{step_key}\', this)">{tag_label} ({count})</button>'

    html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM 完整 Prompt 日志 — {html.escape(song_title or project_name)}</title>
<style>{CSS}</style>
</head>
<body>
<h1>🎬 LLM 完整 Prompt 日志 — {html.escape(song_title or project_name)}</h1>
<div class="sub">{project_name} &nbsp;|&nbsp; {total} 条记录 &nbsp;|&nbsp; {scenes_count} 场景 &nbsp;|&nbsp; 点击每条展开查看完整内容</div>
<div class="stat">
  <div class="s"><div class="n">{total}</div><div class="l">总调用</div></div>
  <div class="s"><div class="n">{len(providers)}</div><div class="l">Provider</div></div>
  <div class="s"><div class="n">~{total_tokens}</div><div class="l">估算token</div></div>
</div>
<div class="filter">{filter_btns}</div>
{sections_html}
<script>{JS}</script>
</body>
</html>'''

    if output_path:
        Path(output_path).write_text(html_content, encoding='utf-8')
        print(f'✅ 报告已生成: {output_path}')
    else:
        default_output = proj / 'output' / 'llm_report.html'
        default_output.parent.mkdir(exist_ok=True)
        default_output.write_text(html_content, encoding='utf-8')
        print(f'✅ 报告已生成: {default_output}')

    return html_content

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='生成 LLM 交互 HTML 报告')
    parser.add_argument('project_dir', help='项目目录')
    parser.add_argument('--output', '-o', help='输出路径（默认 项目/output/llm_report.html）')
    args = parser.parse_args()
    generate_report(args.project_dir, args.output)