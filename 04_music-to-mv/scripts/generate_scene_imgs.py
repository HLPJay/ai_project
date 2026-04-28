#!/usr/bin/env python3
"""
generate_scene_imgs.py — 并行生成场景图

支持多图片 API（通过环境变量配置）：
  minimax      - MiniMax image-01（默认，需要 MINIMAX_TOKEN）
  pollinations - Pollinations AI 免费（无需 token，flux/sdxl 模型）
  dall-e       - OpenAI DALL-E 3（需要 OPENAI_TOKEN）

用法: python3 generate_scene_imgs.py <project_dir> [--parallel N]

依赖:
  MINIMAX_TOKEN 或 OPENAI_TOKEN（取决于 IMAGE_API_PROVIDER）
  source config.sh 可自动设置（config.sh 读 .env 文件）
"""

import argparse
import json
import os
import sys
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
    """Download file with retry and timeout."""
    delays = [10, 20, 40]
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(output_path, 'wb') as f:
                    f.write(resp.read())
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"   Download failed ({e}), retry {attempt+1}/{max_retries} in {delays[attempt]}s...")
            time.sleep(delays[attempt])

import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── API 配置（从环境变量读取，默认值兼容 minimax）────────────
MINIMAX_TOKEN = os.environ.get("MINIMAX_TOKEN", "")
OPENAI_TOKEN = os.environ.get("OPENAI_TOKEN", "")
ALIBABA_TOKEN = os.environ.get("ALIBABA_TOKEN", "")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")

IMAGE_API_PROVIDER = os.environ.get("IMAGE_API_PROVIDER", "minimax").lower()

# MiniMax（默认）
MINIMAX_API_BASE = os.environ.get("MINIMAX_API_HOST", "https://api.minimaxi.com")
IMAGE_API_URL_MINIMAX = os.environ.get(
    "IMAGE_API_URL_MINIMAX",
    f"{MINIMAX_API_BASE}/v1/image_generation"
)
IMAGE_MODEL_MINIMAX = os.environ.get("IMAGE_MODEL_MINIMAX", "image-01")

# Pollinations（免费）
IMAGE_API_URL_POL = os.environ.get(
    "IMAGE_API_URL_POLLINATIONS",
    "https://image.pollinations.ai"
)
IMAGE_MODEL_POL = os.environ.get("IMAGE_MODEL_POLLINATIONS", "flux")

# DALL-E 3
IMAGE_API_URL_DALLE = os.environ.get(
    "IMAGE_API_URL_DALLE",
    "https://api.openai.com/v1/images/generations"
)
IMAGE_MODEL_DALLE = os.environ.get("IMAGE_MODEL_DALLE", "dall-e-3")

# Alibaba Cloud（通义万通）
IMAGE_API_URL_ALIBABA = os.environ.get(
    "IMAGE_API_URL_ALIBABA",
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
)
IMAGE_MODEL_ALIBABA = os.environ.get("IMAGE_MODEL_ALIBABA", "wanx2.1-t2i-plus")

MAX_RETRY = 3
RETRY_DELAY = 2


def call_minimax(prompt, output_path, project_dir=None, style='', negative_prompt='', seed=0):
    """调用 MiniMax Image-01"""
    style_val = style or os.environ.get("IMAGE_STYLE", "")
    neg_val = negative_prompt or os.environ.get("IMAGE_NEGATIVE", "")
    extra = {}
    seed_val = seed or int(os.environ.get("IMAGE_SEED", "0"))
    aspect_val = os.environ.get("IMAGE_ASPECT_RATIO", "16:9")
    if seed_val:
        extra["seed"] = seed_val
    if style_val:
        # MiniMax image-01 不支持大部分 style 值，跳过以免 invalid params
        # prompt 中已通过 art_style 描述风格
        pass
    if neg_val:
        extra["prompt_negative"] = neg_val
    payload = json.dumps({
        "model": IMAGE_MODEL_MINIMAX,
        "prompt": prompt,
        "aspect_ratio": aspect_val,
        **extra
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        IMAGE_API_URL_MINIMAX,
        data=payload,
        headers={
            "Authorization": f"Bearer {MINIMAX_TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST",
    )
    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    if "image_urls" in data.get("data", {}):
        img_url = data["data"]["image_urls"][0]
        _download_file(img_url, output_path)
        _log = _get_img_logger()
        if _log and project_dir:
            _log(project_dir, "scene_img", "MiniMax", prompt,
                 {"size": os.path.getsize(output_path), "style": style_val, "aspect": aspect_val})
        return os.path.getsize(output_path) > 1000
    return False


def call_pollinations(prompt, output_path, project_dir=None, negative_prompt='', seed=0):
    """调用 Pollinations AI（免费，无需 auth）"""
    escaped_prompt = urllib.parse.quote(prompt)
    url = f"{IMAGE_API_URL_POL}/prompt/{escaped_prompt}?width=1280&height=720&model=flux&n=1"
    neg_val = negative_prompt or os.environ.get("IMAGE_NEGATIVE", "")
    if neg_val:
        url += f"&negative={urllib.parse.quote(neg_val)}"
    seed_val = seed or int(os.environ.get("IMAGE_SEED", "0"))
    if seed_val:
        url += f"&seed={seed_val}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with _urlopen_with_retry(req) as resp:
        with open(output_path, 'wb') as f:
            f.write(resp.read())
    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "Pollinations", prompt, {"size": os.path.getsize(output_path)})
    return os.path.getsize(output_path) > 1000


def call_dalle(prompt, output_path, project_dir=None):
    """调用 OpenAI DALL-E 3"""
    payload = json.dumps({
        "model": IMAGE_MODEL_DALLE,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        IMAGE_API_URL_DALLE,
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST",
    )
    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    if "data" in data and len(data["data"]) > 0:
        img_url = data["data"][0].get("url", "")
        if img_url:
            _download_file(img_url, output_path)
            _log = _get_img_logger()
            if _log and project_dir:
                _log(project_dir, "scene_img", "DALL-E", prompt, {"size": os.path.getsize(output_path)})
            return os.path.getsize(output_path) > 1000
    return False


def call_alibaba(prompt, output_path, project_dir=None, negative_prompt='', seed=0):
    """调用阿里云通义万通图像生成（wan2.2-t2i-plus）"""
    neg_val = negative_prompt or os.environ.get("IMAGE_NEGATIVE", "")
    params = {"size": "1024*1024", "n": 1}
    seed_val = seed or int(os.environ.get("IMAGE_SEED", "0"))
    if seed_val:
        params["seed"] = seed_val
    if neg_val:
        params["negative_prompt"] = neg_val
    payload = json.dumps({
        "model": os.environ.get("IMAGE_MODEL_ALIBABA", "wan2.2-t2i-plus"),
        "input": {"prompt": prompt},
        "parameters": params
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        IMAGE_API_URL_ALIBABA,
        data=payload,
        headers={
            "Authorization": f"Bearer {ALIBABA_TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST",
    )
    with _urlopen_with_retry(req) as resp:
        data = json.loads(resp.read())

    # wan2.2-t2i-plus response: output.results[0].url
    api_results = data.get("output", {}).get("results", [])
    result_size = 0
    success = False
    if api_results and api_results[0].get("url"):
        img_url = api_results[0]["url"]
        # 下载加 60s timeout，防止大图卡死
        with _urlopen_with_retry(img_url) as resp:
            with open(output_path, 'wb') as f:
                f.write(resp.read())
        # 验证文件头（PNG: 89 50 4E 47, JPEG: FF D8 FF）
        try:
            with open(output_path, 'rb') as f:
                magic = f.read(4)
            if magic[:4] == b'\x89PNG' or magic[:3] == b'\xff\xd8\xff':
                result_size = os.path.getsize(output_path)
                success = result_size > 500000  # 500KB 阈值
        except Exception:
            success = False
    _log = _get_img_logger()
    if _log and project_dir:
        _log(project_dir, "scene_img", "Alibaba", prompt, {"size": result_size})
    return success


def generate_scene_image(sid, label, desc, char_prompt, art_style, output_png,
                         mood_desc="", api_style="", negative_prompt="", seed=0,
                         project_dir=None):
    """调用配置的图片 API 生成单张场景图，带重试"""
    mood_section = f", {mood_desc}" if mood_desc else ""
    full_prompt = f"{char_prompt}, {desc}, {art_style}{mood_section}"

    for attempt in range(1, MAX_RETRY + 1):
        try:
            if IMAGE_API_PROVIDER == "pollinations":
                ok = call_pollinations(full_prompt, output_png, project_dir=project_dir, negative_prompt=negative_prompt, seed=seed)
            elif IMAGE_API_PROVIDER == "dall-e":
                ok = call_dalle(full_prompt, output_png, project_dir)
            elif IMAGE_API_PROVIDER == "alibaba":
                ok = call_alibaba(full_prompt, output_png, project_dir=project_dir, negative_prompt=negative_prompt, seed=seed)
            else:  # minimax (default)
                ok = call_minimax(full_prompt, output_png, project_dir=project_dir, style=api_style, negative_prompt=negative_prompt, seed=seed)

            if ok:
                size = os.path.getsize(output_png)
                _log = _get_img_logger()
                if _log and project_dir:
                    _log(project_dir, "scene_img", IMAGE_API_PROVIDER.upper(),
                         full_prompt, {"size": size, "sid": sid, "attempt": attempt})
                return {"sid": sid, "status": "ok", "size": size, "attempt": attempt}
            raise ValueError(f"Provider {IMAGE_API_PROVIDER} returned invalid result")

        except Exception as e:
            err_msg = str(e)
            if attempt == MAX_RETRY:
                return {"sid": sid, "status": "failed", "error": err_msg, "attempt": attempt}
            print(f"   ⚠️ attempt {attempt} failed ({err_msg}), retrying...")
            time.sleep(RETRY_DELAY * attempt)

    return {"sid": sid, "status": "failed", "error": "unknown", "attempt": MAX_RETRY}


def main():
    # 显示当前 API 配置（不泄露 token）
    print(f"🖼️  Image API: {IMAGE_API_PROVIDER.upper()}")
    if IMAGE_API_PROVIDER == "minimax":
        print(f"   URL: {IMAGE_API_URL_MINIMAX}")
        print(f"   Model: {IMAGE_MODEL_MINIMAX}")
    elif IMAGE_API_PROVIDER == "pollinations":
        print(f"   URL: {IMAGE_API_URL_POL}")
        print(f"   Model: {IMAGE_MODEL_POL} (free, no token)")
    elif IMAGE_API_PROVIDER == "dall-e":
        print(f"   URL: {IMAGE_API_URL_DALLE}")
        print(f"   Model: {IMAGE_MODEL_DALLE}")
    elif IMAGE_API_PROVIDER == "alibaba":
        print(f"   URL: {IMAGE_API_URL_ALIBABA}")
        print(f"   Model: {os.environ.get("IMAGE_MODEL","")} (阿里云通义万通)")

    parser = argparse.ArgumentParser(description="并行生成场景图")
    parser.add_argument("project_dir", help="项目目录")
    parser.add_argument("-j", "--parallel", type=int, default=2, help="并发数（默认2）")
    args = parser.parse_args()

    proj = Path(args.project_dir)
    scenes_json = proj / "metadata" / "scenes.json"
    base_char_json = proj / "metadata" / "base_char.json"
    images_dir = proj / "images"
    clips_dir = proj / "clips"
    images_dir.mkdir(exist_ok=True)
    clips_dir.mkdir(exist_ok=True)

    # 读取项目中固定 seed（角色一致性）
    info_json = proj / "metadata" / "info.json"
    image_seed = 0
    if info_json.exists():
        image_seed = json.loads(info_json.read_text()).get("image_seed", 0)

    # 从 style_map 读取角色、风格、情绪、API 参数
    char_prompt = ""
    art_style = ""
    mood_desc = ""
    api_style = ""
    negative_prompt = ""
    if base_char_json.exists():
        from style_map import ART_STYLES, get_mood_desc, get_api_style, get_negative_prompt
        bc = json.loads(base_char_json.read_text())
        char_prompt = bc.get("prompt", "")
        style = bc.get("style", "儿童插画风")
        mood = bc.get("mood", "欢快")
        art_style = ART_STYLES.get(style, "illustration style, soft warm colors, heartwarming")
        mood_desc = get_mood_desc(mood)
        api_style = get_api_style(style, IMAGE_API_PROVIDER)
        negative_prompt = get_negative_prompt(style)

    # 读取场景配置
    scenes = json.loads(scenes_json.read_text())
    print(f"📋 {len(scenes)} 个场景，并发数={args.parallel}")

    # ── 分析需要变体图的场景 ──────────────────────────────────
    VARIANT_THRESHOLD = 4  # 秒，超过此阈值且重复场景生成变体（4s 以上重复段需要多张图避免单调）
    variants_map = {}       # {sid: num_variants}
    all_tasks = []         # [(scene_dict, variant_idx, output_path)]

    for s in scenes:
        sid = s["id"]
        dur = s.get("duration", 0)
        is_rep = s.get("is_repeated", False)

        # 变体数量：优先用 scenes.json 的 variants[]，否则用公式
        scene_variants = s.get('variants', [])
        n_variants = 1
        if isinstance(scene_variants, list) and scene_variants:
            n_variants = len(scene_variants) + 1
            variants_map[sid] = n_variants
        elif is_rep and dur > VARIANT_THRESHOLD:
            n_variants = max(2, min(3, -(-int(dur) // 5)))  # ceiling division
            variants_map[sid] = n_variants

        # 为主图和每个变体都创建任务
        for vi in range(n_variants):
            if vi == 0:
                out_path = images_dir / f"seg{sid}_scene.png"
            else:
                out_path = images_dir / f"seg{sid}_variant{vi}.png"

            # 幂等：已有且大小正常则跳过
            if out_path.exists() and os.path.getsize(out_path) > 500000:
                continue
            # desc from scenes.json (AI-generated variant desc, or main desc)
            if vi == 0:
                desc = s.get('desc', '')
            else:
                desc = scene_variants[vi - 1] if vi - 1 < len(scene_variants) else s.get('desc', '')
            all_tasks.append((s, vi, desc, str(out_path)))

    skipped_ids = set()
    for s, vi, desc, out_path in all_tasks:
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            skipped_ids.add(s["id"])
    skipped = sorted(skipped_ids)

    print(f"⏭️  跳过（已存在）: {skipped}")
    if not all_tasks:
        print("✅ 全部场景图已存在，无需生成")
        if variants_map:
            _write_variants_json(proj, variants_map)
        return

    print(f"🎨 生成中: {len(all_tasks)} 张图片")

    # ── 并行生成 ─────────────────────────────────────────────
    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {}
        for s, vi, desc, out_path in all_tasks:
            def submit_task(_s=s, _vi=vi, _desc=desc, _out=out_path):
                return generate_scene_image(
                    _s["id"], _s.get("label", ""), _desc,
                    char_prompt, art_style, _out, mood_desc,
                    api_style, negative_prompt, image_seed,
                    project_dir=args.project_dir
                )
            future = executor.submit(submit_task)
            futures[future] = (s["id"], vi)

        for future in as_completed(futures):
            sid, vi = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {"sid": sid, "status": "failed", "error": str(e)}

            # 统一 result 格式：确保是 dict 且有 status 字段
            if not isinstance(result, dict) or 'status' not in result:
                result = {"sid": sid, "status": "failed", "error": f"invalid: {type(result).__name__}"}

            results.append(result)
            status = "✅" if result.get("status") == "ok" else "❌"
            size_kb = result.get("size", 0) // 1024
            tag = f"var{vi}" if vi > 0 else ""
            err = f" ({result.get('error','')})" if result.get("status") != "ok" else ""
            print(f"   {status} scene {sid}{tag}: {result.get('status','?')} ({size_kb}KB){err}")

    ok = sum(1 for r in results if r.get("status") == "ok")
    fail = len(results) - ok
    total = len(results)
    print(f"\n🎨 场景图完成: {ok}/{total} 成功 ({fail} 失败)")

    # 写入 variants.json（供 KB 步骤 crossfade 使用）
    if variants_map:
        _write_variants_json(proj, variants_map)


def _write_variants_json(proj, variants_map):
    """写入 variants.json，记录每个场景的变体数量"""
    variants_path = proj / "metadata" / "variants.json"
    import json
    variants_path.write_text(json.dumps({"variant_scenes": variants_map}, ensure_ascii=False, indent=2))
    print(f"📦 变体图配置已写入: {variants_path}")


if __name__ == "__main__":
    os.environ["no_proxy"] = "*"
    main()
