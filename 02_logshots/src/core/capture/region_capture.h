#pragma once

#include "i_capture_engine.h"
#include "platform/interface/i_screen_capturer.h"

#include <QObject>
#include <memory>

namespace longshot {
namespace core {

/**
 * @brief 区域截屏引擎
 *
 * 实现 ICaptureEngine 接口，用于截取指定屏幕区域（单帧）。
 * 用于 RegionSelector 选择的区域。
 */
class RegionCapture : public ICaptureEngine {
    Q_OBJECT

public:
    /**
     * @brief 构造区域截屏引擎
     * @param capturer 平台相关截屏器
     * @param parent 父对象
     */
    explicit RegionCapture(
        std::unique_ptr<IScreenCapturer> capturer,
        QObject* parent = nullptr);

    ~RegionCapture() override;

    void startCapture(const CaptureRequest& request) override;
    void stopCapture() override;

private:
    /// 平台相关截屏器
    std::unique_ptr<IScreenCapturer> capturer_;
};

}  // namespace core
}  // namespace longshot
