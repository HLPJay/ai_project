#pragma once

#include <QImage>
#include <QRect>

/**
 * @brief 截屏器抽象接口
 *
 * 定义平台相关截屏操作的标准接口。
 */
class IScreenCapturer {
public:
    virtual ~IScreenCapturer() = default;

    /**
     * @brief 截取指定窗口
     * @param windowId 窗口 ID (HWND 或 CGWindowID)
     * @return 截取的图像，失败返回空图像
     */
    virtual QImage captureWindow(int64_t windowId) = 0;

    /**
     * @brief 截取指定区域
     * @param rect 区域坐标（屏幕坐标）
     * @return 截取的图像
     */
    virtual QImage captureRegion(const QRect& rect) = 0;

    /**
     * @brief 获取指定窗口的 DPI 缩放因子
     * @param windowId 窗口 ID
     * @return DPI 缩放因子（如 1.0, 1.25, 1.5, 2.0）
     */
    virtual double dpiForWindow(int64_t windowId) const = 0;

    /**
     * @brief 验证窗口是否仍然有效
     * @param windowId 窗口 ID
     * @return 是否有效
     */
    virtual bool isWindowValid(int64_t windowId) const = 0;
};
