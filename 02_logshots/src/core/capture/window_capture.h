#pragma once

#include "i_capture_engine.h"
#include "platform/interface/i_screen_capturer.h"
#include "platform/interface/i_scroll_input.h"

#include <QObject>
#include <QTimer>
#include <QRect>
#include <QImage>
#include <atomic>
#include <memory>

namespace longshot {
namespace core {

/**
 * @brief 窗口截屏引擎
 *
 * 实现 ICaptureEngine 接口，用于截取窗口内容并自动滚动。
 * 支持终止检测（像素差异 + 重试机制）和安全上限。
 */
class WindowCapture : public ICaptureEngine {
    Q_OBJECT

public:
    /**
     * @brief 构造截屏引擎
     * @param capturer 平台相关截屏器
     * @param scrollInput 平台相关滚动输入
     * @param parent 父对象
     */
    explicit WindowCapture(
        std::unique_ptr<IScreenCapturer> capturer,
        std::unique_ptr<IScrollInput> scrollInput,
        QObject* parent = nullptr);

    ~WindowCapture() override;

    void startCapture(const CaptureRequest& request) override;
    void stopCapture() override;

    /**
     * @brief 检测截屏场景（通用/终端）
     */
    enum class CaptureScene { Generic, Terminal };

    CaptureScene detectScene(const QString& className) const;

private:
    /**
     * @brief 截屏状态机
     */
    enum class State { Idle, Capturing, Finished, Error };

    /**
     * @brief 执行单次截屏帧
     */
    void captureFrame();

    /**
     * @brief 执行滚动
     */
    void scrollDown();

    /**
     * @brief 检测是否已滚动到底部
     */
    bool detectEndCondition();

    /**
     * @brief 发送错误信号并停止
     */
    void setError(const QString& message);

    /**
     * @brief 完成截屏
     */
    void finishCapture();

    /// 平台相关截屏器
    std::unique_ptr<IScreenCapturer> capturer_;

    /// 平台相关滚动输入
    std::unique_ptr<IScrollInput> scrollInput_;

    /// 当前状态
    State state_ = State::Idle;

    /// 当前截屏请求
    CaptureRequest request_;

    /// 帧序号
    int frameIndex_ = 0;

    /// 上一帧图像（用于差异检测）
    QImage prevFrame_;

    /// 连续相似帧计数（用于重试检测）
    int consecutiveSimilar_ = 0;

    /// 重试次数
    int retryCount_ = 0;

    /// 最大重试次数
    static constexpr int kMaxRetry = 2;

    /// 停止标志
    std::atomic<bool> stopRequested_{false};

    /// 滚动定时器
    std::unique_ptr<QTimer> scrollTimer_;

    /// 场景类型
    CaptureScene scene_ = CaptureScene::Generic;

    /// 已保存的帧文件路径列表
    QStringList framePaths_;

    /// 预估总帧数（用于进度显示）
    int estimatedTotalFrames_ = 0;
};

}  // namespace core
}  // namespace longshot
