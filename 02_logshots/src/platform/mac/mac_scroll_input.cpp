#include "mac_scroll_input.h"

#include <QApplication>
#include <QDebug>
#include <QThread>

MacScrollInput::MacScrollInput(QObject* parent)
    : QObject(parent)
{
}

MacScrollInput::~MacScrollInput() = default;

bool MacScrollInput::scrollDown(int pixels)
{
    // macOS 上可以在任何线程发送事件，但为了保持一致也在主线程执行
    if (QThread::currentThread() != qApp->thread()) {
        QMetaObject::invokeMethod(this, "doScroll",
                                 Qt::QueuedConnection,
                                 Q_ARG(int, pixels));
        return true;
    }
    doScroll(pixels);
    return true;
}

bool MacScrollInput::activateWindow(int64_t windowId)
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

bool MacScrollInput::moveCursorToCenter(int64_t windowId)
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

QRect MacScrollInput::getWindowCenterRegion(int64_t windowId) const
{
    CGWindowID windowID = static_cast<CGWindowID>(windowId);
    if (windowID == kCGNullWindowID) {
        return QRect();
    }

    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, windowID);
    if (!windowList) {
        return QRect();
    }

    CFIndex count = CFArrayGetCount(windowList);
    if (count == 0) {
        CFRelease(windowList);
        return QRect();
    }

    CFDictionaryRef windowDict = static_cast<CFDictionaryRef>(
        CFArrayGetValueAtIndex(windowList, 0));
    CFDictionaryRef boundsDict = CFDictionaryGetValue(windowDict,
        kCGWindowBounds);

    CGRect bounds = {};
    if (boundsDict) {
        CGRectMakeWithDictionaryRepresentation(
            reinterpret_cast<CFDictionaryRef>(boundsDict), &bounds);
    }

    CFRelease(windowList);

    // 返回中心偏下区域
    qreal x = bounds.origin.x + bounds.size.width / 2;
    qreal y = bounds.origin.y + bounds.size.height * 2 / 3;

    return QRect(static_cast<int>(x) - 50, static_cast<int>(y) - 50, 100, 100);
}

void MacScrollInput::doScroll(int pixels)
{
    // macOS 滚动：正值为向上，负值为向下
    // 但为了与 Windows 保持一致（正值=向下），我们取反
    int32_t scrollDelta = -pixels;

    // 创建滚动事件
    CGEventRef scrollEvent = CGEventCreateScrollWheelEvent(
        nullptr,  // 使用默认事件源
        kCGScrollEventUnitLine,  // 按行滚动
        1,  // 一个滚动轮
        scrollDelta);

    if (scrollEvent) {
        // 发送事件
        CGEventPost(kCGHIDEventTap, scrollEvent);
        CFRelease(scrollEvent);
    } else {
        qWarning("Failed to create scroll wheel event");
    }
}

void MacScrollInput::doActivateWindow(int64_t windowId)
{
    CGWindowID windowID = static_cast<CGWindowID>(windowId);

    // 获取窗口列表以找到对应的 app
    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, windowID);
    if (!windowList) {
        return;
    }

    CFIndex count = CFArrayGetCount(windowList);
    if (count == 0) {
        CFRelease(windowList);
        return;
    }

    CFDictionaryRef windowDict = static_cast<CFDictionaryRef>(
        CFArrayGetValueAtIndex(windowList, 0));

    // 获取窗口所属的 PID
    CFNumberRef pidRef = CFDictionaryGetValue(windowDict, kCGWindowOwnerPID);
    if (!pidRef) {
        CFRelease(windowList);
        return;
    }

    pid_t pid = 0;
    CFNumberGetValue(pidRef, kCFNumberIntType, &pid);

    CFRelease(windowList);

    if (pid == 0) {
        return;
    }

    // 激活对应应用
    ProcessSerialNumber psn = {};
    GetProcessForPID(pid, &psn);
    SetFrontProcess(&psn);
}

void MacScrollInput::doMoveCursorToCenter(int64_t windowId)
{
    QRect centerRegion = getWindowCenterRegion(windowId);
    if (!centerRegion.isEmpty()) {
        // 移动鼠标到窗口中心
        CGWarpMouseCursorPosition(CGPointMake(centerRegion.center().x(),
                                              centerRegion.center().y()));
    }
}

