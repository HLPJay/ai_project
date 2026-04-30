"""
client.py — 统一 LLM API 客户端

封装所有 LLM/API 调用，包括：
- 请求构建
- 重试机制（指数退避）
- 响应验证
- Token 计数（估算）
- 自动日志记录

用法：
    client = LLMClient()
    result = client.call(
        prompt_key="lyrics.generation",
        prompt="创作一首关于春天的歌...",
        model="MiniMax-M2.7",
    )
"""

import json
import os
import time
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from src.llm.logger import LLMLogger, LLMCallRecord


class RetryConfig:
    """重试配置"""
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0,
                 max_delay: float = 30.0, request_timeout: float = 60.0,
                 retryable_status: set = None):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.request_timeout = request_timeout
        self.retryable_status = retryable_status or {429, 500, 502, 503, 504}


class LLMClient:
    """统一 LLM API 客户端（线程安全）

    支持三种 logger 获取方式（按优先级）：
      1. 显式传入: LLMClient(logger=my_logger)
      2. project_dir 自动创建: LLMClient(project_dir="/path/to/project")
      3. 全局单例（懒加载，共享 LLMLogger 实例）
    """

    _global_lock = threading.Lock()
    _global_logger_instance = None

    def __init__(self, logger: LLMLogger = None, project_dir: str = None):
        self._lock = threading.Lock()
        # 禁用代理（仅第一次设置）
        if "no_proxy" not in os.environ:
            os.environ["no_proxy"] = "*"
        if "NO_PROXY" not in os.environ:
            os.environ["NO_PROXY"] = "*"
        # 解析 logger
        self.logger = self._resolve_logger(logger, project_dir)

    def _resolve_logger(self, logger: Optional[LLMLogger],
                        project_dir: Optional[str]) -> Optional[LLMLogger]:
        """按优先级解析 logger"""
        # 优先级 1: 显式传入的 logger 实例
        if logger is not None:
            return logger
        # 优先级 2: project_dir 自动创建
        if project_dir:
            return LLMLogger(project_dir)
        # 优先级 3: 全局单例（懒加载）
        with self._global_lock:
            if self._global_logger_instance is None:
                try:
                    from src.config_manager import ConfigManager
                    cfg = ConfigManager()
                    root = cfg.get("WORKSPACE_ROOT", "")
                    if root:
                        self._global_logger_instance = LLMLogger(root)
                except Exception:
                    pass
        return self._global_logger_instance

    # ── MiniMax LLM ──────────────────────────────────────

    def call_minimax_llm(self, prompt: str, model: str = "MiniMax-M2.7",
                         system_prompt: str = None, max_tokens: int = 4096,
                         temperature: float = 0.7, retry_config: RetryConfig = None,
                         prompt_key: str = "llm_call") -> str:
        """调用 MiniMax LLM（OpenAI 兼容接口），返回文本内容"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()

        token = cfg.get("minimax_token", "")
        if not token:
            raise ValueError("MINIMAX_TOKEN 未设置")

        api_url = "https://api.minimaxi.com/v1/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        resp_data = self._call_raw_api(api_url, data, headers, prompt_key,
                                       model, prompt, retry_config)

        return resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

    # ── MiniMax 歌词 API ─────────────────────────────────

    def call_minimax_lyrics(self, prompt: str, model: str = "MiniMax-M2.7",
                            retry_config: RetryConfig = None) -> Dict:
        """调用 MiniMax 歌词生成 API"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()
        token = cfg.get("minimax_token", "")

        api_url = "https://api.minimaxi.com/v1/lyrics_generation"

        payload = json.dumps({
            "mode": "write_full_song",
            "prompt": prompt
        }, ensure_ascii=False).encode("utf-8")

        resp_data = self._call_raw_api(
            url=api_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            prompt_key="lyrics_generation",
            model=model,
            prompt_text=prompt,
            retry_config=retry_config,
        )

        return {
            "song_title": resp_data.get("song_title", ""),
            "style_tags": resp_data.get("style_tags", ""),
            "lyrics": resp_data.get("lyrics", ""),
            "raw": resp_data,
        }

    # ── MiniMax 音乐 API ─────────────────────────────────

    def call_minimax_music(self, prompt: str, lyrics: str,
                           model: str = "music-2.6",
                           retry_config: RetryConfig = None) -> Dict:
        """调用 MiniMax 音乐生成 API"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()
        token = cfg.get("minimax_token", "")

        api_url = "https://api.minimaxi.com/v1/music_generation"

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "lyrics": lyrics,
            "is_instrumental": False
        }, ensure_ascii=False).encode("utf-8")

        resp_data = self._call_raw_api(
            url=api_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            prompt_key="music_generation",
            model=model,
            prompt_text=prompt,
            retry_config=retry_config,
        )

        audio_hex = resp_data.get("data", {}).get("audio", "")
        return {
            "audio_hex": audio_hex,
            "audio_bytes": bytes.fromhex(audio_hex) if audio_hex else b"",
            "raw": resp_data,
        }

    # ── 图片生成 API ─────────────────────────────────────

    def call_image_api(self, prompt: str, output_path: str,
                       style: str = "", negative_prompt: str = "",
                       seed: int = 0, provider: str = None,
                       prompt_key: str = "image_generation") -> str:
        """通用图片生成，支持多个 Provider"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()

        provider = provider or cfg.get("image_api_provider", "minimax")

        if provider == "minimax":
            return self._call_minimax_image(prompt, output_path, style,
                                           negative_prompt, seed, prompt_key)
        elif provider == "alibaba":
            return self._call_alibaba_image(prompt, output_path, negative_prompt, seed, prompt_key)
        elif provider == "pollinations":
            return self._call_pollinations_image(prompt, output_path, negative_prompt, seed, prompt_key)
        elif provider == "dall-e":
            return self._call_dalle_image(prompt, output_path, prompt_key)
        else:
            raise ValueError(f"Unknown image provider: {provider}")

    def _call_minimax_image(self, prompt: str, output_path: str,
                            style: str = "", negative_prompt: str = "",
                            seed: int = 0, prompt_key: str = "image_generation") -> str:
        """调用 MiniMax 图片生成 API"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()
        token = cfg.get("minimax_token", "")
        api_url = cfg.get_image_api_url()
        model = cfg.get_image_model()

        extra = {}
        if negative_prompt:
            extra["prompt_negative"] = negative_prompt
        if seed:
            extra["seed"] = seed

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "aspect_ratio": "16:9",
            **extra
        }, ensure_ascii=False).encode("utf-8")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp_data = self._call_raw_api(api_url, payload, headers, prompt_key,
                                       f"MiniMax-{model}", prompt)

        data_obj = resp_data.get("data") or {}
        img_url = ""
        if isinstance(data_obj, dict):
            img_url = data_obj.get("image_urls", [""])[0] if data_obj.get("image_urls") else ""
        if not img_url:
            err = resp_data.get("base_resp", {}).get("status_msg", "Unknown error")
            raise ValueError(f"MiniMax 图片生成失败: {err}")

        self._download_file(img_url, output_path)
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        self._log_image_call(prompt_key, f"MiniMax-{model}", prompt, output_path, file_size)
        return output_path

    def _call_alibaba_image(self, prompt: str, output_path: str,
                            negative_prompt: str = "", seed: int = 0,
                            prompt_key: str = "image_generation") -> str:
        """调用阿里云通义万相图片生成 API"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()
        token = cfg.get("alibaba_token", "")
        api_url = cfg.get("image_api_url_alibaba")
        model = cfg.get("image_model_alibaba")

        params = {"size": "1024*1024", "n": 1}
        if seed:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        payload = json.dumps({
            "model": model,
            "input": {"prompt": prompt},
            "parameters": params
        }, ensure_ascii=False).encode("utf-8")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp_data = self._call_raw_api(api_url, payload, headers, prompt_key,
                                       f"Alibaba-{model}", prompt)

        results = resp_data.get("output", {}).get("results", [])
        if not results or not results[0].get("url"):
            raise ValueError(f"阿里云返回无图片链接: {resp_data}")

        img_url = results[0]["url"]
        self._download_file(img_url, output_path)
        file_size = os.path.getsize(output_path)
        self._log_image_call(prompt_key, f"Alibaba-{model}", prompt, output_path, file_size)
        return output_path

    def _call_pollinations_image(self, prompt: str, output_path: str,
                                 negative_prompt: str = "", seed: int = 0,
                                 prompt_key: str = "image_generation") -> str:
        """调用 Pollinations 免费图片 API"""
        base = "https://image.pollinations.ai/prompt"
        escaped = urllib.parse.quote(prompt)
        url = f"{base}/{escaped}?width=1280&height=720&model=flux&n=1"
        if negative_prompt:
            url += f"&negative={urllib.parse.quote(negative_prompt)}"
        if seed > 0:
            url += f"&seed={seed}"

        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib_request.Request(url, headers=headers)
        with self._urlopen_with_retry(req) as resp:
            with open(output_path, "wb") as f:
                f.write(resp.read())

        file_size = os.path.getsize(output_path)
        self._log_image_call(prompt_key, "Pollinations", prompt, output_path, file_size)
        return output_path

    def _call_dalle_image(self, prompt: str, output_path: str,
                          prompt_key: str = "image_generation") -> str:
        """调用 OpenAI DALL-E API"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()
        token = cfg.get("openai_token", "")
        api_url = cfg.get("image_api_url_dalle", "https://api.openai.com/v1/images/generations")
        model = cfg.get("image_model_dalle", "dall-e-3")

        payload = json.dumps({
            "model": model, "prompt": prompt,
            "size": "1024x1024", "n": 1
        }, ensure_ascii=False).encode("utf-8")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp_data = self._call_raw_api(api_url, payload, headers, prompt_key,
                                       f"DALL-E-{model}", prompt)

        img_data = resp_data.get("data", [])
        if not img_data or not img_data[0].get("url"):
            raise ValueError(f"DALL-E 返回无图片链接: {resp_data}")

        img_url = img_data[0]["url"]
        self._download_file(img_url, output_path)
        file_size = os.path.getsize(output_path)
        self._log_image_call(prompt_key, f"DALL-E-{model}", prompt, output_path, file_size)
        return output_path

    # ── 下载辅助 ─────────────────────────────────────────

    def _download_file(self, url: str, output_path: str, max_retries: int = 3):
        """下载文件到本地"""
        delays = [5, 10, 20]
        for attempt in range(max_retries):
            try:
                req = urllib_request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib_request.urlopen(req, timeout=60) as resp:
                    with open(output_path, "wb") as f:
                        f.write(resp.read())
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"   Download failed ({e}), retry {attempt+1}/{max_retries}")
                time.sleep(delays[attempt])

    def _urlopen_with_retry(self, req, max_retries: int = 3):
        """以指数退避重试打开 URL"""
        delays = [5, 10, 20]
        for attempt in range(max_retries):
            try:
                return urllib_request.urlopen(req, timeout=60)
            except HTTPError as e:
                if e.code < 500 or attempt == max_retries - 1:
                    raise
                print(f"   HTTP {e.code}, retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
                time.sleep(delays[attempt])
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"   Request failed ({e}), retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
                time.sleep(delays[attempt])

    # ── 通用 API 调用 ────────────────────────────────────

    def _call_api(self, url: str, payload: Dict, headers: Dict,
                  prompt_key: str, model: str, prompt_text: str,
                  retry_config: RetryConfig = None) -> Any:
        """通用 API 调用（JSON payload）"""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._call_raw_api(url, data, headers, prompt_key, model,
                                  prompt_text, retry_config)

    def _call_raw_api(self, url: str, data: bytes, headers: Dict,
                      prompt_key: str, model: str, prompt_text: str,
                      retry_config: RetryConfig = None,
                      request_timeout: float = None) -> Dict:
        """原始 API 调用（带重试，带日志）

        Args:
            request_timeout: 单次请求超时秒数，None 则从 retry_config 获取
        """
        cfg = retry_config or RetryConfig()
        timeout = request_timeout if request_timeout is not None else cfg.request_timeout
        last_error = None
        start_time = time.time()

        for attempt in range(1, cfg.max_retries + 1):
            try:
                req = urllib_request.Request(
                    url, data=data,
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib_request.urlopen(req, timeout=timeout) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))

                latency = (time.time() - start_time) * 1000

                # 记录成功
                self._log_call(prompt_key, model, prompt_text, response_data,
                              latency=latency)

                return response_data

            except HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                body = e.read().decode("utf-8", errors="replace")[:200]
                if body:
                    last_error += f" ({body})"
                if e.code not in cfg.retryable_status:
                    break

            except (URLError, ConnectionError, TimeoutError) as e:
                last_error = f"{type(e).__name__}: {e}"

            if attempt < cfg.max_retries:
                delay = min(cfg.base_delay * (2 ** (attempt - 1)), cfg.max_delay)
                print(f"  [{prompt_key}] 尝试 {attempt}/{cfg.max_retries} 失败，"
                      f"{delay:.0f}s 后重试... 错误: {last_error}")
                time.sleep(delay)

        # 记录失败
        latency = (time.time() - start_time) * 1000
        self._log_call(prompt_key, model, prompt_text, None,
                      error=last_error, latency=latency)

        raise RuntimeError(
            f"[{prompt_key}] API 调用失败 ({cfg.max_retries}/{cfg.max_retries}): "
            f"{last_error}"
        )

    # ── 日志记录 ─────────────────────────────────────────

    def _log_call(self, prompt_key: str, model: str, prompt_text: str,
                  response: Any, error: str = None,
                  latency: float = 0):
        """记录调用到 LLMLogger"""
        if not self.logger:
            return

        record = LLMCallRecord(
            timestamp=datetime.now(timezone.utc),
            prompt_key=prompt_key,
            model=model,
            rendered_prompt=prompt_text[:1000],
            status="failed" if error else "success",
            error=error,
            latency_ms=latency,
        )

        if response:
            record.response = json.dumps(response, ensure_ascii=False)[:2000]
            record.tokens = self._estimate_tokens(prompt_text, response)

        self.logger.record_call(record)

    def _log_image_call(self, prompt_key: str, model: str, prompt: str,
                        output_path: str, file_size: int):
        """记录图片生成调用"""
        if self.logger:
            self.logger.log_image_call(prompt_key, model, prompt, output_path, file_size)

    @staticmethod
    def _estimate_tokens(prompt: str, response: Any) -> Dict:
        """估算 token 数量（粗略估算，Char/1.3 ≈ token）"""
        resp_str = json.dumps(response, ensure_ascii=False) if response else ""
        return {
            "prompt_tokens": int(len(prompt) / 1.3),
            "completion_tokens": int(len(resp_str) / 1.3),
            "total_tokens": int((len(prompt) + len(resp_str)) / 1.3),
        }
