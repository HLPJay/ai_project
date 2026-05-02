"""
Smoke test for Step ③.5 scene prompt generation.

这个脚本只测试“歌词/SRT -> 场景分段 -> 图片提示词 desc/variants/visual_bible”，
不会生成音乐、不会生图、不会合成视频，适合测试 MiniMax / 阿里云 Qwen 的分镜能力。

示例：
  python tools/test_scene_prompt_provider.py --provider alibaba_qwen --model qwen-plus-2025-07-28

如果不想改 .env，可以临时传入 Key：
  python tools/test_scene_prompt_provider.py --provider alibaba_qwen --api-key "sk-xxx"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = REPO_ROOT / ".reference_tests" / "scene_prompt_provider"
sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SAMPLE_LINES = [
    "小院门前阳光正好",
    "奶奶在厨房忙碌的身影",
    "面条落入沸水翻滚跳跃",
    "热油淋下滋啦响",
    "辣椒面儿红又香",
    "简单一碗油泼面",
    "是记忆里最暖的力量",
    "一口下去是熟悉的味道",
    "厨房的炉火依然温暖",
    "我又想起她慈祥的模样",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="测试 Step③.5 歌词分段图片提示词生成模型。")
    parser.add_argument("--provider", default="alibaba_qwen", choices=["minimax", "alibaba_qwen"])
    parser.add_argument("--model", default="qwen-plus-2025-07-28")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--theme", default="奶奶做的油泼面")
    parser.add_argument("--style", default="手机纪实摄影")
    parser.add_argument("--music-style", default="民谣")
    parser.add_argument("--mood", default="温柔")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--variant-batch-size", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    return parser.parse_args()


def write_srt(path: Path):
    rows = []
    start = 0
    for idx, text in enumerate(SAMPLE_LINES, start=1):
        end = start + 4
        rows.append(
            f"{idx}\n"
            f"00:00:{start:02d},000 --> 00:00:{end:02d},000\n"
            f"{text}\n"
        )
        start = end
    path.write_text("\n".join(rows), encoding="utf-8")


def main() -> int:
    args = parse_args()

    os.environ["SCENE_PROMPT_PROVIDER"] = args.provider
    os.environ["SCENE_PROMPT_MODEL"] = args.model
    os.environ["SCENE_DESC_BATCH_SIZE"] = str(args.batch_size)
    os.environ["VARIANT_DESC_BATCH_SIZE"] = str(args.variant_batch_size)
    os.environ["SCENE_DESC_API_TIMEOUT_SEC"] = str(args.timeout)
    os.environ["VARIANT_API_TIMEOUT_SEC"] = str(args.timeout)
    os.environ["API_LOG_ENABLED"] = os.environ.get("API_LOG_ENABLED", "true")
    os.environ["API_LOG_PROMPT"] = os.environ.get("API_LOG_PROMPT", "false")
    os.environ["API_LOG_RESPONSE"] = os.environ.get("API_LOG_RESPONSE", "false")

    if args.api_key:
        os.environ["DASHSCOPE_API_KEY"] = args.api_key

    project_dir = Path(args.workspace).expanduser().resolve() / (
        f"{args.provider}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    (project_dir / "audio").mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata").mkdir(parents=True, exist_ok=True)

    info = {
        "theme": args.theme,
        "style": args.style,
        "music_style": args.music_style,
        "mood": args.mood,
        "song_title": args.theme,
        "narrative_mode": "memory",
        "visual_mode": "environment-led",
        "character_policy": "optional protagonist",
        "chorus_energy": "lifted",
    }
    (project_dir / "metadata" / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(project_dir / "audio" / "song.srt")

    from src.scene_analyzer import SceneAnalyzer

    print(f"测试项目: {project_dir}")
    print(f"Provider: {args.provider} | model: {args.model}")
    result = SceneAnalyzer(str(project_dir)).analyze()
    print("\n结果摘要:")
    print(json.dumps({
        "scene_count": result.get("scene_count"),
        "desc_source": result.get("desc_source"),
        "total_duration": result.get("total_duration"),
        "scenes_json": str(project_dir / "metadata" / "scenes.json"),
        "visual_bible": str(project_dir / "metadata" / "visual_bible.json"),
        "llm_calls": str(project_dir / "metadata" / "llm_calls.jsonl"),
    }, ensure_ascii=False, indent=2))

    scenes = result.get("scenes", [])
    print("\n前 3 个场景描述:")
    for scene in scenes[:3]:
        print(f"- scene {scene.get('id')}: {scene.get('desc', '')[:180]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
