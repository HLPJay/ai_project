"""
project_manager.py — 统一的项目状态管理器

替代之前各脚本分别编辑 info.json / status.json 的分散方式。
提供原子化的状态更新、暂停点管理、用户选择记录。
"""

import json
import os
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


class ProjectManager:
    """项目管理器 — 统一状态管理核心"""

    STEP_ORDER = [
        "① lyrics", "② music", "③ align",
        "④ base", "⑤-⑦ images", "⑧ kb",
        "⑨ concat", "⑩ merge", "⑪ export"
    ]

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.info_path = self.project_dir / "metadata" / "info.json"
        self.status_path = self.project_dir / "metadata" / "status.json"
        self.interrupt_path = self.project_dir / "metadata" / "interrupt.json"
        self.steps_log = self.project_dir / "metadata" / "steps.log"
        self._info: Optional[Dict] = None

    # ── 属性 ──────────────────────────────────────────────

    @property
    def info(self) -> Dict:
        if self._info is None:
            self._info = self._load_json(self.info_path) or {}
        return self._info

    @property
    def project_name(self) -> str:
        return self.info.get("project_name", "")

    @property
    def theme(self) -> str:
        return self.info.get("theme", "")

    @property
    def style(self) -> str:
        return self.info.get("style", "动漫风")

    @property
    def music_style(self) -> str:
        return self.info.get("music_style", "流行")

    @property
    def mood(self) -> str:
        return self.info.get("mood", "温柔")

    @property
    def language(self) -> str:
        return self.info.get("language", "中文")

    @property
    def song_title(self) -> str:
        return self.info.get("song_title", "")

    @property
    def audio_duration(self) -> int:
        return self.info.get("audio_duration_sec", 0)

    # ── 工厂方法 ─────────────────────────────────────────

    @classmethod
    def init_new(cls, theme: str, style: str = "动漫风",
                 music_style: str = "流行", mood: str = "温柔",
                 language: str = "中文", reference: str = "",
                 workspace_root: str = None) -> "ProjectManager":
        """创建新项目"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()

        root = Path(workspace_root or cfg.get("WORKSPACE_ROOT", "~/.openclaw/workspace/mv")).expanduser()
        safe_name = cls._safe_name(theme)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = root / f"{safe_name}_{timestamp}"

        # 创建目录结构
        for subdir in ["metadata", "audio", "images", "clips", "temp", "output",
                       "metadata/llm_calls/responses"]:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 初始化 info.json
        info = {
            "project_name": theme,
            "theme": theme,
            "safe_name": safe_name,
            "created_at": datetime.now().isoformat(),
            "workspace_root": str(root),
            "notifications": False,
            "style": style,
            "music_style": music_style,
            "mood": mood,
            "language": language,
            "reference": reference,
            "image_seed": random.randint(0, 2147483646),
            "steps_completed": [],
            "pipeline": {step: {"status": "pending", "detail": "", "updated_at": None}
                         for step in cls.STEP_ORDER},
            "config": {
                "resolution": "1280x720",
                "fps": 25,
                "kb_fade_sec": 2,
                "subtitle_font": "Microsoft YaHei",
                "subtitle_size": 32
            }
        }

        pm = cls(str(project_dir))
        pm._save_json(pm.info_path, info)
        pm._info = info

        # 初始化 status.json
        pm._save_json(pm.status_path, {
            "project": safe_name,
            "pipeline": {step: {"status": "pending", "detail": "", "updated_at": None}
                         for step in cls.STEP_ORDER},
            "last_updated": datetime.now().isoformat()
        })

        # 初始化 interrupt.json
        pm._save_json(pm.interrupt_path, {
            "stop": False, "requested_at": None, "cleared_at": None
        })

        pm._log_step(f"Project initialized: {theme}")
        pm._log_step(f"Directory: {project_dir}")
        pm._log_step(f"Style: {style}, Music: {music_style}, Mood: {mood}")

        return pm

    # ── 状态管理 ─────────────────────────────────────────

    def update_step(self, step: str, status: str, detail: str = ""):
        """更新步骤状态（原子操作）"""
        self.info.setdefault("pipeline", {})
        self.info["pipeline"][step] = {
            "status": status,
            "detail": detail,
            "updated_at": datetime.now().isoformat()
        }
        self._save_info()

        # 也同步到 status.json（兼容性）
        status_data = self._load_json(self.status_path) or {}
        status_data.setdefault("pipeline", {})
        status_data["pipeline"][step] = {
            "status": status,
            "detail": detail,
            "updated_at": datetime.now().isoformat()
        }
        status_data["last_updated"] = datetime.now().isoformat()
        self._save_json(self.status_path, status_data)

        self._log_step(f"[{step}] {status}: {detail}")

        # 若完成，记录到 steps_completed
        if status == "completed":
            completed = self.info.get("steps_completed", [])
            if step not in completed:
                completed.append(step)
                self.info["steps_completed"] = completed
                self._save_info()

    def get_step_status(self, step: str) -> Optional[Dict]:
        """获取步骤状态"""
        return self.info.get("pipeline", {}).get(step)

    def is_step_completed(self, step: str) -> bool:
        return step in self.info.get("steps_completed", [])

    # ── 暂停点管理 ───────────────────────────────────────

    def require_approval(self, step_name: str, options: Dict[str, str],
                         prompt: str = ""):
        """设置暂停点，等待用户选择"""
        self.info["pending_approval"] = {
            "step": step_name,
            "options": options,
            "prompt": prompt,
            "awaiting_user": True,
            "user_choice": None,
            "created_at": datetime.now().isoformat()
        }
        self._save_info()
        self._log_step(f"[PAUSE] {step_name} awaiting user approval")

    def approve(self, user_choice: str):
        """用户做出选择"""
        if "pending_approval" not in self.info:
            raise ValueError("No pending approval found")
        self.info["pending_approval"]["awaiting_user"] = False
        self.info["pending_approval"]["user_choice"] = user_choice
        self.info["pending_approval"]["approved_at"] = datetime.now().isoformat()
        self._save_info()
        self._log_step(f"[APPROVE] User chose: {user_choice}")

    @property
    def is_awaiting_approval(self) -> bool:
        return self.info.get("pending_approval", {}).get("awaiting_user", False)

    @property
    def pending_approval_info(self) -> Optional[Dict]:
        return self.info.get("pending_approval") if self.is_awaiting_approval else None

    def get_user_choice(self, step_name: str) -> Optional[str]:
        """获取用户在某个暂停点的选择"""
        pa = self.info.get("pending_approval", {})
        if pa.get("step") == step_name and not pa.get("awaiting_user"):
            return pa.get("user_choice")
        return None

    # ── 数据管理 ─────────────────────────────────────────

    def set(self, key: str, value: Any):
        """设置 info.json 中的任意字段"""
        self.info[key] = value
        self._save_info()

    def get(self, key: str, default=None) -> Any:
        return self.info.get(key, default)

    def save_artifact(self, name: str, content: str, subdir: str = None):
        """保存产物到项目目录"""
        if subdir:
            path = self.project_dir / subdir / name
        else:
            path = self.project_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._log_step(f"[SAVE] {path}")
        return str(path)

    # ── 打断管理 ─────────────────────────────────────────

    def check_interrupt(self) -> bool:
        """检查是否被打断。返回 True=应停止"""
        data = self._load_json(self.interrupt_path)
        if data and data.get("stop", False):
            data["stop"] = False
            data["cleared_at"] = datetime.now().isoformat()
            self._save_json(self.interrupt_path, data)
            return True
        return False

    def request_interrupt(self):
        """请求打断（由用户或 Agent 调用）"""
        self._save_json(self.interrupt_path, {
            "stop": True,
            "requested_at": datetime.now().isoformat(),
            "cleared_at": None
        })

    # ── 内部方法 ─────────────────────────────────────────

    def _log_step(self, message: str):
        """写入步骤日志"""
        self.steps_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.steps_log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

    def _save_info(self):
        """保存 info.json"""
        self._save_json(self.info_path, self.info)

    @staticmethod
    def _load_json(path: Path) -> Optional[Dict]:
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    @staticmethod
    def _save_json(path: Path, data: Dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    @staticmethod
    def _safe_name(name: str) -> str:
        import re
        safe = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_-]', '_', name)
        return safe

    def __repr__(self):
        return f"<ProjectManager: {self.project_name} @ {self.project_dir}>"
