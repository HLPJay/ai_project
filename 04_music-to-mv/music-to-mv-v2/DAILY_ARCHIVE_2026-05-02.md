# 2026-05-02 项目问题处理归档

## 总览

今天主要围绕 `music-to-mv-v2` 的自动 MV 生成链路做稳定性、可观测性和风格表达优化。核心问题集中在 Step ③.5 场景分析阶段：大模型生成场景 prompt、视觉总纲和重复副歌变体时，容易出现超时、`<think>`/reasoning 输出过长、JSON 解析失败以及局部 fallback。另一个重点是主题主体识别和摄影风格体系，尤其是“奶奶做的油泼面”这种亲情人物 + 食物主体 + 生活纪实复合主题。

处理后的方向是：主场景描述更稳定，变体描述有独立超时和极简重试，执行过程有总结报告，摄影类风格扩展为更明确的可选项。

---

## 1. 主题主体识别与复合主题

### 问题

“奶奶做的油泼面”最初只被识别为 `family_person`，系统会更偏“奶奶/亲情人物”，没有把“油泼面”作为强食物主体处理。这样会导致主参考图和场景 prompt 可能偏人像、厨房氛围，而不是清楚表现油泼面。

### 原因

`config/theme_reference_modes.json` 里原本有“汤面、面条、拉面”等关键词，但没有具体菜名“油泼面”。同时场景分析阶段原先只取最高优先级主体类型，不支持 `family_person + food_subject` 这种复合主题。

### 处理

- 在 `config/theme_reference_modes.json` 中补充：
  - `油泼面`
  - `臊子面`
  - `炸酱面`
  - `牛肉面`
- 在 `src/scene_analyzer.py` 增加复合主题识别：
  - `奶奶做的油泼面` 现在可识别为 `["family_person", "food_subject"]`
- 场景分析 prompt 会同时加入：
  - `EMOTIONAL SUBJECT`：奶奶、长辈、家庭记忆、手部动作、厨房生活细节
  - `FOOD ANCHOR`：面条、辣椒油、热油光泽、热气、碗、桌面、灶台、食材

### 效果

同一个主题现在不会只偏人物，也不会只偏食物，而是把“奶奶的情感记忆”和“油泼面的视觉主体”同时纳入画面约束。

---

## 2. `scene_desc_batch` 超时、thinking 与 JSON 解析

### 问题

日志中多次出现：

```text
finish_reason=length
reasoning_content 很长
content 为空或 JSON 不完整
[LLM batch descs] 解析失败，使用 local fallback
```

或者：

```text
TimeoutError: The read operation timed out
```

### 原因

MiniMax-M2.7 是偏 reasoning 的模型。即使 prompt 明确要求 `Return JSON only`，模型仍可能先产生大量 reasoning。复杂主题下，比如“奶奶 + 油泼面 + 手机原片 + 未修图 + 民谣 + 温柔”，模型需要同时平衡人物、食物、风格和情绪，推理时间变长，输出 JSON 被截断或请求超时。

### 处理

`scene_desc_batch` 已做稳定性增强：

- 独立配置：
  - `SCENE_DESC_API_MAX_RETRIES=3`
  - `SCENE_DESC_API_BASE_DELAY_SEC=2`
  - `SCENE_DESC_API_TIMEOUT_SEC=120`
- 请求参数加入：
  - `temperature=0.2`
  - `reasoning_split=True`
- 加入 `scene_desc_batch_compact` 极简重试：
  - 主请求被 `<think>`、`finish_reason=length` 或解析失败影响时，自动用更短 prompt 再请求一次
- `.env` 中已把：
  - `SCENE_DESC_BATCH_SIZE=1`
  - `SCENE_DESC_MAX_TOKENS=4096`

### 当前理解

如果日志中第一次请求超时，但第二次成功：

```text
attempt=1/3 failed
attempt=2/3 success
```

这不是最终失败，而是自动重试生效。

---

## 3. `variant_desc_batch` 变体描述稳定性

### 问题

重复副歌或长场景的变体描述经常出现：

```text
variant_desc_batch timeout=60.0s
TimeoutError: The read operation timed out
[LLM batch variants] 失败
```

### 业务含义

`variant_desc_batch` 不是主场景分析，而是给重复段/副歌补充变体图提示词。它的目标是让重复歌词不使用完全相同画面，而是在相同语义下变化镜头、动作、光线、前景或构图。

例如主场景是：

```text
辣椒面铺在面上，热油即将浇下
```

变体可以是：

```text
奶奶的手从侧逆光角度浇热油，红亮辣椒面升起蒸汽
```

### 原因

变体请求之前仍然吃通用配置：

```text
API_TIMEOUT_SEC=60
```

并且没有 `reasoning_split`、低温度、极简重试。对 MiniMax-M2.7 来说，变体规则又很多：不能改主题、不能改身份、不能改时代、要选择变化轴、要输出 JSON，所以容易超时。

### 处理

新增独立变体 API 配置：

```env
VARIANT_API_MAX_RETRIES=3
VARIANT_API_BASE_DELAY_SEC=2
VARIANT_API_TIMEOUT_SEC=120
VARIANT_DESC_BATCH_SIZE=1
```

代码中改为：

```python
RetryConfig.for_profile("variant")
```

并在 `variant_desc_batch` payload 加入：

```json
{
  "temperature": 0.2,
  "reasoning_split": true
}
```

新增 `variant_desc_batch_compact` 极简重试。当原始变体请求超时、截断或解析失败时，自动使用更短 prompt 重试。

同时收紧 `prompts/image/shot_variants_v1.txt`：

- 变体描述从 `26-40` 词缩短为 `16-28` 词
- 简化变化轴描述
- 输出结构只保留必要字段

---

## 4. 执行过程总结报告

### 需求

希望项目执行完后，能总结：

- 内部哪些交互超时
- 是否有错误
- 总共和大模型交互多少次
- 错误原因是什么
- 哪些请求最慢

### 处理

扩展 `src/report_generator.py` 和 `src/llm/logger.py`。

新增产物：

```text
metadata/execution_summary.json
output/execution_summary.json
output/llm_report.html
```

`execution_summary.json` 会统计：

- `api_calls`：API/LLM 总调用数
- `success` / `failed`
- `timeouts`
- `avg_latency_ms` / `max_latency_ms`
- `finish_reason_length`
- `reasoning_only_responses`
- `by_prompt_key`
- `top_errors`
- `slow_calls`
- `notes`

HTML 报告 `output/llm_report.html` 顶部新增“执行过程摘要”，不用翻 JSON 也能看出哪里慢、哪里失败、错误原因是什么。

### 细节

为了报告准确，`LLMLogger` 的 `calls.jsonl` 和完整 response 文件现在会记录：

```json
{
  "status": "success|failed",
  "error": "..."
}
```

这样失败原因不会只存在于 `errors.jsonl`，也能被主报告聚合。

---

## 5. 摄影/纪实风格扩展

### 问题

用户想要“类似手机直接拍出的没有修过图的照片”，但原来的 `写实摄影风` 偏精修写实：

```text
golden hour soft light
shallow depth of field
muted realistic color grading
clean environment
cinematic white balance
low noise
no clutter
```

这些词更接近商业摄影或电影感，不适合“手机原片、未修图、生活抓拍”。

### 处理

在 `src/style_map.py` 中新增 7 个摄影/纪实类风格：

```text
手机纪实摄影
家庭DV风
美食纪实摄影
街头纪实摄影
新闻纪实摄影
宝丽来快照风
黑白纪实摄影
```

推荐使用方式：

```powershell
python -m src.main --theme "奶奶做的油泼面" --style "手机纪实摄影" --music-style "民谣" --mood "温柔"
```

如果更强调食物：

```powershell
python -m src.main --theme "奶奶做的油泼面" --style "美食纪实摄影" --music-style "民谣" --mood "温柔"
```

如果更强调家庭录像和记忆：

```powershell
python -m src.main --theme "奶奶做的油泼面" --style "家庭DV风" --music-style "民谣" --mood "怀旧"
```

### 文档

`README.md` 已更新为 19 种画面风格，`python -m src.main --options` 会自动列出新增风格。

---

## 6. 场景拆分策略进入待优化项

### 问题

当前完整歌曲的场景切分主要由本地规则完成：

- SRT 歌词行数
- 总时长
- 重复歌词
- 最短间隔

大模型只负责对已切好的场景写视觉描述，不参与决定哪里应该合并、哪里应该单独成场。

这对自动化稳定，但不够“导演化”。例如“奶奶做的油泼面”更适合按故事推进：

```text
老屋开场 -> 灶台 -> 揉面 -> 泼油 -> 端碗 -> 回忆 -> 情感收束
```

### 归档到 Roadmap

已在 `OPTIMIZATION_ROADMAP.md` 增加：

```text
#19 scene_analyzer.py — LLM 辅助导演式场景切分
```

方案：

1. 本地生成安全候选切分
2. LLM 做导演式合并/命名/叙事功能标注
3. 本地校验时间轴、覆盖率、不重叠、不乱序
4. 失败回退本地规则

验收标准包括：

- 所有 SRT 行必须覆盖一次
- 场景时间不重叠
- LLM 输出失败自动 fallback
- 对叙事主题、古诗意境、动物冒险、食物记忆等主题，场景名称和 dramatic_function 更贴合主题推进

---

## 7. 今日重点结论

### 已解决或增强

- 复合主题识别：`奶奶做的油泼面` 可同时识别亲情人物和食物主体。
- 主场景描述稳定性：`scene_desc_batch` 有独立超时、reasoning_split 和 compact 重试。
- 变体描述稳定性：`variant_desc_batch` 新增独立超时、reasoning_split、低温度、compact 重试。
- 执行总结报告：新增 `execution_summary.json` 和 HTML 顶部摘要。
- 摄影风格扩展：新增 7 个纪实/摄影类风格。
- 待优化项归档：加入 LLM 辅助导演式场景切分。

### 仍需观察

- MiniMax-M2.7 仍可能在复杂主题下产生很长 reasoning，导致偶发超时或 `finish_reason=length`。
- `visual_bible` 目前也可能带 `<think>`，虽然多数情况下能解析成功，后续可考虑同样加入独立 profile 和 compact retry。
- 如果追求更快速度，后续应考虑把 `variant_desc_batch` 部分完全改成本地规则生成，减少不必要 LLM 调用。
- “手机原片感”最好直接使用 `手机纪实摄影`，不要再把“手机随手拍、未修图”塞进很长的 theme，避免主题字段承担风格职责。

---

## 8. 建议下一步

1. 用新风格重跑小样：

```powershell
python -m src.main --theme "奶奶做的油泼面" --style "手机纪实摄影" --music-style "民谣" --mood "温柔" --test-reference prompt
```

2. 如果 prompt 满意，再跑完整流程。

3. 跑完后查看：

```text
output/execution_summary.json
output/llm_report.html
```

4. 如果仍发现变体描述慢，可以考虑把重复段变体改成本地规则，不再请求 LLM。

