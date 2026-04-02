# Milestone 5: UI 完善 + StorageManager

## 目标
完成产品级 UI 交互和文件存储管理。

## 前置依赖
- Milestone 1-4 所有模块可用

## 交付清单

### 5.1 主控制条 UI 完善
- src/ui/main_window.h/cpp 重构

**布局：**
- 无边框悬浮窗，圆角矩形（8px），带阴影效果
- 水平排列图标按钮，每个 40x40px，间距 8px
- 鼠标悬停按钮时显示 tooltip 和微动效（颜色变化）
- 窗口可拖动（鼠标左键按住空白区域拖动）
- 样式使用 Qt StyleSheet，主色调深灰/白色极简风

**按钮组：**
| 图标 | 功能 | 快捷键 |
|------|------|--------|
| 🌐 | 网页长截屏 | Ctrl+Shift+L / Cmd+Shift+L |
| 🪟 | 窗口长截屏 | - |
| ⬜ | 区域长截屏 | Ctrl+Shift+A / Cmd+Shift+A |
| 🎬 | 录屏转长图 | - |
| ⚙️ | 设置 | - |

### 5.2 截屏进度 UI
- src/ui/widgets/progress_overlay.h/cpp
- 截屏开始后，控制条变为进度模式：
  - 左侧：帧数统计 "第 12 帧 / 约 30 帧"
  - 中间：进度条（QProgressBar 自定义样式）
  - 右侧：[停止] 按钮（红色）

### 5.3 预览窗口
- src/ui/preview_window.h/cpp

**功能：**
- 截屏完成后弹出，显示拼接后的长图
- 使用 QScrollArea + QLabel 展示大图
- 支持鼠标滚轮缩放（Ctrl+滚轮 或 触摸板缩放手势）
- 缩放范围 10% - 400%，状态栏显示当前缩放比例
- 支持鼠标拖拽平移（按住空格或鼠标中键）
- 底部操作栏：

| 按钮 | 功能 | 说明 |
|------|------|------|
| 保存 | 保存到默认路径 | 触发 StorageManager |
| 另存为 | 选择路径保存 | QFileDialog::getSaveFileName |
| 复制到剪贴板 | QClipboard::setImage | 大图时警告可能截断 |
| 重新截取 | 关闭预览，回到控制条 | - |

### 5.4 设置面板
- src/ui/settings_dialog.h/cpp
- QDialog 模态对话框

**设置项：**
- 截屏设置：滚动延迟（滑块 100-2000ms）、重叠像素（50-300）、输出格式（PNG/JPEG）、JPEG 质量
- 存储设置：默认保存路径（带浏览按钮）、文件命名模板预览
- 快捷键设置：网页截屏、区域截屏（QKeySequenceEdit 录入）
- 通用设置：开机自启（注册表/LaunchAgents）、启动时最小化到托盘

所有设置通过 QSettings 持久化，修改后立即生效。

### 5.5 全局快捷键
- src/app/shortcut_manager.h/cpp

**实现方案：**
- Windows: `RegisterHotKey()` API
- macOS: 使用 Qt 的 QShortcut 无法捕获全局快捷键，需要用 Carbon API `InstallEventHandler` 或 Accessibility API
- 封装为 ShortcutManager 统一接口，平台差异在 platform/ 层处理

### 5.6 系统托盘完善
- 更新 tray_manager.h/cpp
- 托盘菜单：
  - 显示主窗口
  - 快速截屏 → 子菜单 [网页 / 窗口 / 区域]
  - 打开截图文件夹（QDesktopServices::openUrl）
  - 设置
  - 分隔线
  - 退出

### 5.7 StorageManager
- src/core/storage/storage_manager.h/cpp

**职责：**
```cpp
class StorageManager {
public:
    // 保存图片到默认路径，返回完整文件路径
    QString saveImage(const QImage& image, const QString& sceneTag);
    // 保存图片到指定路径
    QString saveImageAs(const QImage& image, const QString& filePath);
    // 清理临时帧文件
    void cleanupTempFrames();
    // 获取默认保存目录（不存在则创建）
    QString defaultSavePath();
};
```

**文件命名规则：**
`LongShot_YYYYMMDD_HHmmss_场景标签.格式`
- 示例：`LongShot_20260401_143022_网页.png`
- 场景标签：网页 / 窗口 / 区域 / 录屏
- 如果文件名冲突，追加 `_1`, `_2`, ...

## 完成标准
- [ ] 控制条 UI 美观、可拖动、交互响应流畅
- [ ] 截屏过程有清晰的进度反馈
- [ ] 预览窗口支持缩放和平移，大图体验流畅
- [ ] 全局快捷键在目标应用处于前台时仍能触发
- [ ] 设置修改后立即生效且重启后保留
- [ ] 文件正确保存、命名无冲突
