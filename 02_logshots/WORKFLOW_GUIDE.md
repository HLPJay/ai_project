# LongShot × Claude Code 协作工作流指南

## 文件结构总览

```
longshot/
├── CLAUDE.md                  ← 项目宪法（~800 tokens，每次自动加载）
├── docs/
│   ├── milestone-1.md         ← M1 详细需求（~600 tokens）
│   ├── milestone-2.md         ← M2 详细需求（~700 tokens）
│   ├── milestone-3.md         ← M3 详细需求（~800 tokens）
│   ├── milestone-4.md         ← M4 详细需求（~900 tokens）
│   ├── milestone-5.md         ← M5 详细需求（~800 tokens）
│   ├── milestone-6.md         ← M6 详细需求（~700 tokens）
│   ├── milestone-7.md         ← M7 详细需求（~700 tokens）
│   └── tech-decisions.md      ← 决策日志（逐步增长）
├── src/                       ← 代码（Claude Code 直接读写）
├── tests/
└── ...
```

## 核心原理：为什么这样拆分

### 之前（单个大 Prompt）
```
每次对话 = 完整 Prompt（3000 tokens）+ 全部历史对话
→ 第 20 轮对话时：3000 + 20 × 平均 1500 = 33000 tokens
→ 大量 token 浪费在"不相关模块的需求描述"上
→ 上下文窗口被填满后，AI 开始遗忘早期约束
```

### 现在（分层 Prompt + Claude Code）
```
每次对话 = CLAUDE.md（800 tokens）+ 当前 milestone（~700 tokens）+ 当前任务
→ 始终 ~1500 tokens 的固定上下文开销
→ AI 每轮都能完整看到项目规则和当前任务
→ 不会因为上下文膨胀而遗忘约束
```

Token 节省估算：一个 Milestone 开发周期约 30 轮对话，
旧方案累积 ~90000 tokens，新方案 ~50000 tokens，**节省约 40%**。

---

## 使用步骤

### 第 0 步：安装 Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

### 第 1 步：初始化项目

```bash
mkdir longshot && cd longshot
# 把 CLAUDE.md 放在项目根目录
# 把 docs/ 目录放在项目根目录
git init
```

### 第 2 步：启动 Claude Code

```bash
claude
```

Claude Code 启动时会**自动读取项目根目录的 CLAUDE.md**，
这就是你的"项目宪法"，它会在每一轮对话中自动作为上下文。

### 第 3 步：开始 Milestone 1

直接给 Claude Code 下达指令：

```
读取 docs/milestone-1.md，按照交付清单开始搭建项目骨架。
先从 CMakeLists.txt 和 vcpkg.json 开始。
```

**关键点：让 Claude Code 主动读取 milestone 文件，而不是你把内容粘贴给它。**
Claude Code 可以直接访问项目文件系统，它会自己 `cat docs/milestone-1.md` 读取内容。

### 第 4 步：逐任务推进

每次只给一个具体任务：

```
# 好的指令 ✓（具体、单一、有验证标准）
实现 src/app/config.h 和 config.cpp，按照 milestone-1.md 中的配置项表格定义所有 key

# 不好的指令 ✗（太大、太模糊）
把 Milestone 1 全部完成
```

### 第 5 步：Milestone 切换

当一个 Milestone 的所有交付清单打勾后：

```
Milestone 1 已完成。请读取 docs/milestone-2.md，
我们开始 CaptureCore 模块的开发。先从接口定义开始。
```

同时更新 CLAUDE.md 底部的进度清单：
```markdown
- [x] Milestone 1: 项目骨架      ← 更新为 x
- [ ] Milestone 2: CaptureCore
```

### 第 6 步：记录技术决策

开发过程中遇到技术选型，让 Claude Code 记录：

```
把刚才关于"行哈希 vs 模板匹配"的决策记录到 docs/tech-decisions.md
```

---

## 常用指令模板

### 开始新模块
```
读取 docs/milestone-{N}.md，按交付清单 {N.X} 实现 {具体文件}。
```

### 要求代码审查
```
检查 src/core/stitcher/overlap_detector.cpp，
对照 docs/milestone-3.md 中的算法描述，看是否有遗漏。
```

### 请求技术对比
```
我在 {A 方案} 和 {B 方案} 之间犹豫，
请对比两者的性能/复杂度/维护成本，给出建议。
```

### 修复 Bug
```
编译报错：{错误信息}。请分析原因并修复。
```

### 阶段验收
```
对照 docs/milestone-{N}.md 的"完成标准"清单，
逐项检查当前代码是否满足，列出未满足的项。
```

---

## 注意事项

### CLAUDE.md 的维护
- CLAUDE.md 是活文档，随项目推进应该更新
- 主要更新点：进度清单、新增的全局约束
- 不要在 CLAUDE.md 中加入太多细节（保持 < 1000 tokens）
- 细节放在对应的 milestone-{N}.md 中

### 会话管理
- Claude Code 的每个 session 是独立的，退出后重新进入会丢失对话历史
- 但 CLAUDE.md 会重新加载，所以核心约束不会丢
- 如果一个 milestone 跨多个 session，在新 session 开头说：

```
继续 Milestone 3 的开发。上次已完成 3.1 接口定义和 3.2 重叠检测。
现在开始 3.3 Sticky Header/Footer 检测。
```

### 何时开新 Session
- 完成一个 Milestone 后，开新 session（清理上下文）
- 遇到 AI 开始"遗忘"之前的约束时，开新 session
- 长时间未操作后回来，开新 session

### 与 Claude Chat（Web）的配合
- 架构级讨论、技术调研 → 用 Claude Chat（本界面）
- 具体编码实现 → 用 Claude Code（终端）
- 两个场景不需要共享上下文，CLAUDE.md 是它们的共同锚点




# 和其他ai对话建议的优化，在claude.md中优化
## AI 执行循环（必须遵守）

    你必须按以下循环执行：

    1. 读取“当前进度”
    2. 只关注当前 Milestone
    3. 先输出设计（不写代码）
    4. 等我确认
    5. 再输出代码（最小可运行）
    6. 自检是否符合架构规则
    7. 更新“当前进度”
    8. 进入下一个任务

    禁止：
    - 跳步骤
    - 一次输出多个模块
    - 未确认直接写代码

-----》这里用的这个，多了也不好
## AI 执行模式

你必须严格按以下模式工作，违反时请自我纠正：

1. **先分析任务** → 给出设计方案（不写代码）
2. **等我确认后** → 再写代码
3. **每次只实现一个类或一个模块**
4. 所有代码必须：可编译、有最小示例、附带对应单元测试
5. 不允许一次性输出大量代码

### AI 必须主动拒绝执行（先澄清）的情况

- 任务涉及 2 个以上模块同时修改
- 需求与架构规则或层级依赖规则冲突
- 实现方案有 2 种以上合理选择 且影响后续设计
- 任务属于排除项（Out of Scope）

## 测试规范

- 每个核心类**交付时必须附带最小单元测试**，不附带则视为未完成
- 测试框架：**Qt Test**（已内置，不引入 gtest / catch2）
- Mock 使用**手写 Mock 类**（实现纯虚接口），不引入 gmock
- 测试**不得依赖文件系统**，图像数据用内存构造（`QImage` 内存填充）
- 测试**不得依赖网络或真实窗口句柄**
- 测试文件命名：`test_<模块名>.cpp`，放在 `tests/` 目录


## 编码规范

### 命名与风格

- C++17 标准，启用 `-Wall -Wextra -Werror`
- 类命名：PascalCase（`CaptureCore`）
- 方法命名：camelCase（`startCapture`）
- 文件命名：snake_case（`capture_core.h` / `capture_core.cpp`）
- 所有公共方法必须有 Doxygen 注释
- Include guard 统一使用 `#pragma once`，禁止其他形式

### 内存与异常

- 禁止裸 `new` / `delete`，统一使用 `std::unique_ptr` / `std::shared_ptr`
- 禁止裸 `catch(...)`，所有异常有明确类型
- 禁止使用 `QMutex` 直接操作，统一封装为 RAII 的 `QMutexLocker`

### 字符串与日志

- 字符串统一使用 `QString`，与标准库交互时用 `.toStdString()`
- 日志使用 `qDebug` / `qInfo` / `qWarning` / `qCritical`，发布版本通过 `QLoggingCategory` 过滤

### 信号槽

- 信号槽连接**禁止**使用 `SIGNAL()` / `SLOT()` 字符串形式
- 必须使用函数指针形式：
```cpp
// ✅ 正确
connect(engine, &ICaptureEngine::frameReady, this, &MainWindow::onFrameReady);

// ❌ 错误
connect(engine, SIGNAL(frameReady(QImage)), this, SLOT(onFrameReady(QImage)));
```
### 头文件

- 禁止在头文件中写非 `inline` 的函数实现
- 模板实现统一放在 `.hpp` 文件中并在头文件末尾 include


## 测试规范

- 每个核心类**交付时必须附带最小单元测试**，不附带则视为未完成
- 测试框架：**Qt Test**（已内置，不引入 gtest / catch2）
- Mock 使用**手写 Mock 类**（实现纯虚接口），不引入 gmock
- 测试**不得依赖文件系统**，图像数据用内存构造（`QImage` 内存填充）
- 测试**不得依赖网络或真实窗口句柄**
- 测试文件命名：`test_<模块名>.cpp`，放在 `tests/` 目录




## 架构规则

- 主线程仅处理 UI，所有截屏/拼接操作在 `QThread` 工作线程中执行
- 模块间通过 Qt 信号槽通信，**禁止直接跨模块函数调用**
- 平台相关代码统一放在 `platform/` 目录，通过编译宏隔离（`Q_OS_WIN` / `Q_OS_MACOS`）
- 所有对外暴露的接口使用纯虚基类（Interface），便于测试和替换

### 层级依赖规则（单向，禁止反向依赖）

```
ui/   →   core/   →   platform/
ui/   →   utils/
```

- `core/` **禁止** include `ui/` 的任何头文件
- `ui/` **禁止** include `platform/` 的任何头文件，只能通过 `core/` 接口访问
- `utils/` 不得依赖 `core/` 或 `ui/`

### 接口规则

- 每个核心模块必须**先定义 `i_xxx.h`（纯虚接口）**，再写实现类，不得跳过
- 实现类的头文件禁止被 `ui/` 层直接 include，只能 include 接口头文件
- 工厂函数统一放在对应模块目录的 `factory.h` 中
- 示例结构：

```cpp
// ✅ 正确：ui 层只看到接口
#include "core/capture/i_capture_engine.h"
std::unique_ptr<ICaptureEngine> engine = CaptureFactory::create();

// ❌ 错误：ui 层直接依赖实现类
#include "core/capture/web_capture.h"
```

### 平台隔离规则

```cpp
// ❌ 错误：core/ 中不能出现平台宏
#ifdef Q_OS_WIN
    ::SendMessage(...);
#endif

// ✅ 正确：core/ 只调用 platform/ 提供的接口
m_scrollInput->simulateScroll(delta);
```
