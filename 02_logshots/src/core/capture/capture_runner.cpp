#include "capture_runner.h"

#include "web_capture.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QDebug>
#include <QStandardPaths>

namespace longshot {
namespace core {

// ============================================================================
// FrameSaver
// ============================================================================

FrameSaver::FrameSaver(const QString& tempDir, QObject* parent)
    : QObject(parent)
    , tempDir_(tempDir)
{
    // Ensure temp directory exists
    QDir dir(tempDir_);
    if (!dir.exists()) {
        dir.mkpath(tempDir_);
    }
}

FrameSaver::~FrameSaver()
{
    stop();
}

void FrameSaver::saveFrame(int index, const QImage& image)
{
    QMutexLocker locker(&mutex_);

    if (stopRequested_) {
        return;
    }

    // Generate filename: frame_0000.png, frame_0001.png, ...
    QString fileName = QString("frame_%1.png").arg(index, 4, 10, QChar('0'));
    QString filePath = tempDir_ + fileName;

    // Save to disk
    if (image.save(filePath, "PNG")) {
        savedPaths_.append(filePath);
        qDebug() << "[FrameSaver] Saved frame:" << filePath;
        emit frameSaved(index, filePath);
    } else {
        qWarning() << "[FrameSaver] Failed to save frame:" << filePath;
        emit saveFailed(QStringLiteral("帧保存失败: %1").arg(filePath));
    }
}

void FrameSaver::stop()
{
    QMutexLocker locker(&mutex_);
    stopRequested_ = true;
    waitCondition_.wakeAll();
}

void FrameSaver::reset()
{
    QMutexLocker locker(&mutex_);
    stopRequested_ = false;
    savedPaths_.clear();
}

void FrameSaver::cleanup()
{
    QMutexLocker locker(&mutex_);

    qDebug() << "[FrameSaver] Cleaning up temp files in:" << tempDir_;
    QDir dir(tempDir_);
    QStringList files = dir.entryList(QStringList() << "frame_*.png");
    for (const QString& file : files) {
        if (dir.remove(file)) {
            qDebug() << "[FrameSaver] Removed:" << file;
        } else {
            qWarning() << "[FrameSaver] Failed to remove:" << file;
        }
    }

    // Remove the directory itself if empty
    if (dir.exists() && dir.entryList().isEmpty()) {
        dir.rmdir(tempDir_);
    }

    savedPaths_.clear();
    emit cleanupDone();
}

QStringList FrameSaver::savedPaths() const
{
    QMutexLocker locker(&mutex_);
    return savedPaths_;
}

// ============================================================================
// CaptureRunner
// ============================================================================

CaptureRunner::CaptureRunner(const ScrollConfig& config, QObject* parent)
    : ICaptureEngine(parent)
    , config_(config)
{
    // Create FrameSaver in worker thread
    frameSaver_ = new FrameSaver(QStandardPaths::writableLocation(QStandardPaths::TempLocation)
                                 + "/longshot_frames/");
    frameSaver_->moveToThread(&workerThread_);

    // Connect FrameSaver signals to our signals
    // Note: frameSaved is for internal tracking only, not external signaling
    // External listeners receive QImage via onFrameReady -> frameReady
    connect(frameSaver_, &FrameSaver::saveFailed, this, &CaptureRunner::captureError);
    connect(frameSaver_, &FrameSaver::cleanupDone, this, [this]() {
        qDebug() << "[CaptureRunner] FrameSaver cleanup done";
    });

    // Connect worker thread lifecycle
    connect(&workerThread_, &QThread::finished, frameSaver_, &QObject::deleteLater);

    // Start worker thread
    workerThread_.start();

    // Create WebCapture (must be in main thread)
    createWebCapture();
}

CaptureRunner::~CaptureRunner()
{
    stopCapture();

    workerThread_.quit();
    workerThread_.wait();
}

void CaptureRunner::createWebCapture()
{
    // WebCapture uses QWebEngineView which MUST live in main thread
    webCapture_ = std::make_unique<WebCapture>(config_);

    // Connect WebCapture signals to our signals
    connect(webCapture_.get(), &WebCapture::captureProgress,
            this, &CaptureRunner::captureProgress);
    connect(webCapture_.get(), &WebCapture::captureFinished,
            this, &CaptureRunner::onCaptureFinished);
    connect(webCapture_.get(), &WebCapture::captureError,
            this, &CaptureRunner::onCaptureError);

    // WebCapture emits frameReady(QImage) - forward to external listeners for preview
    // Using QueuedConnection for thread safety
    connect(webCapture_.get(), &WebCapture::frameReady,
            this, &CaptureRunner::onFrameReady,
            Qt::QueuedConnection);

    // Also send to FrameSaver for saving to disk
    // Using QueuedConnection so QImage is safely copied to worker thread
    connect(webCapture_.get(), &WebCapture::frameReady,
            frameSaver_, &FrameSaver::saveFrame,
            Qt::QueuedConnection);
}

void CaptureRunner::startCapture(const CaptureRequest& request)
{
    if (isCapturing_) {
        qWarning() << "[CaptureRunner] Already capturing";
        return;
    }

    isCapturing_ = true;

    // 清理上次的临时文件，然后重置状态（注意：不能调 stop()，它会把 stopRequested_ 设为 true 导致帧不被保存）
    frameSaver_->cleanup();
    frameSaver_->reset();

    // Start capture on WebCapture
    webCapture_->startCapture(request);
}

void CaptureRunner::stopCapture()
{
    if (!isCapturing_) {
        return;
    }

    isCapturing_ = false;

    if (webCapture_) {
        webCapture_->stopCapture();
    }

    frameSaver_->stop();
}

void CaptureRunner::onCaptureFinished(const CaptureResult& result)
{
    isCapturing_ = false;

    // 用已知的 tempDir 路径，而不是 savedPaths()：
    // frameReady→saveFrame 是 QueuedConnection，此时磁盘写入可能还未全部完成。
    // 路径是固定的，文件会在这之后写完。
    CaptureResult finalResult;
    finalResult.framePaths = QStringList() << frameSaver_->tempDir();
    finalResult.error = result.error;

    emit captureFinished(finalResult);
}

void CaptureRunner::onCaptureError(const QString& message)
{
    isCapturing_ = false;
    emit captureError(message);
}

void CaptureRunner::onFrameReady(int index, const QImage& image)
{
    // Forward the QImage to external listeners for real-time preview
    emit frameReady(index, image);
}

}  // namespace core
}  // namespace longshot
