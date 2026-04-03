#pragma once

#include "i_capture_engine.h"
#include "scroll_strategy.h"

#include <QObject>
#include <QString>
#include <QWebEngineView>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QTimer>
#include <QDir>
#include <memory>

namespace longshot {
namespace core {

/**
 * @brief WebCapture — 网页长截屏实现
 *
 * 使用 QWebEngineView 加载目标 URL，通过 JavaScript 注入控制滚动，
 * 逐帧截取并保存到临时目录。
 *
 * 架构：
 * - QWebEngineView 在主线程创建和管理（Qt 强制要求）
 * - 滚动控制逻辑在工作线程运行，通过信号槽与主线程通信
 * - 帧图片通过 QWebEngineView::grab() 在主线程截取
 */
class WebCapture : public QObject {
    Q_OBJECT

public:
    /**
     * @brief 构造网页截屏器
     * @param config 滚动配置
     * @param parent 父对象
     */
    explicit WebCapture(const ScrollConfig& config, QObject* parent = nullptr);

    ~WebCapture() override;

    /**
     * @brief 开始截屏
     */
    void startCapture(const CaptureRequest& request);

    /**
     * @brief 停止截屏
     */
    void stopCapture();

signals:
    /**
     * @brief 帧截取完成
     */
    void frameReady(int index, const QImage& image);

    /**
     * @brief 截屏进度更新
     */
    void captureProgress(int current, int estimatedTotal);

    /**
     * @brief 截屏完成
     */
    void captureFinished(const CaptureResult& result);

    /**
     * @brief 截屏错误
     */
    void captureError(const QString& message);

private slots:
    void onLoadFinished(bool ok);
    void onJavaScriptResult(const QVariant& result);
    void captureCurrentFrame();
    void scrollAndCapture();
    void onSafetyTimer();

private:
    /**
     * @brief 初始化 WebEngineView
     */
    void setupWebView();

    /**
     * @brief 注入初始化 JS 并获取页面信息
     */
    void initPageAndGetInfo();

    // Qt requires WebView to live in main thread
    QWebEngineView* view_ = nullptr;
    QWebEnginePage* page_ = nullptr;

    std::unique_ptr<ScrollStrategy> strategy_;
    QTimer scrollTimer_;
    QTimer safetyTimer_;                  ///< Safety net: fires every 1s to detect stalled scroll
    int safetyCheckFrameIndex_ = 0;       ///< Frame index at last safety check

    CaptureRequest request_;
    int currentFrameIndex_ = 0;
    int estimatedTotalFrames_ = 0;
    int currentScrollTop_ = 0;
    int pageScrollHeight_ = 0;
    int pageViewportHeight_ = 0;
    int initRetryCount_ = 0;
    int lastScrollHeight_ = 0;        // 上一次滚动后的页面高度
    int stableScrollCount_ = 0;      // 连续稳定滚动次数（页面高度无显著变化）
    bool isCapturing_ = false;
    bool stopRequested_ = false;
    enum class State {
        Idle,
        Loading,
        GettingPageInfo,
        Scrolling,
        Finished
    };
    State state_ = State::Idle;
};

}  // namespace core
}  // namespace longshot
