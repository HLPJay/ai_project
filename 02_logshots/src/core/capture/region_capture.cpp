#include "region_capture.h"

#include "../../platform/interface/i_screen_capturer.h"

#include <QDebug>
#include <QDir>
#include <QLoggingCategory>

using namespace longshot::core;

Q_LOGGING_CATEGORY(lcRegionCapture, "regioncapture")

RegionCapture::RegionCapture(
    std::unique_ptr<IScreenCapturer> capturer,
    QObject* parent)
    : ICaptureEngine(parent)
    , capturer_(std::move(capturer))
{
}

RegionCapture::~RegionCapture() = default;

void RegionCapture::startCapture(const CaptureRequest& request)
{
    if (request.mode != CaptureMode::Region) {
        qWarning("RegionCapture: invalid capture mode");
        emit captureError(QStringLiteral("无效的截屏模式"));
        return;
    }

    if (request.regionRect.isNull() || request.regionRect.isEmpty()) {
        qWarning("RegionCapture: invalid region rect");
        emit captureError(QStringLiteral("无效的区域"));
        return;
    }

    qInfo("Starting region capture: rect=(%d,%d %dx%d)",
          request.regionRect.x(), request.regionRect.y(),
          request.regionRect.width(), request.regionRect.height());

    // Capture region
    QImage image;
    if (capturer_) {
        image = capturer_->captureRegion(request.regionRect);
    }

    if (image.isNull()) {
        qWarning("RegionCapture: failed to capture region");
        emit captureError(QStringLiteral("区域截屏失败"));
        return;
    }

    // Ensure directory exists
    QDir dir(request.framesDir);
    if (!dir.exists()) {
        dir.mkpath(request.framesDir);
    }

    // Save single frame (with proper path separator)
    QString fileName = QString("frame_%1.png").arg(0, 4, 10, QChar('0'));
    QString filePath = request.framesDir;
    if (!filePath.endsWith('/') && !filePath.endsWith('\\')) {
        filePath += '/';
    }
    filePath += fileName;

    if (!image.save(filePath, "PNG")) {
        qWarning("RegionCapture: failed to save image");
        emit captureError(QStringLiteral("保存截屏失败"));
        return;
    }

    qInfo("Region capture saved: %s", qUtf8Printable(filePath));

    // Emit completion with actual file path
    CaptureResult result;
    result.framePaths = QStringList() << filePath;
    result.error.clear();

    emit captureFinished(result);
}

void RegionCapture::stopCapture()
{
    // Region capture is single-shot, no stop needed
}