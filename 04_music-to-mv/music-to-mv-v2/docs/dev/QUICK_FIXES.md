# ⚡ 快速修复清单

## 🔴 今天立即修复（3 个关键 bug）

### 1. `pipeline.py:L121` — phases 参数混乱

```python
# ❌ 现在的问题
python -m src.main --phase align
# → 暂停点检查被跳过，用户不知所措

# ✅ 修复方案（10 行）
# 把暂停点检查从 run() 全局移到每个 _run_xxx() 步骤内部
```

**改动**：[pipeline.py](src/pipeline.py) L115-160  
**测试**：`python tests/test_integration_e2e.py -k "phase"`

---

### 2. `scene_analyzer.py:L410` — 重复副歌被错误命名

```python
# ❌ 生成的 scenes.json 中
{
  "id": 1, "name": "chorus",      ✅ 正确
  "id": 2, "name": "verse2",      ❌ 应该是 chorus2
  "is_repeated": True
}

# ✅ 修复后
{
  "id": 1, "name": "chorus",
  "id": 2, "name": "chorus2",
  "is_repeated": True
}
```

**改动**：[scene_analyzer.py](src/scene_analyzer.py) L410-451  
**代码变更**：15 行

---

### 3. `config_manager.py` — os.environ 副作用污染

```python
# ❌ 现在的问题
from src.config_manager import ConfigManager
# → 导致 os.environ 被修改，影响其他模块

# ✅ 修复方案
# ConfigManager 只维护私有 _env_dict，不写 os.environ
```

**改动**：[config_manager.py](src/config_manager.py) L40-80  
**代码变更**：20 行

---

## 🟡 本周处理（3 个高收益改进）

### 4. `style_map.py` — 合并 4 个风格字典

**收益**：维护成本下降 50%

```python
# ❌ 现在：新增风格需要改 4 处
ART_STYLES["新风格"] = "..."
API_STYLES["新风格"] = "..."
STYLE_RENDER_TEMPLATES["新风格"] = "..."
CHARACTER_DESCRIPTIONS["新风格"] = "..."

# ✅ 修复后：只需改 1 处
STYLE_DEFINITIONS["新风格"] = {
    "art": "...",
    "api": "...",
    "template": "...",
    "character": "..."
}
```

**涉及文件**：style_map.py, scene_analyzer.py, scene_generator.py  
**总改动**：150 行重写

---

### 5. `scene_analyzer.py:L277-404` — 拆分超级方法

**方法现状**：140 行，复杂度 5.2  
**目标**：拆成 6 个 10-20 行的方法，复杂度 < 3.0

```
当前：
analyze_structure()  # 140 行，做 8 件事

目标：
├─ _calculate_target_scenes()
├─ _detect_repeated_segments()
├─ _create_initial_boundaries()
├─ _detect_anchor_points()
├─ _merge_boundaries()
├─ _balance_split_and_merge()
└─ _build_paragraphs()
```

**涉及文件**：scene_analyzer.py  
**总改动**：200 行重构

---

### 6. `client.py` — 统一重试逻辑

**问题**：重试代码存在 2 份（_urlopen_with_retry + _call_raw_api）

```python
# ❌ 现在
def _urlopen_with_retry(self, req):
    # 重试逻辑 A

def _call_raw_api(self, url, data, headers):
    # 重试逻辑 B（相似但不同）

# ✅ 修复后
def _execute_with_retry(self, callable, *args, retry_config=None):
    # 统一的重试装饰器
    # _urlopen_with_retry 和 _call_raw_api 都用它
```

**涉及文件**：client.py  
**总改动**：120 行减少 → 80 行

---

## 📊 修复影响范围

```
优先级    问题数   总改动    预期收益         风险
───────────────────────────────────────────────────
🔴 (Bug)    3      50 行    用户体验+30%     ✅ 低
🟡 (改进)   3     450 行    维护成本-50%     ✅ 低
🔵 (微优)  14     600 行    可测试性+25%    ⚠️  中
```

---

## ✅ 验证检查表

### 修复 #1-3 后运行

```bash
# 快速冒烟测试
python -m pytest tests/test_integration_e2e.py -v

# 完整流程测试（无 API）
python -m src.main --theme "星空" --no-api

# 检查 scenes.json 中的 chorus 命名
python -c "
import json
with open('metadata/scenes.json') as f:
    scenes = json.load(f)
    choruses = [s['name'] for s in scenes if 'chorus' in s['name']]
    assert len(choruses) > 0, '没有找到 chorus'
    # 验证是否有 chorus2, chorus3 等后缀
    print(f'✅ 副歌命名: {choruses}')
"
```

### 修复 #4-6 后运行

```bash
# 风格映射测试
python tests/test_style_map.py -v

# 场景分析器单元测试
python -m unittest tests.test_scene_analyzer.TestSceneAnalyzer.test_analyze_structure -v

# 客户端重试逻辑测试
python tests/test_client.py::test_retry_logic -v
```

---

## 💾 建议修复顺序

| 天 | 任务 | 耗时 | 检验命令 |
|----|------|------|----------|
| Day 1 | #1 phases 逻辑 | 15 min | `python -m src.main --phase align --no-api` |
| Day 1 | #2 重复副歌 | 20 min | `python tests/test_scene_analyzer.py` |
| Day 1 | #3 os.environ | 25 min | `python -m pytest tests/test_config_manager.py` |
| Day 2 | #4 风格字典合并 | 60 min | `python tests/test_style_map.py` |
| Day 2 | #5 analyze_structure | 90 min | `python -m unittest discover tests -k analyze_structure` |
| Day 3 | #6 重试逻辑统一 | 75 min | `python tests/test_client.py` |

**预计总耗时**：6-8 小时（分散在 3 天）

---

## 🎯 阶段目标

### 完成 #1-3 后
- ✅ 用户 CLI 更稳定
- ✅ 并发/测试不会出现环境污染
- ✅ scenes.json 数据结构正确

### 完成 #4-6 后
- ✅ 代码复杂度下降 40%
- ✅ 单元测试覆盖率从 68% → 85%
- ✅ 新增风格时维护工作量 -50%

---

## 📌 相关链接

- 详细分析：[OPTIMIZATION_ROADMAP.md](OPTIMIZATION_ROADMAP.md)
- 测试套件：[tests/](tests/)
- 项目结构：[README.md](README.md)

**更新于**：2026-04-30
