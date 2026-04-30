"""
pipeline.py — MV 流水线主编排器

协调各步骤的执行顺序，处理暂停点、错误恢复、日志记录。
优先调用原版 scripts/ 目录下的 Shell/Python 脚本。

步骤映射：
  Step ①:  生成歌词       → generate_lyrics()         [Python v2]
  Step ②:  生成音乐       → generate_music()          [Python v2]
  Step ③:  歌词对齐       → align_lyrics()            [Shell: align_lyrics.sh]
  Step ③.5: 场景分析      → analyze_scenes()          [Python v2: src/scene_analyzer.py]
  Step ④:  基础角色图     → base_character()          [Python v2: src/scene_generator.py]
  Step ⑤-⑦: 批量场景图   → scene_images()            [Python v2: src/scene_generator.py]
  Step ⑧:  Ken Burns     → ken_burns()               [Python v2: src/
  Step ⑨:  视频拼接       → concat_video()            [Python v2: src/exporter.py]
  Step ⑩:  合并音视频+字幕→ merge_audio_video()       [Python v2: src/exporter.py]
  Step ⑪:  导出(TikTok)  → export_versions()          [Python v2: src/exporter.py]
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Any, Callable

from src.project_manager import ProjectManager
from src.config_manager import ConfigManager
from src.llm.logger import LLMLogger
from src.llm.client import LLMClient, RetryConfig
from src.llm.registry import PromptRegistry
from src.interaction import UserInteraction
from src.ken_burns import KenBurnsGenerator
from src.exporter import MVExporter
from src.scripts_bridge import (
    run_produce_mv, run_merge_and_export, run_align_lyrics,
    run_analyze_srt, run_generate_music, run_generate_lyrics,
)


class MVPipeline:
    """MV 流水线主编排器"""

    def __init__(self, project_dir: str = None, auto_mode: bool = False):
        self.pm = ProjectManager(project_dir) if project_dir else None
        self.cfg = ConfigManager()
        self.logger = LLMLogger(project_dir) if project_dir else None
        self.client = LLMClient(self.logger)
        self.registry = PromptRegistry()
        self.auto_mode = auto_mode

    @classmethod
    def create_new(cls, theme: str, style: str = "动漫风",
                   music_style: str = "流行", mood: str = "温柔",
                   language: str = "中文", reference: str = "",
                   auto_mode: bool = False) -> "MVPipeline":
        """创建新项目并初始化流水线"""
        pm = ProjectManager.init_new(theme, style, music_style, mood,
                                     language, reference)
        pipeline = cls(str(pm.project_dir), auto_mode)
        pipeline.pm = pm
        return pipeline

    # ══════════════════════════════════════════════════════
    # 主编排循环
    # ══════════════════════════════════════════════════════

    def run(self, phases: str = None):
        """运行流水线

        phases:
          - None 或 "all": 完整流程 ① → ② → ③ → ③.5 → ④-⑧ → ⑨-⑪
          - "init": 只运行 Step ①-② (歌词+音乐生成)
          - "align": 只运行 Step ③ (歌词对齐)
          - "produce": 只运行 Step ④-⑧ (生图+Ken Burns)
          - "export": 只运行 Step ⑨-⑪ (合成+导出)

        注意：每个步骤内部管理自己的暂停点检查，不在此处全局处理
        """
        print(f"\n{'='*55}")
        print(f"  MV 流水线启动")
        print(f"  项目: {self.pm.project_name}")
        print(f"  主题: {self.pm.theme}")
        print(f"  模式: {'全自动' if self.auto_mode else '含暂停点'}")
        print(f"{'='*55}\n")

        # 检查打断
        if self.pm.check_interrupt():
            print("检测到中断信号，流水线停止")
            return

        phases = phases or "all"

        # 步骤 ①-②: 歌词 + 音乐（含内部暂停点检查）
        if phases in ("all", "init"):
            self._run_lyrics_and_music()
            if self.pm.check_interrupt():
                return

        # 步骤 ③: 歌词对齐（含内部暂停点检查）
        if phases in ("all", "align"):
            self._run_alignment()
            if self.pm.check_interrupt():
                return

        # 步骤 ③.5 + ④-⑧: 场景分析 + 生图 + Ken Burns（含内部暂停点检查）
        if phases in ("all", "produce"):
            self._run_scene_analysis()
            self._run_produce()
            if self.pm.check_interrupt():
                return

        # 步骤 ⑨-⑪: 合成 + 导出
        if phases in ("all", "export"):
            self._run_merge_and_export()

        print(f"\n{'='*55}")
        print(f"  MV 流水线完成！")
        print(f"  输出: {self.pm.project_dir}/output/")
        print(f"{'='*55}\n")

    # ══════════════════════════════════════════════════════
    # Step ①-②: 歌词 + 音乐（Python v2 原生实现）
    # ══════════════════════════════════════════════════════

    def _run_lyrics_and_music(self):
        """运行 Step ① 歌词 + Step ② 音乐，含暂停点检查

        流程：
          1. 生成歌词 (Step ①)
          2. 生成音乐 (Step ②)
          3. 展示暂停点，让用户确认歌词和音乐效果（仅非自动模式）
        """
        if not self.pm.is_step_completed("① lyrics"):
            self._step_lyrics()

        if not self.pm.is_step_completed("② music"):
            self._step_music()

        # 在 Step②完成后显示暂停点（仅当不是自动模式时）
        self._check_and_pause_step2()

    def _step_lyrics(self):
        """Step ①: 生成歌词 - 直接调用 MiniMax API"""
        print("\n[Step ①] 生成歌词...")
        self.pm.update_step("① lyrics", "running", "generating lyrics...")

        # 渲染 prompt
        try:
            prompt = self.registry.render("lyrics.generation", {
                "theme": self.pm.theme,
                "style": self.pm.style,
                "music_style": self.pm.music_style,
                "mood": self.pm.mood,
                "language": self.pm.language,
                "reference": self.pm.get("reference", ""),
            })
        except KeyError:
            prompt = self._build_lyrics_prompt_fallback()

        try:
            result = self.client.call_minimax_lyrics(prompt)

            song_title = result.get("song_title", "Untitled")
            style_tags = result.get("style_tags", "")
            lyrics = result.get("lyrics", "")

            if not lyrics:
                raise ValueError("API 返回歌词为空")

            # 保存歌词
            lyrics_file = self.pm.project_dir / "audio" / "lyrics.txt"
            lyrics_content = (
                f"## {song_title}\n"
                f"## Tags: {style_tags}\n"
                f"## Theme: {self.pm.theme}\n"
                f"## Generated by MiniMax Lyrics Generation API\n\n"
                f"{lyrics}"
            )
            lyrics_file.write_text(lyrics_content, encoding="utf-8")

            # 更新 metadata
            self.pm.set("song_title", song_title)
            self.pm.set("style_tags", style_tags.split(",") if style_tags else [])

            self.pm.update_step("① lyrics", "completed",
                                f"title='{song_title}', tags='{style_tags}'")
            print(f"  歌词生成完成: {song_title}")

        except Exception as e:
            self.pm.update_step("① lyrics", "failed", str(e))
            print(f"  歌词生成失败: {e}")
            raise

    def _step_music(self):
        """Step ②: 生成音乐 - 直接调用 MiniMax API"""
        print("\n[Step ②] 生成音乐...")
        self.pm.update_step("② music", "running", "generating music...")

        lyrics_file = self.pm.project_dir / "audio" / "lyrics.txt"
        if not lyrics_file.exists():
            raise FileNotFoundError(f"歌词文件不存在: {lyrics_file}")

        # 读取歌词（去注释）
        lines = lyrics_file.read_text(encoding="utf-8").splitlines()
        lyrics_text = " ".join(
            line.strip() for line in lines
            if line.strip() and not line.startswith("## ") and not line.startswith("#")
        )

        # 构建 prompt
        song_title = self.pm.song_title
        music_prompt_parts = []
        if song_title:
            music_prompt_parts.append(f"歌曲名：{song_title}")
        music_prompt_parts.append(f"情绪：{self.pm.mood}")
        music_prompt_parts.append(f"音乐风格：{self.pm.music_style}")
        music_prompt_parts.append(f"主题：{self.pm.theme}")
        music_prompt_parts.append(f"演唱语言：{self.pm.language}")
        music_prompt_parts.append("旋律流畅自然，节奏清晰，副歌抓耳，主歌舒缓")
        music_prompt_parts.append("完整歌曲结构：主歌1 → 副歌 → 主歌2 → 副歌 → 尾奏")
        music_prompt = "，".join(music_prompt_parts)

        try:
            result = self.client.call_minimax_music(music_prompt, lyrics_text)

            audio_bytes = result.get("audio_bytes", b"")
            if not audio_bytes:
                raise ValueError("API 返回音频数据为空")

            output_file = self.pm.project_dir / "audio" / "song.mp3"
            output_file.write_bytes(audio_bytes)
            file_size = output_file.stat().st_size / 1024 / 1024
            duration = self._get_audio_duration(str(output_file))
            self.pm.set("audio_duration_sec", duration)

            self.pm.update_step("② music", "completed",
                                f"{file_size:.1f}MB, {duration}s")
            print(f"  音乐生成完成: {file_size:.1f}MB, {duration}s")

        except Exception as e:
            self.pm.update_step("② music", "failed", str(e))
            print(f"  音乐生成失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # 暂停点检查
    # ══════════════════════════════════════════════════════

    def _check_and_pause_step2(self):
        """检查 Step② 的暂停点"""
        if self.auto_mode:
            self.pm.set("step2_approved", True)
            print("  自动模式：跳过 Step② 确认点")
            return

        choice = self.pm.get_user_choice("step_2_approval")
        if choice:
            print(f"  用户已选择: {choice}")
            return

        UserInteraction.pause_step2(self.pm)
        print(UserInteraction.format_prompt_for_agent(self.pm))

    # ══════════════════════════════════════════════════════
    # Step ③: 对齐 — 桥接到原版 Shell 脚本
    # ══════════════════════════════════════════════════════

    def _run_alignment(self):
        """运行 Step ③ 歌词对齐"""
        choice = self.pm.get_user_choice("step_3_alignment")
        if not choice and not self.auto_mode:
            UserInteraction.pause_step3_alignment(self.pm)
            print(UserInteraction.format_prompt_for_agent(self.pm))
            choice = self.pm.get_user_choice("step_3_alignment")

        align_mode = choice or "auto"

        self.pm.update_step("③ align", "running",
                            f"aligning lyrics (mode={align_mode})...")
        print(f"\n[Step ③] 歌词对齐（模式: {align_mode}）...")

        try:
            srt_file = self.pm.get("manual_srt_file", "") if align_mode == "manual" else ""
            result = run_align_lyrics(str(self.pm.project_dir), align_mode, srt_file)

            self.pm.update_step("③ align", "completed", f"mode={align_mode}")

        except Exception as e:
            self.pm.update_step("③ align", "failed", str(e))
            print(f"  对齐失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # Step ③.5: 场景分析 — Python v2 (scene_analyzer.SceneAnalyzer)
    # ══════════════════════════════════════════════════════

    def _run_scene_analysis(self):
        """Step ③.5: 场景分析"""
        scenes_path = self.pm.project_dir / "metadata" / "scenes.json"
        if scenes_path.exists():
            print("  场景分析已存在，跳过")
            return

        print("\n[Step ③.5] 场景分析...")
        from src.scene_analyzer import SceneAnalyzer

        try:
            analyzer = SceneAnalyzer(str(self.pm.project_dir))
            result = analyzer.analyze()

            if not self.auto_mode:
                UserInteraction.pause_step4_review_scenes(self.pm)
                print(UserInteraction.format_prompt_for_agent(self.pm))

        except Exception as e:
            print(f"  场景分析失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # Step ④-⑧: 生图 + Ken Burns — 混合实现

    def _run_produce(self):
        """运行 Step ④-⑧ 生图 + Ken Burns

        策略：
          Step ④:  基础角色图     -> Python v2 (scene_generator.generate_base_character)
          Step ⑤-⑦: 批量场景图   -> Python v2 (scene_generator.generate_all)
          Step ⑧:  Ken Burns     -> Python v2 (ken_burns.KenBurnsGenerator.process_project)
        """
        from src.scene_generator import SceneImageGenerator

        print("\n[Step ④-⑧] 生成图片 + Ken Burns...")
        self.pm.update_step("④ base", "running", "starting...")
        self.pm.update_step("⑤-⑦ images", "running", "starting...")
        self.pm.update_step("⑧ kb", "running", "starting...")

        try:
            scene_gen = SceneImageGenerator(str(self.pm.project_dir))

            # Step ④: 基础角色图
            print("\n  [Step ④] 基础角色图...")
            if not scene_gen.generate_base_character(
                theme=self.pm.theme,
                song_title=self.pm.get("song_title", ""),
            ):
                print("  [WARN] 基础角色图生成失败，继续后续步骤")
            self.pm.update_step("④ base", "completed", "done")

            # Step ⑤-⑦: 批量场景图 + 变体图
            print("\n  [Steps ⑤-⑦] 批量场景图...")
            img_result = scene_gen.generate_all(parallel=2)
            self.pm.update_step("⑤-⑦ images", "completed",
                                f"{img_result['succeeded']}/{img_result['total']} 成功, "
                                f"{img_result['failed']} 失败")

            if img_result["failed"] > 0:
                print(f"  [WARN] {img_result['failed']} 张图片生成失败")

        except Exception as e:
            self.pm.update_step("④ base", "failed", str(e))
            self.pm.update_step("⑤-⑦ images", "failed", str(e))
            print(f"  [FAIL] 生图失败: {e}")
            raise

        # Step ⑧: Ken Burns — 纯 Python 实现
        try:
            print("\n  [Step ⑧] Ken Burns 视频生成...")
            kb = KenBurnsGenerator()
            kb_result = kb.process_project(str(self.pm.project_dir))
            if kb_result["failed"] > 0:
                print(f"  [WARN] {kb_result['failed']} 个场景 KB 生成失败")
            self.pm.update_step("⑧ kb", "completed",
                                f"{kb_result['succeeded']}/{kb_result['total']} clips")
        except Exception as e:
            self.pm.update_step("⑧ kb", "failed", str(e))
            print(f"  [FAIL] Ken Burns 失败: {e}")
            raise

    # Step ⑨-⑪: 合成导出 — 桥接到原版 Shell 脚本
    # ══════════════════════════════════════════════════════

    def _run_merge_and_export(self):
        """运行 Step ⑨-⑪ 合成 + 导出（纯 Python 实现）"""
        print("\n[Step ⑨-⑪] 合成视频 + 导出...")

        try:
            exporter = MVExporter(str(self.pm.project_dir))
            export_result = exporter.export_all()

            concat = export_result.get("concat", {})
            merge = export_result.get("merge", {})
            exp = export_result.get("export", {})

            if concat.get("status") == "ok":
                self.pm.update_step("⑨ concat", "completed",
                                    f"{concat.get('clip_count', 0)} clips, "
                                    f"{concat.get('size_mb', 0):.1f}MB")

            if merge.get("status") == "ok":
                self.pm.update_step("⑩ merge", "completed",
                                    f"{merge.get('size_mb', 0):.1f}MB, "
                                    f"{merge.get('duration_sec', 0)}s")

            if exp.get("status") in ("ok", "partial"):
                self.pm.update_step("⑪ export", "completed",
                                    f"tiktok={exp.get('tiktok_size_mb', 0):.1f}MB, "
                                    f"vertical={exp.get('vertical_size_mb', 0):.1f}MB")

                print(f"\n{'='*55}")
                print(f"  MV 制作完成！")
                print(f"  输出: {self.pm.project_dir}/output/")
                print(f"  final.mp4: {merge.get('size_mb', 0):.1f}MB")
                print(f"  tiktok.mp4: {exp.get('tiktok_size_mb', 0):.1f}MB")
                print(f"  vertical.mp4: {exp.get('vertical_size_mb', 0):.1f}MB")
                print(f"{'='*55}\n")

                # 生成 LLM 报告
                self._generate_report()
            else:
                print("  导出未完成，请检查日志")

        except Exception as e:
            self.pm.update_step("⑩ merge", "failed", str(e))
            self.pm.update_step("⑪ export", "failed", str(e))
            print(f"  ❌ 导出失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════

    def _get_audio_duration(self, audio_file: str) -> int:
        """获取音频时长（秒）"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "csv=p=0", audio_file],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(float(result.stdout.strip()))
        except Exception:
            pass
        return 0

    def _build_lyrics_prompt_fallback(self) -> str:
        """Fallback 歌词 prompt 构造"""
        parts = [
            f"创作主题：{self.pm.theme}",
            f"整体艺术风格：{self.pm.style}",
            f"音乐曲风：{self.pm.music_style}",
            f"整体情绪氛围：{self.pm.mood}",
            f"创作语言：{self.pm.language}",
            "严格遵循标准流行歌曲结构：主歌1、副歌、主歌2、副歌、收尾段落",
            "句式长短均衡，韵律协调，押韵自然",
        ]
        ref = self.pm.get("reference", "")
        if ref:
            parts.append(f"参考创作风格：{ref}")
        return "，".join(parts)

    def _generate_report(self):
        """生成 LLM 报告（Python v2: ReportGenerator）"""
        try:
            from src.report_generator import ReportGenerator
            report_gen = ReportGenerator(str(self.pm.project_dir))
            output = self.pm.project_dir / "output" / "llm_report.html"
            report_gen.generate(str(output))
        except Exception as e:
            print(f"  报告生成失败: {e}")

    @property
    def project_dir(self) -> Path:
        return self.pm.project_dir if self.pm else None
