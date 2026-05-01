"""
Reference anchor and batch image smoke tests.

这个脚本用于本地低成本验证“主题主体锚定”是否正确，不跑完整 MV。

三种模式的消耗范围：

- prompt:
  只创建测试项目并打印 Step④ 主参考图 prompt、场景图主体锚定 prompt。
  不调用生图 API，不消耗额度。适合先检查“小狗是否被识别为主体”。

- image:
  每个 case 只生成一张 Step④ 主参考图：images/base_character.png。
  不跑歌词、音乐、场景分析、批量场景图、Ken Burns、视频合成。
  例如 `--case puppy` 只会生成“小狗的夏日冒险”这一张主参考图。
  多个 case 会每个主题各生成一张；`--case all` 当前会生成 8 张。

- batch:
  自动创建一个最小 scenes.json，然后只运行 Step⑤-⑦ 批量场景图。
  `--dry-run` 时只生成占位图，不调用 API；去掉 `--dry-run` 才会真实批量生图。
  适合测试场景图主体是否持续锚定、变体图是否正常生成。

输出目录默认是仓库内 `.reference_tests/`，不会污染正式 workspace。

Examples:
    python tools/test_reference_anchors.py
    python tools/test_reference_anchors.py --mode image --case puppy --provider pollinations
    python tools/test_reference_anchors.py --mode prompt --case love poem galaxy
    python tools/test_reference_anchors.py --mode batch --case puppy --dry-run
    python tools/test_reference_anchors.py --mode batch --case puppy --provider pollinations --limit-scenes 3
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = REPO_ROOT / ".reference_tests"

sys.path.insert(0, str(REPO_ROOT))

from src.project_manager import ProjectManager
from src.scene_generator import SceneImageGenerator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class ReferenceCase:
    key: str
    theme: str
    style: str
    music_style: str
    mood: str
    note: str


CASES: tuple[ReferenceCase, ...] = (
    ReferenceCase(
        key="love",
        theme="爱情",
        style="国风",
        music_style="中国风",
        mood="浪漫",
        note="人物关系主体，检查是否是情侣/关系氛围，而不是空风景",
    ),
    ReferenceCase(
        key="poem",
        theme="春江花月夜",
        style="国风",
        music_style="中国风",
        mood="梦幻",
        note="古诗意境，检查月、江、花、夜、留白等诗性意象",
    ),
    ReferenceCase(
        key="war",
        theme="战争后的黎明",
        style="电影感",
        music_style="史诗",
        mood="史诗",
        note="人物行动/群像，检查是否有战争后的故事压力和人类尺度",
    ),
    ReferenceCase(
        key="puppy",
        theme="小狗的夏日冒险",
        style="动漫风",
        music_style="流行",
        mood="欢快",
        note="非人物主体，检查小狗是否是主体，不能被夏日风景替代",
    ),
    ReferenceCase(
        key="galaxy",
        theme="星系漂流",
        style="赛博朋克",
        music_style="电子",
        mood="梦幻",
        note="宇宙环境，检查星系/星云/行星尺度是否明确",
    ),
    ReferenceCase(
        key="urban-rain",
        theme="城市夜雨",
        style="写实风",
        music_style="R&B",
        mood="孤独",
        note="城市生活，检查湿街、窗光、交通、日常物件",
    ),
    ReferenceCase(
        key="object",
        theme="旧照片里的童年",
        style="复古胶片",
        music_style="民谣",
        mood="怀旧",
        note="物件象征，检查旧照片/相册是否承担情绪",
    ),
    ReferenceCase(
        key="myth",
        theme="山海经异梦",
        style="国风",
        music_style="中国风",
        mood="魔幻",
        note="神话幻想，检查神话生物、山海、古老符号和幻想尺度",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量测试 Step④ 主参考图/锚定图 prompt 或单图生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["prompt", "image", "batch"],
        default="prompt",
        help=(
            "prompt=只打印提示词；image=每个 case 只生成一张主参考图；"
            "batch=创建测试 scenes.json 并运行 Step⑤-⑦ 批量生图"
        ),
    )
    parser.add_argument(
        "--case",
        nargs="+",
        default=["all"],
        help="选择 case key，默认 all。可用: " + ", ".join(c.key for c in CASES),
    )
    parser.add_argument(
        "--provider",
        choices=["minimax", "pollinations", "alibaba", "dall-e"],
        help="临时覆盖 IMAGE_API_PROVIDER，仅对子进程生效",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(DEFAULT_WORKSPACE),
        help="测试项目输出目录，默认写入仓库内 .reference_tests",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出可用 case 后退出",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="batch 模式只生成占位图，不调用生图 API",
    )
    parser.add_argument(
        "--limit-scenes",
        type=int,
        default=4,
        help="batch 模式每个 case 创建多少个测试场景，默认 4",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="batch 模式批量生图并发数，默认 1",
    )
    return parser.parse_args()


def selected_cases(keys: Iterable[str]) -> list[ReferenceCase]:
    requested = list(keys)
    if "all" in requested:
        return list(CASES)

    by_key = {case.key: case for case in CASES}
    unknown = [key for key in requested if key not in by_key]
    if unknown:
        raise SystemExit(
            "未知 case: "
            + ", ".join(unknown)
            + "\n可用: "
            + ", ".join(by_key)
        )
    return [by_key[key] for key in requested]


def run_case(case: ReferenceCase, mode: str, env: dict[str, str]) -> int:
    """运行 prompt/image 测试。

    prompt 模式只打印提示词；image 模式只生成当前 case 的一张 Step④ 主参考图。
    这里特意不进入完整 pipeline，避免一次性消耗歌词、音乐、批量图和视频生成成本。
    """
    print("\n" + "=" * 72)
    print(f"[{case.key}] {case.theme}")
    print(f"说明: {case.note}")
    print("=" * 72)

    cmd = [
        sys.executable,
        "-m",
        "src.main",
        "--theme",
        case.theme,
        "--style",
        case.style,
        "--music-style",
        case.music_style,
        "--mood",
        case.mood,
        "--test-reference",
        mode,
    ]
    print("命令:", " ".join(f'"{x}"' if " " in x else x for x in cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    return completed.returncode


def create_batch_scenes(case: ReferenceCase, limit: int) -> list[dict]:
    """创建一组小型测试 scenes.json，覆盖主图和 chorus 变体图。"""
    samples = {
        "love": [
            ("intro", "月色桥边，两人背影相隔一盏灯", "relationship, moonlit bridge, two silhouettes, emotional distance"),
            ("verse1", "旧伞下的手指轻轻错过", "hands nearly touching under an old umbrella"),
            ("chorus", "风吹起花瓣，二人终于回望", "couple turns back among falling petals"),
            ("outro", "空桥只剩一束温柔灯光", "empty bridge after farewell, warm lantern"),
        ],
        "poem": [
            ("intro", "春江潮水连海平", "moonlit river, spring mist, wide poetic emptiness"),
            ("verse1", "花影落在一叶孤舟旁", "flowers, lone boat, river reflection"),
            ("chorus", "明月升起，山水留白", "bright moon, layered mountains, ink wash negative space"),
            ("outro", "远亭隐入烟波", "distant pavilion dissolving into mist"),
        ],
        "war": [
            ("intro", "黎明照在残破旗帜上", "dawn after battle, torn flag, quiet battlefield"),
            ("verse1", "士兵穿过尘土与烟雾", "soldier silhouettes crossing smoke"),
            ("chorus", "人群走向远处的光", "crowd moving toward sunrise after conflict"),
            ("outro", "废墟中开出第一朵花", "flower blooming among ruins"),
        ],
        "puppy": [
            ("intro", "小狗站在夏日街角，尾巴摇晃", "cute puppy at summer street corner, wagging tail"),
            ("verse1", "小狗追着纸飞机穿过草地", "puppy chasing paper airplane through grass"),
            ("chorus", "小狗跃过水洼，阳光飞溅", "puppy jumping over puddle, splashing sunlight"),
            ("outro", "小狗趴在夕阳下的台阶上", "puppy resting on sunset steps"),
        ],
        "galaxy": [
            ("intro", "星系像河流一样缓慢旋转", "spiral galaxy drifting like a river"),
            ("verse1", "飞船掠过蓝紫色星云", "small spacecraft passing blue purple nebula"),
            ("chorus", "行星在远处点亮边缘光", "planets rim-lit in deep space"),
            ("outro", "星尘汇入安静的黑暗", "stardust fading into quiet darkness"),
        ],
        "urban-rain": [
            ("intro", "夜雨落在城市玻璃窗上", "rainy city window, night reflections"),
            ("verse1", "地铁口人影匆匆散去", "subway entrance, silhouettes in rain"),
            ("chorus", "湿街霓虹映出孤独背影", "wet street neon, lonely figure"),
            ("outro", "清晨只剩路灯和积水", "early morning street lights and puddles"),
        ],
        "object": [
            ("intro", "旧照片压在泛黄相册里", "old photograph in yellowed album"),
            ("verse1", "玩具车停在窗边灰尘中", "toy car near dusty window"),
            ("chorus", "阳光照亮照片里的笑脸", "sunlight touching old childhood photo"),
            ("outro", "相册合上，尘埃缓缓落下", "album closing, dust in warm light"),
        ],
        "myth": [
            ("intro", "群山间浮现古老异兽的影子", "ancient beast silhouette among mountains"),
            ("verse1", "云海托起发光的神话符号", "glowing mythic symbols above cloud sea"),
            ("chorus", "巨龙掠过山海之间", "dragon crossing mountains and ocean"),
            ("outro", "梦境消散，石碑仍在发光", "dream fading, glowing stone tablet"),
        ],
    }
    rows = samples.get(case.key, samples["poem"])[: max(1, limit)]
    scenes = []
    for idx, (label, lyric, desc) in enumerate(rows, start=1):
        is_chorus = label == "chorus"
        scenes.append({
            "id": idx,
            "name": label,
            "display_name": label.title(),
            "label": label,
            "text_preview": lyric,
            "desc": desc,
            "duration": 9.0 if is_chorus else 5.0,
            "is_repeated": is_chorus,
            "visual_focus": "mixed",
            "shot_type": "wide" if idx == 1 else "medium",
            "character_needed": case.key in ("love", "war", "urban-rain"),
            "symbolic_objects": [],
            "motion_hint": "slow drift",
            "variants": [
                desc + ", alternate composition with stronger subject focus"
            ] if is_chorus else [],
        })
    return scenes


def run_batch_case(case: ReferenceCase, args: argparse.Namespace,
                   env: dict[str, str]) -> int:
    """创建最小项目并运行 Step⑤-⑦ 批量生图。

    这是“批量场景图”测试入口。它不依赖歌词/音乐产物，只写入最小
    `metadata/scenes.json` 和 `metadata/visual_bible.json`。
    使用 `--dry-run` 时不会调用生图 API，只能验证任务数量、输出文件名和变体逻辑；
    不使用 `--dry-run` 时会真实调用当前 provider，每个场景/变体都会消耗一次生图。
    """
    print("\n" + "=" * 72)
    print(f"[batch:{case.key}] {case.theme}")
    print(f"说明: {case.note}")
    print("=" * 72)

    old_workspace = os.environ.get("WORKSPACE_ROOT")
    old_provider = os.environ.get("IMAGE_API_PROVIDER")
    os.environ["WORKSPACE_ROOT"] = env["WORKSPACE_ROOT"]
    if args.provider:
        os.environ["IMAGE_API_PROVIDER"] = args.provider
    try:
        pm = ProjectManager.init_new(
            theme=case.theme,
            style=case.style,
            music_style=case.music_style,
            mood=case.mood,
        )
    finally:
        if old_workspace is None:
            os.environ.pop("WORKSPACE_ROOT", None)
        else:
            os.environ["WORKSPACE_ROOT"] = old_workspace
        if args.provider:
            if old_provider is None:
                os.environ.pop("IMAGE_API_PROVIDER", None)
            else:
                os.environ["IMAGE_API_PROVIDER"] = old_provider

    scenes = create_batch_scenes(case, args.limit_scenes)
    scenes_path = pm.project_dir / "metadata" / "scenes.json"
    scenes_path.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
    (pm.project_dir / "metadata" / "visual_bible.json").write_text(
        json.dumps({
            "world_style": f"{case.theme} coherent MV test world",
            "palette": ["warm gold", "soft blue", "clean cream"],
            "lighting": "cinematic soft light with clear subject separation",
            "texture": "clean detailed image with gentle atmosphere",
            "camera_language": "clear main subject, readable foreground, stable composition",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"测试项目目录: {pm.project_dir}")
    print(f"scenes.json: {scenes_path}")
    print(f"dry_run: {args.dry_run}")
    print(f"parallel: {args.parallel}")

    gen = SceneImageGenerator(str(pm.project_dir), dry_run=args.dry_run)
    try:
        result = gen.generate_all(parallel=args.parallel)
    except Exception as exc:
        print(f"批量生图失败: {exc}")
        return 1

    print("\n批量生图结果:")
    print(json.dumps({
        "total": result.get("total"),
        "succeeded": result.get("succeeded"),
        "failed": result.get("failed"),
        "skipped": result.get("skipped"),
        "variant_scenes": result.get("variant_scenes"),
    }, ensure_ascii=False, indent=2))
    print(f"图片目录: {pm.project_dir / 'images'}")
    return 0


def main() -> int:
    args = parse_args()

    if args.list:
        print("可用 reference anchor 测试 case:")
        for case in CASES:
            print(f"  {case.key:12} {case.theme:12} {case.note}")
        return 0

    workspace = Path(args.workspace_root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["WORKSPACE_ROOT"] = str(workspace)
    if args.provider:
        env["IMAGE_API_PROVIDER"] = args.provider

    print(f"测试模式: {args.mode}")
    print(f"输出目录: {workspace}")
    if args.provider:
        print(f"临时 Provider: {args.provider}")
    if args.mode == "image":
        print("注意: image 模式会为每个 case 调用一次生图 API。")
    if args.mode == "batch":
        if args.dry_run:
            print("batch dry-run: 只生成占位图，不调用生图 API。")
        else:
            print("batch image: 会按 scenes.json 批量调用生图 API。")

    failed = []
    for case in selected_cases(args.case):
        if args.mode == "batch":
            rc = run_batch_case(case, args, env)
        else:
            rc = run_case(case, args.mode, env)
        if rc != 0:
            failed.append((case.key, rc))

    if failed:
        print("\n失败 case:")
        for key, rc in failed:
            print(f"  {key}: exit={rc}")
        return 1

    print("\n全部 reference anchor 测试完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
