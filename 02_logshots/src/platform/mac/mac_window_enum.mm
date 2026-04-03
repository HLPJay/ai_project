#include "mac_window_enum.h"

#include <Foundation/Foundation.h>
#include <AppKit/AppKit.h>

MacWindowEnumerator::MacWindowEnumerator(QObject* parent)
    : IWindowEnumerator(parent)
{
}

MacWindowEnumerator::~MacWindowEnumerator() = default;

QList<WindowInfo> MacWindowEnumerator::enumerateWindows()
{
    lastResult_.clear();

    // 获取窗口列表 - 只获取屏幕上的窗口
    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
        kCGNullWindowID);

    if (!windowList) {
        qWarning("[MacWindowEnumerator] CGWindowListCopyWindowInfo returned NULL");
        return lastResult_;
    }

    CFIndex count = CFArrayGetCount(windowList);
    for (CFIndex i = 0; i < count; ++i) {
        CFDictionaryRef windowDict = reinterpret_cast<CFDictionaryRef>(
            CFArrayGetValueAtIndex(windowList, i));

        if (shouldExclude(windowDict)) {
            continue;
        }

        WindowInfo info = getWindowInfo(windowDict);

        // 检查最小尺寸
        if (info.geometry.width() >= minWindowSize_ ||
            info.geometry.height() >= minWindowSize_) {
            lastResult_.append(info);
        }
    }

    CFRelease(windowList);
    return lastResult_;
}

bool MacWindowEnumerator::shouldExclude(CFDictionaryRef windowDict) const
{
    if (!windowDict) {
        return true;
    }

    // 获取窗口层
    CFNumberRef layerRef = reinterpret_cast<CFNumberRef>(
        CFDictionaryGetValue(windowDict, kCGWindowLayer));
    if (!layerRef) {
        return true;
    }

    int32_t layer = 0;
    if (!CFNumberGetValue(layerRef, kCFNumberSInt32Type, &layer)) {
        return true;
    }

    // kCGNormalWindowLevel = 0, 其他值为特殊窗口
    // 一般应用程序窗口都在这个层级
    if (layer != 0) {
        return true;
    }

    // 获取窗口所有者名称（类似 className）
    CFStringRef ownerNameRef = reinterpret_cast<CFStringRef>(
        CFDictionaryGetValue(windowDict, kCGWindowOwnerName));
    if (!ownerNameRef) {
        return true;
    }

    QString ownerName = QString::fromCFString(ownerNameRef);

    // 排除系统 UI
    static const QStringList systemApps = {
        "Dock",           // 码头
        "SystemUIServer", // 系统 UI 服务器
        "Control Center", // 控制中心
        "Notification Center", // 通知中心
        "Spotlight",      // 聚焦搜索
        "VoiceOver",      // 旁白
        "Window Server",  // 窗口服务器
    };

    for (const QString& sysApp : systemApps) {
        if (ownerName == sysApp) {
            return true;
        }
    }

    // 获取窗口 Bounds
    CFDictionaryRef boundsRef = reinterpret_cast<CFDictionaryRef>(
        CFDictionaryGetValue(windowDict, kCGWindowBounds));
    if (!boundsRef) {
        return true;
    }

    CGFloat x = 0, y = 0, width = 0, height = 0;
    CFNumberRef xRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("X")));
    CFNumberRef yRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Y")));
    CFNumberRef widthRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Width")));
    CFNumberRef heightRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Height")));

    if (xRef) CFNumberGetValue(xRef, kCFNumberCGFloatType, &x);
    if (yRef) CFNumberGetValue(yRef, kCFNumberCGFloatType, &y);
    if (widthRef) CFNumberGetValue(widthRef, kCFNumberCGFloatType, &width);
    if (heightRef) CFNumberGetValue(heightRef, kCFNumberCGFloatType, &height);

    // 检查尺寸有效性
    if (width <= 0 || height <= 0) {
        return true;
    }

    // 获取窗口 ID
    CFNumberRef windowIDRef = reinterpret_cast<CFNumberRef>(
        CFDictionaryGetValue(windowDict, kCGWindowNumber));
    if (!windowIDRef) {
        return true;
    }

    int64_t windowID = 0;
    CFNumberGetValue(windowIDRef, kCFNumberSInt64Type, &windowID);

    // 排除自身窗口
    if (excludedWindow_ != 0 && windowID == excludedWindow_) {
        return true;
    }

    // 获取窗口名称（可能为空）
    CFStringRef windowNameRef = reinterpret_cast<CFStringRef>(
        CFDictionaryGetValue(windowDict, kCGWindowName));
    if (windowNameRef) {
        // 窗口有名称才会进一步检查
    }

    return false;
}

WindowInfo MacWindowEnumerator::getWindowInfo(CFDictionaryRef windowDict) const
{
    WindowInfo info;

    // 获取窗口 ID
    CFNumberRef windowIDRef = reinterpret_cast<CFNumberRef>(
        CFDictionaryGetValue(windowDict, kCGWindowNumber));
    if (windowIDRef) {
        int64_t windowID = 0;
        CFNumberGetValue(windowIDRef, kCFNumberSInt64Type, &windowID);
        info.windowId = windowID;
    }

    // 获取窗口名称
    CFStringRef windowNameRef = reinterpret_cast<CFStringRef>(
        CFDictionaryGetValue(windowDict, kCGWindowName));
    if (windowNameRef && CFStringGetLength(windowNameRef) > 0) {
        info.title = QString::fromCFString(windowNameRef);
    }

    // 获取所有者名称 (相当于 className)
    CFStringRef ownerNameRef = reinterpret_cast<CFStringRef>(
        CFDictionaryGetValue(windowDict, kCGWindowOwnerName));
    if (ownerNameRef) {
        info.className = QString::fromCFString(ownerNameRef);
    }

    // 获取窗口 Bounds
    CFDictionaryRef boundsRef = reinterpret_cast<CFDictionaryRef>(
        CFDictionaryGetValue(windowDict, kCGWindowBounds));
    if (boundsRef) {
        CGFloat x = 0, y = 0, width = 0, height = 0;
        CFNumberRef xRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("X")));
        CFNumberRef yRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Y")));
        CFNumberRef widthRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Width")));
        CFNumberRef heightRef = reinterpret_cast<CFNumberRef>(CFDictionaryGetValue(boundsRef, CFSTR("Height")));

        if (xRef) CFNumberGetValue(xRef, kCFNumberCGFloatType, &x);
        if (yRef) CFNumberGetValue(yRef, kCFNumberCGFloatType, &y);
        if (widthRef) CFNumberGetValue(widthRef, kCFNumberCGFloatType, &width);
        if (heightRef) CFNumberGetValue(heightRef, kCFNumberCGFloatType, &height);

        // macOS 坐标系: 原点在左下角，转换为 Qt 的左上角
        // 需要获取屏幕高度来转换
        CGDirectDisplayID displayID = CGMainDisplayID();
        CGFloat screenHeight = CGDisplayBounds(displayID).size.height;

        info.geometry = QRect(static_cast<int>(x),
                              static_cast<int>(screenHeight - y - height),
                              static_cast<int>(width),
                              static_cast<int>(height));
    }

    // 获取所有者 PID
    CFNumberRef ownerPIDRef = reinterpret_cast<CFNumberRef>(
        CFDictionaryGetValue(windowDict, kCGWindowOwnerPID));
    if (ownerPIDRef) {
        int32_t pid = 0;
        CFNumberGetValue(ownerPIDRef, kCFNumberSInt32Type, &pid);
        info.processId = static_cast<int>(pid);

        // 获取进程名
        if (pid > 0) {
            // 使用 NSRunningApplication 来获取进程信息
            pid_t appPid = static_cast<pid_t>(pid);
            NSRunningApplication* app = [NSRunningApplication runningApplicationWithProcessIdentifier:appPid];
            if (app) {
                info.processName = QString::fromNSString(app.localizedName ?: @"");
                NSURL* appURL = app.executableURL;
                if (appURL) {
                    info.processPath = QString::fromNSString(appURL.path);
                }
            }
        }
    }

    // 获取窗口层级
    CFNumberRef layerRef = reinterpret_cast<CFNumberRef>(
        CFDictionaryGetValue(windowDict, kCGWindowLayer));
    if (layerRef) {
        int32_t layer = 0;
        CFNumberGetValue(layerRef, kCFNumberSInt32Type, &layer);
        // layer == 0 表示普通窗口
        info.isVisible = (layer == 0);
    }

    return info;
}

void MacWindowEnumerator::setExcludedWindow(int64_t windowId)
{
    excludedWindow_ = windowId;
}

int64_t MacWindowEnumerator::excludedWindow() const
{
    return excludedWindow_;
}

void MacWindowEnumerator::setMinWindowSize(int minSize)
{
    minWindowSize_ = minSize;
}

int MacWindowEnumerator::minWindowSize() const
{
    return minWindowSize_;
}
