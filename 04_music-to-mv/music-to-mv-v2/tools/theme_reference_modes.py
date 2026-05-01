"""
Inspect theme reference mode configuration.

Examples:
    python tools/theme_reference_modes.py --list
    python tools/theme_reference_modes.py --theme "小狗的夏日冒险"
    python tools/theme_reference_modes.py --theme "春江花月夜" --title "古诗 MV"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.scene_generator import (  # noqa: E402
    SceneImageGenerator,
    THEME_REFERENCE_CONFIG,
    _load_theme_reference_config,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看/测试主题主体推断配置")
    parser.add_argument("--list", action="store_true", help="列出配置中的所有 mode")
    parser.add_argument("--theme", default="", help="测试主题")
    parser.add_argument("--title", default="", help="可选歌曲名")
    parser.add_argument("--anchors", default="", help="可选 visual_anchors")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = _load_theme_reference_config()

    if args.list:
        print(f"配置文件: {THEME_REFERENCE_CONFIG}")
        print(f"default_mode: {config.get('default_mode', 'environment_symbolic')}")
        print("\nModes:")
        for item in sorted(config.get("modes", []), key=lambda x: int(x.get("priority", 1000))):
            keywords = item.get("keywords", [])
            print(
                f"- {item.get('mode')} "
                f"(priority={item.get('priority')}): "
                f"{item.get('description', '')}"
            )
            print(f"  keywords: {', '.join(str(k) for k in keywords[:12])}")
        return 0

    if not args.theme:
        print("请指定 --list 或 --theme")
        return 1

    mode = SceneImageGenerator._infer_base_reference_mode(
        args.theme,
        args.title,
        args.anchors,
    )
    hint = SceneImageGenerator._build_theme_visual_hint(
        args.theme,
        args.title,
        mode,
    )
    print(json.dumps({
        "theme": args.theme,
        "title": args.title,
        "anchors": args.anchors,
        "mode": mode,
        "visual_hint": hint,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
