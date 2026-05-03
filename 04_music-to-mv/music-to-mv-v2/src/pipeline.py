"""
pipeline.py — MV 流水线主编排器

协调各步骤的执行顺序，处理暂停点、错误恢复、日志记录。
优先调用原版 scripts/ 目录下的 Shell/Python 脚本。

步骤映射：
  Step ①:  生成歌词       → generate_lyrics()         [Python v2]
  Step ②:  生成音乐       → generate_music()          [Python v2]
  Step ③:  歌词对齐       → align_lyrics()            [Shell: align_lyrics.sh]
  Step ③.5: 场景分析      → analyze_scenes()          [Python v2: src/scene_analyzer.py]
  Step ④:  基础视觉参考图 → base_character()          [Python v2: src/scene_generator.py]
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
from src.song_structure import select_song_structure
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

    def validate_tokens(self, phases: str = "all"):
        """启动前校验必要的 API token，缺失时提前报错

        phases 决定需要检查哪些 token：
          - init/all: 需要 minimax_token（歌词+音乐生成）
          - produce/all: 需要图片 provider 对应的 token
        """
        missing = []
        phases = phases or "all"

        if phases in ("all", "init"):
            if not self.cfg.get("minimax_token"):
                missing.append("MINIMAX_TOKEN（歌词/音乐生成）")

        if phases in ("all", "produce"):
            provider = self.cfg.get("image_api_provider", "minimax")
            token_map = {
                "minimax": ("minimax_token", "MINIMAX_TOKEN（图片生成）"),
                "alibaba": ("alibaba_token", "ALIBABA_TOKEN（图片生成）"),
                "dall-e":  ("openai_token",  "OPENAI_TOKEN（图片生成）"),
            }
            token_map["comfyui"] = ("", "本地 ComfyUI（无需 Token）")
            if provider in token_map and token_map[provider][0]:
                key, label = token_map[provider]
                if not self.cfg.get(key):
                    missing.append(label)

        if missing:
            raise ValueError(
                "缺少必要的 API Token，请在 .env 中配置：\n"
                + "\n".join(f"  - {m}" for m in missing)
            )

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
        # 启动前校验 token，缺失时立即报错
        self.validate_tokens(phases)

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

        # 步骤 0: 创意简报 (Creative Brief) — 在所有步骤之前执行
        if phases in ("all", "init"):
            self._run_creative_brief()
            if self.pm.check_interrupt():
                return

        # 步骤 ①
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
    # Step 0: 创意简报 (Creative Brief)
    # ══════════════════════════════════════════════════════

    def _run_creative_brief(self):
        """Step 0: 生成创意简报 — 在所有 LLM 步骤之前执行

        调用 LLM 将用户原始输入扩展为结构化 brief：
        - narrative_mode, visual_mode, character_policy, chorus_energy
        - visual_anchors, do_not_do
        这些字段会持久化到 info.json，供后续场景分析和图片生成使用。
        """
        if self.pm.get("narrative_mode"):
            if not self.pm.get("song_structure"):
                structure = self._select_song_structure()
                self.pm.set("song_structure_name", structure.name)
                self.pm.set("song_structure", structure.sequence)
                self.pm.set("song_structure_notes", structure.notes)
            print("  创意简报已存在，跳过")
            return

        print("\n[Step 0] 创意简报...")
        self.pm.update_step("① lyrics", "running", "creative brief...")

        try:
            prompt = self.registry.render("brief.creative", {
                "theme": self.pm.theme,
                "style": self.pm.style,
                "mood": self.pm.mood,
                "music_style": self.pm.music_style,
                "language": self.pm.language,
                "reference": self.pm.get("reference", ""),
            })

            api_url = "https://api.minimaxi.com/v1/chat/completions"
            payload = json.dumps({
                "model": self.cfg.get("llm_model", "MiniMax-M2.7"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.cfg.get_int("creative_brief_max_tokens", 2048),
            }).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {self.cfg.get('minimax_token', '')}",
                "Content-Type": "application/json",
            }

            resp_data = self.client._call_raw_api(
                api_url, payload, headers,
                prompt_key="creative_brief",
                model=self.cfg.get("llm_model", "MiniMax-M2.7"),
                prompt_text=prompt,
            )
            raw = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 解析 JSON（兼容 markdown 代码块包裹）
            import re
            json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                brace_start = raw.find("{")
                brace_end = raw.rfind("}")
                json_str = raw[brace_start:brace_end + 1] if brace_start != -1 and brace_end > brace_start else raw

            brief = json.loads(json_str) if json_str.strip().startswith("{") else {}

            for key in ("narrative_mode", "visual_mode", "character_policy",
                        "chorus_energy", "visual_anchors", "do_not_do"):
                if key in brief:
                    self.pm.set(key, brief[key])

            structure = self._select_song_structure()
            self.pm.set("song_structure_name", structure.name)
            self.pm.set("song_structure", structure.sequence)
            self.pm.set("song_structure_notes", structure.notes)

            print(f"  brief: narrative={brief.get('narrative_mode', 'N/A')}, "
                  f"visual={brief.get('visual_mode', 'N/A')}, "
                  f"character={brief.get('character_policy', 'N/A')}, "
                  f"chorus={brief.get('chorus_energy', 'N/A')}, "
                  f"structure={structure.name}")

            self.pm.update_step("① lyrics", "running", "creative brief done")

        except Exception as e:
            print(f"  创意简报生成失败: {e}（使用默认值继续）")
            # 失败不阻塞流程，使用默认值
            self.pm.set("narrative_mode", "mixed")
            self.pm.set("visual_mode", "environment-led")
            self.pm.set("character_policy", "optional protagonist")
            self.pm.set("chorus_energy", "lifted")
            structure = self._select_song_structure()
            self.pm.set("song_structure_name", structure.name)
            self.pm.set("song_structure", structure.sequence)
            self.pm.set("song_structure_notes", structure.notes)
            self.pm.update_step("① lyrics", "running", "creative brief fallback")

    def _select_song_structure(self):
        """根据配置和创意简报选择歌词/音乐共用的歌曲结构。"""
        return select_song_structure(
            theme=self.pm.theme,
            music_style=self.pm.music_style,
            mood=self.pm.mood,
            narrative_mode=self.pm.get("narrative_mode", ""),
            chorus_energy=self.pm.get("chorus_energy", ""),
            mode=self.cfg.get("lyrics_structure_mode", "adaptive"),
            override=self.cfg.get("lyrics_structure", ""),
        )

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
            structure = self._select_song_structure()
            if not self.pm.get("song_structure"):
                self.pm.set("song_structure_name", structure.name)
                self.pm.set("song_structure", structure.sequence)
                self.pm.set("song_structure_notes", structure.notes)

            # 根据情绪判断歌词长度要求（动态）
            mood_text = (self.pm.mood or "").lower()
            music_style_text = (self.pm.music_style or "").lower()

            is_fast = any(k in mood_text or k in music_style_text
                         for k in ("欢快", "energetic", "激烈", "摇滚", "rock",
                                  "热血", "燃", "爆发", "happy", "upbeat"))

            is_slow = any(k in mood_text or k in music_style_text
                         for k in ("舒缓", "抒情", "温暖", "温柔", "ballad",
                                  "故事", "回忆", "怀旧", "sad", "gentle",
                                  "梦幻", "空灵", "缥缈", "诗意", "悠扬",
                                  "dreamy", "ethereal", "poetic", "melancholic"))

            if is_fast:
                lyrics_length_req = "段落数：8-10 个段落；每段 3-5 句；总歌词 30-40 行，适配歌曲时长 120-150 秒"
            elif is_slow:
                lyrics_length_req = "段落数：12-16 个段落；每段 3-4 句；总歌词 50-70 行，适配歌曲时长 180-240 秒"
            else:
                lyrics_length_req = "段落数：10-12 个段落；每段 3-4 句；总歌词 40-55 行，适配歌曲时长 150-200 秒"

            prompt = self.registry.render("lyrics.generation", {
                "theme": self.pm.theme,
                "style": self.pm.style,
                "music_style": self.pm.music_style,
                "mood": self.pm.mood,
                "language": self.pm.language,
                "reference": self.pm.get("reference", ""),
                "song_structure": self.pm.get("song_structure", structure.sequence),
                "structure_notes": self.pm.get("song_structure_notes", structure.notes),
                "lyrics_length_requirement": lyrics_length_req,
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
        structure = self._select_song_structure()
        if not self.pm.get("song_structure"):
            self.pm.set("song_structure_name", structure.name)
            self.pm.set("song_structure", structure.sequence)
            self.pm.set("song_structure_notes", structure.notes)
        try:
            music_prompt = self.registry.render("music.generation", {
                "song_title": song_title or self.pm.theme,
                "mood": self.pm.mood,
                "music_style": self.pm.music_style,
                "theme": self.pm.theme,
                "language": self.pm.language,
                "reference": self.pm.get("reference", ""),
                "song_structure": self.pm.get("song_structure", structure.sequence),
                "structure_notes": self.pm.get("song_structure_notes", structure.notes),
            })
        except KeyError:
            music_prompt_parts = []
            if song_title:
                music_prompt_parts.append(f"歌曲名：{song_title}")
            music_prompt_parts.append(f"情绪：{self.pm.mood}")
            music_prompt_parts.append(f"音乐风格：{self.pm.music_style}")
            music_prompt_parts.append(f"主题：{self.pm.theme}")
            music_prompt_parts.append(f"演唱语言：{self.pm.language}")
            music_prompt_parts.append(
                f"歌曲结构：{self.pm.get('song_structure', structure.sequence)}"
            )
            music_prompt_parts.append("旋律流畅自然，节奏清晰，hook 抓耳，段落层次分明")
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

    def _wait_for_user_choice(self, step_name: str) -> str:
        """等待用户选择，兼容终端交互（input）和 Agent 模式（approve）

        检查顺序：
          1. get_user_choice() — Agent 已通过 approve() 设置的选择
          2. auto_mode — 跳过，返回默认值
          3. 终端 input() — 交互式等待用户输入
        """
        choice = self.pm.get_user_choice(step_name)
        if choice:
            return choice

        if self.auto_mode:
            defaults = {
                "step_2_approval": "continue",
                "step_3_alignment": "auto",
                "step_4_scene_review": "continue",
            }
            return defaults.get(step_name, "continue")

        options_map = {
            "step_2_approval": {
                "": "continue",
                "1": "continue", "2": "pause", "3": "retry_music", "4": "retry_lyrics",
                "c": "continue", "continue": "continue", "y": "continue", "yes": "continue", "继续": "continue",
                "p": "pause", "pause": "pause", "暂停": "pause",
                "retry_music": "retry_music", "重做音乐": "retry_music", "重新生成音乐": "retry_music",
                "retry_lyrics": "retry_lyrics", "重做歌词": "retry_lyrics", "重新生成歌词": "retry_lyrics",
            },
            "step_3_alignment": {
                "": "auto",
                "1": "auto", "2": "manual", "a": "auto", "b": "manual",
                "auto": "auto", "manual": "manual", "自动": "auto", "手动": "manual",
            },
            "step_4_scene_review": {
                "": "continue",
                "1": "continue", "2": "retry", "c": "continue", "continue": "continue", "r": "retry", "retry": "retry",
                "继续": "continue", "重新分析": "retry",
            },
        }
        opts = options_map.get(step_name, {"": "continue"})
        hint_map = {
            "step_2_approval": "回车/1/continue=继续，2/pause=暂停，3/retry_music=重做音乐，4/retry_lyrics=重做歌词",
            "step_3_alignment": "回车/1/auto/A=自动对齐，2/manual/B=手动 SRT",
            "step_4_scene_review": "回车/1/continue=继续，2/retry=重新分析",
        }
        if step_name in hint_map:
            print(f"  可输入: {hint_map[step_name]}")
        while True:
            raw = input("\n请输入选项（直接回车=默认继续/自动）> ").strip().lower()
            if raw in opts:
                selected = opts[raw]
                self.pm.approve(selected)
                return selected
            print(f"  无效输入: {raw or '<空>'}，请重新选择。")

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
        print(UserInteraction.format_prompt_for_agent(self.pm, cli_mode=True))

        choice = self._wait_for_user_choice("step_2_approval")

        if choice == "retry_lyrics":
            print("  用户选择重新生成歌词...")
            self.pm.update_step("① lyrics", "pending", "retry")
            self.pm.set("step2_approved", False)
            return self._run_lyrics_and_music()
        elif choice == "retry_music":
            print("  用户选择重新生成音乐...")
            self.pm.update_step("② music", "pending", "retry")
            self.pm.set("step2_approved", False)
            return self._run_lyrics_and_music()
        elif choice == "pause":
            print("  用户选择暂停，流水线停止")
            sys.exit(0)
        else:
            self.pm.set("step2_approved", True)
            print("  ✅ 继续执行")

    # ══════════════════════════════════════════════════════
    # Step ③: 对齐 — 桥接到原版 Shell 脚本
    # ══════════════════════════════════════════════════════

    def _run_alignment(self):
        """运行 Step ③ 歌词对齐"""
        choice = self.pm.get_user_choice("step_3_alignment")
        if not choice and not self.auto_mode:
            UserInteraction.pause_step3_alignment(self.pm)
            print(UserInteraction.format_prompt_for_agent(self.pm, cli_mode=True))
            choice = self._wait_for_user_choice("step_3_alignment")

        align_mode = choice or "auto"

        self.pm.update_step("③ align", "running",
                            f"aligning lyrics (mode={align_mode})...")
        print(f"\n[Step ③] 歌词对齐（模式: {align_mode}）...")

        try:
            srt_file = self.pm.get("manual_srt_file", "") if align_mode == "manual" else ""
            result = run_align_lyrics(
                str(self.pm.project_dir),
                align_mode,
                srt_file,
                timeout=self.cfg.get_int("align_timeout_sec", 600),
            )
            self.pm.set("alignment", {
                "mode": align_mode,
                "status": result.get("status", "completed"),
                "engine": result.get("engine", ""),
                "srt_path": result.get("srt_path", ""),
                "aligned_lines": result.get("aligned_lines", 0),
                "total_lines": result.get("total_lines", 0),
                "total_lyrics_lines": result.get("total_lines", 0),
                "srt_entries": result.get("srt_entries", 0),
                "timeline_fallback": result.get("timeline_fallback", False),
                "timeline_strategy": result.get("timeline_strategy", ""),
            })

            self.pm.update_step("③ align", "completed", f"mode={align_mode}")

        except Exception as e:
            self.pm.update_step("③ align", "failed", str(e))
            print(f"  对齐失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # 步骤 ③.5: 场景分析 — Python v2 (scene_analyzer.SceneAnalyzer)
    # ══════════════════════════════════════════════════════

    def _run_scene_analysis(self):
        """Step ③.5: 场景分析"""
        scenes_path = self.pm.project_dir / "metadata" / "scenes.json"
        if scenes_path.exists():
            self.pm.update_step("scene_analysis", "completed", "cached scenes.json")
            print("  场景分析已存在，跳过")
            return

        print("\n[Step ③.5] 场景分析...")
        self.pm.update_step("scene_analysis", "running", "analyzing scenes...")
        from src.scene_analyzer import SceneAnalyzer

        try:
            analyzer = SceneAnalyzer(str(self.pm.project_dir))
            result = analyzer.analyze()
            self.pm.update_step(
                "scene_analysis",
                "completed",
                f"{result.get('scene_count', 0)} scenes, source={result.get('desc_source', 'unknown')}",
            )

            if not self.auto_mode:
                UserInteraction.pause_step4_review_scenes(self.pm)
                print(UserInteraction.format_prompt_for_agent(self.pm, cli_mode=True))
                choice = self._wait_for_user_choice("step_4_scene_review")
                if choice == "retry":
                    print("  用户选择重新分析...")
                    if scenes_path.exists():
                        scenes_path.unlink()
                    return self._run_scene_analysis()

        except Exception as e:
            self.pm.update_step("scene_analysis", "failed", str(e))
            print(f"  场景分析失败: {e}")
            raise

    # ══════════════════════════════════════════════════════
    # Step ④-⑧: 生图 + Ken Burns — 混合实现

    def _run_produce(self):
        """运行 Step ④-⑧ 生图 + Ken Burns

        策略：
          Step ④:  基础视觉参考图 -> Python v2 (scene_generator.generate_base_character)
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

            # Step ④: 基础视觉参考图
            print("\n  [Step ④] 基础视觉参考图...")
            if not scene_gen.generate_base_character(
                theme=self.pm.theme,
                song_title=self.pm.get("song_title", ""),
            ):
                print("  [WARN] 基础视觉参考图生成失败，继续后续步骤")
            self.pm.update_step("④ base", "completed", "done")

            # Step ④.5: 全局锚定图（environment + symbolic anchor）
            print("\n  [Step ④.5] 全局锚定图...")
            scenes = scene_gen._load_scenes()
            anchor_result = scene_gen.generate_anchors(scenes)
            if anchor_result:
                print(f"  [Anchors] environment={bool(anchor_result.get('environment_anchor'))}, "
                      f"symbolic={bool(anchor_result.get('symbolic_anchor'))}")

            # Step ⑤-⑦: 批量场景图 + 变体图
            print("\n  [Steps ⑤-⑦] 批量场景图...")
            img_result = scene_gen.generate_all(
                parallel=max(1, self.cfg.get_int("image_parallel", 1))
            )
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
            kb = KenBurnsGenerator(
                timeout_buffer_sec=self.cfg.get_int("kb_timeout_buffer_sec", 30)
            )
            kb_result = kb.process_project(str(self.pm.project_dir))
            if kb_result["failed"] > 0:
                failed_rows = [
                    r for r in kb_result.get("results", [])
                    if r.get("status") == "failed"
                ]
                detail = "; ".join(
                    f"scene {r.get('sid')}: {r.get('error', 'unknown')}"
                    for r in failed_rows[:3]
                )
                raise RuntimeError(
                    f"{kb_result['failed']} 个场景 KB 生成失败: {detail}"
                )
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
            exporter = MVExporter(
                str(self.pm.project_dir),
                ffmpeg_timeout=self.cfg.get_int("ffmpeg_timeout_sec", 600),
                ffprobe_timeout=self.cfg.get_int("ffprobe_timeout_sec", 10),
            )
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
                capture_output=True, text=True,
                timeout=self.cfg.get_int("ffprobe_timeout_sec", 10)
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(float(result.stdout.strip()))
        except Exception:
            pass
        return 0

    def _build_lyrics_prompt_fallback(self) -> str:
        """Fallback 歌词 prompt 构造（方案 B：根据情绪设置歌词长度）"""
        structure = self._select_song_structure()

        # 根据情绪/风格判断歌词目标长度
        mood_text = (self.pm.mood or "").lower()
        music_style_text = (self.pm.music_style or "").lower()

        # 快节奏、高能情绪 → 较短歌词
        is_fast = any(k in mood_text or k in music_style_text
                     for k in ("欢快", "energetic", "激烈", "摇滚", "rock",
                              "热血", "燃", "爆发", "happy", "upbeat"))

        # 慢歌、抒情、叙事 → 长歌词
        is_slow = any(k in mood_text or k in music_style_text
                     for k in ("舒缓", "抒情", "温暖", "温柔", "ballad",
                              "故事", "回忆", "怀旧", "sad", "gentle",
                              "梦幻", "空灵", "缥缈", "诗意", "悠扬",
                              "dreamy", "ethereal", "poetic", "melancholic"))

        # 根据判断设置目标行数和时长
        if is_fast:
            target_lines = "30-40"
            duration = "120-150"
        elif is_slow:
            target_lines = "50-70"
            duration = "180-240"
        else:
            target_lines = "40-55"
            duration = "150-200"

        parts = [
            f"创作主题：{self.pm.theme}",
            f"整体艺术风格：{self.pm.style}",
            f"音乐曲风：{self.pm.music_style}",
            f"整体情绪氛围：{self.pm.mood}",
            f"创作语言：{self.pm.language}",
            f"推荐歌曲结构：{self.pm.get('song_structure', structure.sequence)}",
            f"结构说明：{self.pm.get('song_structure_notes', structure.notes)}",
            "可按音乐性微调结构，避免所有歌曲都套用固定主歌-副歌模板",
            "句式长短均衡，韵律协调，押韵自然",
            f"歌词行数：生成 {target_lines} 行歌词，确保歌曲时长约 {duration} 秒（{duration.split('-')[0]}秒-{duration.split('-')[1]}秒）",
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
