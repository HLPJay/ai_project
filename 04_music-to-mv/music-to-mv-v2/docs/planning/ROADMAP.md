# 🗺️ 项目路线图与待办事项

> **最后更新**: 2026-05-03  
> **优先级说明**: 🔴 立即开始 | 🟠 1-2周 | 🟡 3-4周 | 🔵 5+周 | 💜 可选/长期

---

## 📊 优先级总览

| 优先级 | 任务数 | 时间估计 | 状态 |
|--------|--------|---------|------|
| 🔴 立即开始（本周） | 6 | 4-6 小时 | 待开始 |
| 🟠 第 1-2 周 | 8 | 10-15 小时 | 待开始 |
| 🟡 第 3-4 周 | 6 | 8-10 小时 | 待开始 |
| 🔵 第 5+ 周 | 10 | 15-20 小时 | 待开始 |
| 💜 可选/长期 | 6 | 20-30 小时 | 待开始 |

---

## 🔴 立即开始（本周，4-6 小时）

### 性能优化
- [ ] **改进并行生图配置** (15 分钟)
  - 修改 `.env.example`: `IMAGE_PARALLEL=1` → `IMAGE_PARALLEL=3`
  - 文件: `.env.example`, `src/config_manager.py`
  - 收益: 减少 30~50% 生图耗时

### A/B 测试框架 - 阶段 1（核心）

- [ ] **扩展 registry.yaml 支持 A/B 配置** (30 分钟)
  - 添加 `ab_test` 字段到 `prompts/registry.yaml`
  - 示例配置:
    ```yaml
    lyrics.generation:
      ab_test:
        enabled: true
        control_version: "v2.0"
        treatment_version: "v3.0"
        split_ratio: 0.5
    ```
  - 文件: `prompts/registry.yaml`

- [ ] **扩展 ProjectManager 支持 A/B 记录** (1 小时)
  - 新增方法: `set_ab_test_info(step: str, assigned_version: str, score: float)`
  - 存储位置: `metadata/info.json` 的 `ab_tests` 字段
  - 文件: `src/project_manager.py`

- [ ] **新建歌词评分器 `simple_scorer.py`** (2 小时)
  - 位置: `src/ab_testing/simple_scorer.py`
  - 功能:
    - `score_lyrics_simple()`: 1-10 分评分
    - `count_rhymes()`: 韵脚检查
    - `check_keywords()`: 情绪关键词匹配
  - 文件: 新建 `src/ab_testing/simple_scorer.py`

- [ ] **新建 A/B 测试模块** (30 分钟)
  - 创建: `src/ab_testing/__init__.py`
  - 作用: 模块化 A/B 测试功能

- [ ] **更新 .env.example 配置** (15 分钟)
  - 添加:
    ```ini
    # A/B 测试配置
    AB_TEST_ENABLED=true
    AB_TEST_PROMPT_KEYS=lyrics.generation
    ```
  - 文件: `.env.example`

---

## 🟠 第 1-2 周（10-15 小时）

### A/B 测试框架 - 阶段 1（继续）

- [ ] **修改 pipeline.py - 添加 A/B 分配逻辑** (2 小时)
  - 文件: `src/pipeline.py`
  - 新增方法:
    - `_allocate_ab_version(prompt_key: str) -> str`
    - `_score_lyrics(lyrics: str, mood: str, theme: str) -> float`
  - 修改方法: `_step_lyrics()`
    - 添加版本分配
    - 添加自动评分
    - 记录 A/B 信息

- [ ] **新建简单报告工具 `ab_report_simple.py`** (1.5 小时)
  - 位置: `tools/ab_report_simple.py`
  - 功能:
    - 遍历所有项目的 `metadata/info.json`
    - 统计各版本的评分
    - 生成简单对比报告
  - 输出示例:
    ```
    [① lyrics]
      v2.0: 8.47 分 (n=3)
      v3.0: 8.22 分 (n=2)
    ```

- [ ] **生成 20-30 个 MV 收集测试数据** (5-7 小时)
  - 运行: `python -m src.main --theme "主题" --auto`
  - 目标: 收集至少 20-30 个样本
  - 分布: 不同主题、风格、情绪的组合
  - 验证: 确保 A/B 日志正确记录

- [ ] **分析 A/B 测试数据** (2-3 小时)
  - 运行: `python tools/ab_report_simple.py`
  - 分析:
    - 整体胜出版本
    - 是否有显著差异
    - 是否需要细分分析（按主题/情绪）
  - 输出: 分析报告文档

---

## 🟡 第 3-4 周（8-10 小时）

### 代码质量

- [ ] **补充类型标注 - pipeline.py** (2 小时)
  - 文件: `src/pipeline.py`
  - 覆盖:
    - 所有公开方法的参数和返回值类型
    - 使用 `Literal` 约束 `phases` 参数
    - 使用 `Dict`, `Optional`, `Union` 等类型

- [ ] **补充类型标注 - scene_generator.py** (1.5 小时)
  - 文件: `src/scene_generator.py`
  - 关键方法:
    - `generate_all()` 的返回值
    - `_load_scenes()` 的返回值
    - 私有方法的参数和返回值

- [ ] **补充类型标注 - exporter.py** (1 小时)
  - 文件: `src/exporter.py`
  - 补全: `merge_audio_subtitles()`, `export_versions()`, `generate_quality_report()` 等方法的返回值类型

- [ ] **运行 mypy 检查并修复** (1.5 小时)
  - 创建: `mypy.ini` 配置文件
  - 运行:
    ```bash
    mypy src/pipeline.py src/scene_generator.py src/exporter.py
    ```
  - 修复: 所有类型错误直到零错误为止

### 可靠性

- [ ] **改进重试策略 - 实现指数退避** (2 小时)
  - 文件: `src/llm/client.py`
  - 改动:
    - 从固定 3 次重试改为指数退避（1s → 2s → 4s）
    - 实现熔断机制（连续失败后暂停）
    - 记录 rate-limit 头信息

---

## 🔵 第 5+ 周（15-20 小时）

### A/B 测试框架 - 阶段 2

- [ ] **对 Step ④ 角色参考图 Prompt 做 A/B 测试** (3 小时)
  - 文件: `src/scene_generator.py`
  - 修改: `generate_base_character()` 添加 `prompt_version` 参数
  - 评分: 集成 `image_quality.py` 的图片质检

- [ ] **集成图片质量评分到 A/B 框架** (2 小时)
  - 文件: `src/image_quality.py`, `src/ab_testing/`
  - 功能: 图片自动评分（1-10 分）

### A/B 测试框架 - 阶段 3

- [ ] **对 Step ③.5 场景分析 Prompt 做 A/B 测试** (3 小时)
  - 文件: `src/scene_analyzer.py`
  - 修改: `analyze()` 添加版本支持

- [ ] **新建场景描述评分器** (2 小时)
  - 位置: `src/ab_testing/scene_scorer.py`
  - 评分维度: 多样性、语义准确度、场景完整性

### 代码质量

- [ ] **分离配置管理 - 创建 config/*.yaml** (2 小时)
  - 新建文件结构:
    ```
    config/
      ├── lyrics.yaml      # 歌词相关配置
      ├── image.yaml       # 图片相关配置
      ├── music.yaml       # 音乐相关配置
      └── llm.yaml         # LLM 相关配置
    ```
  - 文件: `src/config_manager.py`

- [ ] **统一日志体系 - 迁移到 RotatingFileHandler** (2 小时)
  - 文件: `src/llm/logger.py`
  - 改动: 用 `logging.handlers.RotatingFileHandler` 替代混合方式

- [ ] **增强单元测试覆盖** (3 小时)
  - 目标: 达到 60%+ 代码覆盖率
  - 新增 mock 层测试
  - 文件: `tests/`

---

## 💜 可选/长期（20-30 小时）

### A/B 测试框架 - 阶段 4（可选）

- [ ] **对 Step ② 音乐 Prompt 做 A/B 测试** (4 小时)
  - 注意: 音乐生成耗时较长（~60s），成本较高
  - 优先级: 仅在歌词 + 图片 A/B 稳定后考虑

### 高级功能

- [ ] **完整 A/B 测试框架 - 含统计和决策机制** (5 小时)
  - 新建: `src/ab_testing/reporter.py`
  - 功能:
    - 统计学显著性检验 (t-test)
    - 置信区间计算
    - 分层分析（按主题/情绪）
    - 自动决策（升级或保留当前版本）

- [ ] **图片质检升级为交互式 UI** (4 小时)
  - 技术: Gradio 或 Streamlit
  - 功能: 人工审核 + 反馈

- [ ] **支持多语言 Prompt** (3 小时)
  - 新增语言: 日文、韩文、粤语等
  - 需要补充相应的 prompt 翻译版本

- [ ] **音乐自动质检 - 接入 librosa** (3 小时)
  - 检测维度: 音高、节奏、和声
  - 评分: 1-10 分

- [ ] **生成 GIF 预览** (3 小时)
  - 功能: 快速视觉确认而无需看完整 MV
  - 位置: `output/preview.gif`

### 架构升级（可选）

- [ ] **微服务化 - 分离图片生成服务** (8+ 小时)
- [ ] **任务队列 - 支持批量生产** (10+ 小时)
- [ ] **Web UI - 使用 Gradio/Streamlit** (12+ 小时)
- [ ] **Docker 容器化** (5-6 小时)

---

## 📈 推荐的执行路径

### **路径 A：快速验证（2-3 周）**
推荐用于快速了解 A/B 测试效果。

```
Week 1  → 🔴 阶段 1 基础 + 🟠 数据收集
Week 2  → 🟠 数据分析 + 决策
Week 3  → 🟡 代码质量优化（可选）
```

**预计投入**: 20-25 小时

### **路径 B：完整优化（4-5 周）**
推荐用于完整系统升级。

```
Week 1  → 🔴 立即开始 + 🟠 A/B 阶段 1
Week 2  → 🟠 数据收集和分析
Week 3  → 🟡 代码质量 + 可靠性
Week 4  → 🔵 A/B 阶段 2-3
Week 5  → 💜 高级功能（可选）
```

**预计投入**: 45-50 小时

---

## ✅ 检查清单

### 开始前检查
- [ ] 已复制 `.env.example` 到 `.env`
- [ ] 已设置 `MINIMAX_TOKEN`
- [ ] 已验证项目可以生成 1 个完整 MV

### A/B 测试 Phase 1 验收标准
- [ ] `registry.yaml` 包含 `ab_test` 配置
- [ ] `ProjectManager` 可以记录 A/B 信息
- [ ] `simple_scorer.py` 对 20 个样本的评分合理（5-9 分）
- [ ] `pipeline.py` 自动分配版本和记录
- [ ] 报告工具能正确统计数据

### 整体验收标准
- [ ] `mypy` 检查无错误
- [ ] 所有公开方法都有类型标注
- [ ] 测试覆盖率 ≥ 60%
- [ ] A/B 测试数据完整（≥ 30 个样本）
- [ ] 文档更新完整

---

## 🔗 相关文档

- [README.md](./README.md) - 项目概览
- [测试指南](./tests/) - 单元测试说明
- [配置文件](./env.example) - 环境变量说明
- [Prompt 管理](./prompts/registry.yaml) - Prompt 版本管理

---

## 📝 更新日志

| 日期 | 更新内容 |
|------|---------|
| 2026-05-03 | 初次创建，包含所有优化项和 A/B 测试框架 |

---

## 功能问题归纳与后期优化方向

> 2026-05-05 补充：当前项目已经具备完整 MV 生成链路，但从产品功能看，问题不在于“还缺一个巨大智能导演模块”，而在于生成结果还不够可解释、可控、可返工。后期优化应避免一开始就做高复杂度导演系统，先做低风险、低耦合、能明显提升交付体验的功能闭环。

### 当前功能层面的主要问题

- **创作控制粒度不足**：用户只能输入 theme/style/music-style/mood/reference，难以明确控制 MV 是叙事型、氛围型、角色型还是风景型，也难以控制主角策略、镜头密度和成片节奏。
- **质量结果不够透明**：流程中存在 fallback、跳过、降级、部分失败等情况，但最终用户不一定知道哪些步骤是高质量输出，哪些步骤是凑合完成。
- **坏图和低质量产物缺少自动返工**：已有图片质量检查能力，但后续动作偏报告化，缺少“明显坏图自动重试一次，仍失败再标记”的闭环。
- **对齐风险没有产品化呈现**：歌词对齐可能使用 ASR、缓存、fallback timeline 或人工 SRT，但最终报告里需要更直观展示对齐置信度和风险。
- **视觉一致性仍依赖 prompt 约束**：visual_bible、anchors、base reference 已经具备雏形，但角色/主体在多图间仍可能漂移，暂不适合直接上复杂语义质检或导演模型。
- **剪辑运动仍偏模板化**：Ken Burns 能保证快速出片，但节奏点、高潮段运动、转场策略等更像长期增强项，不应放在第一优先级。

### 后期优化原则

先做“可解释、可控、可少量返工”，再做“智能导演”和“高级审美判断”。

具体原则：

1. **先暴露问题，再自动修问题**：先把 fallback、失败、低质量图片、对齐风险写入最终报告，避免用户误以为所有步骤都高质量成功。
2. **先增加简单开关，不做复杂导演系统**：优先加入 `--mv-mode`、`--character-policy`、`--pacing`、`--quality` 这类明确参数，并把它们注入 creative brief、scene prompt 和 Ken Burns 配置。
3. **先处理明显坏图，不做复杂语义质检**：第一阶段只处理文件过小、分辨率过低、无效图片、亮度/方差异常、API 错误页等确定性问题。
4. **先做轻量返工闭环**：图片质检失败后自动重试 1 次；仍失败则继续流程但在报告中标记为高风险。
5. **先增强 prompt 注入，不重构算法**：角色一致性、情绪弧线、副歌变化等优先通过稳定注入 visual_bible、anchors、scene context、用户模式参数来改善。

### 建议的第一阶段落地项

- [ ] **最终报告增加 fallback/risk summary** (1-2 小时)
  - 汇总每一步是否使用 fallback、失败次数、重试次数、部分成功状态。
  - 显示 `alignment.timeline_fallback`、`engine`、`aligned_lines/total_lines`。
  - 显示图片质检 summary：总数、失败数、重试后仍失败数。

- [ ] **CLI 增加低成本创作控制参数** (1-2 小时)
  - `--mv-mode narrative|atmosphere|character|landscape`
  - `--character-policy fixed|optional|none`
  - `--pacing slow|medium|fast`
  - `--quality fast|normal|strict`
  - 第一版只写入 metadata，并注入 prompt/配置，不做复杂行为系统。

- [ ] **图片质检失败自动重试一次** (2-3 小时)
  - 复用 `image_quality.py` 的确定性检查。
  - 只重试明显坏图，不尝试判断审美或语义是否匹配。
  - 记录 retry reason 和最终状态。

- [ ] **对齐风险产品化展示** (1 小时)
  - 在最终报告中给出 “精准 / 可用 / 风险较高” 三档提示。
  - 不先改 ASR 算法，只把已有对齐状态解释清楚。

- [ ] **Prompt 统一注入用户模式参数** (2 小时)
  - 将 mv-mode、character-policy、pacing、quality 注入 creative brief、scene description、image prompt。
  - 避免新增一套复杂导演模型。

### 暂缓的大型优化

以下方向仍然有价值，但实现成本高、耦合面大，建议在第一阶段稳定后再做：

- LLM 辅助导演式完整分镜重排。
- 基于音乐节拍/鼓点的自动剪辑。
- 图像语义级质检：主体是否匹配歌词、是否人物畸形、是否画风跑偏。
- 跨镜头角色身份一致性模型或参考图强绑定方案。
- 复杂 A/B 测试决策系统和统计显著性判断。

