"""
main.py — Music-to-MV v2 命令行入口

用法：
    python -m src.main --theme "春天" --style "国风" [选项...]
    python -m src.main --project <项目目录> --phase align|produce|export
    python -m src.main --project <项目目录> --continue
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 确保 src 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import MVPipeline
from src.config_manager import ConfigManager
from src.project_manager import ProjectManager
from src.interaction import UserInteraction


def main():
    parser = argparse.ArgumentParser(
        description="Music-to-MV v2 — LLM-First AI MV 生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 创建新项目（全流程）
  python -m src.main --theme "童年" --style "水彩插画风" --mood "怀旧"

  # 从指定阶段继续
  python -m src.main --project ~/mv/童年_20260425 --phase align

  # 全自动模式（无暂停点）
  python -m src.main --theme "春天" --auto

  # 列出所有项目
  python -m src.main --list
        """
    )

    # ── 创建新项目参数 ──
    parser.add_argument("--theme", help="MV 主题")
    parser.add_argument("--style", default="动漫风",
                       help="画面风格（默认: 动漫风）")
    parser.add_argument("--music-style", default="流行",
                       help="音乐风格（默认: 流行）")
    parser.add_argument("--mood", default="欢快",
                       help="情绪基调（默认: 欢快）")
    parser.add_argument("--language", default="中文",
                       help="歌词语言（默认: 中文）")
    parser.add_argument("--reference", default="", help="参考描述/角色设定")

    # ── 续跑参数 ──
    parser.add_argument("--project", help="已有项目目录路径")
    parser.add_argument("--phase", choices=["init", "align", "produce", "export"],
                       help="指定执行的阶段")

    # ── 通用参数 ──
    parser.add_argument("--auto", action="store_true",
                       help="全自动模式（跳过所有暂停点）")
    parser.add_argument("--list", action="store_true",
                       help="列出所有已有项目")

    args = parser.parse_args()

    # ── 列出项目 ──────────────────────────────────────────
    if args.list:
        _list_projects()
        return

    # ── 继续已有项目 ──────────────────────────────────────
    if args.project:
        project_dir = os.path.expanduser(args.project)
        if not os.path.isdir(project_dir):
            print(f"❌ 项目目录不存在: {project_dir}")
            sys.exit(1)

        pipeline = MVPipeline(project_dir, auto_mode=args.auto)
        phase = args.phase or "all"
        print(f"📂 继续项目: {pipeline.pm.project_name}")
        print(f"   路径: {project_dir}")
        print(f"   阶段: {phase}")

        # 检查是否处于暂停点
        if UserInteraction.is_paused(pipeline.pm):
            print("⏸️  项目处于暂停状态，等待用户确认。")
            print(UserInteraction.format_prompt_for_agent(pipeline.pm))
            return

        pipeline.run(phases=phase)
        return

    # ── 创建新项目 ───────────────────────────────────────
    if not args.theme:
        parser.print_help()
        print("\n❌ 请指定 --theme 或 --project")
        sys.exit(1)

    # 初始化配置
    cfg = ConfigManager()

    # 检查必要配置
    minimax_token = cfg.get("minimax_token", "")
    if not minimax_token:
        print("⚠️  未设置 MINIMAX_TOKEN")
        print("   请创建 .env 文件并设置环境变量。")
        print("   参考: cp .env.example .env")
        print()
        response = input("是否继续？(y/N): ").strip().lower()
        if response != "y":
            sys.exit(1)

    # 创建流水线
    pipeline = MVPipeline.create_new(
        theme=args.theme,
        style=args.style,
        music_style=args.music_style,
        mood=args.mood,
        language=args.language,
        reference=args.reference,
        auto_mode=args.auto,
    )

    print(f"\n📁 项目目录: {pipeline.project_dir}")

    # 运行
    pipeline.run()


def _list_projects():
    """列出所有已有项目"""
    cfg = ConfigManager()
    root = Path(cfg.get("WORKSPACE_ROOT", "~/.openclaw/workspace/mv")).expanduser()

    if not root.exists():
        print("📂 暂无项目（目录不存在）")
        return

    projects = []
    for d in sorted(root.iterdir(), reverse=True):
        if d.is_dir() and (d / "metadata" / "info.json").exists():
            try:
                info = json.loads((d / "metadata" / "info.json").read_text(encoding="utf-8"))
                name = info.get("project_name", d.name)
                theme = info.get("theme", "")
                song = info.get("song_title", "未生成")
                completed = info.get("steps_completed", [])
                status = "✅ 完成" if "all" in completed else f"⏳ {len(completed)}/11步"
                projects.append((d, name, theme, song, status))
            except Exception:
                projects.append((d, d.name, "", "", "⚠️ 损坏"))

    if not projects:
        print("📂 暂无项目")
        return

    print(f"\n📂 已有项目 ({len(projects)} 个):")
    print(f"{'='*60}")
    for d, name, theme, song, status in projects:
        print(f"  {d.name}")
        print(f"    主题: {theme}  ·  歌曲: {song}  ·  {status}")
        print(f"    路径: {d}")
        print()


if __name__ == "__main__":
    main()
