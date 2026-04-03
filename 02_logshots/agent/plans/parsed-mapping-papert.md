# Milestone 4 实现计划: WindowManager + 非网页场景

## Context

Milestone 4 是 LongShot 长截屏工具的核心里程碑，需要实现窗口选择器、区域框选和通用窗口截屏能力，支持聊天软件（微信/QQ/钉钉）和终端（cmd/PowerShell/Terminal）等非网页场景。

**关键发现（代码审查后）:**
1. `src/platform/` 目录**不存在**，需要从零创建
2. `ImageStitcher` **未继承** `IStitcher` 接口 — 设计不一致需修复
3. `CaptureRequest.target` 类型歧义 — 无法区分 URL / 窗口句柄
4. **WindowPicker 透明穿透方案错误** — `WindowFromPoint` 无法穿透透明覆盖层
5. **RegionSelector 无背景图** — 透明窗口下没有屏幕内容可透传
6. 所有 milestone-4 文件均需新建
7. 可复用 `ICaptureEngine` 接口模式、`WebCapture` 状态机、Qt 信号槽通信模式

---

## 严重问题清单（实现前必须修复）

### P0 — 设计缺陷

| # | 问题 | 文件 | 修复方案 |
|---|------|------|----------|
| 1 | `ImageStitcher` 未继承 `IStitcher` | `image_stitcher.h:17` | 添加 `, public IStitcher` 继承 |
| 2 | `CaptureRequest.target` 歧义 | `i_capture_engine.h:14` | 扩展 enum `CaptureMode` + `windowHandle` 字段 |
| 3 | WindowPicker `WindowFromPoint` 命中覆盖层自身 | 4.2 设计 | 使用 `ChildWindowFromPointEx` + `GA_ROOT` 或鼠标钩子 |
| 4 | RegionSelector 透明窗口下无背景内容 | 4.3 设计 | 先捕获全屏截图作为背景，再绘制遮罩 |

### P1 — 运行期风险

| # | 问题 | 风险 | 缓解方案 |
|---|------|------|----------|
| 5 | `SendInput` / `SetForegroundWindow` 线程要求 | 崩溃/静默失败 | 在主线程调用，或专用 QThread + 事件循环 |
| 6 | DPI 缩放 > 100% 时截图坐标错误 | 截图尺寸偏差 | `PrintWindow` 优先 + `GetDpiForWindow` 换算 |
| 7 | 1% 像素差异终止条件过于简单 | 误终止（内容变化小）或无限滚动 | 增加滚动条位置检测 + 重试机制 |
| 8 | 窗口消失竞态 | 截屏中途窗口关闭 | 截屏前 `IsWindow()` 验证 |

---

## 交付清单

| 任务 | 文件 | 优先级 | 依赖 |
|------|------|--------|------|
| 4.1 | `src/platform/win/win_window_enum.h/cpp` | P0 | 需先修1 |
| 4.1 | `src/platform/mac/mac_window_enum.h/cpp` | P0 | 需先修1 |
| 4.2 | `src/ui/window_picker.h/cpp` | P0 | 需先修3 |
| 4.3 | `src/ui/region_selector.h/cpp` | P0 | 需先修4 |
| 4.4 | `src/core/capture/window_capture.h/cpp` | P0 | 需先修2 |
| 4.4 | `src/platform/win/win_screen_capture.h/cpp` | P1 | 4.1 |
| 4.4 | `src/platform/mac/mac_screen_capture.h/cpp` | P1 | 4.1 |
| 4.4 | `src/platform/win/win_scroll_input.h/cpp` | P1 | 4.1 |
| 4.4 | `src/platform/mac/mac_scroll_input.h/cpp` | P1 | 4.1 |

---

## 修复 P0 设计缺陷

### 修复 1: ImageStitcher 继承 IStitcher

**文件**: `src/core/stitcher/image_stitcher.h`

```cpp
// 修改前
class ImageStitcher : public QObject {

// 修改后
class ImageStitcher : public QObject, public IStitcher {
    Q_OBJECT
    Q_INTERFACES(IStitcher)  // Qt 元对象接口注册
```

并确保 `stitch()`, `stop()` 在 `public` 下实现。

---

### 修复 2: CaptureRequest 扩展支持 Window/Region 模式

**文件**: `src/core/capture/i_capture_engine.h`

```cpp
// 新增
enum class CaptureMode { Web, Window, Region };

struct CaptureRequest {
    CaptureMode mode = CaptureMode::Web;
    /** 目标 URL（网页场景）或窗口标题（窗口场景） */
    QString target;
    /** 窗口句柄: Win32 HWND (int64_t) / macOS CGWindowID (uint64_t) */
    int64_t windowHandle = 0;
    /** 区域坐标（Region 模式） */
    QRect regionRect;
    /** 滚动时相邻帧重叠像素数 */
    int overlapPixels = 100;
    /** 滚动后等待渲染时间（毫秒） */
    int scrollDelayMs = 300;
    /** 安全上限，防止无限滚动 */
    int maxFrames = 200;
};
```

---

### 修复 3: WindowPicker 透明穿透检测（正确方案）

**问题**: `Qt::WA_TranslucentBackground` 创建的透明窗口仍是一个实体，`WindowFromPoint()` 会命中它自身。

**正确方案**:
```cpp
// 方案 A (推荐): 使用 GetAncestor 获取顶层窗口
HWND hwnd = WindowFromPoint(pt);
if (hwnd) {
    HWND root = GetAncestor(hwnd, GA_ROOT);  // 获取真正的顶层窗口
    if (root != overlayWindowHandle_) {
        hoveredHwnd_ = root;
    }
}

// 方案 B: 使用 ChildWindowFromPointEx 跳过不可见/透明
HWND hwnd = ChildWindowFromPointEx(
    GetDesktopWindow(), pt,
    CWP_SKIPINVISIBLE | CWP_SKIPTRANSPARENT);

// 方案 C: 鼠标钩子 (最准确但最复杂)
// 仅在方案 A/B 失效时使用
```

**自窗口排除**:
```cpp
// 在 MainWindow 构造或 showEvent 中保存自身 HWND
HWND selfHwnd = reinterpret_cast<HWND>(winId());

// 在 mouseMoveEvent 中过滤
if (hoveredHwnd_ == selfHwnd_) return;
```

---

### 修复 4: RegionSelector 背景捕获

**问题**: 透明窗口下没有屏幕内容，无法实现"选区内透明、选区外灰暗"。

**正确方案**:
```cpp
class RegionSelectorOverlay : public QWidget {
private:
    QImage backgroundScreenshot_;  // 全屏背景截图

    void captureBackground() {
        // 方案 A: Qt 跨平台方式
        QScreen* screen = QGuiApplication::primaryScreen();
        backgroundScreenshot_ = screen->grabWindow(WId(-1)).toImage();

        // 方案 B: Windows 方式 (更可靠)
        // HDC hdcDesk = GetDC(NULL);
        // BitBlt(...);
        // ReleaseDC(NULL, hdcDesk);
    }

    void paintEvent(QPaintEvent*) override {
        QPainter painter(this);

        // 1. 绘制全屏背景截图
        painter.drawImage(0, 0, backgroundScreenshot_);

        // 2. 绘制半透明灰色遮罩（选区外）
        QColor grayOverlay(0, 0, 0, 128);
        painter.fillRect(rect(), grayOverlay);

        // 3. 清除选区内部 (CompositionMode_Clear)
        painter.setCompositionMode(QPainter::CompositionMode_Clear);
        painter.fillRect(selectionRect_, Qt::transparent);

        // 4. 恢复绘制模式
        painter.setCompositionMode(QPainter::CompositionMode_SourceOver);

        // 5. 绘制选区边框
        painter.setPen(QPen(Qt::white, 2));
        painter.drawRect(selectionRect_);

        // 6. 绘制 8 个调整手柄
        drawHandles(painter);

        // 7. 绘制尺寸标注
        painter.drawText(selectionRect_.topLeft() + QPoint(0, -20),
            QString("%1 x %2").arg(selectionRect_.width()).arg(selectionRect_.height()));
    }
};
```

**时序**: 在 `showEvent` 中先调用 `captureBackground()` 截取当前屏幕，再显示覆盖层。

---

## 实现方案（修正后）

### 1. 平台层接口设计

**IWindowEnumerator** — 窗口枚举抽象:
```cpp
class IWindowEnumerator {
public:
    virtual ~IWindowEnumerator() = default;
    virtual QList<WindowInfo> enumerateWindows() = 0;
    /** 排除指定窗口（用于排除 LongShot 自身） */
    virtual void setExcludedWindow(int64_t handle) = 0;
};

struct WindowInfo {
    int64_t windowId;       // Win: HWND, Mac: CGWindowID
    QString title;
    QString className;
    QString processPath;
    QRect geometry;
    bool isVisible;
};
```

**IScreenCapturer** — 截屏抽象:
```cpp
class IScreenCapturer {
public:
    virtual ~IScreenCapturer() = default;
    /** 截取指定窗口 */
    virtual QImage captureWindow(int64_t windowId) = 0;
    /** 截取指定区域 */
    virtual QImage captureRegion(const QRect& rect) = 0;
    /** 获取指定窗口的 DPI 缩放因子 */
    virtual double dpiForWindow(int64_t windowId) const = 0;
    /** 验证窗口是否仍然有效 */
    virtual bool isWindowValid(int64_t windowId) const = 0;
};
```

**IScrollInput** — 滚动输入抽象:
```cpp
class IScrollInput {
public:
    virtual ~IScrollInput() = default;
    /** 向下滚动指定像素 */
    virtual bool scrollDown(int pixels) = 0;
    /** 激活指定窗口（置前） */
    virtual bool activateWindow(int64_t windowId) = 0;
    /** 将光标移动到窗口中心区域（用于触发悬停事件） */
    virtual bool moveCursorToCenter(int64_t windowId) = 0;
};
```

---

### 2. Windows 实现要点

**窗口枚举** (`win_window_enum.cpp`):
- `EnumWindows()` 遍历 → `GetWindowTextW()` + `GetClassNameW()` + `GetWindowRect()`
- 过滤: `Progman`/`WorkerW`(桌面), `Shell_TrayWnd`(任务栏), 自身 HWND, <100px
- 自窗口 HWND 通过 `setExcludedWindow()` 注入

**截屏** (`win_screen_capture.cpp`):
```cpp
QImage captureWindow(int64_t hwnd) {
    // 1. 验证窗口有效
    if (!IsWindow((HWND)hwnd)) return QImage();

    // 2. 获取窗口 DPI
    UINT dpi = GetDpiForWindow((HWND)hwnd);
    double scale = dpi / 96.0;

    // 3. 优先使用 PrintWindow (处理 DPI)
    HDC hdcMem = CreateCompatibleDC(NULL);
    RECT rect;
    GetWindowRect((HWND)hwnd, &rect);
    int width = (rect.right - rect.left) * scale;
    int height = (rect.bottom - rect.top) * scale;

    HBITMAP hBitmap = CreateCompatibleBitmap(hdcScreen, width, height);
    HGDIOBJ old = SelectObject(hdcMem, hBitmap);

    // PrintWindow 更可靠，自动处理 DPI
    PrintWindow((HWND)hwnd, hdcMem, PW_CLIENTONLY);

    // 4. 转换为 QImage
    QImage result = QImage::fromHBITMAP(hBitmap, ...);

    SelectObject(hdcMem, old);
    DeleteObject(hBitmap);
    DeleteDC(hdcMem);
    return result;
}
```

**滚动** (`win_scroll_input.cpp`):
- `SetForegroundWindow()` + `SendInput()` **必须在主线程调用**
- 不要在工作线程调用！否则静默失败或崩溃
- 方案: `QMetaObject::invoke` 将调用转发到主线程

```cpp
// 错误 ❌
QThread* scrollThread = new QThread;
connect(scrollThread, &QThread::started, [](){ SendInput(...); }); // 崩溃!

// 正确 ✅
class ScrollInputThread : public QObject {
    Q_OBJECT
public slots:
    void doScroll(int pixels) {
        // 这些 API 必须在有消息队列的线程中
        SetForegroundWindow(targetHwnd_);
        SendInput(...);
        emit scrolled();
    }
signals:
    void scrolled();
private:
    HWND targetHwnd_;
};

// 主线程创建并连接
ScrollInputThread* worker = new ScrollInputThread;
worker->moveToThread(qApp->thread());  // 放回主线程
QMetaObject::invokeMethod(worker, "doScroll", Qt::QueuedConnection, Q_ARG(int, 120));
```

---

### 3. macOS 实现要点

**窗口枚举** (`mac_window_enum.cpp`):
- `CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)`
- 取 `kCGWindowOwnerName`, `kCGWindowBounds`, `kCGWindowNumber`
- 过滤: `kCGWindowLayer != 0` → 非正常窗口

**截屏** (`mac_screen_capture.cpp`):
```cpp
QImage captureWindow(CGWindowID windowId) {
    CGRect bounds = CGRectNull;  // 获取窗口边界

    // 1. 获取窗口信息
    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, windowId);
    // 解析 bounds

    // 2. 截取窗口
    CGImageRef cgImage = CGWindowListCreateImage(
        bounds,
        kCGWindowListOptionIncludingWindow,
        windowId,
        kCGWindowImageBoundsIgnoreFraming);

    // 3. Retina 处理: CGImage 像素是逻辑像素 2x
    int logicalWidth = CGImageGetWidth(cgImage);
    int logicalHeight = CGImageGetHeight(cgImage);
    bool isRetina = (logicalWidth != bounds.size.width);

    QImage result = // 转换为 QImage

    if (isRetina) {
        result = result.scaled(logicalWidth/2, logicalHeight/2,
            Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    }

    CGImageRelease(cgImage);
    return result;
}
```

**滚动** (`mac_scroll_input.cpp`):
- `CGEventCreateScrollWheelEvent()` 创建事件
- `CGEventPost(kCGHIDEventTap, event)` 发送
- macOS 无线程限制，但同样建议在主线程执行

---

### 4. WindowPickerOverlay UI（修正后）

**交互流程:**
1. `showEvent`: 先调用 `captureBackground()` 截取全屏
2. 创建全屏覆盖层 `QWidget(Qt::FramelessWindowHint | Qt::Tool)`
3. 光标变为十字 (`Qt::CrossCursor`)
4. `eventFilter` 追踪鼠标移动
5. `ChildWindowFromPointEx(GetDesktopWindow(), pt, ...)` 获取真实窗口
6. `GetAncestor(hwnd, GA_ROOT)` 获取顶层窗口
7. 在覆盖层上绘制蓝色边框高亮
8. 点击 → `emit windowSelected(hwnd)` → 关闭
9. Esc → `emit cancelled()` → 关闭

**关键实现**:
```cpp
bool eventFilter(QObject* watched, QEvent* event) override {
    if (event->type() == QEvent::MouseMove) {
        QPoint globalPos = QCursor::pos();
#ifdef Q_OS_WIN
        HWND hwnd = WindowFromPoint(POINT{globalPos.x(), globalPos.y()});
        if (hwnd) {
            HWND root = GetAncestor(hwnd, GA_ROOT);
            if (root && root != (HWND)winId()) {
                hoveredHwnd_ = (int64_t)root;
                update();  // 触发重绘高亮
            }
        }
#endif
    }
    return false;  // 不拦截事件，让它继续传递
}
```

---

### 5. RegionSelectorOverlay UI（修正后）

**交互流程:**
1. `showEvent`: 先调用 `captureBackground()` 截取全屏
2. 全屏覆盖层，背景为捕获的屏幕截图
3. 在背景上绘制半透明灰色遮罩
4. 用 `QRegion::subtracted()` 扣除选区（透明）
5. 鼠标拖拽橡皮筋矩形
6. 8个调整手柄 (四角+四边中点)
7. 显示尺寸标注 `"1920 x 400"`
8. 双击/Enter → `emit regionSelected(QRect)` → 关闭
9. Esc → `emit cancelled()` → 关闭

---

### 6. WindowCapture 引擎（修正后）

**状态机** (复用 WebCapture 模式):
```
Idle → Capturing → Finished
         ↓
       Error
```

**终止检测（增强版）**:
```cpp
// 1. 像素差异检测（基础）
double diff = cv::norm(prev, curr, cv::NORM_L2) / (prev.total() * prev.channels());

// 2. 窗口内容变化检测（增强）
//    连续 N 次滚动后像素差异仍小 → 可能已到底
if (diff < 0.01) {
    consecutiveSimilar_++;
} else {
    consecutiveSimilar_ = 0;
}

// 3. 重试机制：尝试小幅度滚动确认
if (consecutiveSimilar_ >= 2) {
    // 再尝试滚动 50px
    scrollBy(50);
    if (stillNoChange) {
        finishCapture();  // 确认已到底
    }
}

// 4. 安全上限
if (currentFrameIndex_ >= maxFrames_) {
    finishCapture();
}
```

**线程模型**:
- `WindowCapture` 自身在主线程（管理 Qt 信号槽）
- 截屏调用通过 `Qt::QueuedConnection` 异步执行
- 帧保存在 `FrameSaver` 工作线程

---

### 7. 场景适配

**检测方案:** 通过窗口类名识别终端:
```cpp
enum class CaptureScene { Generic, Terminal };

CaptureScene detectScene(const QString& className) {
    static const QStringList terminalClasses = {
        "ConsoleWindowClass",     // cmd.exe
        "powershell",             // PowerShell
        "WindowsTerminal",        // Windows Terminal
        "iTerm2",                 // iTerm2
        "AppleTerminal"           // macOS Terminal
    };

    for (const auto& tc : terminalClasses) {
        if (className.contains(tc, Qt::CaseInsensitive)) {
            return CaptureScene::Terminal;
        }
    }
    return CaptureScene::Generic;
}

// 场景特定配置
int overlapPixels = (scene == CaptureScene::Terminal) ? 200 : 100;
```

---

## 修复清单汇总

| 修复 | 文件 | 修改内容 |
|------|------|----------|
| 修复1 | `src/core/stitcher/image_stitcher.h` | 添加 `, public IStitcher` 和 `Q_INTERFACES(IStitcher)` |
| 修复2 | `src/core/capture/i_capture_engine.h` | 添加 `enum CaptureMode` 和 `windowHandle`/`regionRect` 字段 |
| 修复3 | `src/ui/window_picker.h/cpp` | 使用 `ChildWindowFromPointEx` + `GetAncestor` 替代直接 `WindowFromPoint` |
| 修复4 | `src/ui/region_selector.h/cpp` | `showEvent` 中先捕获全屏背景再显示覆盖层 |
| 修复5 | `src/core/capture/window_capture.h/cpp` | 增加 `isWindowValid()` 前置检查 + 增强终止检测 |
| 修复6 | `src/platform/win/win_scroll_input.cpp` | 滚动调用使用 `QMetaObject::invoke` 转发到主线程 |
| 修复7 | `src/platform/win/win_screen_capture.cpp` | DPI 处理: `GetDpiForWindow` + 缩放因子换算 |
| 修复8 | `src/ui/main_window.cpp` | `onWindowCaptureClicked` 连接 WindowPicker 信号 |

---

## 关键文件

| 文件 | 作用 |
|------|------|
| `src/core/capture/i_capture_engine.h` | 需修复2，WindowCapture 需实现的接口 |
| `src/core/capture/capture_runner.cpp` | 线程模型参考 |
| `src/core/stitcher/image_stitcher.h` | 需修复1，继承问题 |
| `src/ui/main_window.cpp` | WindowPicker/RegionSelector 集成点 |

---

## 验证方案

| 测试 | 验证点 | 预期结果 |
|------|--------|----------|
| 窗口枚举 | 列出所有可见窗口 | 桌面/任务栏/自身窗口被正确过滤 |
| WindowPicker | 光标移到窗口上 | 蓝色边框高亮正确跟随，无抖动 |
| WindowPicker | 点击选择窗口 | 正确返回选中窗口的 HWND |
| RegionSelector | 拖拽框选 | 选区内透明显示原屏幕内容，选区外灰暗 |
| RegionSelector | 调整大小 | 8个手柄可拖动，尺寸标注实时更新 |
| 窗口截屏 | 截取计算器 | 自动滚动截屏，拼接生成完整图 |
| DPI 缩放 | 150% 缩放下截屏 | 截图尺寸与窗口逻辑尺寸一致 |
| 终端场景 | 截取 PowerShell 长输出 | 200px overlap 确保不漏行 |
| 终止检测 | 记事本滚动到底 | 正确检测到底并停止 |
| 窗口消失 | 截屏中途关闭窗口 | 捕获 error 信号，不崩溃 |

---

## 风险项（更新）

| 风险 | 缓解方案 | 状态 |
|------|----------|------|
| ~~跨线程 SendInput 调用失败~~ | **已修复**: 使用 QMetaObject::invoke 到主线程 | ✅ |
| DPI 缩放导致截图坐标错误 | PrintWindow 优先 + GetDpiForWindow 换算 | ⚠️ 需实测 |
| 窗口在截屏过程中消失 | 截屏前验证 IsWindow() | ✅ |
| ~~透明覆盖层鼠标穿透问题~~ | **已修复**: 使用 ChildWindowFromPointEx + GetAncestor | ✅ |
| RegionSelector 无背景内容 | **已修复**: showEvent 中先捕获全屏 | ✅ |
| 像素差异终止条件误判 | 增强: 重试机制 + 滚动条位置检测 | ⚠️ 需实测 |
| 窗口枚举时窗口已消失 | 枚举结果缓存 + 截屏前验证 | ⚠️ 需实测 |

---

## 实现顺序

```
Phase 0: 修复设计缺陷
├── 修复 ImageStitcher 继承问题 (修复1)
├── 扩展 CaptureRequest 支持 Window/Region (修复2)
└── 创建统一的 WindowInfo 和平台接口

Phase 1: 平台层基础
├── 实现 WinWindowEnumerator (含自窗口排除)
├── 实现 MacWindowEnumerator
└── 验证: 枚举结果正确过滤

Phase 2: UI 覆盖层 (优先验证透明穿透问题)
├── WindowPickerOverlay (修复3: 正确的窗口检测)
├── RegionSelectorOverlay (修复4: 背景捕获)
└── 验证: 高亮跟随 + 选区显示正确

Phase 3: 截屏引擎
├── WindowCapture 状态机
├── WinScreenCapturer (修复7: DPI 处理)
├── WinScrollInput (修复6: 主线程调用)
├── 增强终止检测 (修复5)
└── 验证: 截屏 + 拼接流程

Phase 4: 场景适配
├── 场景检测 (终端类名识别)
├── overlapPixels 参数调优
└── 验证: 终端长日志截屏
```
