#pragma once

#include "scroll_strategy.h"

#include <QObject>
#include <QString>
#include <memory>

namespace longshot {
namespace core {
class CaptureRunner;
struct CaptureResult;
}  // namespace core
}  // namespace longshot

/**
 * @brief 截屏门面类（UI 层接入点）
 *
 * 封装 CaptureRunner，为 UI 层提供简化接口：
 * - startCapture() 弹出 URL 输入对话框，再启动截屏
 * - 将 CaptureResult 适配为 UI 友好的信号
 */
class CaptureCore : public QObject {
    Q_OBJECT

public:
    /**
     * @brief 构造截屏门面
     * @param config 滚动配置，默认使用标准参数
     * @param parent 父对象
     */
    explicit CaptureCore(
        const longshot::core::ScrollConfig& config = longshot::core::ScrollConfig{},
        QObject* parent = nullptr);

    ~CaptureCore() override;

public slots:
    /**
     * @brief 开始截屏
     *
     * 弹出 URL 输入框；用户取消则不启动截屏。
     */
    void startCapture();

    /**
     * @brief 停止截屏
     */
    void stopCapture();

signals:
    /**
     * @brief 截屏完成
     * @param framesDir 帧文件所在临时目录路径
     */
    void captureFinished(const QString& framesDir);

    /**
     * @brief 截屏失败
     * @param error 错误信息
     */
    void captureFailed(const QString& error);

    /**
     * @brief 截屏进度更新
     * @param current  当前帧序号
     * @param estimated 预估总帧数
     */
    void captureProgress(int current, int estimated);

private slots:
    void onCaptureFinished(const longshot::core::CaptureResult& result);
    void onCaptureError(const QString& message);

private:
    std::unique_ptr<longshot::core::CaptureRunner> runner_;
};
