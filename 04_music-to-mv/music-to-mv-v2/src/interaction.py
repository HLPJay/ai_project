"""
interaction.py — 用户交互管理器

管理流水线中的暂停点，提供清晰的 Agent 交互接口。
暂停点自动检测，Agent 读取后展示给用户，用户回复后自动推进。
"""

from datetime import datetime
from typing import Optional, Dict, Any, Callable

from src.project_manager import ProjectManager


class UserInteraction:
    """用户交互管理器"""

    # ── 暂停点定义 ───────────────────────────────────────

    @staticmethod
    def pause_step2(pm: ProjectManager):
        """Step② 完成后暂停：询问用户是否继续"""
        pm.require_approval(
            step_name="step_2_approval",
            options={
                "continue": "✅ 继续 — 进入 Step③ 歌词对齐",
                "pause": "⏸️ 暂停 — 查看歌词/音乐后再决定",
                "retry_music": "🔄 重新生成音乐",
                "retry_lyrics": "🔄 重新生成歌词",
            },
            prompt=(
                "🎵 歌曲创作已完成！\n"
                f"   歌曲：{pm.song_title}\n"
                f"   时长：{pm.audio_duration}s\n"
                f"   主题：{pm.theme}\n"
                "\n"
                "是否继续后续步骤？"
            )
        )

    @staticmethod
    def pause_step3_alignment(pm: ProjectManager):
        """Step③ 前暂停：询问对齐方式"""
        pm.require_approval(
            step_name="step_3_alignment",
            options={
                "auto": "🔊 A. Demucs 自动对齐 — 全自动分离人声 + Whisper 转写 + 对齐",
                "manual": "📝 B. 手动 SRT — 用户提供 SRT 文件，跳过 ASR 阶段",
            },
            prompt=(
                "请选择歌词对齐方式：\n"
                "  A) 自动模式 — 使用 Demucs 分离人声 + Whisper 自动转写 + 智能对齐\n"
                "  B) 手动模式 — 跳过 ASR，直接使用您提供的 SRT 字幕文件\n"
                "\n"
                "输入 A 或 B 选择："
            )
        )

    @staticmethod
    def pause_step3_manual_srt(pm: ProjectManager):
        """Step③ 手动模式：询问 SRT 文件路径"""
        pm.require_approval(
            step_name="step_3_srt_path",
            options={
                # options are just for reference; Agent will ask for path
            },
            prompt=(
                "📝 请提供 SRT 字幕文件的路径：\n"
                "  (例如：/path/to/lyrics.srt)"
            )
        )

    @staticmethod
    def pause_step4_review_scenes(pm: ProjectManager):
        """Step③.5 场景分析后：展示场景列表，询问是否继续"""
        scenes_path = pm.project_dir / "metadata" / "scenes.json"
        if scenes_path.exists():
            import json
            scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
            scene_lines = []
            for i, s in enumerate(scenes, 1):
                label = s.get("label", "?")
                desc = s.get("description", "")[:60]
                scene_lines.append(f"  {i}. [{label}] {desc}")
            scene_preview = "\n".join(scene_lines)
        else:
            scene_preview = "  (暂无可预览的场景)"

        pm.require_approval(
            step_name="step_4_scene_review",
            options={
                "continue": "✅ 继续 — 生成场景图片",
                "retry": "🔄 重新分析 — 重新生成场景描述",
            },
            prompt=(
                "📋 场景分析完成！共 N 个场景：\n"
                f"{scene_preview}\n"
                "\n"
                "是否继续生成图片？"
            )
        )

    # ── 处理用户选择 ─────────────────────────────────────

    @staticmethod
    def handle_choice(pm: ProjectManager, choice: str) -> str:
        """处理用户选择，返回后续动作

        返回值：
            "continue" — 继续执行（无需等待）
            "retry"    — 需要重试当前步骤
            "pause"    — 用户暂停，等待
        """
        pending = pm.pending_approval_info
        if not pending:
            return "continue"

        step = pending.get("step", "")
        options = pending.get("options", {})

        cm = choice.strip().lower()

        if step == "step_2_approval":
            if cm in ("continue", "继续", "c", "y", "yes"):
                pm.approve("continue")
                return "continue"
            elif cm in ("pause", "暂停", "p"):
                pm.approve("pause")
                return "pause"
            elif cm in ("retry_music", "retry_music", "重做音乐", "重新生成音乐"):
                pm.approve("retry_music")
                return "retry"
            elif cm in ("retry_lyrics", "retry_lyrics", "重做歌词", "重新生成歌词"):
                pm.approve("retry_lyrics")
                return "retry"
            else:
                pm.approve(cm)
                return "continue"

        elif step == "step_3_alignment":
            if cm in ("a", "auto", "a)", "自动"):
                pm.approve("auto")
                return "continue"
            elif cm in ("b", "manual", "b)", "手动", "手动模式"):
                pm.approve("manual")
                return "manual_srt"  # 需要进一步询问 SRT 路径
            else:
                # 默认自动模式
                pm.approve("auto")
                return "continue"

        elif step == "step_4_scene_review":
            if cm in ("continue", "继续", "c"):
                pm.approve("continue")
                return "continue"
            else:
                pm.approve("retry")
                return "retry"

        else:
            # 未知步骤，直接继续
            pm.approve(choice)
            return "continue"

    # ── 检查暂停点 ───────────────────────────────────────

    @staticmethod
    def check_approval_status(pm: ProjectManager) -> Optional[Dict]:
        """检查是否有未处理的暂停点，返回信息供 Agent 使用"""
        return pm.pending_approval_info

    @staticmethod
    def is_paused(pm: ProjectManager) -> bool:
        """判断流水线是否处于暂停状态"""
        return pm.is_awaiting_approval

    @staticmethod
    def format_prompt_for_agent(pm: ProjectManager) -> str:
        """生成给 Agent 的提示文本"""
        pending = pm.pending_approval_info
        if not pending:
            return ""

        step = pending.get("step", "")
        prompt = pending.get("prompt", "")
        options = pending.get("options", {})

        lines = []
        lines.append("=" * 55)
        lines.append(f"  ⏸️ 用户交互暂停点: {step}")
        lines.append("=" * 55)
        if prompt:
            lines.append("")
            lines.append(prompt)

        if options:
            lines.append("")
            lines.append("可选操作：")
            for key, desc in options.items():
                lines.append(f"  {key}: {desc}")

        lines.append("")
        lines.append("请向用户展示以上信息，等待用户回复。")
        lines.append("用户做出选择后，调用 UserInteraction.handle_choice() 推进流水线。")
        lines.append("=" * 55)

        return "\n".join(lines)
