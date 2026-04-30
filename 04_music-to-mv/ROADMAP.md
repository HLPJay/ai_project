---
title: Music-to-MV LLM 核心系统 - 完整实施路线图
date: 2026-04-28
priority: 🔴 核心优化
---

# 完整实施路线图

## 概览图

```
┌─────────────────────────────────────────────────────────────────────┐
│           WEEK 1: 基础设施搭建（LLM 交互层）                         │
│  ├─ Day 1-2: Prompt 管理系统（Registry + Template）                 │
│  ├─ Day 3-4: LLM 日志系统（Logger + 统计）                          │
│  └─ Day 5:   集成测试                                               │
├─────────────────────────────────────────────────────────────────────┤
│           WEEK 2: 核心功能交付（LLM 客户端 + 编排）                 │
│  ├─ Day 1-2: LLMClient + 请求/响应管理                             │
│  ├─ Day 3-4: PromptEvaluator + 版本控制                             │
│  └─ Day 5:   与现有 Scripts 集成 + E2E 测试                        │
├─────────────────────────────────────────────────────────────────────┤
│           WEEK 3: 编排和用户交互改进                                 │
│  ├─ Day 1-2: MVPipeline 新编排器 + 暂停点管理                      │
│  ├─ Day 3-4: UserInteraction 强制审批流程                          │
│  └─ Day 5:   5 个完整 MV 生成 + 验收                               │
├─────────────────────────────────────────────────────────────────────┤
│           WEEK 4 (可选): 监控和优化                                  │
│  ├─ 实时性能监控仪表盘                                               │
│  ├─ 成本预测和告警                                                   │
│  └─ Prompt 自动优化建议                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 详细计划表

### WEEK 1: 基础设施搭建（LLM 交互层）

#### Day 1-2: Prompt 管理系统

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 创建 `prompts/` 目录结构 | 🔴 必做 | 目录树 | 6 个子目录创建完成 |
| 编写 `prompts/registry.yaml` | 🔴 必做 | YAML 文件 | 所有 prompt_key 都有 2+ 个版本 |
| 编写 Prompt 模板 | 🔴 必做 | 5 个 .md 文件 | lyrics/v2.0.md, music/v1.2.md, scene_analysis/v2.0.md, image/base_character/v1.5.md, image/scene_image/v2.0.md |
| 实现 `PromptRegistry` 类 | 🔴 必做 | lib/llm/prompt_registry.py | 通过单元测试（5 个用例） |
| 实现 `PromptTemplate` 类 | 🔴 必做 | lib/llm/prompt_template.py | 支持 Jinja2 变量填充 |

**关键产出物：**

```
prompts/
├── registry.yaml                          ← 所有 prompt 的索引
├── lyrics/
│   ├── v1.0.md                           ← 基础版本（可保留作参考）
│   └── v2.0.md                           ← 当前版本（支持 music_style）
├── music/
│   ├── v1.0.md
│   └── v1.2.md                           ← 当前版本
├── image/
│   ├── base_character/
│   │   ├── v1.0.md
│   │   └── v1.5.md                       ← 当前版本
│   └── scene_image/
│       ├── v1.0.md
│       └── v2.0.md                       ← 当前版本
└── scene_analysis/
    ├── v1.0.md
    └── v2.0.md                           ← 当前版本
```

**Checklist：**
- [ ] registry.yaml 能被 YAML 解析器正确加载
- [ ] PromptRegistry.load_template("lyrics_generation") 返回 v2.0 内容
- [ ] PromptTemplate.render({"theme": "春天"}) 正确填充变量

---

#### Day 3-4: LLM 日志系统

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实现 `LLMLogger` 核心 | 🔴 必做 | lib/llm/llm_logger.py | 记录、读取、统计 3 个功能完整 |
| 实现 `LLMCallRecord` 数据类 | 🔴 必做 | lib/llm/llm_logger.py | 支持 15+ 字段 |
| 实现统计聚合逻辑 | 🔴 必做 | LLMLogger._update_stats() | stats.json 生成正确 |
| 实现版本使用追踪 | 🔴 必做 | LLMLogger._update_versions() | versions.json 记录所有版本 |

**产出物结构：**

```
metadata/llm_calls/
├── calls.jsonl                            ← 所有调用摘要（流式）
├── errors.jsonl                           ← 失败记录
├── evaluations.jsonl                      ← 质量评估
├── stats.json                             ← 汇总统计
├── versions.json                          ← 版本使用统计
└── responses/                             ← 完整响应存储
    ├── 2026-04-28T10-15-30.123456__lyrics_generation.json
    ├── 2026-04-28T10-16-45.234567__music_generation.json
    └── ...
```

**Checklist：**
- [ ] LLMLogger 是单例，线程安全
- [ ] record_call() 后 calls.jsonl 有新行
- [ ] get_stats() 返回的 total_calls 和 by_prompt_key 统计正确
- [ ] 完整响应文件单独保存，不影响 calls.jsonl 大小

---

#### Day 5: 集成测试

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 编写单元测试 | 🔴 必做 | tests/llm/test_*.py | 覆盖率 > 80% |
| 编写集成测试 | 🔴 必做 | tests/integration/ | 3 个完整流程测试 |
| 验证文件结构 | 🟠 重要 | 手工验证 | 所有文件正确生成 |

**Test Cases：**

```python
# tests/llm/test_registry.py
- test_load_registry_yaml()
- test_get_default_version()
- test_get_metadata()
- test_load_template_with_variables()

# tests/llm/test_logger.py
- test_record_single_call()
- test_stats_aggregation()
- test_thread_safety()
- test_version_tracking()

# tests/llm/test_template.py
- test_render_simple_variables()
- test_render_conditional_blocks()
- test_render_default_values()
```

**验收标准：**
- ✅ `pytest tests/llm/` 全部通过
- ✅ 代码覆盖率 > 80%
- ✅ 没有线程竞态条件

---

### WEEK 2: 核心功能交付（LLM 客户端 + 编排）

#### Day 1-2: LLMClient + 请求/响应管理

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实现 `LLMClient.generate()` | 🔴 必做 | lib/llm/llm_client.py | 支持 MiniMax / OpenAI 双后端 |
| 实现 `RequestBuilder` | 🔴 必做 | lib/llm/request_builder.py | 构建格式化请求，包含系统提示 |
| 实现 `ResponseValidator` | 🔴 必做 | lib/llm/response_validator.py | 验证 JSON 格式、必需字段、值范围 |
| 实现重试机制 | 🔴 必做 | LLMClient._call_with_retry() | 指数退避，最多 3 次 |
| 实现 Token 计数 | 🔴 必做 | lib/llm/token_counter.py | 精确计算 Token 数 |

**LLMClient 核心流程：**

```python
response = llm_client.generate(
    prompt_key="lyrics_generation",
    context={"theme": "春天", "mood": "温柔"},
    temperature=0.85
)
# 返回 LLMResponse 对象，包含：
# - content: 生成的内容
# - metadata: LLMCallRecord（完整日志）
# - evaluation: 质量评分
```

**Checklist：**
- [ ] 第一次调用失败时，自动重试
- [ ] Token 消耗正确计算（支持中文 1.3x 倍数）
- [ ] 响应格式验证通过
- [ ] 自动调用 logger.record_call()

---

#### Day 3-4: PromptEvaluator + 版本控制

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实现 `PromptEvaluation` | 🟠 重要 | lib/llm/prompt_evaluator.py | 评分维度：相关性、完整性、创意性、可用性 |
| 实现 `PromptAnalyzer` | 🟠 重要 | lib/llm/prompt_analyzer.py | 支持版本对比、性能分析 |
| 实现版本自动选择 | 🟡 优化 | PromptRegistry.find_best_version() | 基于历史评分选择最优版本 |

**质量评分维度：**

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 相关性（Relevance） | 30% | 输出是否符合要求 |
| 完整性（Completeness） | 25% | 是否包含所有必需字段 |
| 创意性（Creativity） | 20% | 是否新颖、有趣 |
| 可用性（Usability） | 20% | 下游系统是否能处理 |
| 格式有效性 | 5% | JSON 是否正确 |

**Checklist：**
- [ ] PromptEvaluation 根据 prompt_key 自适应评分
- [ ] PromptAnalyzer 能对比版本，输出 delta 指标
- [ ] registry.yaml 中的 avg_quality 能自动更新

---

#### Day 5: 与现有 Scripts 集成 + E2E 测试

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 改造 generate_lyrics.sh | 🔴 必做 | scripts/generate_lyrics.py | 调用 LLMClient，自动日志 |
| 改造 generate_music.sh | 🔴 必做 | scripts/generate_music.py | 同上 |
| 改造 generate_scene_imgs.sh | 🔴 必做 | scripts/generate_scene_imgs.py | 同上 |
| 端到端测试 | 🔴 必做 | 真实流程 1 次 | 日志完整、成本透明 |

**集成示例：**

```python
# scripts/generate_lyrics.py (新)
#!/usr/bin/env python3

from lib.llm.llm_client import LLMClient
from lib.llm.llm_logger import LLMLogger
from lib.project_manager import ProjectManager
import json

def main(project_dir, theme, style, music_style, mood, language):
    pm = ProjectManager(project_dir)
    logger = LLMLogger(project_dir)
    client = LLMClient(logger=logger)
    
    context = {
        "theme": theme,
        "style": style,
        "music_style": music_style,
        "mood": mood,
        "language": language
    }
    
    pm.update_step("① lyrics", "running", "generating...")
    
    try:
        response = client.generate(
            prompt_key="lyrics_generation",
            context=context,
            temperature=0.85
        )
        
        # 保存内容
        with open(f"{project_dir}/audio/lyrics.txt", 'w') as f:
            f.write(response.content)
        
        # 记录元数据（title, song_length 等）
        if isinstance(response.metadata.evaluation, dict):
            quality = response.metadata.evaluation.get("overall_score", 0)
        else:
            quality = 8.0
        
        pm.update_step("① lyrics", "completed", f"quality={quality:.1f}")
        
    except Exception as e:
        pm.update_step("① lyrics", "failed", str(e))
        raise

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--style", default="动漫风")
    parser.add_argument("--music-style", default="流行")
    parser.add_argument("--mood", default="温柔")
    parser.add_argument("--language", default="中文")
    
    args = parser.parse_args()
    main(args.project_dir, args.theme, args.style, 
         args.music_style, args.mood, args.language)
```

**Checklist：**
- [ ] 旧的 shell 脚本可以继续工作（兼容模式）
- [ ] 新的 Python 脚本调用 LLMClient
- [ ] metadata/llm_calls/ 目录正确生成
- [ ] stats.json 显示正确的 Token 和成本

---

### WEEK 3: 编排和用户交互改进

#### Day 1-2: MVPipeline 新编排器 + 暂停点管理

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实现 `MVPipeline` 类 | 🔴 必做 | lib/mv_pipeline.py | 支持 11 步编排，包括暂停 |
| 实现暂停点管理 | 🔴 必做 | MVPipeline.pause_for_approval() | Step②、Step③ 暂停正常工作 |
| 实现用户输入处理 | 🔴 必做 | ProjectManager.get_user_choice() | 读取用户的选择（A/B/C） |

**MVPipeline 伪代码：**

```python
class MVPipeline:
    def run(self):
        # Step ① ② - 音频管道
        self._step_lyrics()
        self._step_music()
        
        # [暂停点 1] 是否继续
        UserInteraction.pause_for_approval(
            self.pm, "step_2_review",
            {"continue": "继续", "pause": "暂停"}
        )
        
        # [暂停点 2] 对齐方式选择
        UserInteraction.pause_for_approval(
            self.pm, "step_3_alignment",
            {
                "A": "Demucs 自动",
                "B": "手动 SRT",
                "C": "跳过对齐"
            }
        )
        
        # 根据选择执行对齐
        choice = self.pm.get_user_choice("step_3_alignment")
        if choice == "A":
            self._step_align_auto()
        elif choice == "B":
            self._step_align_manual()
        # ...
        
        # 后续步骤自动执行
        self._step_scene_analysis()
        self._step_images()
        # ...
```

**Checklist：**
- [ ] pause_for_approval() 设置 pending_approval 标记
- [ ] Agent 检测到标记后停止执行
- [ ] 用户回复选择后调用 approve()
- [ ] info.json 中记录了用户的选择

---

#### Day 3-4: UserInteraction 强制审批流程

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实现 `UserInteraction` 类 | 🔴 必做 | lib/user_interaction.py | 管理所有暂停点 |
| 实现 approve() 方法 | 🔴 必做 | UserInteraction.approve() | 更新 pending_approval 状态 |
| 更新 SKILL.md 交互规范 | 🔴 必做 | 文档更新 | Agent 按新规范执行 |

**强制暂停点示例（更新 SKILL.md）：**

```markdown
### Step ② 完成后的强制暂停

🎵 歌曲《春天的雨》已生成完毕（时长 180 秒）
📝 歌词已同步。

**请确认是否继续后续步骤？**
- 继续：进入 Step③ 对齐阶段
- 暂停：查看歌词/听音乐，稍后再说

> **强制规则**：在用户回复前，系统不会自动进入 Step③
> 这由 info.json 中的 `pending_approval` 机制保证

---

### Step ③ 对齐前的强制选择

现在进入 Step③ 对齐（约 5-10 分钟）

**请选择对齐方式：**
- **A. Demucs 自动（推荐）** 
  - 人声分离 + Whisper 对齐
  - 精度最高，自动处理
  
- **B. 手动 SRT**
  - 我有现成的字幕文件
  - 需要提供 .srt 文件路径

回复：A / B（或直接告诉我 SRT 文件路径）

> **强制规则**：未收到用户明确选择前，系统不会执行对齐
```

**Checklist：**
- [ ] SKILL.md 中明确描述了两个暂停点和选择方式
- [ ] Agent 正确解析了用户的选择（A/B/C/路径等）
- [ ] UserInteraction.approve() 更新了正确的字段

---

#### Day 5: 5 个完整 MV 生成 + 验收

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 执行 5 个完整流程 | 🔴 必做 | 5 个项目目录 | 每个都生成 final.mp4 |
| 验证日志完整性 | 🔴 必做 | 日志审查 | 所有 LLM 调用都有记录 |
| 验证成本透明 | 🔴 必做 | stats.json 检查 | 总 Token 和总成本清晰可见 |
| 验证暂停点 | 🔴 必做 | 用户交互测试 | Step② 和 Step③ 都能成功暂停和恢复 |
| 生成最终报告 | 🔴 必做 | llm_report.html | HTML 展示所有调用、统计、评分 |

**验收清单：**

```
5 个完整 MV：
├── MV_1: 春天 (动漫风, 流行, 温柔)
│   ├── ✅ final.mp4 生成
│   ├── ✅ metadata/llm_calls/ 完整
│   ├── ✅ stats.json 显示成本
│   └── ✅ llm_report.html 生成
├── MV_2: 星空 (国风, 民谣, 梦幻)
├── MV_3: 战争 (写实风, 摇滚, 热血)
├── MV_4: 童年 (水彩风, 爵士, 怀旧)
└── MV_5: (用户自选参数)
```

---

### WEEK 4 (可选): 监控和优化

| 任务 | 优先级 | 成果物 | 验收标准 |
|------|--------|--------|---------|
| 实时性能仪表盘 | 🟡 优化 | Web UI | 显示当前生成进度、Token 消耗 |
| 成本预测告警 | 🟡 优化 | 告警系统 | 接近预算时自动告警 |
| Prompt 自动优化 | 🟡 优化 | 建议引擎 | 基于评分推荐更优版本 |

---

## 工时估算

| 阶段 | 工时 | 人员 | 风险 |
|------|------|------|------|
| Week 1 | 40 小时 | 1 人 | ⚠️ Prompt 模板质量难以预测 |
| Week 2 | 40 小时 | 1 人 | ⚠️ 兼容性测试耗时 |
| Week 3 | 30 小时 | 1 人 | ✅ 相对风险低 |
| Week 4 (可选) | 20 小时 | 1 人 | ✅ 优化项 |
| **总计** | **130 小时** | **1 人** | **完成时间：3-4 周** |

---

## 关键风险和应对

| 风险 | 概率 | 影响 | 应对方案 |
|------|------|------|---------|
| **Prompt 质量不稳定** | 中 | 高 | 编写详细的示例（few-shot），迭代优化 |
| **Token 计数不精确** | 低 | 中 | 使用官方 API 反馈的 token count |
| **日志文件过大** | 中 | 低 | 定期清理老日志，只保留 7 天内 |
| **暂停点用户体验差** | 低 | 中 | 清晰的菜单提示和错误处理 |
| **兼容性问题** | 低 | 高 | 保持旧脚本可用，逐步迁移 |

---

## 成功指标（GO/NO-GO）

**绿灯条件（可上线）：**
- ✅ LLMLogger 记录率 100%
- ✅ ResponseValidator 通过率 > 95%
- ✅ 5 个完整流程都成功
- ✅ 日志清晰可读，HTML 报告美观
- ✅ 暂停点正常工作，用户能成功选择
- ✅ 没有数据丢失或竞态条件

**红灯条件（不可上线）：**
- ❌ LLMLogger 有数据丢失
- ❌ 日志文件损坏或无法读取
- ❌ Token 计数严重偏离实际
- ❌ 暂停点无法正常工作
- ❌ 有线程竞态或内存泄漏

---

## 后续优化空间

**已确认的后续工作（不在本期范围内）：**

1. **字级对齐**（Priority: 中）
   - 当前：行级对齐
   - 未来：用 WhisperX 实现字级时间戳，支持卡拉 OK 特效

2. **Prompt A/B 测试框架**（Priority: 中）
   - 自动对比两个 Prompt 版本的性能
   - 统计显著性检验

3. **自适应 Prompt 选择**（Priority: 低）
   - 根据 theme 和 style 自动选择最优的 Prompt 版本
   - 学习系统

4. **成本优化**（Priority: 低）
   - 缓存常用 Prompt 的响应
   - Token 压缩技术

---

## 文档更新清单

| 文档 | 更新内容 | 优先级 |
|------|---------|--------|
| SKILL.md | 更新交互规范，明确暂停点 | 🔴 必做 |
| README.md | 补充新的日志和成本透明说明 | 🟠 重要 |
| API 文档 | LLMClient / LLMLogger 的 API 文档 | 🟠 重要 |
| 故障排查指南 | 常见问题和调试方法 | 🟡 可选 |

---

## 配置示例

**setup.sh（一键初始化）：**

```bash
#!/bin/bash

echo "🚀 Music-to-MV LLM 系统初始化"

# 1. 创建目录结构
mkdir -p lib/llm
mkdir -p prompts/{lyrics,music,image/{base_character,scene_image},scene_analysis}
mkdir -p tests/{llm,integration}
mkdir -p metadata/llm_calls/responses

# 2. 复制模板
cp prompts/registry.example.yaml prompts/registry.yaml
cp lib/llm/.env.example lib/llm/.env

# 3. 安装依赖
pip install pyyaml jinja2 pytest

# 4. 验证结构
python3 -c "from lib.llm.prompt_registry import PromptRegistry; print('✅ Registry OK')"
python3 -c "from lib.llm.llm_logger import LLMLogger; print('✅ Logger OK')"

echo "✅ 初始化完成！"
echo "执行: pytest tests/ 运行测试"
```

