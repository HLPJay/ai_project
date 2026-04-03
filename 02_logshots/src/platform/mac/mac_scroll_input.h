#pragma once

#include <ApplicationServices/ApplicationServices.h>

#include "../interface/i_scroll_input.h"
#include <QRect>

/**
 * @brief macOS 滚动输入实现
 *
 * 使用 CGEventCreateScrollWheelEvent 模拟滚动事件。
 */
class MacScrollInput : public QObject, public IScrollInput {
    Q_OBJECT

public:
    explicit MacScrollInput(QObject* parent = nullptr);
    ~MacScrollInput() override;

    bool scrollDown(int pixels) override;
    bool activateWindow(int64_t windowId) override;
    bool moveCursorToCenter(int64_t windowId) override;
    QRect getWindowCenterRegion(int64_t windowId) const override;

public slots:
    /**
     * @brief 执行滚动
     * @param pixels 滚动像素数
     */
    void doScroll(int pixels);

    /**
     * @brief 激活窗口
     * @param windowId 窗口 ID
     */
    void doActivateWindow(int64_t windowId);

    /**
     * @brief 移动光标到窗口中心
     * @param windowId 窗口 ID
     */
    void doMoveCursorToCenter(int64_t windowId);
};

