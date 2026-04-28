#!/usr/bin/env python3
"""归档 llm_calls/ 目录下的日志文件（按日期分类）

用法:
    python3 archive_llm_logs.py [project_dir]
    python3 archive_llm_logs.py --all root_dir   # 扫描所有子目录

输出: 归档后打印 "Archived N files"
"""
import os, sys, time
from pathlib import Path

ARCHIVE_LOG_NAME = "archive.log"  # 用于 produce_mv.sh 捕获输出

def archive_one(log_dir: Path) -> int:
    """归档单个项目的 llm_calls 目录，返回归档文件数。"""
    if not log_dir.exists():
        return 0
    archive_dir = log_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = 0
    for f in sorted(log_dir.iterdir()):
        if f.is_file() and f.suffix == ".jsonl":
            mtime = f.stat().st_mtime
            date_str = time.strftime("%Y-%m-%d", time.localtime(mtime))
            month_dir = archive_dir / date_str[:7]  # YYYY-MM
            month_dir.mkdir(parents=True, exist_ok=True)
            dest = month_dir / f.name
            if dest.exists():
                dest = month_dir / f"{f.stem}_{int(mtime * 1000)}{f.suffix}"
            f.rename(dest)
            archived += 1
    return archived


def main():
    if len(sys.argv) == 1:
        # 无参数：默认行为，找同目录下的 metadata/llm_calls
        script_dir = Path(__file__).parent.resolve()
        log_dir = script_dir / "metadata" / "llm_calls"
        count = archive_one(log_dir)
        print(f"Archived {count} files", file=sys.stderr)
        # 输出数字供 shell 捕获
        print(count)

    elif len(sys.argv) == 2 and sys.argv[1] == "--all":
        print("Usage: archive_llm_logs.py --all <root_dir>")
        sys.exit(1)

    elif len(sys.argv) == 3 and sys.argv[1] == "--all":
        root = Path(sys.argv[2]).resolve()
        total = 0
        for project_dir in sorted(root.glob("mv/*/")):
            llm_dir = project_dir / "metadata" / "llm_calls"
            if llm_dir.exists() and any(llm_dir.glob("*.jsonl")):
                n = archive_one(llm_dir)
                if n:
                    print(f"  {project_dir.name}: {n} files")
                    total += n
        print(f"Total: {total} files archived")

    elif len(sys.argv) == 2:
        # 单个项目目录
        project_dir = Path(sys.argv[1]).resolve()
        log_dir = project_dir / "metadata" / "llm_calls"
        count = archive_one(log_dir)
        print(f"Archived {count} files", file=sys.stderr)
        print(count)

    else:
        print(f"Usage: {sys.argv[0]} [project_dir]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
