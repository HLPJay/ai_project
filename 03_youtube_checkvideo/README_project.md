这里已经进行了原型思考，开始考虑如何节省token以及基于更上层进行管理。





不关注产品功能，从claude的使用角度上来说，现在我们是定义了claude.md和plan.md分布对约束和目标进行了定义，从这个角度上说 还有那些可优化的？

4月11日

识别了文档结构缺陷并提出优化策略。

从 Claude Code 的实际工作方式来看，现在的方案有几个结构性问题。

------

**问题一：CLAUDE.md 职责不清**

现在 CLAUDE.md 把三种不同性质的内容混在一起：

```
每次都需要读的：Rules、Auth 约定
只在特定任务需要：DB Schema、API 接口表
永远不变的背景：Stack、目录结构
```

Claude Code 每次启动都全量加载 CLAUDE.md，但大部分内容和当前任务无关。可以拆成三个文件：

```
CLAUDE.md        ← 只放约束和规范（每次必读，控制在30行内）
ARCHITECTURE.md  ← 目录结构、DB Schema、API 表（按需引用）
CONVENTIONS.md   ← 代码风格、命名规范（按需引用）
```

------

**问题二：PLAN.md 没有状态**

现在 PLAN.md 执行完一个 Task 之后没有变化，Claude Code 下次不知道哪些已完成、哪些待做，需要你手动告诉它。

更好的做法是在每个 Task 前加状态标记，执行完后 Claude Code 自己更新：

markdown

```markdown
- [ ] Task 1.1 · config.py
- [x] Task 1.2 · schemas.py       ← 已完成
- [ ] Task 1.3 · 日期格式修复
```

------

**问题三：Task 规格缺少验证指令**

现在每个 Task 描述了做什么，但没有说怎么验证做对了。Claude Code 执行完不知道是否成功，你也不知道该运行什么命令检查。

每个 Task 应该带一条可执行的验收命令：

markdown

```markdown
### Task 1.1 · config.py
...
VERIFY: python -c "from config import settings; print(settings.PORT)"
```

------

**问题四：tasks/ 目录比单一 PLAN.md 更适合 Claude Code**

单一 PLAN.md 随着项目增长会越来越大，每次执行任何任务都要加载全部内容。

更好的结构：

```
tasks/
├── 1.1-config.md
├── 1.2-schemas.md
├── 1.3-date-fix.md
├── 2.1-youtube-api.md
└── ...
```

执行时只加载对应文件：`claude "执行 tasks/1.3-date-fix.md"`

------

**把这些改进落实成新的文件结构：**

Created 7 files, ran 3 commands, read a file

------

**三个核心优化点总结**

**① CLAUDE.md 从 100 行压缩到 21 行**

只留约束和禁止改动的文件，背景知识全部移到 `ARCHITECTURE.md`。Claude Code 每次启动只加载 21 行，需要查结构时再引用 `ARCHITECTURE.md`。

**② PLAN.md 拆成 `tasks/` 目录**

每个任务一个文件，执行时只加载当前任务。Task 文件的格式统一为：背景 → 精确改动 → 可运行的验收命令 → 完成后更新 STATUS.md。验收命令是关键——Claude Code 执行完能自己跑一遍确认结果。

**③ `tasks/STATUS.md` 追踪状态**

Claude Code 执行完任务后把 `[ ]` 改成 `[x]`，下次启动时通过读 STATUS.md 知道从哪里继续，不需要你手动告诉它进度。

**使用方式**

bash

```bash
# 查看当前进度
claude "读取 tasks/STATUS.md，告诉我下一个待执行的 Task 是哪个"

# 执行单个任务（只加载必要上下文）
claude "执行 tasks/1.3-date-fix.md"

# plan 模式：先让 Claude 规划再确认
claude --plan "执行 tasks/2.1-youtube-api.md"
```



Radar v2

ZIP 

目前这个阶段，还有那些可以优化的，这里本质上还是控制大模型的记忆模块吧

4月11日

分析了LLM记忆层级结构与上下文工程优化空间。

对，你抓住了本质。`CLAUDE.md`、`ARCHITECTURE.md`、`tasks/` 本质上是在做**外部记忆工程**——补偿 Claude Code 跨会话没有持久记忆的缺陷。

用认知科学的记忆分类来审视现在的方案：

```
记忆类型        对应文件              现状
─────────────────────────────────────────────
程序性记忆      CLAUDE.md            ✅ 已有（规则/约束）
语义记忆        ARCHITECTURE.md      ✅ 已有（知识/结构）
工作记忆        tasks/1.x-task.md    ✅ 已有（当前任务）
状态记忆        tasks/STATUS.md      ✅ 已有（进度）
错误记忆        ——                   ❌ 缺失
决策记忆        ——                   ❌ 缺失
情节记忆        ——                   ❌ 缺失
```

缺失的三类是真正的问题。

------

**❌ 错误记忆——GOTCHAS.md**

Claude Code 犯了一个错误，你纠正了，下次新会话它会重犯同样的错误。现在没有地方记录「这个坑我们踩过了」。

markdown

```markdown
# GOTCHAS.md

## yt-dlp 日期格式
upload_date 返回 '20250409'，不是 ISO 格式。
必须转换：f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
已在 Task 1.3 修复，禁止回退。

## DeepSeek 响应有时带 ```json 包裹
generate_report.py 的 _parse_json() 已处理，
不要在其他地方直接 json.loads(response)。

## faster-whisper 在 Windows 需要手动加 dll 路径
见 local_transcript.py 顶部，不要删除那段 os.add_dll_directory()。
```

`GOTCHAS.md` 加入 `CLAUDE.md` 的必读引用，每次会话都加载。

------

**❌ 决策记忆——DECISIONS.md**

Claude Code 看到 SQLite 可能觉得「应该换成 PostgreSQL」，看到无框架前端可能想「应该用 React」。没有记录当初为什么这样选，它会反复挑战已定的决策。

markdown

```markdown
# DECISIONS.md

## 为什么用 SQLite 不用 PostgreSQL
单机部署，Windows 环境，无运维成本。
数据量预估单用户千级视频，FTS5 够用。
禁止建议换数据库。

## 为什么前端不用 React
减少构建工具依赖，Claude Code 直接改 HTML 即可部署。
禁止引入 npm/vite/webpack。

## 为什么字幕用两级降级而不只用 Whisper
youtube-transcript-api 速度快、无 GPU 消耗。
Whisper 只在没有官方字幕时启用，不要合并两个路径。
```

------

**❌ 情节记忆——任务日志**

每个 Task 执行后实际发生了什么、遇到了什么问题，现在完全丢失。下次相关任务时 Claude Code 没有上下文。

在 Task 文件末尾加一个执行日志区块，Claude Code 完成后填写：

markdown

```markdown
## 执行记录

**执行时间**：2025-04-11  
**实际改动**：修改了 _fetch_meta() 第 87 行  
**遇到的问题**：yt-dlp 在某些视频返回 None，加了空值判断  
**副作用**：无
```

------

**还有一个更深层的问题：上下文污染**

当前 Task 文件会让 Claude Code 去读对应的源文件，但源文件可能很大。比如执行 Task 3.3（index.html 加反馈按钮）时，Claude Code 会把整个 467 行的 `index.html` 加载进上下文。

解法是在 Task 文件里指定精确的读取范围：

markdown

```markdown
## 需要读取的上下文

- `templates/index.html` 第 280-320 行（.dr-acts 区域）
- `schemas.py` FeedbackBody 定义
- 不需要读取其他文件
```

这样 Claude Code 只用 `view` 工具读指定行，不加载全文件。

------

**整合后的完整记忆架构**

```
始终加载（每次会话）：
  CLAUDE.md          ← 约束 + 禁止改动
  GOTCHAS.md         ← 已知坑，防重复犯错

按需加载：
  ARCHITECTURE.md    ← 查结构时引用
  DECISIONS.md       ← 质疑设计选择时引用
  tasks/STATUS.md    ← 查进度时引用

任务执行时加载：
  tasks/1.x-task.md  ← 当前任务规格（含精确行号）
```

**使用方式变化**

bash

```bash
# 现在
claude "执行 tasks/1.3-date-fix.md"

# 优化后——Claude 会自动加载 GOTCHAS 和 DECISIONS 避免踩坑
claude "读取 CLAUDE.md 和 GOTCHAS.md，然后执行 tasks/1.3-date-fix.md，
        完成后更新 tasks/1.3-date-fix.md 的执行记录和 tasks/STATUS.md"
```

要不要现在把 `GOTCHAS.md` 和 `DECISIONS.md` 补进去，把当前项目里已经踩过的坑都记录下来？