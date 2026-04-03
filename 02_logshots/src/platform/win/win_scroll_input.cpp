#include "win_scroll_input.h"

#include <QApplication>
#include <QScreen>
#include <QPoint>
#include <QDebug>
#include <QThread>

WinScrollInput::WinScrollInput(QObject* parent)
    : QObject(parent)
    , targetHwnd_(nullptr)
{
}

WinScrollInput::~WinScrollInput() = default;

bool WinScrollInput::scrollDown(int pixels)
{
    // 必须在主线程调用 SendInput
    if (QThread::currentThread() != qApp->thread()) {
        // 转发到主线程
        QMetaObject::invokeMethod(this, "doScroll",
                                 Qt::QueuedConnection,
                                 Q_ARG(int, pixels));
        return true;
    }
    doScroll(pixels);
    return true;
}

bool WinScrollInput::activateWindow(int64_t windowId)
{
    if (QThread::currentThread() != qApp->thread()) {
        QMetaObject::invokeMethod(this, "doActivateWindow",
                                 Qt::QueuedConnection,
                                 Q_ARG(int64_t, windowId));
        return true;
    }
    doActivateWindow(windowId);
    return true;
}

bool WinScrollInput::moveCursorToCenter(int64_t windowId)
{
    if (QThread::currentThread() != qApp->thread()) {
        QMetaObject::invokeMethod(this, "doMoveCursorToCenter",
                                 Qt::QueuedConnection,
                                 Q_ARG(int64_t, windowId));
        return true;
    }
    doMoveCursorToCenter(windowId);
    return true;
}

QRect WinScrollInput::getWindowCenterRegion(int64_t windowId) const
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    if (!hwnd || !IsWindow(hwnd)) {
        return QRect();
    }

    RECT rect;
    if (!GetWindowRect(hwnd, &rect)) {
        return QRect();
    }

    int width = rect.right - rect.left;
    int height = rect.bottom - rect.top;

    // 返回中心偏下区域（滚动条通常在右侧）
    int centerX = rect.left + width / 2;
    int centerY = rect.top + height * 2 / 3;  // 偏下 2/3 处

    return QRect(centerX - 50, centerY - 50, 100, 100);
}

void WinScrollInput::doScroll(int pixels)
{
    // MOUSEEVENTF_WHEEL: mouseData 以 WHEEL_DELTA(120) 为单位，正值向上，负值向下
    // 将像素值换算为最接近的 WHEEL_DELTA 倍数（至少 1 个单位）
    int clicks = qMax(1, pixels / WHEEL_DELTA);
    // 向下滚动 → 负值，DWORD 存储时用二进制补码，Windows API 内部按 signed 解读
    DWORD delta = static_cast<DWORD>(-clicks * WHEEL_DELTA);

    INPUT input = {};
    input.type = INPUT_MOUSE;
    input.mi.mouseData = delta;
    input.mi.dwFlags = MOUSEEVENTF_WHEEL;

    UINT result = SendInput(1, &input, sizeof(INPUT));
    if (result != 1) {
        qWarning("SendInput failed: %lu", GetLastError());
    }
}

void WinScrollInput::doActivateWindow(int64_t windowId)
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    if (!hwnd || !IsWindow(hwnd)) {
        qWarning("Invalid window handle: %lld", windowId);
        return;
    }

    targetHwnd_ = hwnd;

    // 尝试激活窗口
    if (!SetForegroundWindow(hwnd)) {
        qWarning("SetForegroundWindow failed for hwnd: %p", hwnd);
    }

    // 确保窗口不是最小化
    if (IsIconic(hwnd)) {
        ShowWindow(hwnd, SW_RESTORE);
    }
}

void WinScrollInput::doMoveCursorToCenter(int64_t windowId)
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    if (!hwnd || !IsWindow(hwnd)) {
        return;
    }

    // 获取窗口中心偏下区域（滚动条位置）
    RECT rect;
    if (!GetWindowRect(hwnd, &rect)) {
        return;
    }

    int width = rect.right - rect.left;
    int height = rect.bottom - rect.top;

    // 移动到窗口右侧中间偏下位置
    int x = rect.left + width - 30;
    int y = rect.top + height / 2;

    // 获取当前屏幕的句柄
    HMONITOR hMonitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
    if (hMonitor) {
        // 使用 VirtualScreen 而不是窗口坐标
        x = rect.left + width - 30;
        y = rect.top + height / 2;
    }

    SetCursorPos(x, y);
}

