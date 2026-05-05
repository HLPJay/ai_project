"""
main.py — Music-to-MV v2 命令行入口

用法：
    python -m src.main --theme "春天" --style "国风" [选项...]
    python -m src.main --project <项目目录> --phase align|produce|export
    python -m src.main --project <项目目录> --continue
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# 确保 src 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.log_setup import setup_logging

from src.pipeline import MVPipeline, detect_mood_tempo
from src.config_manager import ConfigManager
from src.project_manager import ProjectManager
from src.interaction import UserInteraction
from src.scene_generator import SceneImageGenerator
from src.style_map import STYLES, MUSIC_PROMPT_DETAILS, MOOD_DESCRIPTIONS, THEME_VISUALS


PHASE_ALIASES = {
    "all": "all",
    "0": "all",
    "全部": "all",
    "完整": "all",
    "1": "init",
    "init": "init",
    "初始化": "init",
    "创作": "init",
    "2": "align",
    "align": "align",
    "对齐": "align",
    "字幕": "align",
    "3": "produce",
    "produce": "produce",
    "生图": "produce",
    "视频片段": "produce",
    "4": "export",
    "export": "export",
    "导出": "export",
    "合成": "export",
}


def _phase_help_text() -> str:
    return """阶段参数 --phase:
  all / 0      完整流程：Step 0-⑪
  init / 1     Step 0-②：创意简报、歌词、音乐
  align / 2    Step ③：歌词对齐、生成 audio/song.srt
  produce / 3  Step ③.5-⑧：场景分析、主参考图、锚定图、批量场景图、Ken Burns
  export / 4   Step ⑨-⑪：拼接、合并音频字幕、导出版本、生成报告
"""


def _normalize_phase(raw_phase: str = "") -> str:
    """Normalize user-facing phase aliases to pipeline phase names."""
    if not raw_phase:
        return ""
    key = str(raw_phase).strip().lower()
    return PHASE_ALIASES.get(key, "")


def _cli_guide_text(short: bool = False) -> str:
    """CLI 使用指南。short=True 用作 argparse --help 的 epilog。"""
    text = """
常用入口:
  # 查看基础帮助
  python -m src.main --help

  # 查看完整指南（参数、阶段、测试入口、配置文件、产物位置）
  python -m src.main --guide

  # 查看 --style / --music-style / --mood / --theme 的可参考项
  python -m src.main --options

  # 创建新项目并跑完整 MV 流程
  python -m src.main --theme "春雨" --style "国风" --music-style "中国风" --mood "梦幻" --auto

  # 继续已有项目的某个阶段
  python -m src.main --project "C:/Users/you/.openclaw/workspace/mv/春雨_xxxxxx" --phase produce --auto

  # 列出已有项目
  python -m src.main --list

轻量测试入口:
  # 只打印 Step④ 主参考图 prompt，不调用生图 API
  python -m src.main --theme "小狗的冒险" --style "动漫风" --test-reference prompt

  # 只生成 Step④ 主参考图，只消耗一张生图
  python -m src.main --theme "小狗的冒险" --style "动漫风" --test-reference image

  # 汇总测试多个主题的主参考图/批量图
  python tools/test_reference_anchors.py --list
  python tools/test_reference_anchors.py --case puppy
  python tools/test_reference_anchors.py --mode image --case puppy --provider pollinations
  python tools/test_reference_anchors.py --mode batch --case puppy --dry-run
  python tools/test_reference_anchors.py --mode batch --case puppy --provider pollinations --limit-scenes 3

  # 查看主题主体推断结果
  python tools/theme_reference_modes.py --theme "春江花月夜"

  # 对已有项目生成 HTML 预览页 / 复查图片质量
  python tools/generate_preview.py --project <项目目录>
  python tools/check_image_quality.py --project <项目目录>
"""
    if short:
        return text + """
更多说明:
  python -m src.main --guide
  README.md
  ENVIRONMENT_SETUP.md
"""

    return text + """
主要参数:
  --theme              MV 主题，例如 "爱情"、"小狗的夏日冒险"、"春江花月夜"；可重复传入，会合并
  --style              画面风格，默认 "动漫风"
  --music-style        音乐风格，默认 "流行"
  --mood               情绪基调，默认 "欢快"
  --language           歌词语言，默认 "中文"
  --reference          参考描述/角色设定/补充要求
  --auto               全自动模式，跳过暂停点
  --project            已有项目目录，用于续跑
  --phase              运行阶段，可选 all/0, init/1, align/2, produce/3, export/4
  --test-reference     只测试 Step④ 主参考图，可选 prompt / image
  --list               列出已有项目
  --guide              打印本完整指南

可参考项:
""" + _cli_options_text() + """

""" + _phase_help_text() + """

配置文件:
  .env                         本地私密配置，token、provider、并发、超时等
  .env.example                 配置模板和参数注释
  ENVIRONMENT_SETUP.md         环境安装、依赖、参数解释
  config/theme_reference_modes.json
                               主题主体推断配置，新增主题类别优先改这里
  prompts/                     LLM prompt 模板目录
  prompts/registry.yaml        prompt 版本注册表

关键配置:
  IMAGE_API_PROVIDER           minimax / pollinations / alibaba / dall-e / comfyui
  IMAGE_MODEL_POLLINATIONS     仅 provider=pollinations 时生效
  IMAGE_PARALLEL               批量生图并发
  API_LOG_ENABLED              是否打印 API 请求摘要
  API_LOG_PROMPT               是否打印 prompt 预览
  API_LOG_RESPONSE             是否打印 response 预览
  LYRICS_STRUCTURE_MODE        歌曲结构模式，默认 adaptive
  LYRICS_STRUCTURE             自定义歌曲结构，填写后优先级最高
  ALIGN_ASR_ENABLED            是否启用 Whisper/Demucs 精准对齐；false=快速均匀 SRT
  ALIGN_WHISPER_MODEL          Whisper 对齐模型，默认 medium
  ALIGN_WHISPER_DEVICE         Whisper 设备，默认 auto（有 CUDA 用显卡，否则 CPU）
  ALIGN_DEMUCS_DEVICE          Demucs 人声分离设备，默认 auto
  IMAGE_QUALITY_ENABLED        是否启用图片自动质检

产物位置:
  默认项目根目录:
    C:/Users/<你>/.openclaw/workspace/mv/<主题>_<时间>/

  关键产物:
    metadata/info.json                    项目信息、歌曲结构、创意简报
    metadata/scenes.json                  场景分析结果
    metadata/visual_bible.json            全局视觉总纲
    metadata/image_quality_report.json    图片自动质检报告
    images/base_character.png             Step④ 主参考图（历史文件名）
    images/segN_scene.png                 场景主图
    images/segN_variantM.png              场景变体图
    clips/                                Ken Burns 片段
    output/final.mp4                      最终横屏 MV
    output/tiktok.mp4                     TikTok 版本
    output/vertical.mp4                   竖屏版本
    output/llm_report.html                LLM 调用报告
    preview.html                          测试/项目 HTML 预览页

推荐测试顺序:
  1. python tools/theme_reference_modes.py --theme "你的主题"
  2. python -m src.main --theme "你的主题" --test-reference prompt
  3. python -m src.main --theme "你的主题" --test-reference image
  4. python tools/test_reference_anchors.py --mode batch --case puppy --dry-run
  5. 确认无误后再跑完整 `python -m src.main --theme ... --auto`
"""


def _format_names(names, per_line: int = 6) -> str:
    rows = []
    items = [str(name) for name in names]
    for idx in range(0, len(items), per_line):
        rows.append("  " + " / ".join(items[idx:idx + per_line]))
    return "\n".join(rows)


def _cli_options_text() -> str:
    """列出入口参数的可参考/可选择项。"""
    style_names = list(STYLES.keys())
    music_names = list(MUSIC_PROMPT_DETAILS.keys())
    mood_names = list(MOOD_DESCRIPTIONS.keys())
    theme_names = list(THEME_VISUALS.keys())

    language_examples = ["中文", "英文", "日文", "韩文", "粤语", "中英混合"]
    custom_note = (
        "  说明: --theme 不限制只能用以下词；可以自由输入短语，"
        "例如“小狗的夏日冒险”“战争后的黎明”“春江花月夜”。"
    )

    return f"""
--style 画面风格（建议从下列项中选）:
{_format_names(style_names)}

--music-style 音乐风格（建议从下列项中选）:
{_format_names(music_names)}

--mood 情绪基调（建议从下列项中选）:
{_format_names(mood_names)}

--language 歌词语言（示例）:
{_format_names(language_examples)}

--theme 主题参考词（可自由输入，以下仅为内置视觉关键词参考）:
{_format_names(theme_names, per_line=5)}
{custom_note}
"""


def _estimate_generation_time(mood: str, music_style: str) -> dict:
    """根据情绪和风格估计歌词生成时间。

    返回: {"target_lines": "X-Y", "duration": "A-B秒", "estimate_time": "X-Y分钟"}
    """
    is_fast, is_slow = detect_mood_tempo(mood, music_style)

    if is_fast:
        return {
            "target_lines": "30-40行",
            "duration": "120-150秒",
            "lyrics_time": "2-3分钟",
            "music_time": "3-4分钟",
            "total_time": "5-7分钟",
        }
    elif is_slow:
        return {
            "target_lines": "50-70行",
            "duration": "180-240秒",
            "lyrics_time": "3-5分钟",
            "music_time": "4-6分钟",
            "total_time": "7-11分钟",
        }
    else:
        return {
            "target_lines": "40-55行",
            "duration": "150-200秒",
            "lyrics_time": "2-4分钟",
            "music_time": "3-5分钟",
            "total_time": "5-9分钟",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Music-to-MV v2 — LLM-First AI MV 生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_cli_guide_text(short=True),
    )

    # ── 创建新项目参数 ──
    parser.add_argument("--theme", action="append",
                       help="MV 主题；可重复传入，多个主题会合并，例如 --theme 妈妈 --theme 奶奶")
    parser.add_argument("--style", default="动漫风",
                       help="画面风格（默认: 动漫风）")
    parser.add_argument("--music-style", default="流行",
                       help="音乐风格（默认: 流行）")
    parser.add_argument("--mood", default="欢快",
                       help="情绪基调（默认: 欢快）")
    parser.add_argument("--language", default="中文",
                       help="歌词语言（默认: 中文）")
    parser.add_argument("--reference", default="", help="参考描述/角色设定")
    parser.add_argument("--test-reference", choices=["prompt", "image"],
                       help="只测试 Step④ 主参考图：prompt=只打印提示词；image=只生成一张参考图")

    # ── 续跑参数 ──
    parser.add_argument("--project", help="已有项目目录路径")
    parser.add_argument("--phase",
                       help="指定执行阶段：all/0, init/1, align/2, produce/3, export/4")

    # ── 通用参数 ──
    parser.add_argument("--auto", action="store_true",
                       help="全自动模式（跳过所有暂停点）")
    parser.add_argument("--list", action="store_true",
                       help="列出所有已有项目")
    parser.add_argument("--guide", action="store_true",
                       help="打印完整入口指南：参数、阶段、测试脚本、配置文件和产物位置")
    parser.add_argument("--options", action="store_true",
                       help="列出 --theme/--style/--music-style/--mood/--language 的可参考项")

    # ── 日志参数 ──
    parser.add_argument("--log-level",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="终端日志级别（也可用 MV_LOG_LEVEL 环境变量或 .env 配置；默认 INFO）")
    parser.add_argument("--log-file",
                       help="日志同时写入此文件（也可用 MV_LOG_FILE 环境变量或 .env 配置）")
    parser.add_argument("--log-file-level",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="文件日志级别（也可用 MV_LOG_FILE_LEVEL 配置；默认 DEBUG）")

    args = parser.parse_args()

    # 构建运行标识：用于日志文件自动命名（项目名_时间戳）
    _ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.theme:
        _raw = args.theme[0] if isinstance(args.theme, list) else args.theme
    elif args.project:
        _raw = Path(os.path.expanduser(args.project)).name
    else:
        _raw = "mv"
    _safe = re.sub(r'[\\/:*?"<>|\s]+', "_", _raw)[:50].strip("_") or "mv"
    _run_name = f"{_safe}_{_ts}"

    setup_logging(cli_level=args.log_level, cli_file=args.log_file,
                  cli_file_level=args.log_file_level, run_name=_run_name)
    if isinstance(args.theme, list):
        args.theme = "、".join(t.strip() for t in args.theme if t and t.strip())
    if args.phase:
        normalized_phase = _normalize_phase(args.phase)
        if not normalized_phase:
            print(f"❌ 未知 --phase: {args.phase}\n")
            print(_phase_help_text())
            sys.exit(1)
        args.phase = normalized_phase

    # ── 完整帮助指南 ─────────────────────────────────────
    if args.guide:
        print(_cli_guide_text(short=False))
        return

    # ── 参数可选项 ───────────────────────────────────────
    if args.options:
        print(_cli_options_text())
        return

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
        pm = pipeline.pm
        print(f"📂 继续项目: {pm.project_name}")
        print(f"   主题: {pm.theme or '-'}")
        print(f"   风格: {pm.style}  音乐: {pm.music_style}")
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
        if args.phase:
            print("\n你指定了 --phase，但还需要指定一个新主题或已有项目。")
            print("示例：")
            print('  python -m src.main --theme "春雨" --phase 1')
            print('  python -m src.main --project "<项目目录>" --phase 2')
        sys.exit(1)

    # 初始化配置
    cfg = ConfigManager()

    # ── 只测试 Step④ 主参考图 ─────────────────────────────
    if args.test_reference:
        _test_reference(args, cfg)
        return

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

    # 显示歌词生成时间估计
    time_estimate = _estimate_generation_time(args.mood, args.music_style)
    print(f"\n⏱️  预计生成时间（仅 Step ①-② 歌词和音乐）:")
    print(f"   • 歌词行数: {time_estimate['target_lines']}")
    print(f"   • 歌曲时长: {time_estimate['duration']}")
    print(f"   • 歌词生成: {time_estimate['lyrics_time']}")
    print(f"   • 音乐生成: {time_estimate['music_time']}")
    print(f"   • 小计: {time_estimate['total_time']}")
    print(f"\n   📝 注：实际时间受网络、API 负载、token 可用额度等影响。")
    print(f"   🎬 完整 MV 流程（Step ③-⑪）另需 5-15 分钟（图片生成 + 视频处理）。\n")

    # 运行
    pipeline.run(phases=args.phase or "all")


def _test_reference(args, cfg: ConfigManager):
    """只测试 Step④ 主参考图，不跑完整流水线。"""
    pm = ProjectManager.init_new(
        theme=args.theme,
        style=args.style,
        music_style=args.music_style,
        mood=args.mood,
        language=args.language,
        reference=args.reference,
    )
    gen = SceneImageGenerator(str(pm.project_dir), dry_run=(args.test_reference == "prompt"))

    mode = gen._infer_base_reference_mode(args.theme, args.theme)
    ref_prompt = gen._build_base_reference_prompt(args.theme, args.theme)
    sample_scene_prompt = gen._build_scene_prompt(
        f"{args.theme}, representative MV shot, clear main subject, cinematic composition",
        provider=cfg.get("image_api_provider", "minimax"),
    )

    print(f"\n📁 测试项目目录: {pm.project_dir}")
    print(f"主题主体类型: {mode}")
    print("\n[Step④ 主参考图 Prompt]")
    print(ref_prompt)
    print("\n[场景图主体锚定 Prompt 预览]")
    print(sample_scene_prompt[:900])

    if args.test_reference == "prompt":
        print("\n仅打印 prompt，未调用生图 API。")
        return

    provider = cfg.get("image_api_provider", "minimax")
    token = cfg.get_image_token()
    if provider not in ("pollinations", "comfyui") and not token:
        print(f"\n❌ 当前 IMAGE_API_PROVIDER={provider} 需要对应 token，无法生成图片。")
        print("   如果只想免费/本地测试，可设置 IMAGE_API_PROVIDER=pollinations 或 comfyui。")
        sys.exit(1)

    ok = gen.generate_base_character(theme=args.theme, song_title=args.theme)
    output = pm.project_dir / "images" / "base_character.png"
    if ok and output.exists():
        print(f"\n主参考图已生成: {output}")
    else:
        print("\n主参考图生成失败，请查看上方错误日志。")
        sys.exit(1)


def _list_projects():
    """列出所有已有项目"""
    cfg = ConfigManager()
    root = Path(cfg.get("workspace_root", "~/.openclaw/workspace/mv")).expanduser()

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
                total_steps = len(info.get("pipeline", {})) or 10
                status = "✅ 完成" if len(completed) >= total_steps else f"⏳ {len(completed)}/{total_steps}步"
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
