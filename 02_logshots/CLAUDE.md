# LongShot — 桌面端长截屏工具

## 项目概述
一个基于 C++ + Qt6 + OpenCV 的桌面端长截屏工具，支持自动滚动截屏并智能拼接为完整长图。
覆盖网页、聊天软件、终端等多种场景。100% 本地离线运行，开源项目（LGPL 许可）。

## 技术栈
- **语言**: C++17
- **GUI 框架**: Qt 6.5+（QWidgets，LGPL 动态链接）
- **图像处理**: OpenCV 4.x（重叠检测、拼接）
- **网页截屏**: QWebEngineView + JavaScript 注入
- **视频处理**: FFmpeg C API（libavformat/libavcodec），P2 阶段
- **构建系统**: CMake 3.20+
- **包管理**: vcpkg（管理 OpenCV、FFmpeg 等第三方依赖）
- **打包**: CPack + NSIS(Windows) / macOS Bundle
- **目标平台**: Windows 10/11, macOS 12+

## 架构规则
- 主线程仅处理 UI，所有截屏/拼接操作在 QThread 工作线程中执行
- 模块间通过 Qt 信号槽通信，禁止直接跨模块函数调用
- 平台相关代码统一放在 platform/ 目录，通过编译宏隔离（Q_OS_WIN / Q_OS_MACOS）
- 所有对外暴露的接口使用纯虚基类（Interface），便于测试和替换

## 核心模块（按依赖顺序）
1. **CaptureCore** — 截屏引擎（滚动控制 + 逐帧截取）
2. **Stitcher** — 拼接引擎（重叠检测 + 去重拼接 + sticky 元素处理）
3. **WindowManager** — 窗口管理（窗口选择器 + 区域框选）
4. **StorageManager** — 存储管理（文件命名 + 格式输出）
5. **VideoFrameExtractor** — 视频帧提取（P2 阶段）

## 编码规范
- C++17 标准，启用 -Wall -Wextra -Werror
- 类命名: PascalCase（CaptureCore）, 方法: camelCase（startCapture）
- 文件命名: snake_case（capture_core.h / capture_core.cpp）
- 所有公共方法必须有 Doxygen 注释
- 禁止裸 new/delete，使用 std::unique_ptr / std::shared_ptr
- 禁止裸 catch(...)，所有异常有明确类型
- 字符串统一使用 QString，与标准库交互时用 toStdString()
- 日志使用 qDebug/qInfo/qWarning/qCritical，发布版本通过 QLoggingCategory 过滤

## 目录结构
```
longshot/
├── CMakeLists.txt                 # 顶层 CMake
├── vcpkg.json                     # 依赖声明
├── CLAUDE.md                      # 本文件
├── src/
│   ├── main.cpp                   # 入口
│   ├── app/                       # 应用级（Application 单例、全局配置）
│   │   ├── application.h/cpp
│   │   └── config.h/cpp
│   ├── core/                      # 核心业务逻辑（无 UI 依赖）
│   │   ├── capture/               # CaptureCore 模块
│   │   │   ├── i_capture_engine.h     # 接口
│   │   │   ├── web_capture.h/cpp      # 网页截屏实现
│   │   │   ├── window_capture.h/cpp   # 通用窗口截屏实现
│   │   │   └── scroll_strategy.h/cpp  # 滚动策略
│   │   ├── stitcher/              # Stitcher 模块
│   │   │   ├── i_stitcher.h           # 接口
│   │   │   ├── image_stitcher.h/cpp   # 拼接实现
│   │   │   └── overlap_detector.h/cpp # 重叠检测
│   │   ├── window/                # WindowManager 模块
│   │   │   ├── i_window_manager.h
│   │   │   └── window_manager.h/cpp
│   │   ├── storage/               # StorageManager 模块
│   │   │   └── storage_manager.h/cpp
│   │   └── video/                 # VideoFrameExtractor (P2)
│   │       └── frame_extractor.h/cpp
│   ├── platform/                  # 平台相关实现
│   │   ├── win/                   # Windows 专用
│   │   │   ├── win_screen_capture.h/cpp
│   │   │   ├── win_window_enum.h/cpp
│   │   │   └── win_scroll_input.h/cpp
│   │   └── mac/                   # macOS 专用
│   │       ├── mac_screen_capture.h/cpp
│   │       ├── mac_window_enum.h/cpp
│   │       └── mac_scroll_input.h/cpp
│   ├── ui/                        # Qt UI 层
│   │   ├── main_window.h/cpp          # 主控制条窗口
│   │   ├── preview_window.h/cpp       # 截图预览窗口
│   │   ├── region_selector.h/cpp      # 区域框选覆盖层
│   │   ├── window_picker.h/cpp        # 窗口选择器
│   │   ├── settings_dialog.h/cpp      # 设置面板
│   │   ├── tray_manager.h/cpp         # 系统托盘
│   │   └── widgets/                   # 自定义控件
│   │       └── progress_overlay.h/cpp
│   └── utils/                     # 工具函数
│       ├── image_utils.h/cpp
│       └── file_utils.h/cpp
├── resources/                     # 资源文件
│   ├── icons/
│   ├── longshot.qrc
│   └── translations/
├── tests/                         # 单元测试
│   ├── CMakeLists.txt
│   ├── test_stitcher.cpp
│   └── test_overlap_detector.cpp
├── packaging/                     # 打包配置
│   ├── windows/
│   │   └── installer.nsi
│   └── macos/
│       └── Info.plist
└── docs/                          # 里程碑需求文档
    ├── milestone-1.md
    ├── milestone-2.md
    └── ...
```

## 排除项（Out of Scope）
以下内容不属于本项目，如果我提到请提醒我：
- ❌ 云同步 / 网络功能 / 用户账号
- ❌ OCR 文字识别（仅允许用于辅助图像对齐）
- ❌ 截图标注编辑（画笔、马赛克等）
- ❌ 移动端 / Linux 支持（v1）
- ❌ 国际化（v1 仅中文）
- ❌ 插件系统

## 沟通协议
- 不确定时：列出假设，等我确认
- 发现冲突时：给出 2-3 个方案，由我选择
- 每次回复格式：

```
## 当前: [Milestone X — 模块名]
## 交付:
[内容]
## 待确认:
[决策项]
## 下一步:
[预告]
```
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

## 当前进度
- [x] 技术选型确认
- [ ] Milestone 1: 项目骨架
- [ ] Milestone 2: CaptureCore（网页长截屏 P0）
- [ ] Milestone 3: Stitcher（拼接引擎）
- [ ] Milestone 4: WindowManager + 非网页场景（P1）
- [ ] Milestone 5: UI + StorageManager
- [ ] Milestone 6: VideoFrameExtractor（P2）
- [ ] Milestone 7: 打包发布

