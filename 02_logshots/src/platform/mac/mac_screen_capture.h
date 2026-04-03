#pragma once

#include <ApplicationServices/ApplicationServices.h>

#include "../interface/i_screen_capturer.h"
#include <QImage>
#include <QRect>

/**
 * @brief macOS 截屏器实现
 *
 * 使用 CGWindowListCreateImage 截取窗口内容。
 * 自动处理 Retina 屏幕缩放。
 */
class MacScreenCapturer : public IScreenCapturer {
public:
    MacScreenCapturer();
    ~MacScreenCapturer() override;

    QImage captureWindow(int64_t windowId) override;
    QImage captureRegion(const QRect& rect) override;
    double dpiForWindow(int64_t windowId) const override;
    bool isWindowValid(int64_t windowId) const override;

private:
    /**
     * @brief 将 CGImage 转换为 QImage
     */
    QImage cgImageToQImage(CGImageRef cgImage) const;

    /**
     * @brief 检测是否为 Retina 屏幕
     */
    bool isRetinaDisplay() const;

    /// Retina 显示标志缓存
    bool isRetina_;
};

