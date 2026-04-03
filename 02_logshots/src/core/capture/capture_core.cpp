#include "capture_core.h"

#include "capture_runner.h"
#include "i_capture_engine.h"

#include <QInputDialog>
#include <QMessageBox>
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
        QString(),  // 空默认值，强制用户输入
        &ok);

    QString trimmedUrl = url.trimmed();

    // 验证 URL 格式
    if (!ok || trimmedUrl.isEmpty()) {
        qDebug() << "[CaptureCore] User cancelled URL input";
        return;
    }

    // 补全协议前缀
    QString finalUrl = trimmedUrl;
    if (!finalUrl.startsWith("http://") && !finalUrl.startsWith("https://")
        && !finalUrl.startsWith("file://")) {
        finalUrl = "https://" + finalUrl;
    }

    // 验证 URL 有效性（简单检查：包含至少一个点域）
    if (!finalUrl.contains(".") && !finalUrl.contains("file://")) {
        QMessageBox::warning(nullptr, QStringLiteral("无效网址"),
            QStringLiteral("请输入有效的网页地址，例如：\nhttps://example.com"));
        return;
    }

    longshot::core::CaptureRequest request;
    request.target = finalUrl;

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
    // framePaths entries are file paths like /tmp/longshot_frames/frame_0000.png
    QString framesDir;
    if (!result.framePaths.isEmpty()) {
        QString firstPath = result.framePaths.first();
        framesDir = firstPath.left(firstPath.lastIndexOf('/') + 1);
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
