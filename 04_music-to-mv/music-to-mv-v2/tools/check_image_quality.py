"""
Check generated image quality for an existing project.

Examples:
    python tools/check_image_quality.py --project C:/path/to/project
    python tools/check_image_quality.py --project C:/path/to/project --pattern "seg*.png"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config_manager import ConfigManager  # noqa: E402
from src.image_quality import ImageQualityChecker, ImageQualityThresholds  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="复查项目图片质量")
    parser.add_argument("--project", required=True, help="项目目录")
    parser.add_argument("--pattern", default="*.png", help="图片匹配模式，默认 *.png")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.project).expanduser()
    images_dir = project / "images"
    if not images_dir.exists():
        print(f"图片目录不存在: {images_dir}")
        return 1

    paths = sorted(images_dir.glob(args.pattern))
    if not paths:
        print(f"未找到图片: {images_dir / args.pattern}")
        return 1

    cfg = ConfigManager()
    thresholds = ImageQualityThresholds(
        min_file_size=cfg.get_int("image_quality_min_file_size", 1000),
        min_width=cfg.get_int("image_quality_min_width", 512),
        min_height=cfg.get_int("image_quality_min_height", 512),
        min_stddev=cfg.get_float("image_quality_min_stddev", 6.0),
    )
    report = ImageQualityChecker(str(project), thresholds).validate_paths(paths)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"报告: {project / 'metadata' / 'image_quality_report.json'}")

    failed = [item for item in report["items"] if not item["passed"]]
    if failed:
        print("\n失败图片:")
        for item in failed:
            print(f"- {item['relative_path']}: {', '.join(item['errors'])}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
