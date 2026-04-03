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
#include <QtMath>

namespace longshot {
namespace core {

WebCapture::WebCapture(const ScrollConfig& config, QObject* parent)
    : QObject(parent)
    , strategy_(std::make_unique<ScrollStrategy>(config))
    , scrollTimer_(this)
    , safetyTimer_(this)
{
    // Note: All Qt GUI objects (including QWebEngineView) MUST be created in the
    // thread they belong to. We assume WebCapture is created in main thread.

    // Timer for scroll cycle - single-shot, restarted each time
    scrollTimer_.setSingleShot(true);
    connect(&scrollTimer_, &QTimer::timeout, this, &WebCapture::scrollAndCapture, Qt::QueuedConnection);

    // Safety timer: fires every 1s to detect if scroll is stuck
    safetyTimer_.setSingleShot(false);
    safetyTimer_.setInterval(1000);
    connect(&safetyTimer_, &QTimer::timeout, this, &WebCapture::onSafetyTimer, Qt::QueuedConnection);
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
    lastScrollHeight_ = 0;
    stableScrollCount_ = 0;
    safetyCheckFrameIndex_ = 0;
    stopRequested_ = false;
    isCapturing_ = true;
    state_ = State::Loading;

    qDebug() << "[WebCapture] === Starting capture ===";

    setupWebView();

    // Normalize URL
    QString url = request_.target;
    if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("file://")) {
        url = QUrl::fromLocalFile(QFileInfo(url).absoluteFilePath()).toString();
    }

    qDebug() << "[WebCapture] Loading URL:" << url;
    view_->setUrl(QUrl(url));
}

void WebCapture::stopCapture()
{
    if (stopRequested_) {
        return;
    }

    stopRequested_ = true;
    scrollTimer_.stop();
    safetyTimer_.stop();

    if (isCapturing_) {
        isCapturing_ = false;
        qDebug() << "[WebCapture] === Capture stopped ===";

        CaptureResult result;
        result.framePaths.clear();
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
    if (stopRequested_) {
        qDebug() << "[WebCapture] Load finished but stop requested, ignoring";
        return;
    }

    if (!ok) {
        qWarning() << "[WebCapture] Page load failed";
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
    if (stopRequested_) {
        return;
    }

    QString script = strategy_->generateInitScript();
    // runJavaScript is async, result comes via callback in this thread (main thread)
    page_->runJavaScript(script, [this](const QVariant& result) {
        if (stopRequested_) {
            return;
        }
        onJavaScriptResult(result);
    });
}

void WebCapture::onJavaScriptResult(const QVariant& result)
{
    if (stopRequested_) {
        return;
    }

    if (state_ == State::GettingPageInfo) {
        // Parse page info from JSON
        QJsonParseError parseError;
        QJsonDocument doc = QJsonDocument::fromJson(result.toString().toUtf8(), &parseError);

        if (parseError.error != QJsonParseError::NoError) {
            qWarning() << "[WebCapture] Failed to parse page info:" << parseError.errorString();
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
            qWarning() << "[WebCapture] Page height invalid, scrollHeight:" << pageScrollHeight_;
            emit captureError(QStringLiteral("页面高度无效"));
            isCapturing_ = false;
            state_ = State::Idle;
            return;
        }
        initRetryCount_ = 0;

        // Capture first frame (initial position)
        currentFrameIndex_ = 0;
        captureCurrentFrame();

        // Start safety timer to detect stalled scroll
        safetyCheckFrameIndex_ = 0;
        safetyTimer_.start();
        qDebug() << "[WebCapture] Safety timer started";

        // Schedule first scroll after a short delay
        state_ = State::Scrolling;
        scrollTimer_.start(500);  // Small delay before first scroll

    }
    // Note: State::Scrolling is now handled entirely inside scrollAndCapture()
    // to ensure precise scroll-to verification + retry logic
}

void WebCapture::captureCurrentFrame()
{
    if (stopRequested_) {
        return;
    }

    // maxFrames 兜底
    if (currentFrameIndex_ >= strategy_->config().maxFrames) {
        qWarning() << "[WebCapture] Reached maxFrames limit:" << strategy_->config().maxFrames;
        scrollTimer_.stop();
        safetyTimer_.stop();
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
        qWarning() << "[WebCapture] Failed to grab frame" << currentFrameIndex_
                   << "- retrying in 200ms...";
        // Retry after short delay
        QTimer::singleShot(200, this, [this]() {
            if (!stopRequested_) {
                captureCurrentFrame();
            }
        });
        return;
    }

    qDebug() << "[WebCapture] === Capturing frame" << currentFrameIndex_
             << "(scrollTop:" << currentScrollTop_
             << "scrollHeight:" << pageScrollHeight_
             << "viewport:" << pageViewportHeight_
             << ") ===";

    // Emit frame - FrameSaver (in CaptureRunner via QueuedConnection) will save it
    emit frameReady(currentFrameIndex_, image);
    emit captureProgress(currentFrameIndex_ + 1, estimatedTotalFrames_);
}

void WebCapture::onSafetyTimer()
{
    // Safety check: if frame index hasn't advanced, the scroll timer might be stalled
    if (state_ != State::Scrolling || stopRequested_) {
        return;
    }

    if (currentFrameIndex_ == safetyCheckFrameIndex_) {
        qWarning() << "[WebCapture] SAFETY: No new frame captured -"
                  << "frameIndex:" << currentFrameIndex_
                  << "scrollTop:" << currentScrollTop_;
        // Force restart scroll timer if it's not active
        if (!scrollTimer_.isActive()) {
            qWarning() << "[WebCapture] SAFETY: scrollTimer_ stalled, restarting...";
            scrollTimer_.start(100);
        }
    }

    safetyCheckFrameIndex_ = currentFrameIndex_;
}

void WebCapture::scrollAndCapture()
{
    if (stopRequested_ || !isCapturing_) {
        return;
    }

    if (state_ != State::Scrolling) {
        return;
    }

    // Calculate target Y = currentScrollTop + frameOffset
    int targetY = currentScrollTop_ + strategy_->frameOffset(pageViewportHeight_);
    qDebug() << "[WebCapture] scrollAndCapture: targetY =" << targetY
             << "(currentScrollTop:" << currentScrollTop_
             << "frameOffset:" << strategy_->frameOffset(pageViewportHeight_) << ")";

    QString scrollScript = strategy_->generateScrollToScript(targetY);

    // Execute JavaScript - MUST happen in main thread where page_ lives
    page_->runJavaScript(scrollScript, [this, targetY](const QVariant& result) {
        if (stopRequested_) return;

        // Parse scroll response
        QJsonParseError parseError;
        QJsonDocument doc = QJsonDocument::fromJson(result.toString().toUtf8(), &parseError);
        if (parseError.error != QJsonParseError::NoError) {
            qWarning() << "[WebCapture] Failed to parse scrollTo response, retrying...";
            scrollTimer_.start(200);
            return;
        }

        QJsonObject info = doc.object();
        int actualTop = info["scrollTop"].toInt();
        int scrollHeight = info["scrollHeight"].toInt();
        int viewportHeight = info["viewportHeight"].toInt();
        bool reached = info["reached"].toBool();

        qDebug() << "[WebCapture] Scroll result - targetY:" << targetY
                 << "actualTop:" << actualTop
                 << "reached:" << reached
                 << "scrollHeight:" << scrollHeight;

        // Update cached values
        pageScrollHeight_ = scrollHeight;
        if (viewportHeight > 0) pageViewportHeight_ = viewportHeight;

        // Track actual scroll position
        if (reached) {
            currentScrollTop_ = actualTop;
        } else if (actualTop != currentScrollTop_) {
            currentScrollTop_ = actualTop;
        } else {
            currentScrollTop_ = targetY;
            qWarning() << "[WebCapture] Scroll blocked, using expected position:" << currentScrollTop_;
        }

        // ---------- Termination check ----------
        // We use TWO conditions:
        // 1. isAtBottom with ACTUAL scroll position (trust DOM if scroll succeeded)
        // 2. expected position >= page scrollable range (trust frame count if scroll failed)
        bool atBottomByDom = strategy_->isAtBottom(actualTop, scrollHeight, viewportHeight);
        bool atBottomByExpectation = (targetY >= scrollHeight - viewportHeight);
        bool atBottom = atBottomByDom || atBottomByExpectation;
        bool tooManyFrames = (currentFrameIndex_ >= strategy_->config().maxFrames);

        qDebug() << "[WebCapture] Bottom check - byDom:" << atBottomByDom
                 << "byExpectation:" << atBottomByExpectation
                 << "targetY:" << targetY
                 << "scrollHeight-viewport:" << (scrollHeight - viewportHeight);

        if (atBottom || tooManyFrames) {
            scrollTimer_.stop();
            safetyTimer_.stop();
            state_ = State::Finished;
            isCapturing_ = false;

            qDebug() << "[WebCapture] === Finished === atBottom:" << atBottom
                     << "(dom:" << atBottomByDom << "expect:" << atBottomByExpectation << ")"
                     << "totalFrames:" << (currentFrameIndex_ + 1);

            CaptureResult captureResult;
            captureResult.framePaths.clear();
            captureResult.error = QString();
            emit captureFinished(captureResult);
            return;
        }

        // Trigger lazy-load after scrolling
        QString lazyLoadScript = strategy_->generateLazyLoadTriggerScript();
        if (!lazyLoadScript.isEmpty()) {
            page_->runJavaScript(lazyLoadScript, [](const QVariant& res) {
                QJsonParseError pe;
                QJsonDocument d = QJsonDocument::fromJson(res.toString().toUtf8(), &pe);
                if (pe.error == QJsonParseError::NoError) {
                    int triggered = d.object().value("triggered").toInt();
                    if (triggered > 0) {
                        qDebug() << "[WebCapture] Triggered" << triggered << "lazy-load images";
                    }
                }
            });
        }

        // Wait for rendering, then capture and schedule next scroll
        QTimer::singleShot(request_.scrollDelayMs, this, [this]() {
            if (stopRequested_) return;

            currentFrameIndex_++;
            captureCurrentFrame();

            // Schedule next scroll
            scrollTimer_.start(request_.scrollDelayMs);
        });
    });
}

}  // namespace core
}  // namespace longshot
