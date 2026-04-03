#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "../interface/i_scroll_input.h"
#include <QRect>
#include <QObject>

/**
 * @brief Windows 滚动输入实现
 *
 * 使用 SendInput 模拟鼠标滚轮事件。
 * 注意：所有 API 调用必须通过 QMetaObject::invokeMethod 转发到主线程。
 */
class WinScrollInput : public QObject, public IScrollInput {
    Q_OBJECT

public:
    explicit WinScrollInput(QObject* parent = nullptr);
    ~WinScrollInput() override;

    bool scrollDown(int pixels) override;
    bool activateWindow(int64_t windowId) override;
    bool moveCursorToCenter(int64_t windowId) override;
    QRect getWindowCenterRegion(int64_t windowId) const override;

public slots:
    /**
     * @brief 执行滚动（必须在主线程调用）
     * @param pixels 滚动像素数
     */
    void doScroll(int pixels);

    /**
     * @brief 激活窗口（必须在主线程调用）
     * @param windowId 窗口 ID
     */
    void doActivateWindow(int64_t windowId);

    /**
     * @brief 移动光标到窗口中心（必须在主线程调用）
     * @param windowId 窗口 ID
     */
    void doMoveCursorToCenter(int64_t windowId);

private:
    /// 目标窗口句柄
    HWND targetHwnd_;
};

