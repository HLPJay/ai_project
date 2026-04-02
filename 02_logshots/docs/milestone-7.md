# Milestone 7: 打包发布

## 目标
生成 Windows 和 macOS 的可分发安装包，完善发布流程。

## 前置依赖
- Milestone 1-5 完成（核心功能全部可用）
- Milestone 6 视情况可选

## 交付清单

### 7.1 Windows 打包

**Qt 动态库部署：**
```bash
windeployqt --release --no-translations longshot.exe
```
- 自动收集 Qt DLL、插件（platforms/qwindows.dll, imageformats/, webengineview/）
- 手动补充 OpenCV DLL、MSVC 运行时（vcredist）

**安装包 — NSIS：**
- packaging/windows/installer.nsi
- 安装流程：选择安装路径 → 安装 → 创建桌面快捷方式 + 开始菜单项
- 卸载流程：删除文件 + 清理注册表（开机自启项、QSettings）
- 注册文件关联（可选，暂不需要）

**CPack 配置：**
```cmake
set(CPACK_GENERATOR "NSIS")
set(CPACK_NSIS_DISPLAY_NAME "LongShot")
set(CPACK_NSIS_INSTALL_ROOT "$PROGRAMFILES64")
set(CPACK_NSIS_MUI_ICON "${CMAKE_SOURCE_DIR}/resources/icons/longshot.ico")
```

### 7.2 macOS 打包

**App Bundle 结构：**
```
LongShot.app/
├── Contents/
│   ├── Info.plist
│   ├── MacOS/
│   │   └── longshot          # 可执行文件
│   ├── Frameworks/           # Qt 框架 + OpenCV dylib
│   ├── PlugIns/              # Qt 插件
│   └── Resources/
│       └── longshot.icns     # 应用图标
```

**Qt 部署：**
```bash
macdeployqt LongShot.app -dmg
```

**权限声明 — Info.plist：**
```xml
<key>NSScreenCaptureUsageDescription</key>
<string>LongShot 需要屏幕录制权限来截取屏幕内容</string>
<key>NSAppleEventsUsageDescription</key>
<string>LongShot 需要辅助功能权限来控制窗口滚动</string>
```

**代码签名（可选，开源项目可不签）：**
- 未签名的 app 用户需要在"安全性与隐私"中手动允许
- README 中说明操作步骤

**DMG 制作：**
- 使用 create-dmg 工具或 CPack 的 DragNDrop generator
- 背景图 + Applications 文件夹快捷方式

### 7.3 应用图标
- resources/icons/longshot.ico（Windows，含 16/32/48/256px）
- resources/icons/longshot.icns（macOS，含 16/32/128/256/512/1024px）
- resources/icons/longshot.png（托盘图标，32x32）
- 图标设计：简洁的长卷轴/胶卷图形，蓝灰色调

**注意：图标文件需要我提供或用工具生成，你只需要在代码中正确引用路径。**

### 7.4 构建脚本
- scripts/build_windows.bat
- scripts/build_macos.sh

**构建流程：**
```bash
# 1. 安装依赖
vcpkg install

# 2. CMake 配置
cmake --preset=release

# 3. 编译
cmake --build --preset=release

# 4. 部署 Qt 依赖
# (平台相关命令)

# 5. 打包
cpack --config CPackConfig.cmake
```

### 7.5 包体积优化
- Release 模式编译 + strip 符号
- 排除不需要的 Qt 模块（QtNetwork, QtSql, QtMultimedia 等）
- OpenCV 仅链接 core, imgproc, imgcodecs（不需要 highgui, videoio 等）
- FFmpeg 仅链接解码相关库（不需要编码器和滤镜）
- 目标：Windows 安装包 < 80MB，macOS DMG < 70MB

### 7.6 README.md
- 项目介绍 + 截图
- 安装方法（下载安装包 / 从源码编译）
- 使用说明（各场景操作步骤）
- 从源码编译的前置条件和步骤
- 许可证说明（LGPL）
- 贡献指南

## 完成标准
- [ ] Windows: 在全新 Windows 10 上安装并运行成功
- [ ] macOS: 在全新 macOS 12+ 上安装并运行成功（处理权限弹窗）
- [ ] 安装包体积在目标范围内
- [ ] 卸载后无残留文件（配置文件可保留）
- [ ] README 完整可读
