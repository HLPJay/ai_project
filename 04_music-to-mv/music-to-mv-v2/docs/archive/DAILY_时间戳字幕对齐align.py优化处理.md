主要围绕你的 align.py 歌词时间轴对齐模块做了完整分析、迭代修复和策略设计。下面是总结。

1. 项目目标

你的项目不是要让 Whisper 输出“准确歌词”，而是：

lyrics.txt = 权威原始歌词
Demucs 人声分离 + Whisper = 提供人声时间锚点
最终 song.srt = 用 ASR 时间戳挂载原始歌词文本

所以核心目标是：

文本以原始歌词为准
时间尽量来自人声 ASR
ASR 文本可以错，但时间锚点要尽量利用
2. 最初发现的问题

你上传了原始 align.py，我分析后发现几个核心逻辑风险：

强制逐行匹配

旧逻辑倾向于：

一行歌词 ↔ 一个 ASR segment

但歌曲场景里经常是：

一个 ASR segment 包含多行歌词
多个 ASR segment 组成一行歌词
副歌重复
Whisper 漏识别或合并段落

所以单行匹配会导致错位。

低分也会消耗 ASR 段

旧逻辑即使相似度很低，也会把当前歌词行标记为 matched，并消耗 ASR segment。结果是局部识别错误可能扩散成整首错位。

时间修复只修合法性，不修准确性

_repair_alignment_timeline() 可以让 SRT 时间不重叠，但如果前面匹配错了，它只会把错误时间线变得“格式合法”，不会变准确。

3. 关于 Whisper prompt 的讨论

你提到曾尝试用真实歌词构造 initial_prompt，但效果更差。

我们确认了原因：

Whisper initial_prompt 不是词库
它更像“前文上下文”
放太多真实歌词会让模型续写、跳过、 hallucinate

因此最终建议是：

initial_prompt="简体中文歌曲歌词转写。"

或者直接空字符串，不再塞完整歌词或大量关键词。

4. 第一轮核心改造：连续歌词块匹配

我们把对齐思路从：

ASR segment ↔ 单行歌词

改成：

ASR segment ↔ 连续歌词块

也就是一个 ASR 段可以匹配 1～4 行，后来又扩展成动态 1～8 行。

这样解决了你发现的“最后副歌缺失”问题。原先一整段副歌 ASR 可能只被匹配成最像的一句，导致副歌只剩一行；改成连续块后，可以把整段副歌拆成多行歌词。

5. 非歌词 ASR 片段过滤

你举例里出现了：

Zither Harp

这类内容不应该进入最终字幕。

我们讨论后明确：不能写死某个词，而要做通用过滤。

过滤对象包括：

instrumental / interlude / solo / music / backing track
乐器标签
制作信息
字幕信息
版权信息
明显非歌词的短英文标签

但也提醒了风险：不能把真实短英文歌词如 Baby、Oh yeah、I love you 误删。所以最终策略应是：

先尝试匹配歌词
匹配不上，再判断是否是明显非歌词
6. 第二轮问题：完整歌词行显示过快

你发现类似：

00:01:24,920 --> 00:01:25,269
星尘在指尖闪耀

00:01:25,299 --> 00:01:25,649
脉冲划破寂静

每行只有 0.35 秒左右。

我们分析认为，这是因为短 ASR segment 被直接分配给了完整歌词行。

于是加入了：

歌词行最小合理时长
歌词块总时长校验
候选匹配时长惩罚

避免完整中文歌词行被压到 0.3～0.5 秒。

7. 第三轮问题：新增时长限制后，中间字幕提前

加入时长约束后，你发现部分字幕提前。

我们分析出新的副作用：

短 segment 被拒绝
↓
这些歌词行没有 ASR 锚点
↓
进入插值
↓
插值可能把歌词放早

因此我们进一步调整策略：短 segment 不应该直接拒绝，而应该先尝试合并相邻 ASR 段。

8. 第三轮核心改造：相邻 ASR 段合并候选

改成：

当前 ASR segment
当前 + 下一个
当前 + 下两个
当前 + 下三个

形成一个更大的 ASR 时间区间，再拿这个区间去匹配连续歌词块。

这样解决：

单个短 segment 太短
但多个短 segment 合并后足够承载歌词块

避免短段被拒绝后导致插值提前。

9. 关于“大 gap 插值”的讨论

你提供了 星尘回响 示例，发现：

机械之心在跳动
代码编织的梦
赛博幽灵游走
在数字的迷宫

被放在 48s～59s 左右，看起来异常。

一开始我们判断可能是 ASR 没识别到对应时间戳，导致算法用前后锚点插值补出来。

随后你指出更准确的情况可能是：

中间其实有 ASR 内容和时间戳
只是 ASR 文本和真实歌词差距很大

于是我们把这类情况归类为：

weak ASR anchor

而不是 missing anchor。

10. 重要约束：歌词必然正确 + 人声分离降低风险

你补充了两个关键前提：

1. 原始 lyrics.txt 必然正确
2. ASR 是先做人声分离后再提取的

这改变了默认策略。

之前更偏保守：

低置信就跳过

后来调整为：

歌词完整优先
尽量使用 vocals ASR 的时间锚点
文本差但位置合理，也可以作为 weak anchor

因为最终字幕文本永远来自 lyrics.txt，ASR 文本只是用于找时间。

11. 最终策略：strong + weak sequential anchor

最终设计成多级匹配：

1. strong block match
   ASR 文本和歌词块相似度高，直接使用时间戳。

2. merged strong block match
   多个相邻 ASR 段合并后，与连续歌词块强匹配。

3. weak sequential anchor
   文本相似度低，但：
   - 来自 vocals ASR
   - 位置在当前歌词进度附近
   - 时间区间能承载歌词块
   - 不是明显非歌词
   → 使用它的时间戳，标记 low_confidence。

4. merged weak sequential anchor
   合并相邻 ASR 段后作为 weak anchor。

5. interpolation
   完全没有合适 ASR 锚点时才插值。

6. repeat block insertion
   重复副歌/乱序额外段仍然使用高阈值 strong match，不允许 weak match。
12. 为什么 weak anchor 只用于主顺序流程

我们明确了一个重要安全边界：

weak anchor 只用于当前歌词进度附近
不用于乱序副歌或重复段插入

原因是：

主顺序 weak match 风险较低，因为 lyrics.txt 是权威且顺序明确
乱序 weak match 风险较高，容易多插副歌或错插段落

所以最终策略是：

主流程可以 weak
重复/乱序必须 strong
13. 最终完整代码交付内容

我多次根据讨论生成了完整 align.py。最终版本包含这些关键能力：

保留原有 Demucs / Whisper / manual / auto / CLI 接口
重写 SimilarityScorer
重写 _align_manual
增加 ASR 合并候选
增加连续歌词块匹配
增加时长合理性约束
增加 weak sequential anchor
增加非歌词片段过滤
增加重复段保守插入
增加调试 alignment 信息

默认参数大致为：

LyricsAligner(
    threshold_1=0.42,
    threshold_2=0.35,
    search_window=10,
    max_gap_seconds=5.0,
    weak_anchor_threshold=0.18,
    weak_anchor_max_offset=1,
    enable_weak_anchor=True,
)
14. 调试信息设计

为了后续定位问题，最终建议返回 alignment 调试信息，不再返回空列表。

每条字幕可以看到：

{
    "text": "...",
    "start": 123.4,
    "end": 126.8,
    "score": 0.263,
    "_source": "weak_group",
    "_match_kind": "weak",
    "low_confidence": True,
    "_srt_idx": 7,
    "_srt_idx_end": 10,
    "_asr_text": "...",
    "_matched_block": "..."
}

这样可以判断字幕来自：

block
block_group
weak
weak_group
interpolate
repeat_block
uniform_fallback
15. 当前最终推荐理解

这套模块最终应该被理解为：

不是 ASR 转写歌词
而是歌词时间锚点对齐器

它的核心原则是：

歌词文本永远以 lyrics.txt 为准
ASR 文本只用于辅助匹配
ASR 时间戳尽量利用
短片段先合并再判断
长段按连续歌词块拆分
文本差但顺序合理时使用 weak anchor
完全没有锚点时才插值
重复副歌必须高置信

这就是我们整轮讨论逐步收敛出的通用策略。