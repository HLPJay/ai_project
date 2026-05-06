# 2026-05-06 归档：项目全面审查、产品化讨论、日志 Bug 修复

> 本次归档涵盖：项目代码审查与问题分类、config_manager 测试场景设计、
> 产品展示策略与 demo 命令集、运行日志分析（思念_20260506_031628.log）及对应 Bug 修复。

---

## 1. 项目全面审查

### 1.1 整体结论

代码整体无功能性 Bug，均为优化/安全/可维护性问题。

> **整体评分：7.5/10**（代码组织 8、错误处理 6.5、文档 8、安全 4、测试 7、性能 6.5）

### 1.2 问题分类

**需用户在平台侧处理（非代码问题）**

| 问题 | 紧急程度 |
|------|---------|
| 吊销并重新生成泄露的 MINIMAX_TOKEN（.env 已进入 git 历史） | 立即 |
| 用 BFG 或 git filter-branch 清除 git 历史中的 token | 立即 |
| 添加 pre-commit hook（detect-secrets）防止再次误提交 | 高 |
| pip freeze 生成依赖锁定文件 | 中 |
| README 补充故障排查章节 | 低 |

**需 Claude 在代码侧处理**

| 问题 | 优先级 |
|------|--------|
| 提取共享工具函数（retry 逻辑、`_safe_json_dumps`、路径处理）| 中 |
| 硬编码常量移入 config_manager（VARIANT_THRESHOLD、MIN_IMAGE_SIZE 等）| 中 |
| log_setup.py 改用 RotatingFileHandler 防止日志无限增长 | 中 |
| 异常处理改为具体类型，确保每处 handler 都有日志 | 高 |
| 长函数拆分（_build_scene_prompt、run()、_run_creative_brief） | 中 |
| 补充缺失单元测试（config_manager、align.py） | 高 |
| ComfyUI 地址通过 config 暴露，不再硬编码 | 低 |

---

## 2. config_manager.py 单元测试场景设计

> 仅设计场景，不含实现代码。10 个场景覆盖高风险逻辑。

**前置说明**：所有测试前必须重置 `ConfigManager._instance = None`，否则用例之间会互相污染。

| 编号 | 场景 | 测试的高风险逻辑 | 需 mock |
|------|------|-----------------|---------|
| T01 | 配置优先级：env 变量 > .env > 默认值 | 优先级是整个配置体系的核心假设 | os.environ、Path.read_text |
| T02 | .env 缺失时静默降级为默认值 | 不抛异常，使用 dataclass 默认值 | Path.exists → False |
| T03 | _coerce_value：非法值应回退默认，不抛异常 | `API_MAX_RETRIES=abc` 回退到 3 | Path.read_text |
| T04 | 布尔值解析：true/1/yes/on/false/0/no | 类型必须是 bool，不是字符串 | Path.read_text（参数化）|
| T05 | get_llm_token：新旧 token 三种场景 | 有新 token 用新，无新用旧，都没返回空 | Path.read_text |
| T06 | get_image_token：minimax/alibaba/pollinations/comfyui | pollinations 和 comfyui 应返回空字符串 | Path.read_text |
| T07 | get_image_api_url：未知 provider 回退 minimax URL | 不抛异常，不返回 None | Path.read_text |
| T08 | .env 格式容错：注释、引号、无等号行 | 引号被剥离，无效行不导致报错 | Path.read_text |
| T09 | 单例行为：同进程多次实例化返回同一对象 | 第二次传入的 env_file 被忽略 | 仅重置 _instance |
| T10 | _load_env_file：向上搜索目录取第一个 .env | 当前目录无 .env 时向上一级找到 | Path.cwd、Path.exists、Path.read_text |

**优先级**：T05、T06（token 拿错直接导致 API 鉴权失败）> T01、T09 > T03、T04 > 其余

---

## 3. 产品化方向讨论

### 3.1 当前定位

**个人作品展示**，目标用户不明确。不需要用户系统、计费、扩容。

### 3.2 产品化路径（供未来参考）

```
当前（CLI 工具）
    ↓
第一阶段：包成 API（最小改动，快速验证需求）
    ↓
第二阶段：做 Web 前端（有了付费用户再投入）
    ↓
第三阶段：完整 SaaS（用户系统、计费、批量生成）
```

### 3.3 展示策略

不追求"完美成品"，而是展示系统能力边界：
1. **多跑、精选**：每首跑 2-3 次，取 30-60 秒最佳片段
2. **按维度分类**：风格多样性、节奏适配、主题广度

---

## 4. Demo 批量命令集

### 维度一：风格多样性（固定主题"思念"，对比最直观）

```bash
python -m src.main --theme "思念" --style "国风"       --music-style "中国风" --mood "忧伤"  --language "中文" --auto
python -m src.main --theme "思念" --style "动漫风"     --music-style "流行"   --mood "忧伤"  --language "中文" --auto
python -m src.main --theme "思念" --style "水彩插画风" --music-style "民谣"   --mood "忧伤"  --language "中文" --auto
python -m src.main --theme "思念" --style "复古胶片风" --music-style "民谣"   --mood "怀旧"  --language "中文" --auto
python -m src.main --theme "思念" --style "赛博朋克风" --music-style "电子"   --mood "孤独"  --language "中文" --auto
```

### 维度二：节奏适配（快歌 vs 慢歌）

```bash
python -m src.main --theme "勇气" --style "动漫风"       --music-style "摇滚"       --mood "热血" --language "中文" --auto
python -m src.main --theme "校园" --style "动漫风"       --music-style "流行"       --mood "欢快" --language "中文" --auto
python -m src.main --theme "家庭" --style "写实摄影风"   --music-style "新世纪NewAge" --mood "温柔" --language "中文" --auto
python -m src.main --theme "山川" --style "电影感写实风" --music-style "古典"       --mood "史诗" --language "中文" --auto
```

### 维度三：主题广度

```bash
python -m src.main --theme "星空" --style "极简几何风"   --music-style "新世纪NewAge" --mood "梦幻" --language "中文" --auto
python -m src.main --theme "故宫" --style "古风"         --music-style "中国风"       --mood "史诗" --language "中文" --auto
python -m src.main --theme "童年" --style "宝丽来快照风" --music-style "民谣"         --mood "怀旧" --language "中文" --auto
python -m src.main --theme "星际" --style "赛博朋克风"   --music-style "EDM舞曲"     --mood "魔幻" --language "中文" --auto
```

### 推荐验证流程（按顺序执行，避免浪费 API 额度）

```bash
# 第一步：验证 prompt（免费，秒出）
python -m src.main --theme "思念" --style "国风" --mood "忧伤" --test-reference prompt

# 第二步：验证参考图（消耗 1 次生图）
python -m src.main --theme "思念" --style "国风" --mood "忧伤" --test-reference image

# 第三步：确认满意后跑完整流程
python -m src.main --theme "思念" --style "国风" --music-style "中国风" --mood "忧伤" --language "中文" --auto
```

---

## 5. 日志分析：思念_20260506_031628.log

> 运行时间 03:16:28 → 03:29:02（约 12 分 34 秒），日志在 Step⑤ 锚定图生成中途截止，**pipeline 未完成**。

### 5.1 问题汇总

| 级别 | 问题描述 | 日志位置 | 影响 |
|------|---------|---------|------|
| P0 | 歌词生成出现乱码 `"空对孤灯思故aggio"`，污染全部下游步骤 | 第 47 行 lyrics_generation 响应 | 场景描述、Visual Bible 全部含错误词 |
| P1 | scene_desc_batch 两次 `finish_reason=length`，JSON 解析失败 | 第 142、173 行 | 浪费 2 次 API + 50s，重试才成功 |
| P1 | anchor_generation 截断后从 `<think>` 示例 JSON 误提取占位符，用 `"environment anchor image prompt"` 生图 | 第 429-431 行 | 锚定图质量失控 |
| P2 | Whisper 进程 exit code 3221226505（`STATUS_STACK_BUFFER_OVERRUN`），崩溃在退出阶段 | 第 74 行 | 已容错，不影响输出 |
| P2 | 字幕 31.4s 断层警告信息不明确，无法判断是间奏还是对齐失败 | 第 87 行 | 可读性差 |

### 5.2 P0 乱码的传播链

```
Step①  歌词生成 → "空对孤灯思故aggio"（LLM 幻觉）
    ↓ 未被拦截
Step③  ASR 对齐 → 第 8 个插值行含乱码
    ↓
Step③.5 场景描述 → scene 5 的 lyrics 字段含乱码
    ↓
Step④  Visual Bible → 引用了含乱码的场景样本
```

### 5.3 P1 anchor 截断的机制

```
LLM 请求 anchor_generation（max_tokens=512）
    ↓
响应 finish_reason=length，content 只有 <think> 推理链
    ↓
_call_anchor_llm 在 raw 中找第一个 "{"
    ↓
找到的是 prompt 模板示例 JSON 中的 "{"
    ↓
提取出 "environment anchor image prompt"（示例占位符）
    ↓
用此字符串调用生图 API → 图片质量不可控
```

### 5.4 Whisper 崩溃分析

- 崩溃码 `3221226505 = 0xC0000409 = STATUS_STACK_BUFFER_OVERRUN`
- 崩溃发生在进程**退出阶段**（工作已完成），不影响 ASR 输出
- 升级 faster-whisper 可能有效（若 ctranslate2 < 4.0），但不保证
- 换用 CPU 设备（`ALIGN_WHISPER_DEVICE=cpu`）是更稳妥的绕过方案
- 参考：[DAILY_ARCHIVE_2026-05-04.md](DAILY_ARCHIVE_2026-05-04.md) 有完整的 native 崩溃排查方法论

---

## 6. Bug 修复记录

### Fix 1 — P0：歌词乱码检测

**文件**：`src/pipeline.py`

新增模块级函数 `_check_lyrics_garbled(lyrics, language)`：
- 检测中文行中混入 3+ 位拉丁字母（如 `"思故aggio"`）
- 歌词保存前触发，发现问题时打印 `⚠️` 提示并写 WARNING 日志
- 不中断流程，让用户知情后决定是否重新生成

```python
# 检测规则：中文字符紧接 3+ 个拉丁字母，或反向排列
pattern = re.compile(r'[一-鿿][a-zA-Z]{3,}|[a-zA-Z]{3,}[一-鿿]')
```

### Fix 2 — P1-a：scene_desc token 上限

**文件**：`src/config_manager.py`

```python
# before
scene_desc_max_tokens: int = 4096
# after
scene_desc_max_tokens: int = 6144
```

提高默认值，减少 thinking 模型因输出空间不足触发 `finish_reason=length` 的概率。

### Fix 3 — P1-b：anchor_generation 截断修复

**文件**：`src/scene_generator.py`，`_call_anchor_llm()` 方法

两处改动：

1. 检测到 `finish_reason=length` 时直接返回 `None`，不再尝试解析残缺输出
2. 剥离 `<think>...</think>` 内容后再做 JSON 提取，防止从提示词示例 JSON 里误读占位符

```python
# 新增：finish_reason=length 直接放弃
if finish_reason == "length":
    logger.warning("anchor_generation 输出被截断，放弃本次锚定图生成")
    return None

# 新增：剥离 think 块后再提取 JSON
raw_clean = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()
```

### Fix 4 — P2-a：Whisper 崩溃可读性

**文件**：`src/align.py`

```python
# before
logger.warning("faster-whisper worker exited with code %s, using completed ASR output", result.returncode)

# after
_win_codes = {
    3221225477: "ACCESS_VIOLATION (0xC0000005)",
    3221226505: "STACK_BUFFER_OVERRUN (0xC0000409) — 建议升级 faster-whisper",
    3221225725: "UNEXPECTED_ERROR (0xC000009D, 常见 CUDA 崩溃)",
}
code_desc = _win_codes.get(result.returncode, f"code={result.returncode}")
logger.warning("faster-whisper worker 异常退出 [%s]，但已获取完整 ASR 输出，继续处理", code_desc)
```

### Fix 5 — P2-b：字幕断层日志改进

**文件**：`src/align.py`，`_check_alignment_quality()` 方法

断层警告附加额外上下文：
- 断层占歌曲时长的百分比
- 断层发生在歌词中的位置百分比
- 提示"若为间奏/纯音乐段属正常"

```
# before
字幕局部断层过大: gap=31.4s, after_line=11, remaining=9

# after
字幕局部断层过大: gap=31.4s (占歌曲 23%)，发生在第 11 行（55% 处），剩余 9 行。
若此处为间奏/纯音乐段属正常，否则建议检查 ASR 对齐结果
```

---

## 7. 待处理事项

### 用户侧（需手动操作）

- [ ] 吊销并重新生成 MINIMAX_TOKEN
- [ ] 清理 git 历史中的 token（BFG 工具）
- [ ] 确认 ctranslate2 版本：`pip show ctranslate2`（< 4.0 建议升级）
- [ ] 运行 demo 命令集，生成展示素材

### 代码侧（后续 Claude 可继续执行）

- [ ] 为 config_manager 编写单元测试（10 个场景已在本文档第 2 节设计完毕）
- [ ] 提取共享工具函数到 `src/utils.py`
- [ ] 硬编码常量移入 config_manager
- [ ] 添加 pre-commit hook 防止 .env 误提交

---

**归档完成时间**：2026-05-06
**涉及文件**：`src/pipeline.py`、`src/config_manager.py`、`src/scene_generator.py`、`src/align.py`（×2）
