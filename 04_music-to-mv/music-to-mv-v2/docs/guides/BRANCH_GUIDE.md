# 🌳 分支管理指南

## 分支策略

本项目采用 **功能分支模式**，将不同优先级的任务隔离在独立的分支中，完成后合并回 `dev` 分支。

---

## 📌 当前分支概览

### 🔴 立即开始（当前）

```
feat/ab-testing-phase1
├─ 📝 任务：A/B 测试框架 Phase 1（歌词 Prompt 对比）
├─ ⏱️ 时间：1-2 周
├─ 📋 任务清单：见 ROADMAP.md 第 22-29 行
├─ 🎯 目标：
│  ├─ 扩展 registry.yaml A/B 配置
│  ├─ 扩展 ProjectManager
│  ├─ 新建歌词评分器 (simple_scorer.py)
│  ├─ 修改 pipeline.py 集成 A/B
│  ├─ 新建报告工具
│  └─ 收集 20-30 个测试样本
└─ ✅ 合并到：dev → 测试 → main
```

### 🟠 第 3-4 周

```
feat/type-annotations
├─ 任务：补充类型标注 + mypy 检查
├─ 时间：1 周
├─ 文件：pipeline.py, scene_generator.py, exporter.py
└─ 合并到：dev

chore/performance-tuning
├─ 任务：性能优化（并行生图、缓存、Whisper 选项）
├─ 时间：1 周
└─ 合并到：dev
```

### 🔵 第 5+ 周

```
feat/ab-testing-phase2
├─ 任务：A/B 测试 Phase 2（图片参考图对比）
├─ 时间：2 周
└─ 合并到：dev

chore/reliability-improvements
├─ 任务：可靠性改进（重试策略、错误恢复）
├─ 时间：2-3 周
└─ 合并到：dev
```

### 📌 主要分支

```
dev      → 开发集成分支，所有 feature 的汇聚点
main     → 生产稳定分支
```

---

## 🚀 日常工作流

### 1️⃣ 现在开始 A/B 测试 Phase 1

```bash
# 确认在正确的分支上
git branch -v
# * feat/ab-testing-phase1  3dc95eb 清理错误提交

# 开始编码
# 根据 ROADMAP.md 的任务清单逐个完成
```

### 2️⃣ 完成任务后提交

```bash
# 查看改动
git status

# 暂存文件
git add src/ab_testing/ prompts/registry.yaml .env.example

# 提交（格式：类型(模块): 描述）
git commit -m "feat(ab-testing): 实现 Phase 1 框架和歌词评分器

- 扩展 registry.yaml 支持 A/B 配置
- 新建 simple_scorer.py 歌词评分
- 修改 pipeline.py 集成 A/B 分配
- 新建报告工具 ab_report_simple.py

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

### 3️⃣ 准备合并回 dev

```bash
# 确保本地 dev 是最新的
git checkout dev && git pull origin dev

# 切回 feature 分支做 rebase（可选但推荐）
git checkout feat/ab-testing-phase1
git rebase dev

# 如果有冲突，解决冲突后
git add <冲突文件>
git rebase --continue

# 推送到远程
git push origin feat/ab-testing-phase1
```

### 4️⃣ 创建 Pull Request

在 GitHub 上：
- 对比分支：`feat/ab-testing-phase1` → `dev`
- 标题：`feat: A/B 测试框架 Phase 1 - 歌词 Prompt 对比`
- 描述：
  ```
  ## 概述
  实现 A/B 测试框架 Phase 1，支持歌词生成 Prompt 版本对比。
  
  ## 改动
  - 扩展 registry.yaml A/B 配置
  - ProjectManager 新增 A/B 信息记录
  - 实现简单评分器
  - 集成到 pipeline 自动分配版本
  - 新建报告生成工具
  
  ## 测试
  - 生成 20-30 个 MV 验证数据记录正确
  - 验证报告工具正确统计版本评分
  
  ## 关联
  - Closes #ROADMAP
  ```

---

## 🔄 分支切换

### 查看所有分支

```bash
git branch -a
```

### 切换到其他分支

```bash
# 立即开始的分支
git checkout feat/ab-testing-phase1

# 3-4 周的分支
git checkout feat/type-annotations
git checkout chore/performance-tuning

# 主分支
git checkout dev
git checkout main
```

### 创建新分支（如需）

```bash
# 从 dev 创建新分支
git checkout dev
git pull origin dev
git checkout -b feat/new-feature

# 或从 main 创建热修复分支
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug
```

---

## 📊 分支状态查看

### 查看当前分支

```bash
git status
```

### 查看分支对比

```bash
# 看本分支比 dev 多了什么提交
git log dev..HEAD --oneline

# 看 dev 比本分支多了什么提交
git log HEAD..dev --oneline

# 看两个分支的代码差异
git diff dev..HEAD
```

### 查看分支的提交历史

```bash
git log --oneline --graph --all
```

---

## ⚠️ 常见问题解决

### 问题 1：我在错误的分支上做了改动

```bash
# 查看当前分支
git branch -v

# 如果改动还没提交，先暂存
git stash

# 切到正确的分支
git checkout feat/ab-testing-phase1

# 恢复改动
git stash pop
```

### 问题 2：本地分支落后于远程

```bash
# 更新远程追踪分支
git fetch origin

# 查看差异
git log HEAD..origin/feat/ab-testing-phase1

# 更新本地分支
git pull origin feat/ab-testing-phase1
```

### 问题 3：想放弃当前分支的改动

```bash
# 查看改动
git status

# 放弃未暂存的改动
git checkout -- <文件>

# 或放弃所有改动
git reset --hard HEAD
```

### 问题 4：想回到 dev 分支的某个版本

```bash
# 创建新分支从 dev 的某个点
git checkout -b new-branch dev~5  # 回到 5 个提交前

# 或查看历史后选择
git log dev --oneline
git checkout -b new-branch <commit-id>
```

---

## 📝 提交信息规范

使用以下格式确保清晰的提交历史：

```
<type>(<scope>): <subject>

<body>

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

### Type 类型

- `feat`: 新功能（对应 feat/ 分支）
- `fix`: 修复 Bug
- `chore`: 杂务（配置、依赖等，对应 chore/ 分支）
- `refactor`: 代码重构
- `docs`: 文档更新
- `test`: 测试
- `perf`: 性能优化

### Scope 作用域

- `ab-testing`: A/B 测试框能
- `type-annotations`: 类型标注
- `performance`: 性能优化
- `reliability`: 可靠性
- `pipeline`: Pipeline 相关
- 等等

### 例子

```
feat(ab-testing): 实现歌词评分器
chore(performance): 改进并行生图配置
docs: 更新 README 导航
```

---

## 🎯 检查清单

开始工作前：
- [ ] 已确认在正确的分支（`git branch -v`）
- [ ] 已从 dev 拉取最新代码（`git pull origin dev`）
- [ ] 已查看 ROADMAP.md 了解任务清单

完成任务后：
- [ ] 已验证改动正确（`git diff`）
- [ ] 已提交代码（`git commit`）
- [ ] 已推送到远程（`git push origin <branch-name>`）
- [ ] 已在 GitHub 创建 PR

---

## 📞 需要帮助？

常用命令快速查询：

```bash
# 查看当前分支状态
git status

# 查看改动详情
git diff

# 查看已暂存的改动
git diff --cached

# 查看提交历史
git log --oneline -10

# 查看特定文件的改动历史
git log --oneline <file>

# 切换分支
git checkout <branch-name>

# 创建新分支
git checkout -b <new-branch>

# 删除本地分支
git branch -D <branch-name>

# 删除远程分支
git push origin --delete <branch-name>
```

---

**Happy Coding! 🎉**
