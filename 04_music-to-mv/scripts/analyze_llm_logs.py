#!/usr/bin/env python3
"""
analyze_llm_logs.py — 汇总分析所有项目的 LLM 日志

用法:
  python3 analyze_llm_logs.py                          # 分析所有项目
  python3 analyze_llm_logs.py <project_dir>             # 分析指定项目
  python3 analyze_llm_logs.py --step scene_img         # 只看某步骤
  python3 analyze_llm_logs.py --recent 7                # 只看最近7天项目
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta

LOG_DIR = "metadata/llm_calls"
STEP_LABELS = {
    "lyrics": "歌词生成",
    "music": "音乐生成",
    "scene_desc_single": "单场景描述",
    "scene_desc_batch": "批量场景描述",
    "variant_desc_single": "单变体描述",
    "variant_desc_batch": "批量变体描述",
    "scene_img": "场景图片",
}
STEP_ORDER = ["lyrics", "music", "scene_desc_batch", "scene_desc_single",
              "variant_desc_batch", "variant_desc_single", "scene_img"]


def estimate_tokens(text):
    """粗估 token 数量（中文≈2字符/token，英文≈4字符/token）"""
    if not text:
        return 0
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return chinese * 0.5 + other * 0.25


def analyze_project(proj_path, step_filter=None):
    """分析单个项目的 llm_calls 日志"""
    log_dir = Path(proj_path) / LOG_DIR
    if not log_dir.exists():
        return None

    records = []
    for f in sorted(log_dir.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    records.append(r)
                except Exception:
                    pass

    # 读取归档目录日志
    archive_dir = log_dir / "archive"
    if archive_dir.exists():
        for month_dir in sorted(archive_dir.iterdir()):
            if month_dir.is_dir():
                for f in sorted(month_dir.glob("*.jsonl")):
                    with open(f, encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                records.append(json.loads(line))
                            except Exception:
                                pass

    if not records:
        return None

    # 按 step 聚合
    by_step = defaultdict(lambda: {
        "count": 0, "models": set(), "tokens": 0,
        "errors": 0, "prompts": [], "first_seen": None
    })

    for rec in records:
        step = rec.get("step", "?")
        if step_filter and step != step_filter:
            continue
        s = by_step[step]
        s["count"] += 1
        if rec.get("model"):
            s["models"].add(rec["model"])
        if rec.get("error"):
            s["errors"] += 1
        if rec.get("prompt"):
            toks = estimate_tokens(rec["prompt"])
            s["tokens"] += toks
            s["prompts"].append(rec["prompt"])
        ts = rec.get("timestamp", "")
        if ts and (s["first_seen"] is None or ts < s["first_seen"]):
            s["first_seen"] = ts

    return dict(by_step)

def format_project(proj_path, by_step):
    """格式化输出单个项目"""
    proj_name = Path(proj_path).name
    lines = []
    lines.append(f"\n{'='*50}")
    lines.append(f"📁 {proj_name}")
    lines.append(f"{'='*50}")

    total_calls = sum(v["count"] for v in by_step.values())
    total_tokens = sum(v["tokens"] for v in by_step.values())
    total_errors = sum(v["errors"] for v in by_step.values())

    lines.append(f"{'步骤':<18} {'次数':>4}  {'模型':<25} {'估算token':>8} {'错误':>4}")
    lines.append("-" * 65)

    for step in STEP_ORDER:
        if step not in by_step:
            continue
        v = by_step[step]
        label = STEP_LABELS.get(step, step)
        models_str = ",".join(sorted(v["models"])) if v["models"] else "-"
        if len(models_str) > 25:
            models_str = models_str[:22] + "..."
        tok_str = f"{v['tokens']:.0f}" if v["tokens"] > 0 else "-"
        err_str = str(v["errors"]) if v["errors"] > 0 else "-"
        lines.append(f"{label:<18} {v['count']:>4}  {models_str:<25} {tok_str:>8} {err_str:>4}")

    lines.append("-" * 65)
    lines.append(f"{'合计':<18} {total_calls:>4}  {'':<25} {total_tokens:>8} {total_errors:>4}")
    return "\n".join(lines)


def print_prompt_samples(by_step, max_samples=3):
    """打印每个 step 的 prompt 样例"""
    for step in STEP_ORDER:
        if step not in by_step:
            continue
        prompts = by_step[step].get("prompts", [])
        if not prompts:
            continue
        label = STEP_LABELS.get(step, step)
        print(f"\n  📝 [{label}] prompt 样例:")
        for p in prompts[:max_samples]:
            if isinstance(p, dict):
                text = p.get("prompt") or p.get("text") or str(p)
            else:
                text = str(p)
            preview = text[:120].replace("\n", " ")
            print(f"     {preview}{'...' if len(text) > 120 else ''}")


def find_projects(base_dir, recent_days=None):
    """查找项目目录"""
    base = Path(base_dir)
    if not base.exists():
        return []
    projects = []
    for d in base.iterdir():
        if d.is_dir() and (d / LOG_DIR).exists():
            if recent_days:
                age = datetime.now() - datetime.fromtimestamp(d.stat().st_mtime)
                if age <= timedelta(days=recent_days):
                    projects.append(d)
            else:
                projects.append(d)
    return sorted(projects, key=lambda p: p.name)


def main():
    parser = argparse.ArgumentParser(description="LLM 日志汇总分析")
    parser.add_argument("project", nargs="?", default="", help="项目目录（默认分析所有）")
    parser.add_argument("--step", "-s", default="", help="只看某步骤（如 scene_img）")
    parser.add_argument("--recent", "-r", type=int, default=0, help="只看最近N天项目")
    parser.add_argument("--samples", action="store_true", help="显示 prompt 样例")
    parser.add_argument("--summary", action="store_true", help="简洁汇总模式")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent / "mv"
    if args.project:
        projects = [Path(args.project)]
        if not projects[0].exists():
            print(f"❌ 项目不存在: {projects[0]}")
            sys.exit(1)
    else:
        projects = find_projects(base_dir, recent_days=args.recent if args.recent > 0 else None)
        if not projects:
            print("❌ 未找到任何有 llm_calls 日志的项目")
            sys.exit(1)

    print(f"🔍 分析 {len(projects)} 个项目...")
    if args.step:
        print(f"   过滤步骤: {args.step}")

    all_total_calls = 0
    all_total_tokens = 0

    for proj in projects:
        by_step = analyze_project(proj, step_filter=args.step or None)
        if by_step is None:
            continue

        if args.summary:
            total_calls = sum(v["count"] for v in by_step.values())
            total_tokens = sum(v["tokens"] for v in by_step.values())
            models = set()
            for v in by_step.values():
                models.update(v["models"])
            print(f"{proj.name} | {total_calls}次 | {','.join(sorted(models))[:40]}")
            all_total_calls += total_calls
            all_total_tokens += total_tokens
        else:
            print(format_project(proj, by_step))
            if args.samples:
                print_prompt_samples(by_step)
            all_total_calls += sum(v["count"] for v in by_step.values())
            all_total_tokens += sum(v["tokens"] for v in by_step.values())

    if args.summary and len(projects) > 1:
        print(f"\n{'='*50}")
        print(f"总计: {all_total_calls} 次调用, ~{all_total_tokens:.0f} 估算 token")


if __name__ == "__main__":
    main()