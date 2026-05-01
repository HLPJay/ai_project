"""
Generate preview.html for a test/project directory.

Example:
    python tools/generate_preview.py --project C:/path/to/project
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.preview_report import PreviewReport  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成测试产物 HTML 预览页")
    parser.add_argument("--project", required=True, help="项目目录")
    parser.add_argument("--output", default="", help="输出 HTML 路径，默认 <project>/preview.html")
    args = parser.parse_args()

    output = PreviewReport(args.project).generate(args.output or None)
    print(f"预览页: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
