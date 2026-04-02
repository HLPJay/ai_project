# Milestone 2: CaptureCore — 网页长截屏（P0）

## 目标
实现网页场景的自动滚动截屏，输出有序帧序列。

## 前置依赖
- Milestone 1 完成

## 交付清单

### 2.1 接口定义
- src/core/capture/i_capture_engine.h

```cpp
// 参考接口，具体实现时可调整
class ICaptureEngine : public QObject {
    Q_OBJECT
public:
    virtual ~ICaptureEngine() = default;
    virtual void startCapture(const CaptureRequest& request) = 0;
    virtual void stopCapture() = 0;

signals:
    void frameReady(int index, const QImage& frame);
    void captureProgress(int current, int estimated);
    void captureFinished(const CaptureResult& result);
    void captureError(const QString& message);
};
```

### 2.2 网页截屏实现
- src/core/capture/web_capture.h/cpp
- 使用 QWebEngineView 加载目标 URL
- JavaScript 注入实现滚动控制：

**滚动策略：**
1. 注入 JS 获取 `document.documentElement.scrollHeight` 和 `window.innerHeight`
2. 计算总滚动次数：`ceil(scrollHeight / innerHeight)`
3. 每次 `window.scrollBy(0, innerHeight - overlapPx)`，overlap 默认 100px
4. 通过 `QWebEngineView::grab()` 截取当前可视区域
5. 等待 configurable delay（默认 300ms）确保渲染完成
6. 终止条件：`scrollTop + innerHeight >= scrollHeight`

**关键细节：**
- 滚动前先注入 JS 禁用 `scroll-behavior: smooth`，确保滚动立即生效
- 处理懒加载图片：每次滚动后额外等待，或注入 IntersectionObserver 触发
- 处理 `overflow:hidden` 的 body：注入 JS 临时移除
- 页面加载完成判断：监听 `QWebEnginePage::loadFinished` + 额外 500ms 缓冲

### 2.3 滚动策略抽象
- src/core/capture/scroll_strategy.h/cpp

```cpp
struct ScrollConfig {
    int overlapPixels = 100;     // 相邻帧重叠像素
    int scrollDelayMs = 300;     // 滚动后等待时间
    int maxFrames = 200;         // 安全上限，防止无限滚动
    bool disableSmoothScroll = true;
    bool handleLazyLoad = true;
};
```

### 2.4 工作线程封装
- 截屏流程在 QThread 中运行
- 注意：QWebEngineView 必须在主线程创建和操作
- 方案：主线程持有 QWebEngineView，通过信号槽驱动滚动-截取循环
- 截取的 QImage 通过信号传递到工作线程做后续处理

### 2.5 帧序列临时存储
- 截取的帧暂存到临时目录：QStandardPaths::TempLocation + "/longshot_frames/"
- 命名：frame_000.png, frame_001.png, ...
- 截屏完成或取消后清理临时文件

## 完成标准
- [ ] 输入一个 URL，自动加载页面、滚动到底、逐帧截取
- [ ] 输出帧序列到临时目录，帧之间有正确的重叠区域
- [ ] UI 实时显示进度（第 X 帧 / 预估 Y 帧）
- [ ] 可随时点击"停止"中断截屏
- [ ] 长页面（如 Wikipedia 词条）能正确滚动到底
- [ ] 带有 lazy-load 图片的页面能正确等待加载

## 已知风险
- 某些页面的 scrollHeight 会在滚动过程中动态增长（无限滚动），需要 maxFrames 兜底
- iframe 内嵌页面暂不处理（v1 排除）
- HTTPS 证书错误的页面需要配置 QWebEngineProfile 忽略
