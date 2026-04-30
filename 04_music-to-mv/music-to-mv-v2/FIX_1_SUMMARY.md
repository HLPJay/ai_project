# ✅ 修复 #1 完成：pipeline.py phases 逻辑混乱

**日期**：2026-04-30  
**难度**：🟢 低  
**耗时**：15 分钟  
**影响**：用户 CLI 体验

---

## 📋 问题描述

当用户指定 `--phase align` 时（跳过歌词和音乐步骤，只做对齐），暂停点检查仍然会被执行，这会让用户看到"确认歌词和音乐"的提示，尽管他们并未生成歌词和音乐。

### 修复前的问题代码

```python
def run(self, phases: str = None):
    phases = phases or "all"

    if phases in ("all", "init"):
        self._run_lyrics_and_music()

    if phases in ("all", "init", "align"):  # ❌ 问题：为什么包含 "align"?
        self._check_and_pause_step2()       # Step② 的暂停点被全局管理
        if self.pm.check_interrupt():
            return

    if phases in ("all", "align"):
        self._run_alignment()
        # ...
```

**场景**：用户运行 `python -m src.main --project myproject --phase align`
- 跳过 Step ①-② ✓ 正确
- 但仍然执行 Step② 的暂停点 ❌ 不合理

---

## ✅ 修复方案

**原则**：每个步骤内部管理自己的暂停点检查，而不是在全局 `run()` 方法中

### 修复后的代码

1. **简化 run() 方法的逻辑**
```python
def run(self, phases: str = None):
    """运行流水线
    
    phases:
      - None 或 "all": 完整流程
      - "init": 只运行 Step ①-②
      - "align": 只运行 Step ③
      - "produce": 只运行 Step ④-⑧
      - "export": 只运行 Step ⑨-⑪
    
    注意：每个步骤内部管理自己的暂停点检查，不在此处全局处理
    """
    phases = phases or "all"

    # 步骤 ①-②: 歌词 + 音乐（含内部暂停点检查）
    if phases in ("all", "init"):
        self._run_lyrics_and_music()
        if self.pm.check_interrupt():
            return

    # 步骤 ③: 歌词对齐（含内部暂停点检查）
    if phases in ("all", "align"):
        self._run_alignment()
        if self.pm.check_interrupt():
            return

    # ...其他步骤
```

2. **将暂停点检查移到 _run_lyrics_and_music() 内部**
```python
def _run_lyrics_and_music(self):
    """运行 Step ① 歌词 + Step ② 音乐，含暂停点检查
    
    流程：
      1. 生成歌词 (Step ①)
      2. 生成音乐 (Step ②)
      3. 展示暂停点，让用户确认（仅非自动模式）
    """
    if not self.pm.is_step_completed("① lyrics"):
        self._step_lyrics()

    if not self.pm.is_step_completed("② music"):
        self._step_music()

    # 在 Step② 完成后显示暂停点（仅当不是自动模式时）
    self._check_and_pause_step2()
```

---

## 📊 修复对比

| 场景 | 修复前 | 修复后 | 备注 |
|------|--------|--------|------|
| `--phase init` | ① ② + 暂停 ✓ | ① ② + 暂停 ✓ | 不变 |
| `--phase align` | ③ + 暂停 ❌ | ③ ✓ | **修复：跳过不相关的暂停点** |
| `--phase all` | ① ② + 暂停 + ③ + ... ✓ | ① ② + 暂停 + ③ + ... ✓ | 不变 |
| `--phase produce` | 跳过 ① ② ✓ | 跳过 ① ② ✓ | 不变 |

---

## 🧪 验证测试

所有 4 个测试均通过：

```
✓ 测试 1: --phase init 包含暂停点检查
  ✅ _run_lyrics_and_music 被调用一次

✓ 测试 2: --phase align 跳过歌词/音乐的暂停点
  ✅ _run_lyrics_and_music 被跳过
  ✅ _run_alignment 被调用一次

✓ 测试 3: --phase all 执行完整流程
  ✅ _run_lyrics_and_music 被调用
  ✅ _run_alignment 被调用
  ✅ _run_produce 被调用

✓ 测试 4: 暂停点检查在 _run_lyrics_and_music 内部
  ✅ _run_lyrics_and_music 内部包含 _check_and_pause_step2()
  ✅ run() 方法中已删除全局暂停点检查
```

---

## 📝 修改文件

| 文件 | 修改行 | 修改说明 |
|------|--------|---------|
| `src/pipeline.py` | L69-121 | 简化 `run()` 方法的 phases 逻辑，删除全局暂停点检查 |
| `src/pipeline.py` | L127-142 | 将 `_check_and_pause_step2()` 移到 `_run_lyrics_and_music()` 内部 |

**总改动**：22 行（主要是注释完善）

---

## ✨ 优点

1. **逻辑清晰**：每个步骤自己管理自己的暂停点，遵循单一职责原则
2. **用户体验**：不会看到不相关的暂停点提示
3. **易于维护**：后续添加新步骤时，只需在步骤方法内部加暂停点，不需要修改全局 `run()` 方法
4. **向后兼容**：完整流程 (`--phase all`) 的行为完全相同

---

## 🔗 相关代码

- [修复前的 phases 逻辑混乱对比](OPTIMIZATION_ROADMAP.md#优先级-1️⃣-bug-修复-1️⃣-pipelinepy121--phases-逻辑混乱)
- [所有优化的快速清单](QUICK_FIXES.md#1-pipelineypyl121--phases-参数混乱)

---

## ✅ 下一步

进行修复 #2：[scene_analyzer.py:L410 — 重复副歌命名 bug](FIX_2_PLAN.md)

**预计耗时**：20 分钟
