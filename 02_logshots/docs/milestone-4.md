# Milestone 4: WindowManager + 非网页场景（P1）

## 目标
实现窗口选择器、区域框选，适配聊天软件和终端的长截屏。

## 前置依赖
- Milestone 2（CaptureCore 框架）
- Milestone 3（Stitcher 可用）

## 交付清单

### 4.1 窗口枚举 — 平台层
- src/platform/win/win_window_enum.h/cpp
- src/platform/mac/mac_window_enum.h/cpp

**Windows 实现：**
```cpp
// 核心 API
EnumWindows()           // 遍历所有顶层窗口
GetWindowText()         // 获取窗口标题
GetWindowRect()         // 获取窗口位置和大小
IsWindowVisible()       // 过滤不可见窗口
GetClassNameW()         // 获取窗口类名（用于识别应用类型）
GetWindowThreadProcessId() + QueryFullProcessImageName() // 获取进程路径和图标
```

**macOS 实现：**
```cpp
// 核心 API
CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
// 返回 CFArray，每个元素包含 kCGWindowOwnerName, kCGWindowBounds, kCGWindowNumber 等
```

**过滤规则：**
- 排除桌面窗口、任务栏、系统 UI
- 排除 LongShot 自身窗口
- 排除宽或高 < 100px 的窗口

### 4.2 窗口选择器 UI
- src/ui/window_picker.h/cpp
- 交互方式：类似 Windows Spy++ 的窗口选择器
  1. 用户点击"窗口截屏"按钮
  2. 光标变为十字准星
  3. 鼠标移动时，高亮当前光标下的窗口（半透明蓝色边框覆盖）
  4. 鼠标点击确认选择
  5. Esc 取消

**实现方案：**
- 创建一个全屏透明窗口（覆盖层），设置 WA_TranslucentBackground
- 覆盖层捕获鼠标事件
- Windows: 用 `WindowFromPoint()` 获取光标下的窗口句柄
- macOS: 用 `CGWindowListCopyWindowInfo` + 坐标命中测试

### 4.3 区域框选 UI
- src/ui/region_selector.h/cpp
- 交互方式：
  1. 全屏半透明灰色覆盖层
  2. 鼠标拖拽绘制矩形选区
  3. 选区内高亮显示，选区外灰暗
  4. 选区边缘和角上有拖拽手柄，可调整大小
  5. 双击或按 Enter 确认，Esc 取消
  6. 选区旁显示尺寸标注（如 "1920 × 400"）

### 4.4 通用窗口截屏引擎
- src/core/capture/window_capture.h/cpp

**与 web_capture 的区别：**
- 不能注入 JavaScript 控制滚动
- 使用系统级截屏 + 模拟输入来滚动

**滚动控制 — 平台层：**
- src/platform/win/win_scroll_input.h/cpp
  - `SendInput()` 模拟鼠标滚轮事件
  - 先 `SetForegroundWindow()` 激活目标窗口
  - 将光标移动到目标窗口中心区域
  - 发送 `MOUSEEVENTF_WHEEL` 事件，delta = -WHEEL_DELTA（向下滚动）
- src/platform/mac/mac_scroll_input.h/cpp
  - `CGEventCreateScrollWheelEvent()` 模拟滚动
  - `CGEventPost(kCGHIDEventTap, event)` 发送

**截屏 — 平台层：**
- src/platform/win/win_screen_capture.h/cpp
  - `BitBlt` 或 `PrintWindow` 截取指定窗口
  - 注意 DPI 缩放：使用 `GetDpiForWindow()` 获取 DPI，截图坐标需要换算
- src/platform/mac/mac_screen_capture.h/cpp
  - `CGWindowListCreateImage(bounds, kCGWindowListOptionIncludingWindow, windowID, kCGWindowImageDefault)`
  - 注意 Retina 屏幕：CGImage 的实际像素是逻辑像素的 2 倍

**终止条件检测：**
- 方案 1（通用）：连续两帧像素差异 < 1% → 判定已到底
- 方案 2（辅助）：截取前后对比滚动条位置变化（如果可见的话）
- 安全上限：maxFrames 兜底

### 4.5 场景适配说明

**聊天软件（微信/QQ/钉钉）：**
- 无特殊处理，与通用窗口截屏一致
- 注意聊天窗口通常有固定的标题栏和输入框 → Stitcher 的 sticky 检测会自动处理
- 微信的消息列表区域可能需要用户手动框选（因为整个窗口包含侧边栏）

**终端（cmd/PowerShell/Terminal/iTerm2）：**
- 等宽字体的特点：行高固定，对齐更容易
- 滚动粒度可能不是像素级而是行级（终端按行滚动）
- 建议：终端场景使用较大的 overlapPixels（200px），确保至少覆盖 2-3 行

## 完成标准
- [ ] 窗口选择器能正确高亮并选择目标窗口
- [ ] 区域框选交互流畅，选区可调整
- [ ] 对微信聊天窗口能完成自动滚动截屏并拼接
- [ ] 对 Windows Terminal 能完成长日志截屏
- [ ] 截屏过程中不干扰目标窗口的正常显示
- [ ] DPI 缩放场景下截图尺寸正确
