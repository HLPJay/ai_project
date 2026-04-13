"""
报告生成模块
依赖：pip install openai
"""

import json
from openai import OpenAI


# ============================================================
# 配置
# ============================================================

DEEPSEEK_API_KEY = "sk-60b5e8791bc3430a9dc63d4019f566c6"   # ← 替换成你的 key


def get_client():
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )


# ============================================================
# 核心函数：生成报告
# ============================================================

def generate_report(transcript: str, title: str = "", channel: str = "") -> dict:
    """
    把字幕文本传给 DeepSeek，生成结构化报告

    参数：
      transcript - 字幕文本（来自 local_transcript.py 的输出）
      title      - 视频标题（可选，有助于提高报告质量）
      channel    - 频道名称（可选）

    返回：
    {
        'success': True/False,
        'core_thesis': '核心观点',
        'key_points': ['要点1', '要点2', ...],
        'conclusions': ['结论1', '结论2'],
        'target_audience': '适合人群',
        'watch_worthy': True/False,
        'reason': '值得/不值得看的原因',
        'error': None or '错误信息'
    }
    """

    # 字幕过短，没有分析价值
    if len(transcript) < 50:
        return {
            'success': False,
            'error': '字幕内容太短，无法生成有效报告'
        }

    # 字幕过长时截断（DeepSeek 支持 64K token，约 4 万汉字）
    # 超长内容应在上层做分段处理，这里只做简单保护
    max_chars = 30000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "...(内容已截断)"

    prompt = f"""你是一名专业的内容分析师。请分析以下视频的字幕内容，生成一份结构化报告。

视频信息：
- 标题：{title or '未知'}
- 频道：{channel or '未知'}

字幕内容：
{transcript}

请严格按照以下 JSON 格式返回，不要有任何其他文字、不要有 markdown 代码块：
{{
  "core_thesis": "视频的核心观点或主题，一句话概括",
  "key_points": [
    "关键要点1",
    "关键要点2",
    "关键要点3",
    "关键要点4",
    "关键要点5"
  ],
  "conclusions": [
    "主要结论1",
    "主要结论2"
  ],
  "target_audience": "这个视频最适合哪类人观看",
  "watch_worthy": true,
  "reason": "值得看或不值得看的具体原因"
}}"""

    client = get_client()

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,    # 低温度，让输出更稳定
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()

        # 解析 JSON
        try:
            data = json.loads(raw)
            data['success'] = True
            data['error'] = None
            return data
        except json.JSONDecodeError:
            # AI 没有严格按 JSON 输出，尝试提取
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                data['success'] = True
                data['error'] = None
                return data
            return {
                'success': False,
                'error': f'JSON 解析失败，原始输出：{raw[:200]}'
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e).splitlines()[0]
        }


# ============================================================
# 格式化输出（打印用）
# ============================================================

def print_report(report: dict):
    """把报告字典格式化打印出来"""
    if not report.get('success'):
        print(f"❌ 报告生成失败：{report.get('error')}")
        return

    worthy = "✅ 值得看" if report.get('watch_worthy') else "⏭️  可跳过"

    print("\n" + "=" * 55)
    print(f"【核心观点】")
    print(f"  {report.get('core_thesis', '-')}")

    print(f"\n【关键要点】")
    for i, point in enumerate(report.get('key_points', []), 1):
        print(f"  {i}. {point}")

    print(f"\n【主要结论】")
    for c in report.get('conclusions', []):
        print(f"  · {c}")

    print(f"\n【适合人群】")
    print(f"  {report.get('target_audience', '-')}")

    print(f"\n【是否值得看】{worthy}")
    print(f"  {report.get('reason', '-')}")
    print("=" * 55)


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":

    # 用一段示例字幕测试（不需要先跑转录）
    sample_transcript = """
    今天我们来聊一聊 Hermes Agent，这是 Nous Research 最新发布的开源 AI Agent 框架。
    和市面上其他 Agent 不同，Hermes 最核心的特点是它有一个内置的学习闭环。
    每次你完成一个任务，它会把成功的方法保存成一个可复用的技能，下次遇到类似任务直接调用。
    它支持部署在任何地方，从 5 美元的 VPS 到云端服务器，你可以通过 Telegram 随时和它对话。
    模型方面它是完全开放的，支持 OpenRouter 上的 200 多个模型，随时切换。
    和 OpenClaw 相比，Hermes 更强调自动化和自我进化，而 OpenClaw 更注重手动控制。
    总体来说，如果你想要一个越用越聪明的个人 AI 助手，Hermes 是目前最值得关注的开源选项。
    """

    print("测试报告生成...")
    report = generate_report(
        transcript=sample_transcript,
        title="Hermes Agent 深度介绍",
        channel="AI 技术频道"
    )

    print_report(report)
