#include "main_window.h"
#include "window_picker.h"
#include "region_selector.h"
#include "../core/capture/capture_core.h"
#include "../core/capture/capture_runner.h"
#include "../core/capture/window_capture.h"
#include "../core/capture/region_capture.h"
#include "../core/stitcher/image_stitcher.h"
#include "../core/window/i_window_enumerator.h"
#include "../platform/interface/i_screen_capturer.h"
#include "../platform/interface/i_scroll_input.h"
#include <QPushButton>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QLabel>
#include <QWidget>
#include <QFrame>
#include <QMessageBox>
#include <QCloseEvent>
#include <QDesktopServices>
#include <QUrl>
#include <QDebug>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QDateTime>
#include <QStandardPaths>

#ifdef Q_OS_WIN
#include "../platform/win/win_window_enum.h"
#include "../platform/win/win_screen_capture.h"
#include "../platform/win/win_scroll_input.h"
#elif defined(Q_OS_MAC)
#include "../platform/mac/mac_window_enum.h"
#include "../platform/mac/mac_screen_capture.h"
#include "../platform/mac/mac_scroll_input.h"
#endif

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("LongShot");
    setFixedSize(400, 86);
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    setAttribute(Qt::WA_TranslucentBackground);

    auto* centralWidget = new QFrame(this);
    centralWidget->setObjectName("centralWidget");
    centralWidget->setStyleSheet(R"(
        QFrame#centralWidget {
            background-color: #2d2d2d;
            border-radius: 8px;
            border: 1px solid #444;
        }
        QPushButton {
            background-color: #3d3d3d;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: 13px;
            min-width: 60px;
        }
        QPushButton:hover {
            background-color: #4d4d4d;
        }
        QPushButton:pressed {
            background-color: #2d2d2d;
        }
        QLabel#progressLabel {
            color: #aaa;
            font-size: 12px;
        }
    )");

    auto* outerLayout = new QVBoxLayout(centralWidget);
    outerLayout->setContentsMargins(10, 8, 10, 6);
    outerLayout->setSpacing(4);

    auto* btnLayout = new QHBoxLayout();
    btnLayout->setSpacing(8);

    btnWeb_ = new QPushButton("网页", centralWidget);
    btnWindow_ = new QPushButton("窗口", centralWidget);
    btnRegion_ = new QPushButton("区域", centralWidget);
    auto* btnWeb = btnWeb_;
    auto* btnWindow = btnWindow_;
    auto* btnRegion = btnRegion_;
    auto* btnRecord = new QPushButton("录屏", centralWidget);
    auto* btnSettings = new QPushButton("设置", centralWidget);

    btnStop_ = new QPushButton("停止", centralWidget);
    btnStop_->setStyleSheet(R"(
        QPushButton {
            background-color: #c0392b;
            color: #fff;
        }
        QPushButton:hover {
            background-color: #e74c3c;
        }
        QPushButton:pressed {
            background-color: #a93226;
        }
    )");
    btnStop_->hide();

    btnLayout->addWidget(btnWeb);
    btnLayout->addWidget(btnWindow);
    btnLayout->addWidget(btnRegion);
    btnLayout->addWidget(btnRecord);
    btnLayout->addWidget(btnSettings);
    btnLayout->addWidget(btnStop_);

    progressLabel_ = new QLabel(centralWidget);
    progressLabel_->setObjectName("progressLabel");
    progressLabel_->setAlignment(Qt::AlignCenter);
    progressLabel_->hide();

    outerLayout->addLayout(btnLayout);
    outerLayout->addWidget(progressLabel_);

    setCentralWidget(centralWidget);

    captureCore_ = std::make_unique<CaptureCore>();
    stitcher_ = std::make_unique<ImageStitcher>();

    // Initialize window enumerator for window picker
#ifdef Q_OS_WIN
    windowEnumerator_ = new WinWindowEnumerator(this);
#elif defined(Q_OS_MAC)
    windowEnumerator_ = new MacWindowEnumerator(this);
#else
    windowEnumerator_ = nullptr;
#endif

    // Initialize window picker
    windowPicker_ = std::make_unique<WindowPickerOverlay>();
    windowPicker_->setWindowEnumerator(windowEnumerator_);

    // Initialize region selector
    regionSelector_ = std::make_unique<RegionSelectorOverlay>();

    connect(windowPicker_.get(), &WindowPickerOverlay::windowSelected,
            this, &MainWindow::onWindowSelected);
    connect(windowPicker_.get(), &WindowPickerOverlay::cancelled,
            this, &MainWindow::onPickerCancelled);
    connect(regionSelector_.get(), &RegionSelectorOverlay::regionSelected,
            this, &MainWindow::onRegionSelected);
    connect(regionSelector_.get(), &RegionSelectorOverlay::cancelled,
            this, &MainWindow::onPickerCancelled);

    connect(btnWeb, &QPushButton::clicked, this, &MainWindow::onWebCaptureClicked);
    connect(btnWindow, &QPushButton::clicked, this, &MainWindow::onWindowCaptureClicked);
    connect(btnRegion, &QPushButton::clicked, this, &MainWindow::onRegionCaptureClicked);
    connect(btnRecord, &QPushButton::clicked, this, &MainWindow::onRecordClicked);
    connect(btnSettings, &QPushButton::clicked, this, &MainWindow::onSettingsClicked);
    connect(btnStop_, &QPushButton::clicked, this, &MainWindow::onStopCaptureClicked);

    connect(captureCore_.get(), &CaptureCore::captureFinished,
            this, &MainWindow::onCaptureFinished, Qt::QueuedConnection);
    connect(captureCore_.get(), &CaptureCore::captureFailed,
            this, &MainWindow::onCaptureFailed, Qt::QueuedConnection);
    connect(captureCore_.get(), &CaptureCore::captureProgress,
            this, &MainWindow::onCaptureProgress, Qt::QueuedConnection);

    connect(stitcher_.get(), &ImageStitcher::stitchFinished,
            this, &MainWindow::onStitchFinished, Qt::QueuedConnection);
    connect(stitcher_.get(), &ImageStitcher::stitchError,
            this, &MainWindow::onStitchFailed, Qt::QueuedConnection);
    connect(stitcher_.get(), &ImageStitcher::stitchProgress,
            this, &MainWindow::onStitchProgress, Qt::QueuedConnection);

    // Initialize window capture components
    initWindowCapture();
    initRegionCapture();
}

void MainWindow::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        isDragging_ = true;
        dragPosition_ = event->globalPosition().toPoint() - frameGeometry().topLeft();
        event->accept();
    }
}

void MainWindow::mouseMoveEvent(QMouseEvent* event)
{
    if (event->buttons() & Qt::LeftButton && isDragging_) {
        move(event->globalPosition().toPoint() - dragPosition_);
        event->accept();
    }
}

void MainWindow::mouseReleaseEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        isDragging_ = false;
    }
}

void MainWindow::onWebCaptureClicked()
{
    qDebug() << "[MainWindow] Web capture clicked";
    setCaptureButtonsEnabled(false);
    captureCore_->startCapture();
}

void MainWindow::onWindowCaptureClicked()
{
    qDebug() << "[MainWindow] Window capture clicked";

    // Set excluded window to our own, so we don't highlight ourselves
    if (windowEnumerator_) {
#ifdef Q_OS_WIN
        // On Windows, WId is actually HWND which is void*
        // Cast through void* first to avoid MSVC cast issues
        void* hwnd = reinterpret_cast<void*>(winId());
        windowEnumerator_->setExcludedWindow(reinterpret_cast<int64_t>(hwnd));
#else
        windowEnumerator_->setExcludedWindow(static_cast<int64_t>(winId()));
#endif
    }

    // Show window picker overlay
    windowPicker_->showFullscreen();
}

void MainWindow::onRegionCaptureClicked()
{
    qDebug() << "[MainWindow] Region capture clicked";

    // Show region selector overlay
    regionSelector_->showFullscreen();
}

void MainWindow::onRecordClicked()
{
    qDebug() << "[MainWindow] Record clicked";
}

void MainWindow::onSettingsClicked()
{
    qDebug() << "[MainWindow] Settings clicked";
}

void MainWindow::onCaptureFinished(const QString& framesDir)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);
    qDebug() << "[MainWindow] Capture finished, frames dir:" << framesDir;

    if (framesDir.isEmpty()) {
        QMessageBox::warning(this, "截屏失败", "帧文件目录无效");
        return;
    }

    // 列出临时目录中的帧文件
    QDir dir(framesDir);
    QStringList frameFiles = dir.entryList(QStringList() << "frame_*.png", QDir::Files);
    if (frameFiles.isEmpty()) {
        QMessageBox::warning(this, "截屏失败", "未找到帧文件");
        return;
    }

    // 转换为完整路径并按文件名排序
    QStringList framePaths;
    for (const QString& file : frameFiles) {
        framePaths.append(QDir::cleanPath(framesDir + QDir::separator() + file));
    }
    framePaths.sort();
    qDebug() << "[MainWindow] Found" << framePaths.size() << "frames, starting stitch...";

    // 保存 framesDir 供后续使用
    lastFramesDir_ = framesDir;

    // 显示拼接提示
    progressLabel_->setText(QStringLiteral("正在拼接 %1 帧...").arg(framePaths.size()));
    progressLabel_->show();

    // 启动拼接
    StitchConfig config;
    stitcher_->stitch(framePaths, config);
}

void MainWindow::onCaptureFailed(const QString& error)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);
    qDebug() << "[MainWindow] Capture failed:" << error;
    QMessageBox::warning(this, "截屏失败", error);
}

void MainWindow::onStopCaptureClicked()
{
    qDebug() << "[MainWindow] Stop capture clicked";
    if (captureCore_) {
        captureCore_->stopCapture();
    }
    if (windowCapture_) {
        windowCapture_->stopCapture();
    }
    if (regionCapture_) {
        regionCapture_->stopCapture();
    }
    progressLabel_->hide();
    btnStop_->hide();
}

void MainWindow::setCaptureButtonsEnabled(bool enabled)
{
    if (btnWeb_)    btnWeb_->setEnabled(enabled);
    if (btnWindow_) btnWindow_->setEnabled(enabled);
    if (btnRegion_) btnRegion_->setEnabled(enabled);
    if (enabled) btnStop_->hide(); else btnStop_->show();
}

void MainWindow::onCaptureProgress(int current, int estimated)
{
    progressLabel_->show();
    progressLabel_->setText(
        QString("第 %1 帧 / 预估 %2 帧").arg(current + 1).arg(estimated));
}

void MainWindow::onStitchFinished(const StitchResult& result)
{
    progressLabel_->hide();

    if (result.image.isNull()) {
        QMessageBox::warning(this, "拼接失败", "拼接结果图片无效");
        return;
    }

    // 弹出文件保存对话框
    QString defaultName = QString("longshot_%1.png").arg(
        QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss"));
    QString savePath = QFileDialog::getSaveFileName(
        this,
        QStringLiteral("保存长图"),
        defaultName,
        QStringLiteral("PNG 图片 (*.png);;所有文件 (*.*)"));

    if (savePath.isEmpty()) {
        // 用户取消，不保存
        qDebug() << "[MainWindow] User cancelled save dialog";
        return;
    }

    // 确保文件扩展名正确
    if (!savePath.endsWith(".png", Qt::CaseInsensitive)) {
        savePath += ".png";
    }

    // 保存图片
    if (result.image.save(savePath, "PNG")) {
        qDebug() << "[MainWindow] Stitch result saved to:" << savePath;
        QMessageBox::information(this, "保存成功",
            QString("长图已保存到：\n%1").arg(savePath));
        // 打开包含该文件的文件夹
        QFileInfo info(savePath);
        QDesktopServices::openUrl(QUrl::fromLocalFile(info.absolutePath()));
    } else {
        QMessageBox::warning(this, "保存失败", QString("无法保存图片到：\n%1").arg(savePath));
    }
}

void MainWindow::onStitchFailed(const QString& error)
{
    progressLabel_->hide();
    qDebug() << "[MainWindow] Stitch failed:" << error;
    QMessageBox::warning(this, "拼接失败", error);
}

void MainWindow::onStitchProgress(int current, int total)
{
    progressLabel_->show();
    progressLabel_->setText(
        QString("拼接中: %1 / %2").arg(current).arg(total));
}

void MainWindow::closeEvent(QCloseEvent* event)
{
    hide();
    event->ignore();
    qDebug() << "[MainWindow] Minimized to tray";
}

void MainWindow::onWindowSelected(int64_t windowId)
{
    qDebug() << "[MainWindow] Window selected:" << QString::number(windowId, 16);

    // Get window class name for scene detection
    QString className;
    if (windowEnumerator_) {
        QList<WindowInfo> windows = windowEnumerator_->enumerateWindows();
        for (const auto& win : windows) {
            if (win.windowId == windowId) {
                className = win.className;
                break;
            }
        }
    }

    startWindowCaptureWithClass(windowId, className);
}

void MainWindow::onRegionSelected(const QRect& rect)
{
    qDebug() << "[MainWindow] Region selected:" << rect;
    startRegionCapture(rect);
}

void MainWindow::onPickerCancelled()
{
    qDebug() << "[MainWindow] Picker cancelled";
}

void MainWindow::onWindowCaptureFinished(const longshot::core::CaptureResult& result)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);

    if (!result.error.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("窗口截屏失败"), result.error);
        return;
    }

    qDebug() << "[MainWindow] Window capture finished, starting stitch...";

    // Build frame paths from the frames directory
    QDir dir(windowFramesDir_);
    QStringList frameFiles = dir.entryList(QStringList() << "frame_*.png", QDir::Files);
    if (frameFiles.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("窗口截屏失败"), QStringLiteral("未找到帧文件"));
        return;
    }

    QStringList framePaths;
    for (const QString& file : frameFiles) {
        framePaths.append(QDir::cleanPath(windowFramesDir_ + QDir::separator() + file));
    }
    framePaths.sort();

    // Show stitching progress
    progressLabel_->setText(QStringLiteral("正在拼接 %1 帧...").arg(framePaths.size()));
    progressLabel_->show();

    // Start stitching
    StitchConfig config;
    stitcher_->stitch(framePaths, config);
}

void MainWindow::onWindowCaptureError(const QString& error)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);
    qDebug() << "[MainWindow] Window capture error:" << error;
    QMessageBox::warning(this, QStringLiteral("窗口截屏失败"), error);
}

void MainWindow::onWindowCaptureProgress(int current, int estimated)
{
    progressLabel_->show();
    progressLabel_->setText(
        QString("窗口截屏: 第 %1 帧 / 预估 %2 帧").arg(current + 1).arg(estimated > 0 ? QString::number(estimated) : QStringLiteral("?")));
}

void MainWindow::startWindowCapture(int64_t windowId)
{
    startWindowCaptureWithClass(windowId, QString());
}

void MainWindow::startWindowCaptureWithClass(int64_t windowId, const QString& className)
{
    if (!windowCapture_) {
        qWarning() << "[MainWindow] WindowCapture not initialized";
        return;
    }

    setCaptureButtonsEnabled(false);
    progressLabel_->setText(QStringLiteral("窗口截屏初始化中..."));
    progressLabel_->show();

    // 重置 FrameSaver：清理上次帧文件，恢复可写状态
    if (windowFrameSaver_) {
        windowFrameSaver_->cleanup();
        windowFrameSaver_->reset();
    }

    // Build capture request for window mode
    longshot::core::CaptureRequest request;
    request.mode = longshot::core::CaptureMode::Window;
    request.windowHandle = windowId;
    request.windowClassName = className;
    request.framesDir = windowFramesDir_;
    request.overlapPixels = (className.contains(QStringLiteral("Terminal"), Qt::CaseInsensitive)
                           || className.contains(QStringLiteral("Console"), Qt::CaseInsensitive)) ? 200 : 100;
    request.scrollDelayMs = 300;
    request.maxFrames = 200;

    qDebug() << "[MainWindow] Starting window capture for handle:" << QString::number(windowId, 16)
             << "className:" << className;

    // Start capture
    windowCapture_->startCapture(request);
}

void MainWindow::initWindowCapture()
{
#ifdef Q_OS_WIN
    windowScreenCapturer_ = std::make_unique<WinScreenCapturer>();
    scrollInput_ = std::make_unique<WinScrollInput>();
#elif defined(Q_OS_MAC)
    windowScreenCapturer_ = std::make_unique<MacScreenCapturer>();
    scrollInput_ = std::make_unique<MacScrollInput>();
#else
    qWarning() << "[MainWindow] Window capture not supported on this platform";
    return;
#endif

    windowCapture_ = std::make_unique<longshot::core::WindowCapture>(
        std::move(windowScreenCapturer_),
        std::move(scrollInput_));

    windowFramesDir_ = QStandardPaths::writableLocation(QStandardPaths::TempLocation)
                       + "/longshot_window_frames/";

    // Ensure frames directory exists
    QDir().mkpath(windowFramesDir_);

    // Create frame saver for window capture
    windowFrameSaver_ = new longshot::core::FrameSaver(windowFramesDir_, this);
    windowFrameSaver_->moveToThread(&windowCaptureThread_);

    // Connect WindowCapture frameReady to FrameSaver
    connect(windowCapture_.get(), &longshot::core::ICaptureEngine::frameReady,
            windowFrameSaver_, &longshot::core::FrameSaver::saveFrame,
            Qt::QueuedConnection);

    // Connect FrameSaver signals
    connect(windowFrameSaver_, &longshot::core::FrameSaver::saveFailed,
            this, &MainWindow::onWindowCaptureError, Qt::QueuedConnection);

    // Connect WindowCapture signals
    connect(windowCapture_.get(), &longshot::core::ICaptureEngine::captureFinished,
            this, &MainWindow::onWindowCaptureFinished, Qt::QueuedConnection);
    connect(windowCapture_.get(), &longshot::core::ICaptureEngine::captureError,
            this, &MainWindow::onWindowCaptureError, Qt::QueuedConnection);
    connect(windowCapture_.get(), &longshot::core::ICaptureEngine::captureProgress,
            this, &MainWindow::onWindowCaptureProgress, Qt::QueuedConnection);

    // Start worker thread
    windowCaptureThread_.start();

    qDebug() << "[MainWindow] WindowCapture initialized with frames dir:" << windowFramesDir_;
}

void MainWindow::startRegionCapture(const QRect& rect)
{
    if (!regionCapture_) {
        qWarning() << "[MainWindow] RegionCapture not initialized";
        return;
    }

    setCaptureButtonsEnabled(false);
    progressLabel_->setText(QStringLiteral("区域截屏中..."));
    progressLabel_->show();

    // Build capture request for region mode
    longshot::core::CaptureRequest request;
    request.mode = longshot::core::CaptureMode::Region;
    request.regionRect = rect;
    request.framesDir = regionFramesDir_;

    qDebug() << "[MainWindow] Starting region capture for rect:" << rect;

    // Start capture
    regionCapture_->startCapture(request);
}

void MainWindow::initRegionCapture()
{
#ifdef Q_OS_WIN
    regionScreenCapturer_ = std::make_unique<WinScreenCapturer>();
#elif defined(Q_OS_MAC)
    regionScreenCapturer_ = std::make_unique<MacScreenCapturer>();
#else
    qWarning() << "[MainWindow] Region capture not supported on this platform";
    return;
#endif

    regionCapture_ = std::make_unique<longshot::core::RegionCapture>(
        std::move(regionScreenCapturer_));

    regionFramesDir_ = QStandardPaths::writableLocation(QStandardPaths::TempLocation)
                      + "/longshot_region_frames/";

    // Ensure frames directory exists
    QDir().mkpath(regionFramesDir_);

    // Connect RegionCapture signals
    connect(regionCapture_.get(), &longshot::core::ICaptureEngine::captureFinished,
            this, &MainWindow::onRegionCaptureFinished, Qt::QueuedConnection);
    connect(regionCapture_.get(), &longshot::core::ICaptureEngine::captureError,
            this, &MainWindow::onRegionCaptureError, Qt::QueuedConnection);
    connect(regionCapture_.get(), &longshot::core::ICaptureEngine::captureProgress,
            this, &MainWindow::onRegionCaptureProgress, Qt::QueuedConnection);

    qDebug() << "[MainWindow] RegionCapture initialized with frames dir:" << regionFramesDir_;
}

void MainWindow::onRegionCaptureFinished(const longshot::core::CaptureResult& result)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);

    if (!result.error.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("区域截屏失败"), result.error);
        return;
    }

    qDebug() << "[MainWindow] Region capture finished, starting stitch...";

    // Build frame paths from the frames directory
    QDir dir(regionFramesDir_);
    QStringList frameFiles = dir.entryList(QStringList() << "frame_*.png", QDir::Files);
    if (frameFiles.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("区域截屏失败"), QStringLiteral("未找到帧文件"));
        return;
    }

    QStringList framePaths;
    for (const QString& file : frameFiles) {
        framePaths.append(QDir::cleanPath(regionFramesDir_ + QDir::separator() + file));
    }
    framePaths.sort();

    // Show stitching progress (but region capture is single frame, so skip stitch)
    // For region capture, we can directly save the image
    if (framePaths.size() == 1) {
        // Single frame - no stitching needed, just save directly
        QString savePath = QFileDialog::getSaveFileName(
            this,
            QStringLiteral("保存截图"),
            QString("region_%1.png").arg(QDateTime::currentDateTime().toString("yyyyMMdd_hhmmss")),
            QStringLiteral("PNG 图片 (*.png);;所有文件 (*.*)"));

        if (!savePath.isEmpty()) {
            QImage image(framePaths.first());
            if (image.save(savePath, "PNG")) {
                QMessageBox::information(this, QStringLiteral("保存成功"),
                    QStringLiteral("截图已保存到：\n%1").arg(savePath));
            } else {
                QMessageBox::warning(this, QStringLiteral("保存失败"),
                    QStringLiteral("无法保存截图"));
            }
        }
    } else {
        // Multiple frames - use stitcher
        progressLabel_->setText(QStringLiteral("正在拼接 %1 帧...").arg(framePaths.size()));
        progressLabel_->show();
        StitchConfig config;
        stitcher_->stitch(framePaths, config);
    }
}

void MainWindow::onRegionCaptureError(const QString& error)
{
    progressLabel_->hide();
    setCaptureButtonsEnabled(true);
    qDebug() << "[MainWindow] Region capture error:" << error;
    QMessageBox::warning(this, QStringLiteral("区域截屏失败"), error);
}

void MainWindow::onRegionCaptureProgress(int current, int estimated)
{
    Q_UNUSED(estimated);
    progressLabel_->show();
    progressLabel_->setText(QStringLiteral("区域截屏: 第 %1 帧").arg(current + 1));
}

MainWindow::~MainWindow()
{
    // 停止 windowCaptureThread_：FrameSaver 在该线程，必须先退出再析构
    windowCaptureThread_.quit();
    windowCaptureThread_.wait();
}
