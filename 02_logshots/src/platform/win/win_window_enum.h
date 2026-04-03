#pragma once

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "../../core/window/i_window_enumerator.h"

/**
 * @brief Windows 窗口枚举器实现
 *
 * 使用 Win32 API 遍历所有顶层窗口，获取窗口信息并过滤。
 *
 * @note 自窗口排除: 在 MainWindow 的 showEvent() 后调用 setExcludedWindow()，
 *       因为 winId() 在窗口显示前可能返回 0。建议使用:
 *       @code
 *       void MainWindow::showEvent(QShowEvent* event) {
 *           QTimer::singleShot(0, this, [this]() {
 *               enumerator_->setExcludedWindow(reinterpret_cast<int64_t>(winId()));
 *           });
 *           QMainWindow::showEvent(event);
 *       }
 *       @endcode
 */
class WinWindowEnumerator : public IWindowEnumerator {
    Q_OBJECT

public:
    explicit WinWindowEnumerator(QObject* parent = nullptr);
    ~WinWindowEnumerator() override;

    QList<WindowInfo> enumerateWindows() override;
    void setExcludedWindow(int64_t windowId) override;
    int64_t excludedWindow() const override;
    void setMinWindowSize(int minSize) override;
    int minWindowSize() const override;

private:
    /**
     * @brief EnumWindows 回调函数
     */
    static BOOL CALLBACK enumWindowsCallback(HWND hwnd, LPARAM lparam);

    /**
     * @brief 判断窗口是否应被排除
     */
    bool shouldExclude(HWND hwnd) const;

    /**
     * @brief 获取窗口详细信息
     */
    WindowInfo getWindowInfo(HWND hwnd) const;

    int64_t excludedWindow_ = 0;
    int minWindowSize_ = 100;
    QList<WindowInfo> lastResult_;
};
