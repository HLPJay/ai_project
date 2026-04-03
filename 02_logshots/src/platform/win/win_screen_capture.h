#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "../interface/i_screen_capturer.h"
#include <QImage>
#include <QRect>

/**
 * @brief Windows 截屏器实现
 *
 * 使用 PrintWindow 或 BitBlt 截取指定窗口内容。
 * 自动处理 DPI 缩放。
 */
class WinScreenCapturer : public IScreenCapturer {
public:
    WinScreenCapturer();
    ~WinScreenCapturer() override;

    QImage captureWindow(int64_t windowId) override;
    QImage captureRegion(const QRect& rect) override;
    double dpiForWindow(int64_t windowId) const override;
    bool isWindowValid(int64_t windowId) const override;

private:
    /**
     * @brief 使用 PrintWindow 截取窗口（推荐）
     */
    QImage captureWithPrintWindow(HWND hwnd);

    /**
     * @brief 使用 BitBlt 截取窗口（后备）
     */
    QImage captureWithBitBlt(HWND hwnd);

    /// 屏幕 DC 缓存
    HDC hdcScreen_;
};

