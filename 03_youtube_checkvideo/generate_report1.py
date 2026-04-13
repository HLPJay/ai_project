"""
报告生成模块
依赖：pip install openai
"""

import json
from openai import OpenAI

DEEPSEEK_API_KEY = "sk-60b5e8791bc3430a9dc63d4019f566c6"

def get_client():
    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )


def _calc_points_count(word_count: int) -> int:
    """根据内容长度动态决定要点数量"""
    if word_count < 500:   return 3
    if word_count < 1500:  return 5
    if word_count < 3000:  return 7
    if word_count < 6000:  return 9
    return 12


def generate_report(transcript: str, title: str = "", channel: str = "") -> dict:
    """
    生成结构化报告

    返回字段：
      core_thesis     - 核心观点（一句话）
      key_points      - 关键要点列表（数量根据内容长度动态调整）
      detailed_notes  - 详细笔记（更完整的内容，分段落）
      conclusions     - 主要结论
      target_audience - 适合人群
      watch_worthy    - 是否值得看
      reason          - 值得/不值得看的原因
    """

    if len(transcript) < 100:
        return {'success': False, 'error': '内容太短，无法生成有效报告'}

    word_count = len(transcript.split())
    points_count = _calc_points_count(word_count)

    # 超长内容截断保护
    max_chars = 30000
    truncated = len(transcript) > max_chars
    if truncated:
        transcript = transcript[:max_chars] + "...(内容已截断)"

    prompt = f"""你是一名专业的内容分析师。请深度分析以下视频字幕，生成完整的结构化报告。

视频信息：
- 标题：{title or '未知'}
- 频道：{channel or '未知'}
- 内容长度：约 {word_count} 词{'（已截断）' if truncated else ''}

字幕内容：
{transcript}

请严格按 JSON 格式返回，不要有任何其他文字和 markdown 代码块：
{{
  "core_thesis": "视频最核心的一个观点，一句话，要精准",
  "key_points": [
    "要点1（重要程度最高的内容）",
    "要点2",
    ...（共 {points_count} 条，每条 20-50 字，覆盖视频主要内容，不要遗漏重要信息）
  ],
  "detailed_notes": [
    "段落1：对视频某个主题/章节的详细说明，100字左右",
    "段落2：另一个主题的详细说明",
    ...（2-4个段落，补充 key_points 未能覆盖的细节）
  ],
  "conclusions": [
    "结论1",
    "结论2"
  ],
  "target_audience": "最适合哪类人观看，具体描述",
  "watch_worthy": true,
  "reason": "值得看或不值得看的具体理由，30字内"
}}"""

    client = get_client()
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                return {'success': False, 'error': f'JSON 解析失败：{raw[:200]}'}

        data['success'] = True
        data['error'] = None
        data['word_count'] = word_count
        return data

    except Exception as e:
        return {'success': False, 'error': str(e).splitlines()[0]}


def print_report(report: dict):
    if not report.get('success'):
        print(f"❌ {report.get('error')}")
        return
    worthy = "✅ 值得看" if report.get('watch_worthy') else "⏭️  可跳过"
    print("\n" + "="*55)
    print(f"【核心观点】\n  {report.get('core_thesis','')}")
    print(f"\n【关键要点】（共{len(report.get('key_points',[]))}条）")
    for i, p in enumerate(report.get('key_points', []), 1):
        print(f"  {i:02d}. {p}")
    print(f"\n【详细笔记】")
    for p in report.get('detailed_notes', []):
        print(f"  · {p}")
    print(f"\n【主要结论】")
    for c in report.get('conclusions', []):
        print(f"  · {c}")
    print(f"\n【适合人群】\n  {report.get('target_audience','')}")
    print(f"\n【是否值得看】{worthy}")
    print(f"  {report.get('reason','')}")
    print("="*55)


if __name__ == "__main__":
    sample = """
    今天我们来聊一聊 Hermes Agent，这是 Nous Research 最新发布的开源 AI Agent 框架。
    和市面上其他 Agent 不同，Hermes 最核心的特点是它有一个内置的学习闭环。
    每次你完成一个任务，它会把成功的方法保存成一个可复用的技能，下次遇到类似任务直接调用。
    它支持部署在任何地方，从 5 美元的 VPS 到云端服务器，你可以通过 Telegram 随时和它对话。
    模型方面它是完全开放的，支持 OpenRouter 上的 200 多个模型，随时切换。
    和 OpenClaw 相比，Hermes 更强调自动化和自我进化，而 OpenClaw 更注重手动控制。
    总体来说，如果你想要一个越用越聪明的个人 AI 助手，Hermes 是目前最值得关注的开源选项。
    """
    report = generate_report(sample, title="Hermes Agent 深度介绍", channel="AI 技术频道")
    print_report(report)
