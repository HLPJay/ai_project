# Milestone 1: 项目骨架搭建

## 目标
搭建可编译运行的 C++ + Qt6 + OpenCV 项目骨架，验证构建链路和基础通信。

## 交付清单

### 1.1 CMake 构建体系
- 顶层 CMakeLists.txt：配置 C++17、Qt6、OpenCV、编译选项
- src/CMakeLists.txt：按模块组织 target
- tests/CMakeLists.txt：配置 QTest 测试框架
- vcpkg.json：声明 opencv4 依赖
- 预设 CMakePresets.json：debug / release 两个预设

**编译选项要求：**
```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Werror)  # MSVC 用 /W4 /WX
```

### 1.2 应用入口
- src/main.cpp：初始化 QApplication，创建主窗口
- src/app/application.h/cpp：Application 单例，管理全局生命周期
- src/app/config.h/cpp：使用 QSettings 读写配置项

**配置项（初始）：**
| key | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| capture/scrollDelay | int | 300 | 每帧滚动后等待时间(ms) |
| capture/format | string | "png" | 输出格式 png/jpeg |
| capture/jpegQuality | int | 90 | JPEG 质量 1-100 |
| storage/savePath | string | ~/Pictures/LongShot/ | 默认存储路径 |
| shortcuts/webCapture | string | Ctrl+Shift+L | 网页截屏快捷键 |
| shortcuts/regionCapture | string | Ctrl+Shift+A | 区域截屏快捷键 |

### 1.3 主窗口骨架
- src/ui/main_window.h/cpp：
  - 无边框悬浮小窗口（FramelessWindowHint + StayOnTopHint）
  - 横向排列 5 个 QPushButton 占位：[网页] [窗口] [区域] [录屏] [设置]
  - 按钮点击后 qDebug 输出日志即可，不需要实现功能
  - 支持鼠标拖动移动窗口

### 1.4 系统托盘骨架
- src/ui/tray_manager.h/cpp：
  - QSystemTrayIcon + QMenu
  - 菜单项：显示/隐藏主窗口、退出
  - 关闭主窗口时最小化到托盘而非退出

### 1.5 信号槽通信验证
- 在 main_window 中点击"网页"按钮
- 通过信号触发一个 stub CaptureCore
- CaptureCore 在工作线程中 sleep(1s) 模拟截屏
- 完成后信号通知 UI 弹出 QMessageBox

**验证要点：**
- 确认 UI 线程不被阻塞
- 确认跨线程信号槽正确连接（Qt::QueuedConnection）

## 完成标准
- [ ] `cmake --preset=debug && cmake --build --preset=debug` 无警告编译通过
- [ ] 应用启动显示悬浮控制条
- [ ] 点击关闭最小化到托盘
- [ ] 点击"网页"按钮，UI 不卡顿，1s 后弹出完成提示
- [ ] QSettings 配置文件正确生成在标准路径

## 技术注意事项
- Qt6 的 QWebEngineView 需要单独 find_package(Qt6 COMPONENTS WebEngineWidgets)
- Windows 上 vcpkg 需要 x64-windows triplet
- macOS 需要在 Info.plist 中声明 NSScreenCaptureUsageDescription
