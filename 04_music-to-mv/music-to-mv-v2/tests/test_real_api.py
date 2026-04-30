"""
test_real_api.py — 真实 API 调用测试

使用真实的 MINIMAX_TOKEN 调用 MiniMax 服务：
1. 歌词生成 API (MiniMax-M2.7)
2. 音乐生成 API (music-2.6)

使用方式：
  python3 tests/test_real_api.py          # 全流程（歌词+音乐）
  python3 tests/test_real_api.py lyrics   # 仅测试歌词
  python3 tests/test_real_api.py music    # 仅测试音乐（需已有歌词）
  python3 tests/test_real_api.py image    # 仅测试图片生成
  python3 tests/test_real_api.py all      # 测试全部
  python3 tests/test_real_api.py clean    # 清理输出
"""

import json
import os
import sys
import time
from pathlib import Path

# Windows GBK 编码兼容性
if sys.stdout.encoding and sys.stdout.encoding.upper() in ("GBK", "GB2312", "CP936"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CHECK = "[OK]"
CROSS = "[X]"
ARROW = " ->"


def test_lyrics_generation():
    """测试 MiniMax 歌词生成 API"""
    print("\n" + "=" * 55)
    print("  Step ①: 歌词生成 API 测试")
    print("=" * 55)
    print("")

    from src.llm.client import LLMClient
    from src.llm.logger import LLMLogger
    from src.llm.registry import PromptRegistry
    from src.config_manager import ConfigManager

    # 检查 Token
    cfg = ConfigManager()
    token = cfg.get("minimax_token", "")
    if not token:
        print("  [X] MINIMAX_TOKEN 未设置！")
        print(" 请运行: cd music-to-mv-v2; cp .env.example .env")
        print(" 然后在 .env 中填入你的 MINIMAX_TOKEN")
        return False

    print(f"  [OK] Token 已配置: {token[:12]}...{token[-8:]}")
    print("")

    # 准备日志目录
    log_dir = os.path.join(os.path.dirname(__file__), "..", "_test_api_output")
    os.makedirs(log_dir, exist_ok=True)
    logger = LLMLogger(log_dir)
    client = LLMClient(logger)
    registry = PromptRegistry()

    # 测试参数
    theme = "童年记忆"
    style = "动漫风"
    music_style = "民谣"
    mood = "怀旧"
    language = "中文"

    print(f"  主题: {theme}")
    print(f"  风格: {style}")
    print(f"  音乐风格: {music_style}")
    print(f"  情绪: {mood}")
    print(f"  语言: {language}")
    print("")

    # 1. 渲染 Prompt
    print("  [1/3] 渲染歌词 prompt...")
    try:
        prompt = registry.render("lyrics.generation", {
            "theme": theme,
            "style": style,
            "music_style": music_style,
            "mood": mood,
            "language": language,
        })
        print(f"      [OK] Prompt 渲染完成 ({len(prompt)} 字符)")
        print(f"      前200字: {prompt[:200]}...")
    except KeyError:
        print("      [!] 注册表渲染失败，使用 fallback prompt")
        prompt = (
            f"创作一首关于'{theme}'的歌，"
            f"风格：{style}，曲风：{music_style}，"
            f"情绪：{mood}，语言：{language}，"
            f"严格遵循标准歌曲结构：主歌1->副歌->主歌2->副歌->尾奏"
        )
    print("")

    # 2. 调用歌词 API
    print("  [2/3] 调用 MiniMax 歌词生成 API...")
    print("      (预计等待 10-30 秒)")
    print("")
    start = time.time()

    try:
        result = client.call_minimax_lyrics(prompt)

        song_title = result.get("song_title", "")
        lyrics = result.get("lyrics", "")
        style_tags = result.get("style_tags", "")

        elapsed = time.time() - start
        print(f"      [OK] 完成! ({elapsed:.1f}s)")
        print(f"")
        print(f"      歌曲名: {song_title}")
        print(f"      风格标签: {style_tags}")
        print(f"      歌词长度: {len(lyrics)} 字符")
        print(f"")

        # 显示歌词预览
        if lyrics:
            print("      ── 歌词预览 ──")
            for line in lyrics.split("\n")[:20]:
                print(f"        {line}")
            if lyrics.count("\n") > 20:
                print(f"        ... (共 {lyrics.count(chr(10)) + 1} 行)")
        else:
            print("      [!] 歌词为空")

    except Exception as e:
        elapsed = time.time() - start
        print(f"      [X] 失败 ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. 保存结果
    print("")
    print("  [3/3] 保存结果...")
    output_dir = Path(log_dir)
    lyrics_file = output_dir / "lyrics_result.txt"
    lyrics_content = (
        f"## {song_title or 'Untitled'}\n"
        f"## Tags: {style_tags or ''}\n"
        f"## Theme: {theme}\n"
        f"## Style: {style}\n"
        f"## Mood: {mood}\n"
        f"## Music: {music_style}\n\n"
        f"{lyrics}"
    )
    lyrics_file.write_text(lyrics_content, encoding="utf-8")
    print(f"      [OK] 已保存到: {lyrics_file}")

    # 保存完整响应
    raw_file = output_dir / "lyrics_response.json"
    raw_file.write_text(
        json.dumps(result.get("raw", result), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"      [OK] 原始响应: {raw_file}")
    print("")
    print(f"  [OK] 歌词生成测试完成!")

    # 同时输出统计
    print("")
    logger.print_summary()

    return True


def test_music_generation():
    """测试 MiniMax 音乐生成 API"""
    print("\n" + "=" * 55)
    print("  Step ②: 音乐生成 API 测试")
    print("=" * 55)
    print("")

    from src.llm.client import LLMClient
    from src.llm.logger import LLMLogger
    from src.config_manager import ConfigManager

    cfg = ConfigManager()
    token = cfg.get("minimax_token", "")
    if not token:
        print("  [X] MINIMAX_TOKEN 未设置！")
        return False

    print(f"  [OK] Token 已配置: {token[:12]}...{token[-8:]}")

    # 找歌词文件
    log_dir = Path(os.path.join(os.path.dirname(__file__), "..", "_test_api_output"))
    lyrics_file = log_dir / "lyrics_result.txt"

    if not lyrics_file.exists():
        print(f"\n  [!] 未找到歌词文件: {lyrics_file}")
        print("  先用测试歌词作为替代...")
        # 使用默认歌词
        lyrics_text = (
            "[Verse 1]\n"
            "还记得那片蓝天\n"
            "阳光洒在旧照片\n"
            "童年的笑声在耳边回荡\n"
            "那些日子永远难忘\n\n"
            "[Chorus]\n"
            "童年的梦在飞翔\n"
            "带着希望去远方\n"
            "不管风雨有多大\n"
            "心中有光就不怕\n\n"
            "[Verse 2]\n"
            "时光匆匆地流淌\n"
            "回忆珍藏在心上\n"
            "每个微笑都是最美的花\n"
            "陪你走过春秋冬夏\n\n"
            "[Chorus]\n"
            "童年的梦在飞翔\n"
            "带着希望去远方\n"
            "不管风雨有多大\n"
            "心中有光就不怕\n\n"
            "[Outro]\n"
            "童年的梦啊\n"
            "永远闪亮\n"
        )
    else:
        # 从文件读取，去掉注释行
        lines = lyrics_file.read_text(encoding="utf-8").splitlines()
        lyrics_text = "\n".join(
            line for line in lines
            if line.strip() and not line.startswith("## ")
        )

    print(f"\n  歌词长度: {len(lyrics_text)} 字符")
    print(f"  歌词行数: {lyrics_text.count(chr(10)) + 1}")
    print("")

    logger = LLMLogger(str(log_dir))
    client = LLMClient(logger)

    # 构建音乐 prompt
    music_prompt = "歌曲名：童年记忆，情绪：怀旧，音乐风格：民谣，主题：童年，演唱语言：中文，旋律流畅自然，节奏清晰，副歌抓耳，主歌舒缓，完整歌曲结构：主歌1 -> 副歌 -> 主歌2 -> 副歌 -> 尾奏"

    print("  调用 MiniMax 音乐生成 API...")
    print("  (预计等待 30-90 秒)")
    print("")
    start = time.time()

    try:
        result = client.call_minimax_music(music_prompt, lyrics_text)

        audio_hex = result.get("audio_hex", "")
        audio_bytes = result.get("audio_bytes", b"")

        elapsed = time.time() - start
        print(f"  [OK] 完成! ({elapsed:.1f}s)")

        if audio_bytes:
            output_file = log_dir / "generated_song.mp3"
            output_file.write_bytes(audio_bytes)
            file_size = output_file.stat().st_size / 1024 / 1024
            print(f"")
            print(f"  音频大小: {file_size:.1f} MB")
            print(f"  输出文件: {output_file}")

            # 用 ffprobe 获取时长
            try:
                import subprocess
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(output_file)],
                    capture_output=True, text=True, timeout=10
                )
                if probe.returncode == 0 and probe.stdout.strip():
                    duration = float(probe.stdout.strip())
                    print(f"  音频时长: {duration:.1f} 秒 ({duration/60:.1f} 分)")
            except Exception:
                pass
        else:
            print("  [!] 生成的音频数据为空")
            print(f"  原始响应: {json.dumps(result.get('raw', {}), ensure_ascii=False)[:500]}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"  [X] 失败 ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return False

    # 保存原始响应
    raw_file = log_dir / "music_response.json"
    raw_file.write_text(
        json.dumps(result.get("raw", result), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n  原始响应: {raw_file}")
    print("")
    print(f"  [OK] 音乐生成测试完成!")
    print("")
    logger.print_summary()
    return True


def test_image_generation():
    """测试图片生成 API（最耗时）"""
    print("\n" + "=" * 55)
    print("  Step ④: 图片生成 API 测试")
    print("=" * 55)
    print("")

    from src.llm.client import LLMClient
    from src.llm.logger import LLMLogger
    from src.config_manager import ConfigManager
    from src.style_map import build_char_prompt

    cfg = ConfigManager()
    token = cfg.get("minimax_token", "")
    if not token:
        print("  [X] MINIMAX_TOKEN 未设置！")
        return False

    print(f"  [OK] Token 已配置: {token[:12]}...{token[-8:]}")

    log_dir = Path(os.path.join(os.path.dirname(__file__), "..", "_test_api_output"))
    os.makedirs(str(log_dir), exist_ok=True)
    logger = LLMLogger(str(log_dir))
    client = LLMClient(logger)

    # 构建角色 prompt
    char_prompt = build_char_prompt(
        style_name="动漫风",
        theme="童年",
        song_title="童年记忆",
        mood="怀旧",
    )
    print(f"  角色 prompt: {char_prompt[:100]}...")
    print("")

    print("  调用 MiniMax 图片生成 API...")
    print("  (预计等待 20-60 秒)")
    print("")
    start = time.time()

    try:
        output_path = str(log_dir / "test_image.png")
        result_path = client.call_image_api(
            prompt=char_prompt,
            output_path=output_path,
            style="动漫风",
            provider="minimax",
        )

        elapsed = time.time() - start
        file_size = os.path.getsize(result_path) / 1024 / 1024
        print(f"  [OK] 完成! ({elapsed:.1f}s)")
        print(f"  输出: {result_path}")
        print(f"  大小: {file_size:.1f} MB")

    except Exception as e:
        elapsed = time.time() - start
        print(f"  [X] 失败 ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return False

    print("")
    print(f"  [OK] 图片生成测试完成!")
    logger.print_summary()
    return True


def clean_test_output():
    """清理测试输出"""
    log_dir = Path(os.path.join(os.path.dirname(__file__), "..", "_test_api_output"))
    if log_dir.exists():
        import shutil
        shutil.rmtree(str(log_dir))
        print("  已清理测试输出")


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  MiniMax 真实 API 调用测试")
    print("=" * 55)
    print("")

    tests = {
        "lyrics": ("歌词生成", test_lyrics_generation),
        "music": ("音乐生成", test_music_generation),
        "image": ("图片生成", test_image_generation),
    }

    # 仅运行指定测试
    args = [a.lower() for a in sys.argv[1:]] if len(sys.argv) > 1 else ["lyrics", "music"]

    if "clean" in args:
        clean_test_output()
        sys.exit(0)

    if "all" in args:
        args = ["lyrics", "music", "image"]

    results = {}
    for test_name in args:
        if test_name in tests:
            name, func = tests[test_name]
            print(f"\n   >> 测试: {name} << ")
            try:
                results[test_name] = func()
            except Exception as e:
                print(f"\n  [X] 未捕获异常: {e}")
                import traceback
                traceback.print_exc()
                results[test_name] = False

    # 汇总
    print("\n" + "=" * 55)
    print("  测试汇总")
    print("=" * 55)

    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    for name, ok in results.items():
        label = tests.get(name, [name, ""])[0]
        status = "[OK]" if ok else "[X]"
        print(f"  {status} {label}")

    print("")
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 55)
    print("")
    print(f"  输出目录: _test_api_output/")
    print("")

    sys.exit(0 if failed == 0 else 1)
