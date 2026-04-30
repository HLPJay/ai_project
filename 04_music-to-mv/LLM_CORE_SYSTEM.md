---
title: Music-to-MV LLM 核心系统 - 完整指南
date: 2026-04-28
author: AI Architecture Team
version: 2.0
---

# Music-to-MV LLM 核心系统 - 完整指南

> **最后更新**：2026-04-28  
> **状态**：已规划，等待实施  
> **工期**：3-4 周，1 人工程师

---

## 📚 文档导航

本次优化涉及 **3 份核心文档**和**原有的 SKILL.md**：

### 📖 核心文档

| 文档 | 内容 | 适合人群 | 阅读时间 |
|------|------|---------|---------|
| **[ARCHITECTURE_v2.md](ARCHITECTURE_v2.md)** | 完整的系统架构设计（三层模型、五个部分） | 系统设计师、技术主管 | 30-40 分钟 |
| **[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)** | 具体的代码实现指南和示例 | 工程师（实施人员） | 40-50 分钟 |
| **[ROADMAP.md](ROADMAP.md)** | 详细的时间计划、里程碑、验收标准 | 项目经理、技术主管 | 20-30 分钟 |
| **[SKILL.md](SKILL.md)** （原有） | 产品功能规范和交互设计 | 所有人员 | — |

### 🎯 快速导航

**如果你想...**

- 🔍 **了解为什么要做这个优化** → 读 ARCHITECTURE_v2.md 的"核心认知"部分
- 💻 **开始编码（第 1 天）** → 跳到 IMPLEMENTATION_GUIDE.md 的"第一部分"
- 📅 **制定项目计划** → 参考 ROADMAP.md 的"详细计划表"
- 🧪 **编写测试** → 看 IMPLEMENTATION_GUIDE.md 的"第四部分"
- 📊 **监控和调试** → 看 ARCHITECTURE_v2.md 第三部分的"LLMReportGenerator"
- ❓ **常见问题** → IMPLEMENTATION_GUIDE.md 最后的"常见问题"

---

## 🎯 核心概念（5 分钟速览）

### 问题诊断

在测试过程中，你发现了一个**关键事实**：

> **这不是一个视频生成系统，而是一个 LLM 驱动的创意系统。**

- ❌ **当前状态**：LLM 交互是黑盒，调用日志分散，无法追踪质量、成本、失败原因
- ✅ **目标状态**：LLM 交互完全透明化，每个 Prompt 有版本号，每次调用有完整日志，成本清晰可见

### 解决方案：三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  【第 1 层】 Prompt 管理系统（最核心）                        │
│  ├─ PromptRegistry      — 所有提示词的中心索引（registry.yaml) │
│  ├─ PromptTemplate      — 支持变量填充、条件渲染              │
│  ├─ PromptVersion       — 版本控制，支持 A/B 对比             │
│  └─ PromptEvaluation    — 质量评估（5 维度评分）              │
├─────────────────────────────────────────────────────────────┤
│  【第 2 层】 LLM 调用层（执行层）                             │
│  ├─ LLMClient           — 统一的 API 客户端                   │
│  ├─ RequestBuilder      — 标准化请求构建                     │
│  ├─ ResponseValidator   — JSON 格式验证                      │
│  └─ TokenCounter        — Token 消耗计算                     │
├─────────────────────────────────────────────────────────────┤
│  【第 3 层】 可观测性系统（监控层）                           │
│  ├─ LLMLogger           — 核心日志系统（单例，线程安全）      │
│  ├─ PromptAnalyzer      — 版本性能对比分析                   │
│  └─ LLMReportGenerator  — HTML 可视化报告                    │
└─────────────────────────────────────────────────────────────┘
```

### 关键创新点

1. **Prompt 版本化**
   - 每个 Prompt 都有版本号（v1.0, v2.0...）
   - 支持多个版本并行测试
   - 自动统计每个版本的质量和成本

2. **完整的调用日志**
   - `calls.jsonl` — 所有调用的摘要（流式，只记关键字段）
   - `responses/` — 完整的 Prompt 和 Response（单独文件）
   - `stats.json` — 汇总统计（Token、成本、质量）

3. **质量评估**
   - 5 维度评分（相关性、完整性、创意性、可用性、格式）
   - 自动评估每个输出
   - 支持版本自动选择

4. **成本透明**
   - 精确计算每次调用的 Token 消耗
   - 累计项目成本
   - 支持成本预警

---

## 📋 核心实施内容（Week-by-Week）

### Week 1: 基础设施搭建 🔧

```
Day 1-2: Prompt 管理系统
  ✅ prompts/ 目录结构
  ✅ registry.yaml 写 5 个 prompt_key 和多个版本
  ✅ PromptRegistry 类（加载、版本管理）
  ✅ PromptTemplate 类（Jinja2 模板填充）

Day 3-4: LLM 日志系统
  ✅ LLMLogger 单例（线程安全）
  ✅ LLMCallRecord 数据类
  ✅ calls.jsonl 流式追加
  ✅ stats.json 自动聚合

Day 5: 集成测试
  ✅ 单元测试（5 个）
  ✅ 集成测试（3 个完整流程）
  ✅ 代码覆盖率 > 80%
```

### Week 2: 核心功能交付 💻

```
Day 1-2: LLMClient + 请求/响应
  ✅ LLMClient.generate() 主方法
  ✅ RequestBuilder（参数校验）
  ✅ ResponseValidator（JSON 格式检查）
  ✅ 重试机制（指数退避，最多 3 次）

Day 3-4: 质量评估和版本控制
  ✅ PromptEvaluation（5 维度评分）
  ✅ PromptAnalyzer（版本对比）
  ✅ 自动版本选择

Day 5: 与现有脚本集成
  ✅ generate_lyrics.py（调用 LLMClient）
  ✅ generate_music.py
  ✅ generate_scene_imgs.py
  ✅ E2E 测试 1 个完整流程
```

### Week 3: 编排和交互 🎪

```
Day 1-2: MVPipeline 编排器
  ✅ 11 步流程编排
  ✅ 暂停点管理（Step② 和 Step③）
  ✅ 用户选择处理（A/B/C 对齐方式）

Day 3-4: UserInteraction 交互管理
  ✅ pause_for_approval() 方法
  ✅ approve() 方法（用户审批）
  ✅ 更新 SKILL.md（新交互规范）

Day 5: 完整验收
  ✅ 5 个完整 MV 生成
  ✅ 日志完整性检查
  ✅ 暂停点功能测试
  ✅ HTML 报告生成
```

---

## 📊 成本效益分析

### 投入

| 资源 | 数量 | 备注 |
|------|------|------|
| 工程师 | 1 人 | 3-4 周全职 |
| 工时 | 130 小时 | 包含测试和文档 |

### 收益

| 收益 | 度量 | 价值 |
|------|------|------|
| **可观测性** | 100% LLM 调用都有日志 | 能快速定位问题 |
| **可重现性** | 每个产出都知道用了哪个 Prompt 版本 | 便于 debug 和优化 |
| **可调优性** | 支持 A/B 测试和版本对比 | 不断改进 Prompt 质量 |
| **成本控制** | 精确追踪 Token 和美金成本 | 预算可控 |
| **质量保证** | 自动质量评估 | 发现低质量输出 |

### ROI（Return on Investment）

| 时间点 | ROI |
|--------|-----|
| 第 1 周末 | 基础设施就位，可开始监控 |
| 第 2 周末 | 完整的日志和成本透明 |
| 第 3 周末 | 质量可评估，版本可对比 |
| 第 4-8 周 | 不断优化 Prompt，质量和成本同时改善 |

---

## 🚀 快速开始（Day 1 Checklist）

如果今天就开始，按这个顺序做：

```bash
# 1. 创建目录结构（10 分钟）
mkdir -p prompts/{lyrics,music,image/{base_character,scene_image},scene_analysis}
mkdir -p lib/llm
mkdir -p tests/{llm,integration}

# 2. 复制本文档到项目根目录（已完成）
# ARCHITECTURE_v2.md
# IMPLEMENTATION_GUIDE.md
# ROADMAP.md
# LLM_CORE_SYSTEM.md (本文件)

# 3. 从 IMPLEMENTATION_GUIDE.md 的"第一部分"开始
# Step 1.1 - 创建 registry.yaml
# Step 1.2 - 编写 prompt 模板

# 4. 编写第一个测试（了解系统）
# 参考 IMPLEMENTATION_GUIDE.md 的"第四部分"

# 5. 下午开始编码
# lib/llm/prompt_registry.py
# lib/llm/llm_logger.py
```

---

## 🔑 核心文件清单

实施后的项目结构：

```
.
├── prompts/                          # Prompt 管理（第 1 部分）
│   ├── registry.yaml                 # 所有 prompt 的索引
│   ├── lyrics/
│   │   ├── v1.0.md
│   │   └── v2.0.md
│   ├── music/
│   │   ├── v1.0.md
│   │   └── v1.2.md
│   ├── image/
│   │   ├── base_character/
│   │   └── scene_image/
│   └── scene_analysis/
│
├── lib/llm/                          # LLM 交互层（第 2、3 部分）
│   ├── __init__.py
│   ├── llm_client.py                 # ★ 核心：统一 API 客户端
│   ├── llm_logger.py                 # ★ 核心：日志系统
│   ├── prompt_registry.py            # Prompt 管理
│   ├── prompt_template.py            # 模板引擎
│   ├── prompt_evaluator.py           # 质量评估
│   ├── prompt_analyzer.py            # 性能分析
│   ├── request_builder.py            # 请求构建
│   ├── response_validator.py         # 响应验证
│   └── token_counter.py              # Token 统计
│
├── lib/
│   ├── project_manager.py            # （已有，需升级）
│   ├── mv_pipeline.py                # 新编排器
│   └── user_interaction.py           # 交互管理
│
├── metadata/llm_calls/               # 日志输出（自动生成）
│   ├── calls.jsonl
│   ├── errors.jsonl
│   ├── evaluations.jsonl
│   ├── stats.json
│   ├── versions.json
│   └── responses/
│
├── scripts/
│   ├── generate_lyrics.py            # 改造成调用 LLMClient
│   ├── generate_music.py
│   ├── generate_scene_imgs.py
│   └── ...
│
├── tests/llm/                        # 单元测试
│   ├── test_registry.py
│   ├── test_logger.py
│   ├── test_template.py
│   ├── test_client.py
│   └── ...
│
├── tests/integration/                # 集成测试
│   ├── test_lyrics_flow.sh
│   ├── test_music_flow.sh
│   └── ...
│
├── ARCHITECTURE_v2.md                # 本次优化的架构文档
├── IMPLEMENTATION_GUIDE.md           # 实施指南
├── ROADMAP.md                        # 时间计划
└── LLM_CORE_SYSTEM.md               # 本文件（导航）
```

---

## 💡 关键设计决策

### 1. 为什么是 YAML + Markdown 组合？

```yaml
# registry.yaml — 机器可读的索引
prompts:
  lyrics_generation:
    default_version: v2.0
    versions:
      v2.0:
        model: MiniMax-M2.7
        file: lyrics/v2.0.md
        status: active
```

```markdown
# lyrics/v2.0.md — 人类可读的实际内容
# 任务：生成音乐视频歌词
## 背景信息
- 主题：{{ theme }}
## 输出格式
```json
{ ... }
```
```

**优势**：
- ✅ Prompt 在普通编辑器中易读易改
- ✅ 版本控制友好（Markdown diff 清晰）
- ✅ 支持 Jinja2 模板语言
- ✅ 无需复杂的 UI 就能管理

### 2. 为什么日志要分为 calls.jsonl 和 responses/？

**calls.jsonl（摘要）**：
```json
{"timestamp": "...", "prompt_key": "lyrics", "tokens": 100, "cost_usd": 0.01, "response_file": "responses/2026-04-28T10-15-30__lyrics.json"}
```
- ✅ 文件小（可持续增长）
- ✅ 快速查询
- ✅ 易于统计聚合

**responses/（完整）**：
```json
{"prompt_key": "lyrics", "rendered_prompt": "...", "response": "..."}
```
- ✅ 保留完整信息用于调试
- ✅ 分散存储避免单个文件过大
- ✅ 可以定期压缩或清理

### 3. 为什么要 5 维度评估而不是单一评分？

| 维度 | 原因 |
|------|------|
| 相关性 | 输出是否回答了问题 |
| 完整性 | 是否包含所有必需字段 |
| 创意性 | 是否新颖有趣（MV 场景需要创意） |
| 可用性 | 下游系统能否处理 |
| 格式有效性 | JSON 是否正确 |

**多维度的好处**：
- ✅ 能识别不同类型的问题（格式错 vs 质量差）
- ✅ 支持更精细的改进方向
- ✅ 能权衡不同需求（有时牺牲创意换取完整性）

---

## ⚠️ 常见陷阱和避免方法

| 陷阱 | 症状 | 避免方法 |
|------|------|---------|
| **Prompt 过长** | LLM 回复缓慢，成本高 | 在 prompt 中加注释说明，保持简洁 |
| **版本混乱** | 不知道用的哪个版本 | registry.yaml 中强制指定 default_version |
| **日志丢失** | 突然无法查询历史 | 使用 JSONL 格式（append-only），避免覆盖 |
| **线程竞争** | 统计数据不一致 | LLMLogger 使用 threading.Lock() |
| **评估标准不清** | 无法判断质量好坏 | 在 PromptEvaluation 中硬编码评估规则 |

---

## 📞 获取帮助

**如果在某个步骤卡住了：**

1. **Prompt 模板相关** → IMPLEMENTATION_GUIDE.md 的 3.1-3.3 节
2. **日志系统相关** → ARCHITECTURE_v2.md 的第三部分
3. **编码实现相关** → IMPLEMENTATION_GUIDE.md 的第二部分
4. **时间计划相关** → ROADMAP.md
5. **常见问题** → IMPLEMENTATION_GUIDE.md 最后的 Q&A

---

## 📈 预期效果

实施后，你将获得：

```
Before（当前）：
  LLM 调用 → 黑盒 → 输出 ❌ 无法追踪
  问题原因不清 ❌ 花时间 debug
  Prompt 版本混乱 ❌ 无法 A/B 测试
  成本不透明 ❌ 预算失控

After（实施后）：
  LLM 调用 → [完整日志] ✅ 每步可见
         ├─ rendered_prompt（填充后的提示词）
         ├─ response（完整输出）
         ├─ tokens（消耗统计）
         ├─ latency（延迟）
         └─ evaluation（质量评分）
  
  问题定位快速 ✅ 看日志一目了然
  Prompt 版本化 ✅ 支持 A/B 对比
  成本透明 ✅ Token 和美金分别统计
  质量可控 ✅ 自动评估和版本选择
```

---

## 🎓 学习资源

**相关概念阅读：**

- Jinja2 模板语言：https://jinja.palletsprojects.com/
- JSON Lines 格式：https://jsonlines.org/
- Token 计数原理：https://platform.openai.com/docs/guides/tokens
- Prompt Engineering 最佳实践：https://platform.openai.com/docs/guides/prompt-engineering

---

## ✅ 下一步行动

1. **今天（Day 1）**
   - 阅读本文档（15 分钟）
   - 快速浏览 ARCHITECTURE_v2.md（20 分钟）
   - 运行 `bash setup.sh` 创建目录结构

2. **明天（Day 2）**
   - 开始 IMPLEMENTATION_GUIDE.md 的 Step 1.1-1.4
   - 编写 registry.yaml 和 Prompt 模板

3. **本周（Week 1）**
   - 完成 LLMLogger 和 PromptRegistry
   - 编写并通过单元测试

4. **下周（Week 2）**
   - 实现 LLMClient 核心逻辑
   - 集成到现有脚本

5. **第三周（Week 3）**
   - 完整验收测试
   - 文档完善

---

## 许可和贡献

本架构设计是内部优化项目，遵循项目的现有许可协议。

---

**最后问一句：有任何问题或需要澄清吗？**

如果你：
- 🤔 对某个模块不理解
- 💬 想讨论实施策略
- 📝 需要补充某些细节
- 🚀 准备开始编码了

**请直接告诉我！我可以：**
- 详细讲解某个部分
- 提供更多代码示例
- 帮你制定每日计划
- 一起分析可能的问题

---

**文档生成日期**：2026-04-28  
**版本**：2.0 (LLM-First Design)  
**维护者**：Architecture Team
