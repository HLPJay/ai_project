"""
report_generator.py — LLM 交互日志 HTML 报告生成器

纯 Python 实现，替代原版 scripts/generate_llm_report.py（325 行）。
无需 bash，内联 HTML 模板。

功能：
  - 读取 metadata/llm_calls/ 下的所有 JSONL 文件
  - 按 step 分组统计（lyrics, music, analyze, scene_desc, ...）
  - 生成交互式 HTML 报告（可折叠、按类型筛选）
  - 显示 prompt、response、error、token 估算

用法：
    from src.report_generator import ReportGenerator
    generator = ReportGenerator(project_dir)
    html_content = generator.generate()  # 输出到默认路径
    # 或
    html_content = generator.generate(output_path="custom.html")
"""

import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


# ════════════════════════════════════════════════════════════
# Step 标签映射
# ════════════════════════════════════════════════════════════

STEP_LABELS = {
    "lyrics": ("歌词生成", "tag-lyrics"),
    "music": ("音乐生成", "tag-music"),
    "scene_desc": ("场景描述", "tag-scene"),
    "scene_img": ("场景图片", "tag-img"),
    "variant_desc": ("变体描述", "tag-scene"),
    "base_char": ("角色图", "tag-img"),
    "analyze": ("场景分析", "tag-analyze"),
    "unknown": ("未知", "tag-unknown"),
}

STEP_ORDER = [
    "lyrics", "music", "analyze",
    "scene_desc", "variant_desc", "base_char", "scene_img",
]


# ════════════════════════════════════════════════════════════
# HTML/CSS/JS 模板
# ════════════════════════════════════════════════════════════

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
        navigator.clipboard.writeText(text).then(function() { alert('\\u5df2\\u590d\\u5236'); });
    }
}
window.onload = function() {
    var allBtn = document.querySelector('.filter .btn');
    if (allBtn) showAll(allBtn);
};
"""


# ════════════════════════════════════════════════════════════
# 报告生成器
# ════════════════════════════════════════════════════════════

class ReportGeneratorError(Exception):
    """报告生成错误"""
    pass


class ReportGenerator:
    """LLM 交互日志 HTML 报告生成器

    读取 metadata/llm_calls/ 下的所有 JSONL 日志文件，
    生成交互式 HTML 报告（可折叠、可筛选、可复制 prompt）。

    Usage:
        generator = ReportGenerator(project_dir)
        generator.generate()  # 输出到 {project_dir}/output/llm_report.html
        generator.generate("report.html")  # 自定义路径
    """

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.metadata_dir = self.project_dir / "metadata"
        self.llm_dir = self.metadata_dir / "llm_calls"
        self.records: List[Dict] = []

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def generate(self, output_path: Optional[str] = None) -> str:
        """生成报告

        Args:
            output_path: 输出路径（默认 {project_dir}/output/llm_report.html）

        Returns:
            HTML 字符串
        """
        # 1. 收集数据
        self._load_records()
        execution_summary = self.generate_execution_summary(write=True)

        # 2. 读取项目信息
        project_name = self.project_dir.name
        song_title, theme = self._load_project_info()
        scenes_count = self._load_scenes_count()

        # 3. 统计数据
        total = len(self.records)
        providers = self._collect_providers()
        total_tokens = int(sum(self._count_tokens(str(r.get("prompt", "")))
                              for r in self.records))

        # 4. 按 step 分组
        step_groups = self._group_by_step()
        sorted_steps = self._sort_steps(step_groups)

        # 5. 构建 HTML
        summary_html = self._build_execution_summary_html(execution_summary)
        sections_html = self._build_sections(step_groups, sorted_steps)
        filter_btns = self._build_filter_buttons(step_groups, sorted_steps)

        html_content = self._wrap_html(
            project_name, song_title, total, len(providers),
            total_tokens, scenes_count, filter_btns, summary_html + sections_html,
        )

        # 6. 写入文件
        self._write_output(html_content, output_path)

        return html_content

    def generate_execution_summary(self, write: bool = True) -> Dict[str, Any]:
        """生成执行过程摘要，聚合调用次数、超时、错误原因和慢请求。"""
        calls = self._load_call_records()
        song_title, theme = self._load_project_info()

        by_key: Dict[str, Dict[str, Any]] = {}
        errors = Counter()
        slow_calls = []
        finish_reasons = Counter()
        reasoning_only_count = 0

        total_latency = 0.0
        max_latency = 0.0
        success_count = 0
        failed_count = 0
        timeout_count = 0

        for rec in calls:
            key = rec.get("prompt_key") or rec.get("step") or "unknown"
            status = rec.get("status", "success")
            latency = float(rec.get("latency_ms") or 0)
            error = rec.get("error") or ""
            total_latency += latency
            max_latency = max(max_latency, latency)

            if key not in by_key:
                by_key[key] = {
                    "calls": 0,
                    "success": 0,
                    "failed": 0,
                    "timeouts": 0,
                    "avg_latency_ms": 0.0,
                    "max_latency_ms": 0.0,
                    "finish_reasons": {},
                    "errors": {},
                }
            item = by_key[key]
            item["calls"] += 1
            item["max_latency_ms"] = max(item["max_latency_ms"], latency)
            item["avg_latency_ms"] = (
                (item["avg_latency_ms"] * (item["calls"] - 1) + latency) / item["calls"]
            )

            if status == "failed" or error:
                failed_count += 1
                item["failed"] += 1
                if error:
                    errors[error] += 1
                    item_errors = Counter(item["errors"])
                    item_errors[error] += 1
                    item["errors"] = dict(item_errors)
            else:
                success_count += 1
                item["success"] += 1

            if self._is_timeout_error(error):
                timeout_count += 1
                item["timeouts"] += 1

            response_info = self._inspect_response(rec)
            reason = response_info.get("finish_reason")
            if reason:
                finish_reasons[reason] += 1
                item_reasons = Counter(item["finish_reasons"])
                item_reasons[reason] += 1
                item["finish_reasons"] = dict(item_reasons)
            if response_info.get("reasoning_only"):
                reasoning_only_count += 1

            if latency >= 60000:
                slow_calls.append({
                    "prompt_key": key,
                    "model": rec.get("model", ""),
                    "latency_ms": int(latency),
                    "status": status,
                    "error": error,
                    "finish_reason": reason or "",
                })

        total_calls = len(calls)
        summary = {
            "generated_at": datetime.now().isoformat(),
            "project": self.project_dir.name,
            "song_title": song_title,
            "theme": theme,
            "totals": {
                "api_calls": total_calls,
                "success": success_count,
                "failed": failed_count,
                "timeouts": timeout_count,
                "avg_latency_ms": int(total_latency / total_calls) if total_calls else 0,
                "max_latency_ms": int(max_latency),
                "finish_reason_length": finish_reasons.get("length", 0),
                "reasoning_only_responses": reasoning_only_count,
            },
            "by_prompt_key": by_key,
            "top_errors": [
                {"error": err, "count": count}
                for err, count in errors.most_common(10)
            ],
            "slow_calls": sorted(
                slow_calls, key=lambda x: x.get("latency_ms", 0), reverse=True
            )[:20],
            "notes": self._build_execution_notes(timeout_count, failed_count, finish_reasons, reasoning_only_count),
        }

        if write:
            self._write_execution_summary(summary)
        return summary

    # ══════════════════════════════════════════════════════
    # 数据加载
    # ══════════════════════════════════════════════════════

    def _load_records(self):
        """加载所有 JSONL 记录"""
        self.records = []
        if not self.llm_dir.exists():
            return

        for fpath in sorted(self.llm_dir.glob("*.jsonl")):
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self.records.append(self._normalize_record(entry))
                    except json.JSONDecodeError:
                        pass

    def _load_call_records(self) -> List[Dict]:
        """只读取 calls.jsonl，避免 errors/evaluations 重复计数。"""
        calls_path = self.llm_dir / "calls.jsonl"
        if not calls_path.exists():
            return []

        calls = []
        with open(calls_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    calls.append(self._normalize_record(json.loads(line)))
                except json.JSONDecodeError:
                    pass
        return calls

    def _normalize_record(self, entry: Dict) -> Dict:
        """兼容旧版 step/prompt 日志和新版 LLMLogger 摘要日志。"""
        rec = dict(entry)

        response_file = rec.get("response_file")
        full = self._load_response_file(response_file) if response_file else {}

        prompt_key = rec.get("prompt_key") or full.get("prompt_key")
        if "step" not in rec and prompt_key:
            rec["step"] = prompt_key

        prompt = rec.get("prompt") or rec.get("rendered_prompt") or full.get("rendered_prompt")
        if prompt is not None:
            rec["prompt"] = prompt

        if "response" not in rec:
            response = full.get("response") or full.get("raw_response")
            if response not in (None, ""):
                rec["response"] = response

        if rec.get("status") == "failed" and "error" not in rec:
            rec["error"] = full.get("error") or rec.get("error") or "failed"

        return rec

    def _load_response_file(self, response_file: str) -> Dict:
        """读取 LLMLogger 保存的完整响应文件。"""
        if not response_file:
            return {}

        path = Path(response_file)
        if not path.is_absolute():
            path = self.llm_dir / path

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _is_timeout_error(error: str) -> bool:
        lower = (error or "").lower()
        return "timeout" in lower or "timed out" in lower

    @staticmethod
    def _parse_response_payload(response: Any) -> Any:
        if isinstance(response, (dict, list)):
            return response
        if not response:
            return None
        try:
            return json.loads(str(response))
        except (json.JSONDecodeError, TypeError):
            return None

    def _inspect_response(self, rec: Dict) -> Dict[str, Any]:
        """提取 finish_reason 和 reasoning-only 等模型输出特征。"""
        payload = self._parse_response_payload(rec.get("response"))
        if not isinstance(payload, dict):
            return {}

        choices = payload.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return {}

        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content", "")
        reasoning = (
            message.get("reasoning_content")
            or message.get("reasoning_details")
            or message.get("reasoning")
        )
        return {
            "finish_reason": choice.get("finish_reason", ""),
            "reasoning_only": bool(reasoning and not content),
        }

    @staticmethod
    def _build_execution_notes(timeout_count: int, failed_count: int,
                               finish_reasons: Counter,
                               reasoning_only_count: int) -> List[str]:
        notes = []
        if timeout_count:
            notes.append("存在 API 超时，请查看 top_errors 和 slow_calls 中的 prompt_key。")
        if finish_reasons.get("length", 0):
            notes.append("存在 finish_reason=length，说明模型输出被截断，可能导致 JSON 解析失败或触发 fallback。")
        if reasoning_only_count:
            notes.append("存在 reasoning-only 响应，说明推理内容占用输出额度，content 为空。")
        if failed_count == 0 and not notes:
            notes.append("未发现失败调用或明显超时。")
        return notes

    def _write_execution_summary(self, summary: Dict[str, Any]):
        """写入 metadata/output 两份摘要 JSON。"""
        for target in [
            self.metadata_dir / "execution_summary.json",
            self.project_dir / "output" / "execution_summary.json",
        ]:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

    def _load_project_info(self) -> tuple:
        """读取歌曲标题和主题"""
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            return info.get("song_title", ""), info.get("theme", "")
        return "", ""

    def _load_scenes_count(self) -> int:
        """读取场景数量"""
        scenes_path = self.metadata_dir / "scenes.json"
        if scenes_path.exists():
            try:
                scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
                return len(scenes)
            except (json.JSONDecodeError, TypeError):
                pass
        return 0

    # ══════════════════════════════════════════════════════
    # 统计
    # ══════════════════════════════════════════════════════

    def _collect_providers(self) -> set:
        return set(r.get("model", "unknown") for r in self.records)

    def _group_by_step(self) -> Dict[str, List[int]]:
        """按 step 分组，标准化后缀"""
        groups = defaultdict(list)
        for i, rec in enumerate(self.records):
            step = rec.get("step", "unknown")
            step_key = step
            for suffix in ["_batch", "_single"]:
                if step.endswith(suffix):
                    step_key = step[: -len(suffix)]
                    break
            groups[step_key].append(i)
        return groups

    def _sort_steps(self, groups: Dict[str, List[int]]) -> List[str]:
        """按预定义顺序排序"""
        return sorted(
            groups.keys(),
            key=lambda x: STEP_ORDER.index(x) if x in STEP_ORDER else 99,
        )

    # ══════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _get_step_tag(step: str) -> tuple:
        """获取 step 的标签和 CSS class"""
        for key, (label, cls) in STEP_LABELS.items():
            if key in step.lower():
                return label, cls
        return STEP_LABELS["unknown"]

    @staticmethod
    def _count_tokens(text: str) -> float:
        """粗略估算 token 数"""
        if not text:
            return 0
        chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        english = sum(1 for c in text if c.isascii() and c.isprintable())
        return chinese * 2.5 + english * 0.25

    @staticmethod
    def _truncate(s: Any, maxlen: int = 200) -> str:
        s = str(s) if s is not None else ""
        if len(s) <= maxlen:
            return s
        return s[:maxlen] + "..."

    @staticmethod
    def _format_bytes(size: Any) -> str:
        if size is None:
            return ""
        if isinstance(size, dict):
            size = size.get("size", 0)
        if isinstance(size, int):
            return f"{size // 1024}KB"
        return str(size)

    # ══════════════════════════════════════════════════════
    # HTML 构建
    # ══════════════════════════════════════════════════════

    def _build_record_html(self, entry: Dict, index: int) -> str:
        """构建单条记录 HTML"""
        step = entry.get("step", "unknown")
        model = entry.get("model", "unknown")
        timestamp = entry.get("timestamp", "")
        prompt = entry.get("prompt", "")
        response = entry.get("response")
        error = entry.get("error")
        extra = entry.get("extra", {})

        tag_label, tag_cls = self._get_step_tag(step)
        rid = f"rec-{index}"

        prompt_chars = len(str(prompt)) if prompt else 0
        prompt_tokens = int(self._count_tokens(str(prompt)))

        if response is not None:
            resp_info = f"response {len(str(response))} chars"
        elif error:
            resp_info = "失败"
        else:
            resp_info = "response 0 chars"

        meta = (f"{timestamp} | prompt {prompt_chars} chars "
                f"| ~{prompt_tokens} tokens | {resp_info}")

        prompt_html = html.escape(str(prompt)) if prompt else "(empty)"

        if error:
            resp_html = (
                f'<div class="field">'
                f'<div class="field-label">错误</div>'
                f'<div class="field-value">'
                f'<span class="err">{html.escape(str(error))}</span>'
                f'</div></div>'
            )
        elif response is not None:
            resp_str = (
                json.dumps(response, ensure_ascii=False, indent=2)
                if isinstance(response, (dict, list))
                else str(response)
            )
            resp_html = (
                f'<div class="field">'
                f'<div class="field-label">完整 Response / 结果</div>'
                f'<div class="field-value">'
                f'<div class="resp-text">'
                f'{html.escape(self._truncate(resp_str, 2000))}'
                f'</div></div></div>'
            )
        else:
            resp_html = ""

        extra_html = ""
        if extra:
            extra_parts = [f"{k}={v}" for k, v in extra.items() if v]
            if extra_parts:
                extra_html = (
                    f'<div class="field"><div class="field-label">附加信息</div>'
                    f'<div class="field-value" style="font-size:11px;color:#888;">'
                    f'{" | ".join(extra_parts)}</div></div>'
                )

        badge = '<span class="fail-badge">失败</span>' if error else ""

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
      <div class="field-label">完整 Prompt</div>
      <div class="field-value">
        <button class="copy-btn" onclick="event.stopPropagation(); copyText('{rid}-prompt')">复制 Prompt</button>
        <pre class="prompt-full" id="{rid}-prompt">{prompt_html}</pre>
      </div>
    </div>
    {resp_html}
    {extra_html}
  </div>
</div>"""

    def _build_sections(
        self, groups: Dict[str, List[int]], sorted_steps: List[str]
    ) -> str:
        """构建所有 section 的 HTML"""
        sections = ""
        for step_key in sorted_steps:
            indices = groups[step_key]
            tag_label, _ = self._get_step_tag(step_key)

            has_error = any(self.records[i].get("error") for i in indices)
            badge = (
                '<span class="fail-badge">部分失败</span>'
                if has_error
                else '<span class="full-badge">全部成功</span>'
            )

            section = (
                f'<div class="section" id="sec-{step_key}">'
                f'<h2>{tag_label} {len(indices)} 条'
                f'（点击每条展开查看完整 Prompt）{badge}</h2>'
            )

            for idx in indices:
                section += self._build_record_html(self.records[idx], idx)

            section += "</div>\n"
            sections += section

        return sections

    def _build_filter_buttons(
        self, groups: Dict[str, List[int]], sorted_steps: List[str]
    ) -> str:
        """构建类型过滤按钮"""
        btns = '<span class="filter-label">按类型：</span>'
        btns += '<button class="btn active" onclick="showAll(this)">全部</button>'
        for step_key in sorted_steps:
            count = len(groups[step_key])
            tag_label, _ = self._get_step_tag(step_key)
            btns += (
                f'<button class="btn" '
                f'onclick="showSection(\'{step_key}\', this)">'
                f'{tag_label} ({count})</button>'
            )
        return btns

    def _build_execution_summary_html(self, summary: Dict[str, Any]) -> str:
        """构建执行过程摘要 HTML。"""
        totals = summary.get("totals", {})
        notes = summary.get("notes", [])
        top_errors = summary.get("top_errors", [])[:5]
        slow_calls = summary.get("slow_calls", [])[:5]

        notes_html = "".join(
            f"<li>{html.escape(str(note))}</li>" for note in notes
        ) or "<li>暂无提示</li>"
        errors_html = "".join(
            f"<li>{item.get('count', 0)} 次：{html.escape(str(item.get('error', '')))}</li>"
            for item in top_errors
        ) or "<li>无失败错误</li>"
        slow_html = "".join(
            "<li>"
            f"{html.escape(str(item.get('prompt_key', 'unknown')))} "
            f"{int(item.get('latency_ms', 0))}ms "
            f"{html.escape(str(item.get('status', '')))} "
            f"{html.escape(str(item.get('finish_reason', '')))}"
            "</li>"
            for item in slow_calls
        ) or "<li>无超过 60 秒的慢请求</li>"

        return f"""
<div class="section" id="sec-exec-summary">
  <h2>执行过程摘要 <span class="full-badge">自动生成</span></h2>
  <div class="stat">
    <div class="s"><div class="n">{totals.get('api_calls', 0)}</div><div class="l">API 调用</div></div>
    <div class="s"><div class="n">{totals.get('success', 0)}</div><div class="l">成功</div></div>
    <div class="s"><div class="n">{totals.get('failed', 0)}</div><div class="l">失败</div></div>
    <div class="s"><div class="n">{totals.get('timeouts', 0)}</div><div class="l">超时</div></div>
    <div class="s"><div class="n">{totals.get('finish_reason_length', 0)}</div><div class="l">输出截断</div></div>
    <div class="s"><div class="n">{totals.get('reasoning_only_responses', 0)}</div><div class="l">仅推理响应</div></div>
  </div>
  <div class="record">
    <div class="record-body open">
      <div class="field"><div class="field-label">诊断提示</div><div class="field-value"><ul>{notes_html}</ul></div></div>
      <div class="field"><div class="field-label">错误原因 Top</div><div class="field-value"><ul>{errors_html}</ul></div></div>
      <div class="field"><div class="field-label">慢请求 Top</div><div class="field-value"><ul>{slow_html}</ul></div></div>
      <div class="field"><div class="field-label">JSON 摘要文件</div><div class="field-value">output/execution_summary.json</div></div>
    </div>
  </div>
</div>
"""

    def _wrap_html(
        self,
        project_name: str,
        song_title: str,
        total: int,
        provider_count: int,
        total_tokens: int,
        scenes_count: int,
        filter_btns: str,
        sections_html: str,
    ) -> str:
        """包装完整 HTML"""
        title = song_title or project_name
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM Prompt 日志 — {html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<h1>LLM 完整 Prompt 日志 — {html.escape(title)}</h1>
<div class="sub">{project_name} | {total} 条记录 | {scenes_count} 场景 | 点击每条展开查看完整内容</div>
<div class="stat">
  <div class="s"><div class="n">{total}</div><div class="l">总调用</div></div>
  <div class="s"><div class="n">{provider_count}</div><div class="l">Provider</div></div>
  <div class="s"><div class="n">~{total_tokens}</div><div class="l">估算 token</div></div>
</div>
<div class="filter">{filter_btns}</div>
{sections_html}
<script>{JS}</script>
</body>
</html>"""

    def _write_output(self, html_content: str, output_path: Optional[str] = None):
        """写入 HTML 文件"""
        if output_path:
            target = Path(output_path)
        else:
            target = self.project_dir / "output" / "llm_report.html"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html_content, encoding="utf-8")
            print(f"  报告已生成: {target}")
        except (OSError, FileNotFoundError) as e:
            print(f"  报告写入失败: {e}")
