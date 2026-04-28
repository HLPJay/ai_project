#!/usr/bin/env python3
"""
call_image_api.py — 通用图片生成 API 调用
支持 minimax / alibaba / dall-e / pollinations
支持 style 参数和 negative prompt（style_map.py 数据驱动）

用法:
  python3 call_image_api.py <prompt> <output_path> [--provider NAME] [--model NAME] [--style STYLE] [--negative NEGPROMPT]

环境变量:
  IMAGE_API_PROVIDER   minimax | alibaba | dall-e | pollinations
  MINIMAX_TOKEN       MiniMax API key
  ALIBABA_TOKEN        阿里云 API key
  OPENAI_TOKEN         OpenAI API key
  IMAGE_STYLE          MiniMax API style 参数
  IMAGE_NEGATIVE       全局 Negative Prompt
  IMAGE_API_URL        API endpoint（可选）
  IMAGE_MODEL          模型名（可选）
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import time
# 日志记录器（延迟导入避免循环依赖）
_img_logger = None
def _get_img_logger():
    global _img_logger
    if _img_logger is None:
        try:
            from llm_logger import log_llm as _f
            _img_logger = _f
        except ImportError:
            _img_logger = lambda *a, **k: None
    return _img_logger

def _urlopen_with_retry(url_or_req, max_retries=3):
    """Open URL/Request with exponential-backoff retry."""
    delays = [5, 10, 20]
    for attempt in range(max_retries):
        try:
            return urllib.request.urlopen(url_or_req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == max_retries - 1:
                raise
            print(f"   HTTP {e.code}, retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"   Request failed ({e}), retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])

def _download_file(url, output_path, max_retries=3):
    """Download file with retry, using urlopen with explicit timeout."""
    delays = [5, 10, 20]
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(output_path, "wb") as f:
                    f.write(resp.read())
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"   Download failed ({e}), retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])


def call_minimax(prompt, output_path, project_dir=None, style='', negative_prompt='', seed=0):
    token = os.environ.get("MINIMAX_TOKEN", "").strip()
    if not token:
        raise ValueError("MINIMAX_TOKEN 环境变量未设置")

    api_url = os.environ.get("IMAGE_API_URL", "https://api.minimaxi.com/v1/image_generation")
    model = os.environ.get("IMAGE_MODEL", "image-01")
    style_val = style or os.environ.get("IMAGE_STYLE", "")
    neg_val = negative_prompt or os.environ.get("IMAGE_NEGATIVE", "")
    seed_val = seed or int(os.environ.get("IMAGE_SEED", "0"))

    extra = {}
    if neg_val:
        extra["prompt_negative"] = neg_val
    if seed_val:
        extra["seed"] = seed_val

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "aspect_ratio": "16:9",
        **extra
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        api_url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )

    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    data_obj = data.get("data") or {}
    img_url = data_obj.get("image_urls", [""])[0] if isinstance(data_obj, dict) else ""
    if not img_url:
        # 检查是否是参数错误
        err = data.get("base_resp", {}).get("status_msg", "")
        err_code = data.get("base_resp", {}).get("status_code", 0)
        raise ValueError(f"MiniMax 图片生成失败: status_code={err_code}, msg={err}, params={payload.decode()[:100]}")
    _download_file(img_url, output_path)
    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "MiniMax", prompt, {"size": os.path.getsize(output_path)})
    return True


def call_alibaba(prompt, output_path, project_dir=None, negative_prompt='', seed=0):
    token = os.environ.get("ALIBABA_TOKEN", "").strip()
    if not token:
        raise ValueError("ALIBABA_TOKEN 环境变量未设置")

    api_url = os.environ.get("IMAGE_API_URL_ALIBABA",
                            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis")
    model = os.environ.get("IMAGE_MODEL_ALIBABA", "wan2.2-t2i-plus")
    neg_val = negative_prompt or os.environ.get("IMAGE_NEGATIVE", "")
    seed_val = seed or int(os.environ.get("IMAGE_SEED", "0"))

    params = {
        "size": "1024*1024",
        "n": 1
    }
    if seed_val:
        params["seed"] = seed_val
    if neg_val:
        params["negative_prompt"] = neg_val

    payload = json.dumps({
        "model": model,
        "input": {"prompt": prompt},
        "parameters": params
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        api_url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )

    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    results = data.get("output", {}).get("results", [])
    if not results or not results[0].get("url"):
        raise ValueError(f"阿里云返回无图片链接: {data}")

    img_url = results[0]["url"]
    _download_file(img_url, output_path)
    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "Alibaba", prompt, {"size": os.path.getsize(output_path)})
    return True


def call_dalle(prompt, output_path, project_dir=None):
    token = os.environ.get("OPENAI_TOKEN", "").strip()
    if not token:
        raise ValueError("OPENAI_TOKEN 环境变量未设置")

    api_url = os.environ.get("IMAGE_API_URL_DALLE",
                             "https://api.openai.com/v1/images/generations")
    model = os.environ.get("IMAGE_MODEL_DALLE", "dall-e-3")

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        api_url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )

    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    img_data = data.get("data", [])
    if not img_data or not img_data[0].get("url"):
        raise ValueError(f"DALL-E 返回无图片链接: {data}")

    img_url = img_data[0]["url"]
    _download_file(img_url, output_path)
    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "DALL-E", prompt, {"size": os.path.getsize(output_path)})
    return True



def call_pollinations(prompt, output_path, project_dir=None, negative_prompt='', seed=0):
    """免费无密钥图片生成，无需API Key"""
    base = "https://image.pollinations.ai/prompt"
    escaped_prompt = urllib.parse.quote(prompt)
    url = f"{base}/{escaped_prompt}?width=1280&height=720&model=flux&n=1"

    if negative_prompt:
        url += f"&negative={urllib.parse.quote(negative_prompt)}"
    if seed > 0:
        url += f"&seed={seed}"

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    req = urllib.request.Request(url, headers=headers)

    with _urlopen_with_retry(req) as resp:
        with open(output_path, 'wb') as f:
            f.write(resp.read())


    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "Pollinations", prompt, {"size": os.path.getsize(output_path)})
    return True


def main():
    parser = argparse.ArgumentParser(description="通用图片生成API调用")
    parser.add_argument("prompt", help="图片描述 prompt")
    parser.add_argument("output", help="输出文件路径")
    parser.add_argument("--provider", default=None, help="覆盖 IMAGE_API_PROVIDER")
    parser.add_argument("--model", default=None, help="覆盖 IMAGE_MODEL")
    parser.add_argument("--style", default="", help="MiniMax API style 参数")
    parser.add_argument("--seed", type=int, default=0, help="固定 seed 提高角色一致性")
    parser.add_argument("--negative", default="", help="Negative prompt")
    args = parser.parse_args()

    # 覆盖配置
    provider = args.provider or os.environ.get("IMAGE_API_PROVIDER", "minimax")
    if args.model:
        os.environ["IMAGE_MODEL"] = args.model
    if args.style:
        os.environ["IMAGE_STYLE"] = args.style
    if args.negative:
        os.environ["IMAGE_NEGATIVE"] = args.negative

    # 禁用代理
    os.environ["no_proxy"] = "*"
    os.environ["NO_PROXY"] = "*"

    try:
        if provider == "alibaba":
            call_alibaba(args.prompt, args.output, project_dir=None, negative_prompt=args.negative, seed=args.seed)
        elif provider == "dall-e":
            call_dalle(args.prompt, args.output, project_dir=None)
        elif provider == "pollinations":
            call_pollinations(args.prompt, args.output, project_dir=None, negative_prompt=args.negative, seed=args.seed)
        else:
            call_minimax(args.prompt, args.output, project_dir=None, style=args.style, negative_prompt=args.negative, seed=args.seed)

        # 输出成功信息
        size_kb = os.path.getsize(args.output) // 1024
        print(f"✅ 生成成功: {args.output} ({size_kb} KB)")

    except Exception as e:
        print(f"❌ 错误: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()