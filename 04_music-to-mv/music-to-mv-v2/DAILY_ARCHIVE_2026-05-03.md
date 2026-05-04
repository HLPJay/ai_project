# 2026-05-03 阶段修复归档

本次主要围绕 MV 生成链路里的字幕时间戳、ASR 对齐、场景提示词稳定性、图片生成续跑行为和关系类主题跑偏问题进行排查与修复。

## 1. 字幕时间戳整体漂移

代表项目：

- `给女朋友洗脚_疲惫一天后的温柔陪伴_20260503_163725`

现象：

- `audio/song.srt` 第一条字幕从 127s 左右才开始。
- 音频总时长约 141s，但最后字幕结束时间超过了音频时长。
- 视频前半段字幕缺失，后半段字幕整体错位。

根因：

- Whisper ASR 的真实时间戳本身可用，但旧的歌词对齐逻辑在“原歌词”和“ASR 文本”匹配时漂到了后面的重复段落。
- 旧逻辑缺少对“第一条字幕过晚”“字幕覆盖区间过窄”“字幕结束超过音频”等异常时间线的强检测。

修复：

- 在 `src/align.py` 中新增异常时间线检测：
  - 第一条字幕开始过晚。
  - 字幕整体覆盖范围过窄且偏后。
  - 局部字幕断层过大。
  - 最后一条字幕明显超过音频时长。
- 当检测到异常，并且 ASR 段落可用时，不再继续信任漂移后的逐行匹配结果，而是使用 ASR 段落时间戳重建 SRT。
- 最终字幕文本仍使用 `audio/lyrics.txt` 中的原始歌词，时间戳使用 ASR 的真实音频时间。

当前策略：

- 正常情况：`timeline_strategy = "asr_line_match"`
- 异常且 ASR 可用：`timeline_strategy = "asr_segment_rebuild"`
- ASR 不可用：`timeline_strategy = "uniform_timeline"`

## 2. 字幕局部大跳跃

代表项目：

- `童年的小事件_20260503_193005`

现象：

- `audio/song.srt` 前两句时间正常。
- 第三句突然跳到 79s 左右。
- 中间出现约 61.92s 的字幕断层。

根因：

- 旧版 `_filter_misrecognized_asr` 过滤过于激进。
- Whisper 识别出来的 ASR 文本虽然有少量错别字，但时间戳是连续的、可用的。
- 旧过滤逻辑按较高相似度阈值删除了大量“文本不完全一致但时间戳有价值”的 ASR 段落。
- 结果从 29 条 ASR 段落只剩 8 条，导致歌词匹配被迫跳到后面的重复段落。

修复：

- 放宽 ASR 过滤策略。
- 不再因为“ASR 文本和原歌词不够像”就删除大部分段落。
- 只过滤明显无用的 ASR 幻觉，例如：
  - 高 no-speech 概率的重复无意义内容。
  - 明显片头制作信息幻觉。
- 新增局部大断层检测。
- 检测到断层后，优先使用 ASR 段落时间戳重建字幕。

验证结果：

- 原始 ASR：29 条。
- 新过滤后 ASR：27 条。
- 只删除了两个明显无意义的开头幻觉段落。
- 修复后前几句字幕恢复为连续时间：
  - `11.92-14.82` 蝉鸣声在老街回响
  - `14.82-17.18` 阳光碎落一地金黄
  - `17.18-18.66` 巷口那棵老槐树
  - `18.66-23.50` 藏着多少旧时光

## 3. ASR 片头幻觉：编曲 李宗盛

代表项目：

- `月光下的思念_20260503_211547`

现象：

- 用户发现字幕或识别结果中出现 `编曲 李宗盛`。
- 但 `audio/lyrics.txt` 原始歌词中没有这句话。

根因：

- Whisper 在歌曲片头无明显人声或弱人声区域产生了幻觉识别。
- `temp/song.json` 中第一条 ASR 段落为：
  - `0.0-5.0 编曲 李宗盛`
- 真实第一句歌词大约从 15s 开始。
- 旧逻辑没有专门过滤这类制作人员信息幻觉，因此可能将其时间段用于字幕重建。

修复：

- 在 `src/align.py` 中新增 `_is_obvious_asr_hallucination(...)`。
- 对低覆盖度的制作信息类 ASR 进行过滤。
- 关键词包括：
  - `编曲`
  - `作曲`
  - `作词`
  - `演唱`
  - `原唱`
  - `制作人`
  - `出品`
  - `发行`
  - `字幕`
  - `词曲`

验证结果：

- 原始 ASR：44 条。
- 新过滤后 ASR：43 条。
- 被删除段落：`0.0-5.0 编曲 李宗盛`
- 第一条有效 ASR 从约 15s 开始。

## 4. 最后一条字幕被强行拉到音频末尾

现象：

- 歌曲尾奏或纯音乐段落中，最后一句歌词会一直挂在画面上。
- 容易造成“字幕和歌曲不对应”的观感。

根因：

- 旧逻辑会把最后一条字幕强制延长到音频结束附近。
- 对有尾奏、间奏、拖长音的歌曲不合理。

修复：

- 移除了“强制把最后字幕延伸到音频末尾”的逻辑。
- 现在最后字幕跟随 ASR 或对齐结果自然结束。
- 纯音乐尾奏不再默认显示最后一句歌词。

## 5. ASR、SRT 与原歌词的关系

当前链路：

- `temp/song.json`
  - Whisper ASR 识别结果。
  - 主要提供音频里的真实人声时间戳。
  - 文本可能有错别字、漏字、幻觉。

- `audio/lyrics.txt`
  - 歌词生成阶段得到的原始歌词。
  - 是最终字幕文本的标准来源。

- `audio/song.srt`
  - 最终字幕文件。
  - 理想状态是：文本来自原歌词，时间戳来自 ASR。

本次修复后的核心原则：

- 不直接相信 ASR 文本。
- 但尽量保留 ASR 时间戳。
- 当逐行匹配漂移时，用 ASR 段落时间戳重建字幕。

## 6. 当前仍存在的字幕精度限制

已修复：

- 字幕整体漂到后半段。
- 局部大跳跃。
- 片头制作信息幻觉。
- 最后一条字幕拖到尾奏。

仍可能存在：

- 个别字幕略快或略慢。
- 一句歌词内部的字级同步不精确。
- 多句歌词挤在一个 ASR 段落时，只能按段落时间近似拆分。
- 歌曲中有拖腔、间奏、重复副歌时，仍可能出现局部偏差。

原因：

- 当前是 ASR segment 级别对齐，不是 word/phoneme 级别强制对齐。
- Whisper 默认输出的是段级时间戳，不保证每一句原歌词都能精确到字。

后续更高精度方案：

- 引入 WhisperX、stable-ts、MFA、aeneas 等更细粒度强制对齐工具。
- 优先用 Demucs 分离人声后再做 ASR。
- 把 ASR 原文、原歌词、最终 SRT 的差异写入报告，方便人工复核。

## 7. 图片生成续跑与 Ken Burns 片段复用

代表项目：

- `童年的小事件_20260503_193005`

现象：

- 用户更换图片生成方式后重新执行：
  - `python -m src.main --project "<项目路径>" --phase produce --auto`
- 图片重新生成成功。
- 但最终视频看起来没有变化，或者仍像旧版本。

根因：

- 图片文件可以重新生成。
- 但 Ken Burns 阶段会跳过已经存在且文件大小有效的 `clips/seg*_scene_kb.mp4`。
- 因此最终视频可能仍复用旧视频片段。

当前处理方式：

- 如果要让新图片真正进入最终视频，需要先删除旧的 KB 片段：

```powershell
Remove-Item "C:\Users\yun68\.openclaw\workspace\mv\童年的小事件_20260503_193005\clips\*.mp4"
```

然后重新执行：

```powershell
python -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\童年的小事件_20260503_193005" --phase produce --auto
```

后续优化项：

- 增加 `--force-images`。
- 增加 `--force-clips`。
- 增加 `--force-produce`。
- 在报告中明确提示哪些图片、哪些 KB 片段被复用。

## 8. 关系类主题跑偏修复

代表主题：

- `给女朋友洗脚，疲惫一天后的温柔陪伴`

旧问题：

- 主题容易被误判成家庭、亲情或儿童画面。
- `电影感` 风格可能没有明确映射，导致风格兜底不稳定。
- 画面可能出现父母、孩子、老人或泛化人物，和“成年亲密关系照护”不一致。

修复方向：

- 在主题主体推断中提高关系类主题优先级。
- 增加关键词：
  - `女朋友`
  - `女友`
  - `男朋友`
  - `男友`
  - `伴侣`
  - `对象`
- 移除过宽泛的 `陪伴` 对家庭人物判断的影响。
- 增加 `电影感 -> 电影感写实风` 风格别名。
- 场景提示词明确成人、亲密关系、非性化、生活照护语义。
- 避免自动兜底到动漫儿童风。

## 9. 执行过程报告需求

用户期望：

- 项目执行完后，自动总结本次流水线过程。
- 报告应告诉用户：
  - 和大模型交互了多少次。
  - 哪些接口超时。
  - 哪些接口重试。
  - 哪些步骤失败或进入 fallback。
  - 最终使用的是 LLM 结果还是 local fallback。
  - 字幕对齐采用了哪种策略。

建议后续新增报告字段：

- `api_total_requests`
- `api_success_count`
- `api_failure_count`
- `api_retry_count`
- `api_timeout_count`
- `api_failure_reasons`
- `scene_desc_source`
- `variant_desc_source`
- `timeline_strategy`
- `timeline_fallback`
- `raw_asr_segments`
- `filtered_asr_segments`
- `removed_asr_segments`
- `max_subtitle_gap_sec`

## 10. 常用复测命令

重新跑字幕对齐：

```powershell
python -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\童年的小事件_20260503_193005" --phase align --auto
```

重新跑图片与视频生成：

```powershell
python -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\童年的小事件_20260503_193005" --phase produce --auto
```

重新跑导出：

```powershell
python -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\童年的小事件_20260503_193005" --phase export --auto
```

语法检查：

```powershell
python -m py_compile src\align.py src\pipeline.py
```

## 11. 本次修改过的关键文件

- `src/align.py`
  - ASR 过滤策略。
  - 异常字幕时间线检测。
  - ASR segment 时间线重建。
  - 去除最后字幕强制延长。

- `src/pipeline.py`
  - 将 `timeline_strategy` 写入项目元数据。

- `config/theme_reference_modes.json`
  - 关系类主题主体推断规则优化。

- `src/style_map.py`
  - 风格别名与关系类提示词优化。

- `src/scene_generator.py`
  - 主题参考图与场景图主体锚定优化。

- `src/scene_analyzer.py`
  - 场景分析提示词中的主题主体指导增强。

## 12. 后续待优化清单

- 为字幕对齐增加自动诊断报告。
- 为 `song.srt` 生成过程输出：
  - ASR 原始段落数。
  - 过滤后段落数。
  - 被删除的 ASR 片段。
  - 最大字幕断层。
  - 首字幕时间。
  - 末字幕时间。
  - 使用的对齐策略。
- 增加强制重生成参数，避免续跑时误用旧 KB 片段。
- 增加几个固定回归测试项目：
  - `童年的小事件`
  - `给女朋友洗脚`
  - `月光下的思念`
- 引入更细粒度 forced alignment 方案，提升字幕局部同步精度。
- 对繁简字、近音字、错别字做更稳的歌词匹配归一化。
- 将 API 超时、重试、fallback 信息写入最终 HTML 报告。

## 13. 2026-05-04 字幕对齐稳定性补充

本轮继续处理 Step③ 歌词对齐中的 ASR 崩溃和时间线漂移问题，最终确认已走通。

### 13.1 现象

代表项目：

- `母亲的温度_20260504_184427`
- `朋友的陪伴_20260503_231332`

运行命令：

```powershell
python -X utf8 -u -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\母亲的温度_20260504_184427" --phase align --auto
```

日志中可以看到：

```text
faster-whisper medium (cuda, compute_type=int8_float16, beam=5, vad=False)...
[OK] faster-whisper medium (cuda): 21 段
```

但进程随后直接退出，`$LASTEXITCODE` 为：

```text
-1073740791
```

这个退出码不是普通 Python 异常，而是 Windows native crash。Python 的 `try/except` 无法捕获。

### 13.2 根因判断

这次不是 CPU/GPU 选择错误。日志已经明确显示：

```text
faster-whisper medium (cuda)
```

说明：

- ASR 后端是 `faster-whisper`
- 设备是 `cuda`
- GPU 推理已经成功返回了 ASR 段落

崩溃发生在 `[OK] faster-whisper ...` 之后，判断为：

- `faster-whisper / ctranslate2 / CUDA DLL` 在推理结束、释放资源、写缓存或退出阶段发生 native crash。
- 这类问题会直接杀掉主 Python 进程。
- 因此主流程来不及写入 `temp/song.json`、`audio/song.srt`，也来不及把 `metadata/status.json` 从 `running` 改为 `failed`。

### 13.3 环境差异确认

用户对比了两个环境：

当前 MV 项目环境：

```text
ctranslate2     4.7.1
faster-whisper  1.2.1
torch           2.6.0+cu124
```

另一个视频分析环境：

```text
ctranslate2     4.7.1
faster-whisper  1.2.1
torch           2.11.0
```

结论：

- `faster-whisper` 和 `ctranslate2` 版本一致。
- `faster-whisper` 主要依赖 `ctranslate2`，不是主要依赖 `torch`。
- `torch` 差异主要影响 `demucs` 和 `openai-whisper`，不是本次 faster-whisper ASR 的核心差异。
- 本次崩溃更像 CTranslate2/CUDA native crash，而不是 Python 包普通异常。

### 13.4 修复方案

核心修复方向：

```text
把 faster-whisper 放到独立子进程中执行
```

新增文件：

- `src/align_asr_worker.py`

作用：

- 独立加载 `faster-whisper`
- 独立执行 ASR 转写
- 将结果写入临时 JSON
- 主进程读取 JSON 后继续歌词同步

这样即使 `ctranslate2 / CUDA DLL` 在 worker 进程退出时 native crash，也不会把主 MV 流水线进程一起杀掉。

### 13.5 当前配置

`.env` 和 `.env.example` 已增加/使用：

```env
ALIGN_ASR_BACKEND=faster-whisper
ALIGN_WHISPER_COMPUTE_TYPE=float16
ALIGN_WHISPER_BEAM_SIZE=5
ALIGN_WHISPER_VAD_FILTER=true
ALIGN_WHISPER_WORD_TIMESTAMPS=false
```

遇到 8G 显存或 CUDA 稳定性问题时，推荐：

```env
ALIGN_WHISPER_MODEL=small
ALIGN_WHISPER_FALLBACK_MODELS=base,tiny
ALIGN_WHISPER_COMPUTE_TYPE=int8_float16
```

### 13.6 最终验证结果

用户复测后反馈：

- 暂时没有再遇到崩溃。
- 字幕时间线正常。
- `metadata/info.json` 中出现：

```text
timeline_strategy = asr_native_sync
```

这说明当前正确逻辑已生效：

```text
faster-whisper 识别真实人声时间线
↓
保留 ASR 原生时间戳
↓
按顺序同步原始歌词文本
↓
生成 song.srt
```

### 13.7 当前结论

本轮问题标记为：

```text
已修复，继续观察
```

已闭环内容：

- ASR 后端切换到 `faster-whisper`
- GPU 路径确认生效：`cuda`
- 原生时间线同步策略生效：`asr_native_sync`
- Windows native crash 通过 worker 子进程隔离规避
- 字幕大幅漂移问题暂未复现

仍属于后续优化的问题：

- 个别字幕局部快慢仍可能存在，这属于词级/字级 forced alignment 精度问题。
- 后续可继续引入 WhisperX、stable-ts、MFA、aeneas 等更细粒度对齐方案。
- 建议把 worker exit code、stderr、临时 JSON 路径、ASR 后端、模型、compute type 写入最终 HTML 报告。
