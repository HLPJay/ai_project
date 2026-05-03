#!/usr/bin/env python3
"""
诊断歌词对齐问题的工具

用法:
    python tools/diagnose_alignment.py --project "~/.openclaw/workspace/mv/项目目录"
"""

import json
import sys
import io
from pathlib import Path
from typing import List, Dict, Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_alignment_result(project_dir: str) -> Dict[str, Any]:
    """加载对齐结果"""
    project_path = Path(project_dir).expanduser()

    # 查找对齐结果
    alignment_file = project_path / "metadata" / "alignment.json"
    srt_file = project_path / "output" / "output.srt"

    if not alignment_file.exists():
        print(f"❌ 未找到对齐文件: {alignment_file}")
        return {}

    with open(alignment_file) as f:
        alignment = json.load(f)

    return alignment


def analyze_alignment(alignment: Dict[str, Any]) -> None:
    """分析对齐质量"""

    if not alignment.get("alignment"):
        print("❌ 没有对齐数据")
        return

    alignments = alignment["alignment"]

    # 统计
    total = len(alignments)
    matched = sum(1 for a in alignments if a.get("matched"))
    interpolated = sum(1 for a in alignments if a.get("interpolated"))
    unmatched = total - matched - interpolated

    print("\n" + "="*60)
    print("📊 对齐质量分析")
    print("="*60)

    print(f"\n总行数: {total}")
    print(f"  ✅ 已匹配: {matched} ({100*matched/total:.1f}%)")
    print(f"  📍 已插值: {interpolated} ({100*interpolated/total:.1f}%)")
    print(f"  ❌ 未匹配: {unmatched} ({100*unmatched/total:.1f}%)")

    # 匹配分数分布
    scores = [a.get("score", 0) for a in alignments if a.get("matched")]
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        print(f"\n匹配分数:")
        print(f"  平均: {avg_score:.2f}")
        print(f"  范围: {min_score:.2f} - {max_score:.2f}")

    # 找出问题行
    print(f"\n⚠️  问题诊断:")

    problem_lines = [a for a in alignments if not a.get("matched") and not a.get("interpolated")]
    if problem_lines:
        print(f"\n未匹配的行数: {len(problem_lines)}")
        for i, line in enumerate(problem_lines[:5]):  # 只显示前 5 行
            print(f"  行 {line['idx']}: \"{line['text']}\"")
        if len(problem_lines) > 5:
            print(f"  ... 还有 {len(problem_lines)-5} 行")

    # 时间间隔分析
    time_gaps = []
    for i in range(len(alignments) - 1):
        if alignments[i+1]["start"] > 0:  # 跳过未赋值的
            gap = alignments[i+1]["start"] - alignments[i]["end"]
            time_gaps.append(gap)

    if time_gaps:
        avg_gap = sum(time_gaps) / len(time_gaps)
        large_gaps = [g for g in time_gaps if g > 1.0]  # > 1 秒的间隔
        print(f"\n时间间隔分析:")
        print(f"  平均间隔: {avg_gap:.2f}s")
        if large_gaps:
            print(f"  ⚠️  大间隔 (>1s): {len(large_gaps)} 处")
            print(f"     可能表示匹配跳跃或识别错误")


def suggest_fixes(alignment: Dict[str, Any]) -> None:
    """给出改进建议"""

    print(f"\n" + "="*60)
    print("💡 改进建议")
    print("="*60)

    alignments = alignment.get("alignment", [])
    matched = sum(1 for a in alignments if a.get("matched"))
    total = len(alignments)
    match_rate = matched / total if total > 0 else 0

    # 根据匹配率给出建议
    if match_rate < 0.7:
        print("\n🔴 匹配率低于 70%，建议:")
        print("  1. 降低阈值参数:")
        print("     threshold_1: 0.25 → 0.20")
        print("     threshold_2: 0.20 → 0.15")
        print("  2. 增大搜索窗口:")
        print("     search_window: 8 → 12")
        print("  3. 检查 Whisper 识别质量:")
        print("     ALIGN_WHISPER_MODEL=medium (当前可能太小)")

    elif match_rate < 0.85:
        print("\n🟡 匹配率 70-85%，建议:")
        print("  1. 轻微调整阈值:")
        print("     threshold_1: 0.25 → 0.22")
        print("     threshold_2: 0.20 → 0.18")
        print("  2. 确保启用 Demucs 人声分离:")
        print("     ALIGN_DEMUCS_ENABLED=true")

    else:
        print("\n✅ 匹配率 > 85%，质量良好")
        print("  如果还有零散不对，可能是:")
        print("  1. 音乐生成和歌词节奏不匹配")
        print("  2. 某些多音字识别错误")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="诊断歌词对齐问题")
    parser.add_argument("--project", required=True, help="项目目录路径")
    args = parser.parse_args()

    alignment = load_alignment_result(args.project)

    if alignment:
        analyze_alignment(alignment)
        suggest_fixes(alignment)

    print("\n" + "="*60)
    print("📚 更多信息:")
    print("  - 查看完整对齐结果: metadata/alignment.json")
    print("  - 查看生成的字幕: output/output.srt")
    print("  - 查看 ASR 识别: metadata/asr_result.json")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
