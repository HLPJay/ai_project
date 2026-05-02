"""
ComfyUI API smoke test for music-to-mv.

用法：
  1. 只检查 ComfyUI 服务是否可访问，并列出可用 checkpoint：
     python tools/test_comfyui_api.py --list-checkpoints

  2. 用项目内置 ComfyUI provider 生成一张测试图：
     python tools/test_comfyui_api.py --generate --checkpoint "juggernautXL_xxx.safetensors"

  3. 指定自定义 ComfyUI workflow（必须是 API format JSON）：
     python tools/test_comfyui_api.py --generate --workflow workflows/my_sdxl_api.json --checkpoint "xxx.safetensors"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path
from urllib import request as urllib_request


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="测试 ComfyUI API 是否可访问，并可通过项目 provider 生成一张图片。"
    )
    parser.add_argument("--url", default=os.environ.get("IMAGE_API_URL_COMFYUI", "http://127.0.0.1:8188"))
    parser.add_argument("--list-checkpoints", action="store_true", help="列出 ComfyUI 可见的 checkpoint")
    parser.add_argument("--generate", action="store_true", help="调用项目内置 comfyui provider 生成一张测试图")
    parser.add_argument("--checkpoint", default=os.environ.get("IMAGE_MODEL_COMFYUI", ""))
    parser.add_argument("--workflow", default=os.environ.get("COMFYUI_WORKFLOW", ""))
    parser.add_argument("--output", default=str(REPO_ROOT / ".reference_tests" / "comfyui_smoke.png"))
    parser.add_argument(
        "--prompt",
        default=(
            "a candid unedited phone photo of a steaming bowl of biangbiang noodles "
            "on a family kitchen table, warm ordinary home light, realistic texture"
        ),
    )
    parser.add_argument("--negative", default="low quality, blurry, distorted, text, watermark")
    return parser.parse_args()


def get_json(url: str) -> dict:
    with urllib_request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_checkpoints(base_url: str) -> list[str]:
    info = get_json(f"{base_url}/object_info/CheckpointLoaderSimple")
    ckpt = (
        info.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    return list(ckpt or [])


def main() -> int:
    args = parse_args()
    base_url = args.url.rstrip("/")

    print(f"ComfyUI URL: {base_url}")
    try:
        stats = get_json(f"{base_url}/system_stats")
        print("✅ /system_stats 可访问")
        devices = stats.get("devices") or []
        if devices:
            first = devices[0]
            print(f"设备: {first.get('name', 'unknown')} | vram_free={first.get('vram_free', 'unknown')}")
    except Exception as exc:
        print(f"❌ 无法访问 ComfyUI API: {exc}")
        print("请确认 ComfyUI 已启动，并且浏览器能打开该 URL。")
        return 1

    if args.list_checkpoints or args.generate:
        try:
            checkpoints = list_checkpoints(base_url)
            print(f"可用 checkpoint 数量: {len(checkpoints)}")
            for name in checkpoints[:30]:
                print(f"  - {name}")
            if len(checkpoints) > 30:
                print(f"  ... 还有 {len(checkpoints) - 30} 个")
        except Exception as exc:
            print(f"⚠️ 读取 checkpoint 列表失败: {exc}")

    if not args.generate:
        return 0

    if not args.checkpoint and not args.workflow:
        print("❌ 生成测试需要 --checkpoint，或提供 --workflow。")
        print("可先运行: python tools/test_comfyui_api.py --list-checkpoints")
        return 1

    os.environ["IMAGE_API_PROVIDER"] = "comfyui"
    os.environ["IMAGE_API_URL_COMFYUI"] = base_url
    if args.checkpoint:
        os.environ["IMAGE_MODEL_COMFYUI"] = args.checkpoint
    if args.workflow:
        os.environ["COMFYUI_WORKFLOW"] = args.workflow

    from src.llm.client import LLMClient

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    LLMClient().call_image_api(
        prompt=args.prompt,
        output_path=str(output),
        negative_prompt=args.negative,
        provider="comfyui",
        prompt_key="comfyui_smoke_test",
    )
    print(f"✅ 测试图已生成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
