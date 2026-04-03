#pragma once

#include <ApplicationServices/ApplicationServices.h>

#include "../../core/window/i_window_enumerator.h"

/**
 * @brief macOS 窗口枚举器实现
 *
 * 使用 CoreGraphics API 遍历所有窗口，获取窗口信息并过滤。
 */
class MacWindowEnumerator : public IWindowEnumerator {
    Q_OBJECT

public:
    explicit MacWindowEnumerator(QObject* parent = nullptr);
    ~MacWindowEnumerator() override;

    QList<WindowInfo> enumerateWindows() override;
    void setExcludedWindow(int64_t windowId) override;
    int64_t excludedWindow() const override;
    void setMinWindowSize(int minSize) override;
    int minWindowSize() const override;

private:
    /**
     * @brief 判断窗口是否应被排除
     */
    bool shouldExclude(CFDictionaryRef windowDict) const;

    /**
     * @brief 从窗口字典提取窗口信息
     */
    WindowInfo getWindowInfo(CFDictionaryRef windowDict) const;

    int64_t excludedWindow_ = 0;
    int minWindowSize_ = 100;
    QList<WindowInfo> lastResult_;
};
