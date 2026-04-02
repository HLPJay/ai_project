#include "capture_core.h"

#include "capture_runner.h"
#include "i_capture_engine.h"

#include <QInputDialog>
#include <QDir>
#include <QDebug>

CaptureCore::CaptureCore(const longshot::core::ScrollConfig& config, QObject* parent)
    : QObject(parent)
    , runner_(std::make_unique<longshot::core::CaptureRunner>(config))
{
    connect(runner_.get(), &longshot::core::CaptureRunner::captureFinished,
            this, &CaptureCore::onCaptureFinished);
    connect(runner_.get(), &longshot::core::CaptureRunner::captureError,
            this, &CaptureCore::onCaptureError);
    connect(runner_.get(), &longshot::core::CaptureRunner::captureProgress,
            this, &CaptureCore::captureProgress);
}

CaptureCore::~CaptureCore() = default;

void CaptureCore::startCapture()
{
    bool ok = false;
    const QString url = QInputDialog::getText(
        nullptr,
        QStringLiteral("网页截屏"),
        QStringLiteral("请输入要截屏的网页地址："),
        QLineEdit::Normal,
        QStringLiteral("https://"),
        &ok);

    if (!ok || url.trimmed().isEmpty()) {
        qDebug() << "[CaptureCore] User cancelled URL input";
        return;
    }

    longshot::core::CaptureRequest request;
    request.target = url.trimmed();

    qDebug() << "[CaptureCore] Starting capture for URL:" << request.target;
    runner_->startCapture(request);
}

void CaptureCore::stopCapture()
{
    runner_->stopCapture();
}

void CaptureCore::onCaptureFinished(const longshot::core::CaptureResult& result)
{
    if (!result.error.isEmpty()) {
        emit captureFailed(result.error);
        return;
    }

    // Derive the frames directory from the first frame path
    QString framesDir;
    if (!result.framePaths.isEmpty()) {
        framesDir = QDir(result.framePaths.first()).absolutePath();
        // framePaths entries are file paths like /tmp/longshot_frames/frame_0000.png
        // We want the directory, not the file
        framesDir = result.framePaths.first();
        framesDir = framesDir.left(framesDir.lastIndexOf('/') + 1);
    }

    qDebug() << "[CaptureCore] Capture finished, frames dir:" << framesDir
             << ", total frames:" << result.framePaths.size();
    emit captureFinished(framesDir);
}

void CaptureCore::onCaptureError(const QString& message)
{
    qDebug() << "[CaptureCore] Capture error:" << message;
    emit captureFailed(message);
}
