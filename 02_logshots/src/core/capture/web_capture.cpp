#include "web_capture.h"

#include <QApplication>
#include <QWebEngineView>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QTimer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QUrl>
#include <QDebug>
#include <QFileInfo>

namespace longshot {
namespace core {

WebCapture::WebCapture(const ScrollConfig& config, QObject* parent)
    : QObject(parent)
    , strategy_(std::make_unique<ScrollStrategy>(config))
    , scrollTimer_(this)
{
    // Note: All Qt GUI objects (including QWebEngineView) MUST be created in the
    // thread they belong to. We assume WebCapture is created in main thread.
    // scrollTimer_ stays in this thread - all WebView ops must happen in main thread.

    // Timer for scroll cycle - use singleshot for precise control
    scrollTimer_.setSingleShot(true);
    connect(&scrollTimer_, &QTimer::timeout, this, &WebCapture::scrollAndCapture, Qt::QueuedConnection);
}

WebCapture::~WebCapture()
{
    stopCapture();

    if (view_) {
        view_->deleteLater();
        view_ = nullptr;
        page_ = nullptr;
    }
}

void WebCapture::startCapture(const CaptureRequest& request)
{
    if (isCapturing_) {
        qWarning() << "[WebCapture] Already capturing";
        return;
    }

    request_ = request;
    currentFrameIndex_ = 0;
    currentScrollTop_ = 0;
    pageScrollHeight_ = 0;
    pageViewportHeight_ = 0;
    initRetryCount_ = 0;
    stopRequested_ = false;
    isCapturing_ = true;

    setupWebView();

    // Normalize URL
    QString url = request_.target;
    if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("file://")) {
        url = QUrl::fromLocalFile(QFileInfo(url).absoluteFilePath()).toString();
    }

    qDebug() << "[WebCapture] Loading URL:" << url;
    state_ = State::Loading;
    view_->setUrl(QUrl(url));
}

void WebCapture::stopCapture()
{
    stopRequested_ = true;
    scrollTimer_.stop();

    if (isCapturing_) {
        isCapturing_ = false;

        CaptureResult result;
        result.framePaths.clear();  // FrameSaver manages the paths
        result.error = QStringLiteral("用户停止");
        emit captureFinished(result);
    }

    state_ = State::Idle;
}

void WebCapture::setupWebView()
{
    // QWebEngineView must be created in the thread that owns it (main thread)
    if (!view_) {
        // Qt::Tool: 不在任务栏显示；FramelessWindowHint: 无边框
        view_ = new QWebEngineView(static_cast<QWidget*>(nullptr));
        // Qt::Tool: 不显示在任务栏和 Alt+Tab 中
        view_->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint);
        // 透明度 0：窗口不可见但仍正常渲染，WebEngine GPU 进程可获取有效视口
        view_->setWindowOpacity(0.0);
        page_ = view_->page();

        connect(page_, &QWebEnginePage::loadFinished,
                this, &WebCapture::onLoadFinished,
                Qt::QueuedConnection);
    }

    // 必须 show() 且有有效尺寸，WebEngine 才会初始化视口（window.innerHeight 才非零）
    view_->resize(1920, 1080);
    view_->show();
}

void WebCapture::onLoadFinished(bool ok)
{
    if (stopRequested_) return;

    if (!ok) {
        emit captureError(QStringLiteral("页面加载失败"));
        isCapturing_ = false;
        state_ = State::Idle;
        return;
    }

    qDebug() << "[WebCapture] Page loaded, waiting 500ms for rendering...";
    state_ = State::GettingPageInfo;
    // 额外 500ms 缓冲，确保页面完全渲染（动态内容、字体等）
    QTimer::singleShot(500, this, &WebCapture::initPageAndGetInfo);
}

void WebCapture::initPageAndGetInfo()
{
    if (stopRequested_) return;

    QString script = strategy_->generateInitScript();
    // runJavaScript is async, result comes via callback in this thread (main thread)
    page_->runJavaScript(script, [this](const QVariant& result) {
        if (stopRequested_) return;
        onJavaScriptResult(result);
    });
}

void WebCapture::onJavaScriptResult(const QVariant& result)
{
    if (stopRequested_) return;

    if (state_ == State::GettingPageInfo) {
        // Parse page info from JSON
        QJsonParseError parseError;
        QJsonDocument doc = QJsonDocument::fromJson(result.toString().toUtf8(), &parseError);

        if (parseError.error != QJsonParseError::NoError) {
            emit captureError(QStringLiteral("页面信息解析失败: %1").arg(parseError.errorString()));
            isCapturing_ = false;
            state_ = State::Idle;
            return;
        }

        QJsonObject info = doc.object();
        pageScrollHeight_ = info["scrollHeight"].toInt();
        pageViewportHeight_ = info["viewportHeight"].toInt();
        currentScrollTop_ = info["scrollTop"].toInt();

        // JS 无法获取视口高度时（WebEngine 视口未初始化），从 Qt widget 尺寸兜底
        if (pageViewportHeight_ <= 0 && view_) {
            pageViewportHeight_ = view_->height();
            qDebug() << "[WebCapture] viewportHeight fallback from widget:" << pageViewportHeight_;
        }

        qDebug() << "[WebCapture] Page info - scrollHeight:" << pageScrollHeight_
                 << "viewportHeight:" << pageViewportHeight_;

        // Estimate total frames
        estimatedTotalFrames_ = strategy_->estimateTotalFrames(pageScrollHeight_, pageViewportHeight_);
        qDebug() << "[WebCapture] Estimated total frames:" << estimatedTotalFrames_;

        if (estimatedTotalFrames_ <= 0) {
            // scrollHeight 可能尚未就绪（SPA 页面动态渲染），再等 500ms 重试一次
            if (pageScrollHeight_ <= 0 && initRetryCount_ < 3) {
                ++initRetryCount_;
                qDebug() << "[WebCapture] scrollHeight=0, retry" << initRetryCount_ << "after 500ms";
                QTimer::singleShot(500, this, &WebCapture::initPageAndGetInfo);
                return;
            }
            emit captureError(QStringLiteral("页面高度无效"));
            isCapturing_ = false;
            state_ = State::Idle;
            return;
        }
        initRetryCount_ = 0;

        // Capture first frame (initial position)
        currentFrameIndex_ = 0;
        captureCurrentFrame();

    } else if (state_ == State::Scrolling) {
        // Parse scroll result
        QJsonParseError parseError;
        QJsonDocument doc = QJsonDocument::fromJson(result.toString().toUtf8(), &parseError);

        if (parseError.error != QJsonParseError::NoError) {
            qWarning() << "[WebCapture] Failed to parse scroll result";
            return;
        }

        QJsonObject info = doc.object();
        currentScrollTop_ = info["scrollTop"].toInt();
        int scrollHeight = info["scrollHeight"].toInt();
        int viewportHeight = info["viewportHeight"].toInt();

        // 同步更新缓存值，供 captureCurrentFrame() 使用
        pageScrollHeight_ = scrollHeight;
        if (viewportHeight > 0) pageViewportHeight_ = viewportHeight;

        // Check if reached bottom
        if (strategy_->isAtBottom(currentScrollTop_, scrollHeight, viewportHeight)) {
            // Finished scrolling
            scrollTimer_.stop();
            state_ = State::Finished;
            isCapturing_ = false;

            CaptureResult captureResult;
            captureResult.framePaths.clear();
            captureResult.error = QString();
            emit captureFinished(captureResult);
        }
    }
}

void WebCapture::captureCurrentFrame()
{
    if (stopRequested_) return;

    // maxFrames 兜底：防止无限滚动页面永不停止
    if (currentFrameIndex_ >= strategy_->config().maxFrames) {
        qWarning() << "[WebCapture] Reached maxFrames limit:" << strategy_->config().maxFrames;
        scrollTimer_.stop();
        state_ = State::Finished;
        isCapturing_ = false;
        CaptureResult captureResult;
        captureResult.error = QString();
        emit captureFinished(captureResult);
        return;
    }

    // grab() returns QPixmap, convert to QImage
    QImage image = view_->grab().toImage();

    if (image.isNull()) {
        qWarning() << "[WebCapture] Failed to grab frame";
        return;
    }

    // Emit frame - FrameSaver (in CaptureRunner) will save it
    emit frameReady(currentFrameIndex_, image);
    emit captureProgress(currentFrameIndex_ + 1, estimatedTotalFrames_);

    // Check if should continue scrolling
    if (strategy_->isAtBottom(currentScrollTop_, pageScrollHeight_, pageViewportHeight_)) {
        // Reached bottom, finish
        scrollTimer_.stop();
        state_ = State::Finished;
        isCapturing_ = false;

        CaptureResult captureResult;
        captureResult.framePaths.clear();
        captureResult.error = QString();
        emit captureFinished(captureResult);
        return;
    }

    // Schedule next scroll
    currentFrameIndex_++;
    state_ = State::Scrolling;
    scrollTimer_.start(request_.scrollDelayMs);
}

void WebCapture::scrollAndCapture()
{
    if (stopRequested_ || !isCapturing_) return;

    // Generate scroll script
    QString scrollScript = strategy_->generateScrollScript(currentScrollTop_);

    // Execute JavaScript - this MUST happen in main thread where page_ lives
    page_->runJavaScript(scrollScript, [this](const QVariant& /*result*/) {
        if (stopRequested_) return;

        // Trigger lazy-load images after scrolling
        QString lazyLoadScript = strategy_->generateLazyLoadTriggerScript();
        if (!lazyLoadScript.isEmpty()) {
            page_->runJavaScript(lazyLoadScript, [](const QVariant& result) {
                // Log triggered lazy-load images
                QJsonParseError parseError;
                QJsonDocument doc = QJsonDocument::fromJson(result.toString().toUtf8(), &parseError);
                if (parseError.error == QJsonParseError::NoError) {
                    QJsonObject obj = doc.object();
                    int triggered = obj["triggered"].toInt();
                    if (triggered > 0) {
                        qDebug() << "[WebCapture] Triggered" << triggered << "lazy-load images";
                    }
                }
            });
        }

        // Wait for lazy-load and rendering to complete
        QTimer::singleShot(request_.scrollDelayMs, this, [this]() {
            if (stopRequested_) return;

            // Get new scroll position and capture
            QString getPosScript = strategy_->generateGetScrollTopScript();
            page_->runJavaScript(getPosScript, [this](const QVariant& result) {
                if (stopRequested_) return;
                onJavaScriptResult(result);

                // If not finished, capture the frame
                if (state_ == State::Scrolling) {
                    captureCurrentFrame();
                }
            });
        });
    });
}

}  // namespace core
}  // namespace longshot
