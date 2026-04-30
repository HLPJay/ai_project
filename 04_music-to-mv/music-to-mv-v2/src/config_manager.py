"""
config_manager.py — 统一配置管理器

从 .env 文件 + 环境变量加载所有配置。
替代之前 config.sh 的 Shell 方式，统一在 Python 中管理。
"""

import os
import json
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Config:
    """配置数据类"""
    # MiniMax
    minimax_token: str = ""
    minimax_api_host: str = "https://api.minimaxi.com"

    # LLM
    llm_model: str = "MiniMax-M2.7"

    # Image Provider
    image_api_provider: str = "minimax"

    # 各 Provider 的 URL 和 Model
    image_api_url_minimax: str = "https://api.minimaxi.com/v1/image_generation"
    image_model_minimax: str = "image-01"

    image_api_url_pollinations: str = "https://image.pollinations.ai"
    image_model_pollinations: str = "flux"

    image_api_url_alibaba: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    image_model_alibaba: str = "wan2.2-t2i-plus"

    image_api_url_dalle: str = "https://api.openai.com/v1/images/generations"
    image_model_dalle: str = "dall-e-3"

    # 其他 API Keys
    alibaba_token: str = ""
    openai_token: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 项目
    workspace_root: str = "~/.openclaw/workspace/mv"


class ConfigManager:
    """配置管理器（单例）"""

    _instance: Optional["ConfigManager"] = None

    def __new__(cls, env_file: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init(env_file)
        return cls._instance

    def _init(self, env_file: str = None):
        self._env_file = env_file
        self._config = Config()
        self._load_env_file()
        self._load_env_vars()

    def _load_env_file(self):
        """加载 .env 文件"""
        candidates = []

        if self._env_file:
            candidates.append(Path(self._env_file))

        # 从当前目录向上找 .env
        current = Path.cwd()
        for _ in range(5):
            candidates.append(current / ".env")
            candidates.append(current / "../.env")
            current = current.parent

        for env_path in candidates:
            if env_path and env_path.exists():
                self._parse_env_file(env_path)
                return

    def _parse_env_file(self, path: Path):
        """解析 .env 文件"""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                # 只在环境变量未设置时使用 .env 的值
                if key not in os.environ:
                    os.environ[key] = value
        except Exception:
            pass

    def _load_env_vars(self):
        """从环境变量加载"""
        mapping = {
            "MINIMAX_TOKEN": "minimax_token",
            "MINIMAX_API_HOST": "minimax_api_host",
            "LLM_MODEL": "llm_model",
            "IMAGE_API_PROVIDER": "image_api_provider",
            "IMAGE_API_URL_MINIMAX": "image_api_url_minimax",
            "IMAGE_MODEL_MINIMAX": "image_model_minimax",
            "IMAGE_API_URL_POLLINATIONS": "image_api_url_pollinations",
            "IMAGE_MODEL_POLLINATIONS": "image_model_pollinations",
            "IMAGE_API_URL_ALIBABA": "image_api_url_alibaba",
            "IMAGE_MODEL_ALIBABA": "image_model_alibaba",
            "IMAGE_API_URL_DALLE": "image_api_url_dalle",
            "IMAGE_MODEL_DALLE": "image_model_dalle",
            "ALIBABA_TOKEN": "alibaba_token",
            "OPENAI_TOKEN": "openai_token",
            "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
            "TELEGRAM_CHAT_ID": "telegram_chat_id",
            "WORKSPACE_ROOT": "workspace_root",
        }

        for env_key, config_key in mapping.items():
            value = os.environ.get(env_key)
            if value:
                setattr(self._config, config_key, value)

    # ── 属性访问 ─────────────────────────────────────────

    @property
    def config(self) -> Config:
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return getattr(self._config, key, default)

    def get_image_api_url(self) -> str:
        """获取当前 provider 的图片 API URL"""
        provider = self._config.image_api_provider
        mapping = {
            "minimax": self._config.image_api_url_minimax,
            "pollinations": self._config.image_api_url_pollinations,
            "alibaba": self._config.image_api_url_alibaba,
            "dall-e": self._config.image_api_url_dalle,
        }
        return mapping.get(provider, self._config.image_api_url_minimax)

    def get_image_model(self) -> str:
        """获取当前 provider 的图片模型"""
        provider = self._config.image_api_provider
        mapping = {
            "minimax": self._config.image_model_minimax,
            "pollinations": self._config.image_model_pollinations,
            "alibaba": self._config.image_model_alibaba,
            "dall-e": self._config.image_model_dalle,
        }
        return mapping.get(provider, self._config.image_model_minimax)

    def get_image_token(self) -> str:
        """获取当前 provider 的 API Token"""
        provider = self._config.image_api_provider
        mapping = {
            "minimax": self._config.minimax_token,
            "alibaba": self._config.alibaba_token,
            "dall-e": self._config.openai_token,
            "pollinations": "",  # 免费，无需 token
        }
        return mapping.get(provider, "")

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "provider": self._config.image_api_provider,
            "llm_model": self._config.llm_model,
            "image_model": self.get_image_model(),
            "workspace_root": self._config.workspace_root,
            "has_minimax_token": bool(self._config.minimax_token),
            "has_alibaba_token": bool(self._config.alibaba_token),
            "has_openai_token": bool(self._config.openai_token),
        }

    def __repr__(self):
        return f"<ConfigManager: provider={self._config.image_api_provider}>"
