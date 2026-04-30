"""
llm_logger.py — 统一 LLM 调用日志系统

单例模式，线程安全。
记录每次 LLM/API 调用的完整信息，自动聚合统计。
输出到 metadata/llm_calls/ 目录。

用法：
    logger = LLMLogger(project_dir)
    logger.record_call(record)
    stats = logger.get_stats()
    logger.print_summary()
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict, field


@dataclass
class LLMCallRecord:
    """一次 LLM 调用的完整记录"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prompt_key: str = ""           # e.g., "lyrics_generation"
    prompt_version: str = ""       # e.g., "v2.0"
    rendered_prompt: str = ""      # 填充变量后的完整提示词
    model: str = ""                # e.g., "MiniMax-M2.7"
    request_params: Dict = field(default_factory=dict)
    response: str = ""             # 响应内容
    raw_response: str = ""         # 原始响应（用于调试）
    tokens: Dict = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    })
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    status: str = "success"        # success / failed
    error: Optional[str] = None
    evaluation: Optional[Dict] = None
    extra: Dict = field(default_factory=dict)


class LLMLogger:
    """LLM 调用日志系统（非单例模式，线程安全）"""

    def __init__(self, project_dir: str = None):
        # project_dir 为空时使用用户目录下的默认日志位置
        if project_dir:
            self.project_dir = str(Path(project_dir).expanduser())
        else:
            self.project_dir = str(Path.home() / ".music_to_mv_logs")
        self.log_dir = Path(self.project_dir) / "metadata" / "llm_calls"
        self.responses_dir = self.log_dir / "responses"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)

        self.calls_file = self.log_dir / "calls.jsonl"
        self.errors_file = self.log_dir / "errors.jsonl"
        self.evals_file = self.log_dir / "evaluations.jsonl"
        self.stats_file = self.log_dir / "stats.json"
        self.versions_file = self.log_dir / "versions.json"

        self._file_lock = threading.Lock()

        # 初始化日志文件
        for f in [self.calls_file, self.errors_file, self.evals_file]:
            if not f.exists():
                f.touch()

    # ── 核心记录方法 ─────────────────────────────────────

    def record_call(self, record: LLMCallRecord):
        """记录一次 LLM 调用（线程安全）"""
        with self._file_lock:
            # 1. 保存完整响应到单独文件
            response_file = self._save_full_response(record)

            # 2. 记录调用摘要到 calls.jsonl
            call_summary = {
                "timestamp": record.timestamp.isoformat(),
                "prompt_key": record.prompt_key,
                "prompt_version": record.prompt_version,
                "model": record.model,
                "request_params": record.request_params,
                "tokens": record.tokens,
                "latency_ms": record.latency_ms,
                "cost_usd": record.cost_usd,
                "status": record.status,
                "response_file": response_file,
                "evaluation": record.evaluation,
                "extra": record.extra,
            }
            self._append_jsonl(str(self.calls_file), call_summary)

            # 3. 如果失败，记录错误
            if record.status == "failed":
                self._append_jsonl(str(self.errors_file), {
                    "timestamp": record.timestamp.isoformat(),
                    "prompt_key": record.prompt_key,
                    "prompt_version": record.prompt_version,
                    "error": record.error,
                    "model": record.model,
                })

            # 4. 记录评估
            if record.evaluation:
                self._append_jsonl(str(self.evals_file), {
                    "timestamp": record.timestamp.isoformat(),
                    "prompt_key": record.prompt_key,
                    "prompt_version": record.prompt_version,
                    "evaluation": record.evaluation,
                })

            # 5. 更新统计
            self._update_stats(record)

            # 6. 更新版本使用
            self._update_versions(record)

    # ── 简便方法 ─────────────────────────────────────────

    def log_api_call(self, prompt_key: str, model: str, prompt: str,
                     response: Any = None, error: str = None,
                     extra: Dict = None) -> LLMCallRecord:
        """简便记录 API 调用"""
        record = LLMCallRecord(
            timestamp=datetime.now(timezone.utc),
            prompt_key=prompt_key,
            model=model,
            rendered_prompt=prompt,
            response=json.dumps(response, ensure_ascii=False) if response else "",
            raw_response=json.dumps(response, ensure_ascii=False) if response else "",
            status="failed" if error else "success",
            error=error,
            extra=extra or {},
            tokens={"prompt_tokens": len(prompt), "completion_tokens": 0, "total_tokens": len(prompt)},
        )
        self.record_call(record)
        return record

    def log_image_call(self, prompt_key: str, model: str, prompt: str,
                       output_path: str, file_size: int = 0, error: str = None):
        """记录图片生成调用"""
        extra = {"output_path": output_path, "file_size_bytes": file_size}
        return self.log_api_call(prompt_key, model, prompt,
                                 response={"output": output_path, "size": file_size},
                                 error=error, extra=extra)

    # ── 查询方法 ─────────────────────────────────────────

    def get_stats(self) -> Dict:
        """获取聚合统计"""
        stats = self._load_json(str(self.stats_file))
        if not stats:
            stats = {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "by_prompt_key": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        return stats

    def get_calls(self, prompt_key: str = None, limit: int = 50) -> List[Dict]:
        """获取调用记录"""
        calls = []
        if self.calls_file.exists():
            with open(self.calls_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        call = json.loads(line)
                        if prompt_key is None or call.get("prompt_key") == prompt_key:
                            calls.append(call)
                    except json.JSONDecodeError:
                        continue
        return calls[-limit:]

    def generate_summary(self) -> str:
        """生成文本摘要"""
        stats = self.get_stats()

        lines = []
        lines.append("=" * 55)
        lines.append("  LLM 调用统计摘要")
        lines.append("=" * 55)
        lines.append(f"  总调用次数: {stats.get('total_calls', 0)}")
        lines.append(f"  总 Token:    {stats.get('total_tokens', 0):,}")
        lines.append(f"  总成本:      ${stats.get('total_cost_usd', 0):.4f}")
        lines.append("")

        by_key = stats.get("by_prompt_key", {})
        if by_key:
            lines.append("  ── 按类型统计 ──")
            for key, data in sorted(by_key.items()):
                lines.append(f"  {key}:")
                lines.append(f"    {data.get('call_count', 0)} 次调用")
                lines.append(f"    {data.get('total_tokens', 0)} tokens")
                lines.append(f"    ${data.get('total_cost_usd', 0):.4f}")
                if data.get('avg_latency_ms'):
                    lines.append(f"    {data['avg_latency_ms']:.0f}ms 平均延迟")
                lines.append("")

        return "\n".join(lines)

    def print_summary(self):
        """打印摘要"""
        print(self.generate_summary())

    # ── 内部方法 ─────────────────────────────────────────

    def _save_full_response(self, record: LLMCallRecord) -> str:
        """保存完整响应到单独文件，失败时静默返回空路径"""
        ts = record.timestamp.isoformat().replace(":", "-").replace(".", "-")
        filename = f"{ts}__{record.prompt_key}.json"
        filepath = self.responses_dir / filename

        full = {
            "timestamp": record.timestamp.isoformat(),
            "prompt_key": record.prompt_key,
            "prompt_version": record.prompt_version,
            "model": record.model,
            "rendered_prompt": record.rendered_prompt,
            "request_params": record.request_params,
            "response": record.response,
            "raw_response": record.raw_response,
            "tokens": record.tokens,
            "latency_ms": record.latency_ms,
            "cost_usd": record.cost_usd,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(full, f, ensure_ascii=False, indent=2)
            return str(filepath.relative_to(self.log_dir))
        except OSError:
            return ""

    def _update_stats(self, record: LLMCallRecord):
        """更新聚合统计"""
        stats = self._load_json(str(self.stats_file)) or {
            "total_calls": 0, "total_tokens": 0, "total_cost_usd": 0.0,
            "by_prompt_key": {}
        }

        stats["total_calls"] += 1
        stats["total_tokens"] += record.tokens.get("total_tokens", 0)
        stats["total_cost_usd"] += record.cost_usd
        stats["updated_at"] = datetime.now(timezone.utc).isoformat()

        key = record.prompt_key
        if key not in stats["by_prompt_key"]:
            stats["by_prompt_key"][key] = {
                "call_count": 0, "total_tokens": 0, "total_cost_usd": 0.0,
                "avg_latency_ms": 0.0, "success_count": 0, "error_count": 0,
                "versions_used": []
            }

        ks = stats["by_prompt_key"][key]
        ks["call_count"] += 1
        ks["total_tokens"] += record.tokens.get("total_tokens", 0)
        ks["total_cost_usd"] += record.cost_usd

        n = ks["call_count"]
        ks["avg_latency_ms"] = (ks["avg_latency_ms"] * (n - 1) + record.latency_ms) / n

        if record.status == "success":
            ks["success_count"] += 1
        else:
            ks["error_count"] += 1

        if record.prompt_version and record.prompt_version not in ks["versions_used"]:
            ks["versions_used"].append(record.prompt_version)

        self._save_json(str(self.stats_file), stats)

    def _update_versions(self, record: LLMCallRecord):
        """更新版本使用记录"""
        versions = self._load_json(str(self.versions_file)) or {}

        key = f"{record.prompt_key}:{record.prompt_version}"
        if key not in versions:
            versions[key] = {
                "prompt_key": record.prompt_key,
                "version": record.prompt_version,
                "model": record.model,
                "usage_count": 0,
                "first_used_at": record.timestamp.isoformat(),
                "last_used_at": record.timestamp.isoformat(),
            }

        versions[key]["usage_count"] += 1
        versions[key]["last_used_at"] = record.timestamp.isoformat()

        self._save_json(str(self.versions_file), versions)

    def _append_jsonl(self, filepath: str, record: Dict):
        """追加 JSONL 行，写入失败时静默忽略"""
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_json(self, filepath: str) -> Optional[Dict]:
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _save_json(self, filepath: str, data: Dict):
        """写入 JSON 文件，写入失败时静默忽略"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
