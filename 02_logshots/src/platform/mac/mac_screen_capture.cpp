#include "mac_screen_capture.h"

#include <QDebug>
#include <QImage>
#include <QRect>

MacScreenCapturer::MacScreenCapturer()
    : isRetina_(false)
{
    // 检测 Retina 屏幕
    // 通常 Retina 屏幕的 scale factor 为 2.0
    CGDirectDisplayID mainDisplay = CGMainDisplayID();
    isRetina_ = CGDisplayScreenSize(mainDisplay).width > 0;
}

MacScreenCapturer::~MacScreenCapturer() = default;

QImage MacScreenCapturer::captureWindow(int64_t windowId)
{
    CGWindowID windowID = static_cast<CGWindowID>(windowId);
    if (windowID == kCGNullWindowID) {
        return QImage();
    }

    // 验证窗口是否存在
    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, windowID);
    if (!windowList) {
        return QImage();
    }

    CFIndex count = CFArrayGetCount(windowList);
    if (count == 0) {
        CFRelease(windowList);
        return QImage();
    }

    // 获取窗口边界
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

    if (CGRectIsNull(bounds)) {
        return QImage();
    }

    // 截取窗口图像
    CGImageRef cgImage = CGWindowListCreateImage(
        bounds,
        kCGWindowListOptionIncludingWindow,
        windowID,
        kCGWindowImageDefault);

    if (!cgImage) {
        // 尝试忽略边框
        cgImage = CGWindowListCreateImage(
            bounds,
            kCGWindowListOptionIncludingWindow,
            windowID,
            kCGWindowImageBoundsIgnoreFraming);
    }

    if (!cgImage) {
        return QImage();
    }

    QImage result = cgImageToQImage(cgImage);
    CGImageRelease(cgImage);

    return result;
}

QImage MacScreenCapturer::captureRegion(const QRect& rect)
{
    if (rect.isEmpty()) {
        return QImage();
    }

    CGRect cgRect = CGRectMake(rect.x(), rect.y(), rect.width(), rect.height());

    CGImageRef cgImage = CGWindowListCreateImage(
        cgRect,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault);

    if (!cgImage) {
        return QImage();
    }

    QImage result = cgImageToQImage(cgImage);
    CGImageRelease(cgImage);

    return result;
}

double MacScreenCapturer::dpiForWindow(int64_t windowId) const
{
    // macOS 使用点（pt）作为逻辑单位
    // Retina 屏幕的物理像素是逻辑像素的 2 倍
    return isRetina_ ? 2.0 : 1.0;
}

bool MacScreenCapturer::isWindowValid(int64_t windowId) const
{
    CGWindowID windowID = static_cast<CGWindowID>(windowId);
    if (windowID == kCGNullWindowID) {
        return false;
    }

    CFArrayRef windowList = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, windowID);
    if (!windowList) {
        return false;
    }

    CFIndex count = CFArrayGetCount(windowList);
    CFRelease(windowList);

    return count > 0;
}

QImage MacScreenCapturer::cgImageToQImage(CGImageRef cgImage) const
{
    if (!cgImage) {
        return QImage();
    }

    int width = CGImageGetWidth(cgImage);
    int height = CGImageGetHeight(cgImage);

    if (width <= 0 || height <= 0) {
        return QImage();
    }

    // 检查是否为 Retina 图像（像素尺寸是逻辑尺寸的 2 倍）
    int bitsPerComponent = CGImageGetBitsPerComponent(cgImage);
    bool isRetinaImage = (bitsPerComponent == 16);

    // 创建 QImage
    QImage::Format format = QImage::Format_ARGB32;
    QImage result(width, height, format);

    // 获取图像数据
    CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(
        result.bits(),
        width,
        height,
        8,
        result.bytesPerLine(),
        colorSpace,
        kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Little);

    if (!context) {
        CGColorSpaceRelease(colorSpace);
        return QImage();
    }

    // 绘制图像
    CGContextDrawImage(context, CGRectMake(0, 0, width, height), cgImage);

    // 清理
    CGContextRelease(context);
    CGColorSpaceRelease(colorSpace);

    // 如果是 Retina 图像，缩放到逻辑尺寸
    if (isRetinaImage && isRetina_) {
        result = result.scaled(width / 2, height / 2,
                              Qt::IgnoreAspectRatio,
                              Qt::SmoothTransformation);
    }

    return result;
}

bool MacScreenCapturer::isRetinaDisplay() const
{
    return isRetina_;
}

