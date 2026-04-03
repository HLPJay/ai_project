#pragma once

#include <QRect>

/**
 * @brief 滚动输入抽象接口
 *
 * 定义平台相关滚动操作的标准接口。
 */
class IScrollInput {
public:
    virtual ~IScrollInput() = default;

    /**
     * @brief 向下滚动指定像素
     * @param pixels 滚动像素数（正值表示向下）
     * @return 是否成功
     */
    virtual bool scrollDown(int pixels) = 0;

    /**
     * @brief 激活指定窗口（置前）
     * @param windowId 窗口 ID
     * @return 是否成功
     */
    virtual bool activateWindow(int64_t windowId) = 0;

    /**
     * @brief 将光标移动到窗口中心区域（用于触发悬停事件）
     * @param windowId 窗口 ID
     * @return 是否成功
     */
    virtual bool moveCursorToCenter(int64_t windowId) = 0;

    /**
     * @brief 获取窗口中心区域
     * @param windowId 窗口 ID
     * @return 窗口中心矩形区域
     */
    virtual QRect getWindowCenterRegion(int64_t windowId) const = 0;
};
