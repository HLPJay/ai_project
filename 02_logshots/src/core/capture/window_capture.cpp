#include "window_capture.h"

#include "../../platform/interface/i_screen_capturer.h"
#include "../../platform/interface/i_scroll_input.h"

#include <QDebug>
#include <QDir>
#include <QFile>
#include <QLoggingCategory>

using namespace longshot::core;

Q_LOGGING_CATEGORY(lcWindowCapture, "windowcapture")

WindowCapture::WindowCapture(
    std::unique_ptr<IScreenCapturer> capturer,
    std::unique_ptr<IScrollInput> scrollInput,
    QObject* parent)
    : ICaptureEngine(parent)
    , capturer_(std::move(capturer))
    , scrollInput_(std::move(scrollInput))
    , scrollTimer_(std::make_unique<QTimer>(this))
{
    scrollTimer_->setSingleShot(true);
    connect(scrollTimer_.get(), &QTimer::timeout, this, &WindowCapture::captureFrame);
}

WindowCapture::~WindowCapture()
{
    stopCapture();
}

void WindowCapture::startCapture(const CaptureRequest& request)
{
    if (state_ == State::Capturing) {
        qWarning("WindowCapture already capturing");
        return;
    }

    if (request.mode != CaptureMode::Window) {
        setError(QStringLiteral("Invalid capture mode: expected Window"));
        return;
    }

    if (request.windowHandle == 0) {
        setError(QStringLiteral("Invalid window handle"));
        return;
    }

    // 验证窗口有效性
    if (capturer_ && !capturer_->isWindowValid(request.windowHandle)) {
        setError(QStringLiteral("Window is no longer valid"));
        return;
    }

    // 初始化状态
    request_ = request;
    state_ = State::Capturing;
    frameIndex_ = 0;
    prevFrame_ = QImage();
    consecutiveSimilar_ = 0;
    retryCount_ = 0;
    stopRequested_ = false;
    framePaths_.clear();
    estimatedTotalFrames_ = request.maxFrames;

    // 检测场景类型（终端场景使用更大的 overlapPixels）
    scene_ = detectScene(request.windowClassName);

    qInfo("Starting window capture: handle=%lld, className=%s, overlap=%d, maxFrames=%d",
          request.windowHandle, qUtf8Printable(request.windowClassName), request.overlapPixels, request.maxFrames);

    // 开始首次截屏
    captureFrame();
}

void WindowCapture::stopCapture()
{
    stopRequested_ = true;
    if (scrollTimer_->isActive()) {
        scrollTimer_->stop();
    }
    state_ = State::Idle;
}

WindowCapture::CaptureScene WindowCapture::detectScene(const QString& className) const
{
    static const QStringList terminalClasses = {
        QStringLiteral("ConsoleWindowClass"),    // cmd.exe
        QStringLiteral("powershell"),            // PowerShell
        QStringLiteral("WindowsTerminal"),        // Windows Terminal
        QStringLiteral("iTerm2"),                // iTerm2
        QStringLiteral("AppleTerminal")          // macOS Terminal
    };

    for (const auto& tc : terminalClasses) {
        if (className.contains(tc, Qt::CaseInsensitive)) {
            return CaptureScene::Terminal;
        }
    }
    return CaptureScene::Generic;
}

void WindowCapture::captureFrame()
{
    // 防御性检查：确保对象状态有效
    if (!capturer_ || !scrollTimer_) {
        qWarning("WindowCapture: capturer_ or scrollTimer_ is null");
        setError(QStringLiteral("Capture engine not properly initialized"));
        return;
    }

    if (stopRequested_ || state_ != State::Capturing) {
        return;
    }

    // 安全上限检查
    if (frameIndex_ >= request_.maxFrames) {
        qInfo("Reached max frames limit: %d", frameIndex_);
        finishCapture();
        return;
    }

    // 验证窗口句柄有效
    if (request_.windowHandle == 0) {
        qWarning("Window handle is 0, cannot capture");
        setError(QStringLiteral("Invalid window handle"));
        return;
    }

    // 验证窗口仍然有效
    if (!capturer_->isWindowValid(request_.windowHandle)) {
        setError(QStringLiteral("Window is no longer valid"));
        return;
    }

    // 截取当前帧
    QImage frame = capturer_->captureWindow(request_.windowHandle);

    if (frame.isNull()) {
        qWarning("Failed to capture frame %d", frameIndex_);
        // 窗口可能暂时不可捕获，等待后重试
        scrollTimer_->start(request_.scrollDelayMs);
        return;
    }

    // 记录帧文件路径（与 FrameSaver 的命名规则一致）
    QString fileName = QString("frame_%1.png").arg(frameIndex_, 4, 10, QChar('0'));
    QString filePath = request_.framesDir;
    if (!filePath.endsWith('/') && !filePath.endsWith('\\')) {
        filePath += '/';
    }
    filePath += fileName;
    framePaths_.append(filePath);

    // 保存帧（emit frameReady 信号，由 FrameSaver 保存）
    emit frameReady(frameIndex_, frame);

    // 检测终止条件
    if (frameIndex_ > 0 && detectEndCondition()) {
        if (retryCount_ < kMaxRetry) {
            // 重试：再滚动一次，等待后再次截帧确认
            qInfo("Possible end detected, retry %d/%d", retryCount_ + 1, kMaxRetry);
            retryCount_++;
            consecutiveSimilar_ = 0;
            scrollDown();
            scrollTimer_->start(request_.scrollDelayMs);  // 等待滚动稳定后再截帧
        } else {
            // 确认已到底
            qInfo("End condition confirmed after %d retries", kMaxRetry);
            finishCapture();
        }
        return;
    }

    // 发送进度信号（1-based 索引）
    emit captureProgress(frameIndex_ + 1, estimatedTotalFrames_);

    // 保存当前帧用于下次比较
    prevFrame_ = frame;
    frameIndex_++;

    // 先执行滚动，再等待延迟后截下一帧（保证每帧之间确实滚动了）
    scrollDown();
    scrollTimer_->start(request_.scrollDelayMs);
}

void WindowCapture::scrollDown()
{
    if (stopRequested_ || state_ != State::Capturing) {
        return;
    }

    // 防御性检查
    if (!scrollInput_ || request_.windowHandle == 0) {
        qWarning("scrollDown: scrollInput_ is null or windowHandle is 0");
        return;
    }

    // 终端场景使用更大的滚动量（确保覆盖 2-3 行）
    int scrollPixels = (scene_ == CaptureScene::Terminal) ? 200 : 120;

    // 激活窗口并移动光标到中心区域
    scrollInput_->activateWindow(request_.windowHandle);
    scrollInput_->moveCursorToCenter(request_.windowHandle);

    // 执行滚动
    if (!scrollInput_->scrollDown(scrollPixels)) {
        qWarning("Scroll failed for frame %d", frameIndex_);
    }
}

bool WindowCapture::detectEndCondition()
{
    if (prevFrame_.isNull() || !capturer_) {
        return false;
    }

    if (request_.windowHandle == 0) {
        return false;
    }

    // 截取当前帧进行对比
    QImage currentFrame = capturer_->captureWindow(request_.windowHandle);

    if (currentFrame.isNull()) {
        return false;
    }

    // 检查尺寸是否相同（窗口可能被调整大小）
    if (currentFrame.size() != prevFrame_.size()) {
        consecutiveSimilar_ = 0;
        return false;
    }

    // 计算像素差异（简化版：采样对比）
    // 注意：实际应用中应使用 OpenCV 的 norm 或模板匹配
    const int sampleStep = 10;  // 每 10 个像素采样一个
    int diffPixels = 0;
    int totalSamples = 0;

    const uchar* prevBits = prevFrame_.bits();
    const uchar* currBits = currentFrame.bits();

    // 防御性检查：确保 bits() 不返回 nullptr
    if (!prevBits || !currBits) {
        qWarning("detectEndCondition: image bits() returned nullptr");
        return false;
    }

    int bytesPerLine = prevFrame_.bytesPerLine();
    int height = prevFrame_.height();
    int width = prevFrame_.width();

    for (int y = 0; y < height; y += sampleStep) {
        for (int x = 0; x < width; x += sampleStep) {
            int idx = y * bytesPerLine + x * 4;  // ARGB32
            if (idx + 3 < prevFrame_.sizeInBytes() && idx + 3 < currentFrame.sizeInBytes()) {
                // 比较 RGB 通道（忽略 Alpha）
                int prevGray = (prevBits[idx] + prevBits[idx+1] + prevBits[idx+2]) / 3;
                int currGray = (currBits[idx] + currBits[idx+1] + currBits[idx+2]) / 3;
                if (qAbs(prevGray - currGray) > 5) {
                    diffPixels++;
                }
                totalSamples++;
            }
        }
    }

    if (totalSamples == 0) {
        return false;
    }

    double diffRatio = static_cast<double>(diffPixels) / totalSamples;

    qDebug("Frame diff: %.4f (threshold: 0.01)", diffRatio);

    if (diffRatio < 0.01) {
        consecutiveSimilar_++;
    } else {
        consecutiveSimilar_ = 0;
    }

    return consecutiveSimilar_ >= 2;
}

void WindowCapture::setError(const QString& message)
{
    qWarning("WindowCapture error: %s", qUtf8Printable(message));
    state_ = State::Error;
    emit captureError(message);
}

void WindowCapture::finishCapture()
{
    state_ = State::Finished;

    CaptureResult result;
    result.framePaths = framePaths_;
    result.error.clear();

    qInfo("Window capture finished: %d frames", frameIndex_);
    emit captureFinished(result);
}
