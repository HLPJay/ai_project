"""
config_manager.py — 统一配置管理器

从 .env 文件 + 环境变量加载所有配置。
替代之前 config.sh 的 Shell 方式，统一在 Python 中管理。
"""

import os
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class Config:
    """配置数据类"""
    # === MiniMax Token 拆分（向后兼容） ===
    # 旧配置（保留向后兼容）
    minimax_token: str = ""
    minimax_api_host: str = "https://api.minimaxi.com"

    # 新配置（拆分专用 Token）
    minimax_token_llm: str = ""           # LLM 专用（Plus 极速版，月度）
    minimax_api_host_llm: str = "https://api.minimaxi.com"
    minimax_token_image: str = ""         # 图片生成专用（按量计费）
    minimax_api_host_image: str = "https://api.minimaxi.com"

    # LLM
    llm_model: str = "MiniMax-M2.7-highspeed"

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

    image_api_url_comfyui: str = "http://127.0.0.1:8188"
    image_model_comfyui: str = ""
    comfyui_workflow: str = ""
    comfyui_width: int = 1280
    comfyui_height: int = 720
    comfyui_steps: int = 28
    comfyui_cfg: float = 4.5
    comfyui_sampler: str = "dpmpp_2m"
    comfyui_scheduler: str = "karras"
    comfyui_timeout_sec: int = 300
    comfyui_poll_interval_sec: float = 1.0

    # 其他 API Keys
    alibaba_token: str = ""
    openai_token: str = ""
    dashscope_api_key: str = ""

    # 场景分镜 prompt 生成模型。默认沿用 MiniMax；可切到 alibaba_qwen 单独测试。
    scene_prompt_provider: str = "minimax"
    scene_prompt_model: str = ""
    scene_prompt_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    scene_prompt_disable_thinking: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 项目
    workspace_root: str = "~/.openclaw/workspace/mv"

    # API 重试/超时（通用默认）
    api_max_retries: int = 3
    api_base_delay_sec: float = 2.0
    api_max_delay_sec: float = 30.0
    api_timeout_sec: float = 60.0
    api_log_enabled: bool = False
    api_log_retries: bool = True
    api_log_prompt: bool = False
    api_log_response: bool = False
    api_log_max_chars: int = 500

    # 分类型 API 覆盖
    lyrics_api_max_retries: int = 2
    lyrics_api_base_delay_sec: float = 2.0
    lyrics_api_timeout_sec: float = 120.0

    music_api_max_retries: int = 2
    music_api_base_delay_sec: float = 5.0
    music_api_timeout_sec: float = 180.0

    image_api_max_retries: int = 3
    image_api_base_delay_sec: float = 2.0
    image_api_timeout_sec: float = 60.0

    scene_desc_api_max_retries: int = 3
    scene_desc_api_base_delay_sec: float = 2.0
    scene_desc_api_timeout_sec: float = 120.0

    variant_api_max_retries: int = 3
    variant_api_base_delay_sec: float = 2.0
    variant_api_timeout_sec: float = 120.0

    download_max_retries: int = 3
    download_base_delay_sec: float = 2.0
    download_timeout_sec: float = 60.0

    # Chat completion 输出长度
    scene_desc_max_tokens: int = 4096
    scene_desc_batch_size: int = 2
    variant_desc_max_tokens: int = 4096
    variant_desc_batch_size: int = 4
    visual_bible_max_tokens: int = 2048
    creative_brief_max_tokens: int = 2048

    # 并发
    image_parallel: int = 1

    # 歌曲结构
    lyrics_structure_mode: str = "adaptive"
    lyrics_structure: str = ""

    # 本地处理超时
    align_timeout_sec: int = 600
    align_asr_enabled: bool = True
    align_whisper_model: str = "medium"
    align_whisper_fallback_models: str = "small,base,tiny"
    align_whisper_device: str = "auto"
    align_whisper_language: str = "zh"
    align_demucs_enabled: bool = True
    align_demucs_device: str = "auto"
    align_demucs_check_timeout_sec: int = 10
    script_timeout_sec: int = 600
    scene_analysis_timeout_sec: int = 180
    ffmpeg_timeout_sec: int = 600
    ffprobe_timeout_sec: int = 10
    kb_timeout_buffer_sec: int = 30

    # Ken Burns 镜头运动
    kb_zoom_start: float = 1.0
    kb_zoom_end: float = 1.12
    kb_pan_x: float = 30.0
    kb_pan_y: float = 18.0
    kb_supersample_scale: int = 2

    # 图片质检
    image_quality_enabled: bool = True
    image_quality_min_file_size: int = 1000
    image_quality_min_width: int = 512
    image_quality_min_height: int = 512
    image_quality_min_stddev: float = 6.0


class ConfigManager:
    """配置管理器（单例，线程安全）"""

    _instance: Optional["ConfigManager"] = None
    _lock = __import__("threading").Lock()
    _legacy_key_map = {
        "WORKSPACE_ROOT": "workspace_root",
        "MINIMAX_TOKEN": "minimax_token",
        "ALIBABA_TOKEN": "alibaba_token",
        "OPENAI_TOKEN": "openai_token",
        "IMAGE_API_PROVIDER": "image_api_provider",
        "LLM_MODEL": "llm_model",
    }

    def __new__(cls, env_file: str = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = super().__new__(cls)
                    cls._instance._init(env_file)
        return cls._instance

    def _init(self, env_file: str = None):
        self._env_file = env_file
        self._config = Config()
        self._file_values: Dict[str, str] = {}  # .env 解析结果，不写入 os.environ
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
        """解析 .env 文件，结果存入 _file_values，不写 os.environ"""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                self._file_values[key.strip()] = value.strip().strip("\"'")
        except Exception:
            pass

    def _load_env_vars(self):
        """从环境变量（优先）或 .env 文件加载配置"""
        mapping = {
            # 旧配置（向后兼容）
            "MINIMAX_TOKEN": "minimax_token",
            "MINIMAX_API_HOST": "minimax_api_host",
            # 新配置（Token 拆分）
            "MINIMAX_TOKEN_LLM": "minimax_token_llm",
            "MINIMAX_API_HOST_LLM": "minimax_api_host_llm",
            "MINIMAX_TOKEN_IMAGE": "minimax_token_image",
            "MINIMAX_API_HOST_IMAGE": "minimax_api_host_image",
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
            "IMAGE_API_URL_COMFYUI": "image_api_url_comfyui",
            "IMAGE_MODEL_COMFYUI": "image_model_comfyui",
            "COMFYUI_WORKFLOW": "comfyui_workflow",
            "COMFYUI_WIDTH": "comfyui_width",
            "COMFYUI_HEIGHT": "comfyui_height",
            "COMFYUI_STEPS": "comfyui_steps",
            "COMFYUI_CFG": "comfyui_cfg",
            "COMFYUI_SAMPLER": "comfyui_sampler",
            "COMFYUI_SCHEDULER": "comfyui_scheduler",
            "COMFYUI_TIMEOUT_SEC": "comfyui_timeout_sec",
            "COMFYUI_POLL_INTERVAL_SEC": "comfyui_poll_interval_sec",
            "ALIBABA_TOKEN": "alibaba_token",
            "OPENAI_TOKEN": "openai_token",
            "DASHSCOPE_API_KEY": "dashscope_api_key",
            "SCENE_PROMPT_PROVIDER": "scene_prompt_provider",
            "SCENE_PROMPT_MODEL": "scene_prompt_model",
            "SCENE_PROMPT_API_URL": "scene_prompt_api_url",
            "SCENE_PROMPT_DISABLE_THINKING": "scene_prompt_disable_thinking",
            "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
            "TELEGRAM_CHAT_ID": "telegram_chat_id",
            "WORKSPACE_ROOT": "workspace_root",
            "API_MAX_RETRIES": "api_max_retries",
            "API_BASE_DELAY_SEC": "api_base_delay_sec",
            "API_MAX_DELAY_SEC": "api_max_delay_sec",
            "API_TIMEOUT_SEC": "api_timeout_sec",
            "API_LOG_ENABLED": "api_log_enabled",
            "API_LOG_RETRIES": "api_log_retries",
            "API_LOG_PROMPT": "api_log_prompt",
            "API_LOG_RESPONSE": "api_log_response",
            "API_LOG_MAX_CHARS": "api_log_max_chars",
            "LYRICS_API_MAX_RETRIES": "lyrics_api_max_retries",
            "LYRICS_API_BASE_DELAY_SEC": "lyrics_api_base_delay_sec",
            "LYRICS_API_TIMEOUT_SEC": "lyrics_api_timeout_sec",
            "MUSIC_API_MAX_RETRIES": "music_api_max_retries",
            "MUSIC_API_BASE_DELAY_SEC": "music_api_base_delay_sec",
            "MUSIC_API_TIMEOUT_SEC": "music_api_timeout_sec",
            "IMAGE_API_MAX_RETRIES": "image_api_max_retries",
            "IMAGE_API_BASE_DELAY_SEC": "image_api_base_delay_sec",
            "IMAGE_API_TIMEOUT_SEC": "image_api_timeout_sec",
            "SCENE_DESC_API_MAX_RETRIES": "scene_desc_api_max_retries",
            "SCENE_DESC_API_BASE_DELAY_SEC": "scene_desc_api_base_delay_sec",
            "SCENE_DESC_API_TIMEOUT_SEC": "scene_desc_api_timeout_sec",
            "VARIANT_API_MAX_RETRIES": "variant_api_max_retries",
            "VARIANT_API_BASE_DELAY_SEC": "variant_api_base_delay_sec",
            "VARIANT_API_TIMEOUT_SEC": "variant_api_timeout_sec",
            "DOWNLOAD_MAX_RETRIES": "download_max_retries",
            "DOWNLOAD_BASE_DELAY_SEC": "download_base_delay_sec",
            "DOWNLOAD_TIMEOUT_SEC": "download_timeout_sec",
            "SCENE_DESC_MAX_TOKENS": "scene_desc_max_tokens",
            "SCENE_DESC_BATCH_SIZE": "scene_desc_batch_size",
            "VARIANT_DESC_MAX_TOKENS": "variant_desc_max_tokens",
            "VARIANT_DESC_BATCH_SIZE": "variant_desc_batch_size",
            "VISUAL_BIBLE_MAX_TOKENS": "visual_bible_max_tokens",
            "CREATIVE_BRIEF_MAX_TOKENS": "creative_brief_max_tokens",
            "IMAGE_PARALLEL": "image_parallel",
            "LYRICS_STRUCTURE_MODE": "lyrics_structure_mode",
            "LYRICS_STRUCTURE": "lyrics_structure",
            "ALIGN_TIMEOUT_SEC": "align_timeout_sec",
            "ALIGN_ASR_ENABLED": "align_asr_enabled",
            "ALIGN_WHISPER_MODEL": "align_whisper_model",
            "ALIGN_WHISPER_FALLBACK_MODELS": "align_whisper_fallback_models",
            "ALIGN_WHISPER_DEVICE": "align_whisper_device",
            "ALIGN_WHISPER_LANGUAGE": "align_whisper_language",
            "ALIGN_DEMUCS_ENABLED": "align_demucs_enabled",
            "ALIGN_DEMUCS_DEVICE": "align_demucs_device",
            "ALIGN_DEMUCS_CHECK_TIMEOUT_SEC": "align_demucs_check_timeout_sec",
            "SCRIPT_TIMEOUT_SEC": "script_timeout_sec",
            "SCENE_ANALYSIS_TIMEOUT_SEC": "scene_analysis_timeout_sec",
            "FFMPEG_TIMEOUT_SEC": "ffmpeg_timeout_sec",
            "FFPROBE_TIMEOUT_SEC": "ffprobe_timeout_sec",
            "KB_TIMEOUT_BUFFER_SEC": "kb_timeout_buffer_sec",
            "KB_ZOOM_START": "kb_zoom_start",
            "KB_ZOOM_END": "kb_zoom_end",
            "KB_PAN_X": "kb_pan_x",
            "KB_PAN_Y": "kb_pan_y",
            "KB_SUPERSAMPLE_SCALE": "kb_supersample_scale",
            "IMAGE_QUALITY_ENABLED": "image_quality_enabled",
            "IMAGE_QUALITY_MIN_FILE_SIZE": "image_quality_min_file_size",
            "IMAGE_QUALITY_MIN_WIDTH": "image_quality_min_width",
            "IMAGE_QUALITY_MIN_HEIGHT": "image_quality_min_height",
            "IMAGE_QUALITY_MIN_STDDEV": "image_quality_min_stddev",
        }

        for env_key, config_key in mapping.items():
            # os.environ 优先，其次 .env 文件，均无则保留 Config 默认值
            value = os.environ.get(env_key) or self._file_values.get(env_key)
            if value:
                setattr(self._config, config_key, self._coerce_value(config_key, value))

    def _coerce_value(self, config_key: str, value: str) -> Any:
        """按默认值类型转换 .env 字符串。转换失败时保留默认值。"""
        current = getattr(self._config, config_key, "")
        try:
            if isinstance(current, bool):
                return str(value).strip().lower() in ("1", "true", "yes", "on", "y")
            if isinstance(current, int) and not isinstance(current, bool):
                return int(value)
            if isinstance(current, float):
                return float(value)
        except (TypeError, ValueError):
            return current
        return value

    # ── 属性访问 ─────────────────────────────────────────

    @property
    def config(self) -> Config:
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        normalized = self._legacy_key_map.get(key, key)
        return getattr(self._config, normalized, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置，兼容字符串环境变量。"""
        value = self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点配置，兼容字符串环境变量。"""
        value = self.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔配置，兼容 .env 中的 true/false/1/0。"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on", "y")

    def get_image_api_url(self) -> str:
        """获取当前 provider 的图片 API URL"""
        provider = self._config.image_api_provider
        mapping = {
            "minimax": self._config.image_api_url_minimax,
            "pollinations": self._config.image_api_url_pollinations,
            "alibaba": self._config.image_api_url_alibaba,
            "dall-e": self._config.image_api_url_dalle,
            "comfyui": self._config.image_api_url_comfyui,
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
            "comfyui": self._config.image_model_comfyui,
        }
        return mapping.get(provider, self._config.image_model_minimax)

    def get_llm_token(self) -> str:
        """获取 LLM 专用 Token（支持拆分架构）

        优先级：
        1. MINIMAX_TOKEN_LLM (新的拆分 Token)
        2. MINIMAX_TOKEN (兼容旧配置)
        """
        if self._config.minimax_token_llm:
            return self._config.minimax_token_llm
        return self._config.minimax_token

    def get_llm_api_host(self) -> str:
        """获取 LLM 专用 API Host"""
        if self._config.minimax_token_llm:
            return self._config.minimax_api_host_llm
        return self._config.minimax_api_host

    def get_image_token(self) -> str:
        """获取图片生成 Token（支持拆分架构）

        优先级：
        1. MINIMAX_TOKEN_IMAGE (新的拆分 Token)
        2. provider 特定的 Token
        3. 回退到旧 MINIMAX_TOKEN
        """
        provider = self._config.image_api_provider

        # 先检查拆分 Token
        if provider == "minimax" and self._config.minimax_token_image:
            return self._config.minimax_token_image

        # 再检查 provider 特定 Token
        mapping = {
            "minimax": self._config.minimax_token,  # 回退到旧 token
            "alibaba": self._config.alibaba_token,
            "dall-e": self._config.openai_token,
            "pollinations": "",  # 免费，无需 token
            "comfyui": "",  # 本地 ComfyUI，无需 token
        }
        return mapping.get(provider, "")

    def get_image_api_host(self) -> str:
        """获取图片生成 API Host（支持拆分架构）"""
        provider = self._config.image_api_provider

        # 拆分 Token 时使用拆分 Host
        if provider == "minimax" and self._config.minimax_token_image:
            return self._config.minimax_api_host_image

        # 默认使用 minimax host
        return self._config.image_api_url_minimax

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
            "image_parallel": self._config.image_parallel,
            "api_timeout_sec": self._config.api_timeout_sec,
            "api_max_retries": self._config.api_max_retries,
            "api_log_enabled": self._config.api_log_enabled,
        }

    def __repr__(self):
        return f"<ConfigManager: provider={self._config.image_api_provider}>"
