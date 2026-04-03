#include "win_screen_capture.h"

#include <QDebug>
#include <QImage>
#include <QRect>

WinScreenCapturer::WinScreenCapturer()
{
    // 获取屏幕 DC
    hdcScreen_ = GetDC(nullptr);
}

WinScreenCapturer::~WinScreenCapturer()
{
    if (hdcScreen_) {
        ReleaseDC(nullptr, hdcScreen_);
    }
}

QImage WinScreenCapturer::captureWindow(int64_t windowId)
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    if (!hwnd) {
        return QImage();
    }

    // 验证窗口有效性
    if (!IsWindow(hwnd)) {
        return QImage();
    }

    // 优先使用 PrintWindow（更可靠，自动处理 DPI）
    QImage result = captureWithPrintWindow(hwnd);

    // 如果 PrintWindow 失败，尝试 BitBlt
    if (result.isNull()) {
        result = captureWithBitBlt(hwnd);
    }

    return result;
}

namespace {

// MONITOR_DPI_TYPE 枚举（定义在 shellscalingapi.h 中）
enum MONITOR_DPI_TYPE {
    MDT_EFFECTIVE_DPI = 0,
    MDT_ANGULAR_DPI = 1,
    MDT_RAW_DPI = 2,
    MDT_DEFAULT = MDT_EFFECTIVE_DPI
};

// 动态加载 GetDpiForMonitor（shcore.dll 在 Windows 8.1+ 可用）
typedef HRESULT (WINAPI* GetDpiForMonitorFunc)(HMONITOR, MONITOR_DPI_TYPE, UINT*, UINT*);

GetDpiForMonitorFunc getDpiForMonitorFunc() {
    static HMODULE hModule = []() -> HMODULE {
        // Windows 8.1+ 才包含 shcore.dll
        HMODULE h = LoadLibraryW(L"shcore.dll");
        if (h) {
            return h;
        }
        return nullptr;
    }();
    static GetDpiForMonitorFunc func = []() -> GetDpiForMonitorFunc {
        if (hModule) {
            return reinterpret_cast<GetDpiForMonitorFunc>(
                GetProcAddress(hModule, "GetDpiForMonitor"));
        }
        return nullptr;
    }();
    return func;
}

}  // anonymous namespace

QImage WinScreenCapturer::captureRegion(const QRect& rect)
{
    if (!hdcScreen_ || rect.isEmpty()) {
        return QImage();
    }

    // 获取当前显示器 DPI 缩放因子
    double scale = 1.0;
    HMONITOR hmonitor = MonitorFromPoint(POINT{rect.x(), rect.y()}, MONITOR_DEFAULTTOPRIMARY);
    if (hmonitor) {
        auto pfn = getDpiForMonitorFunc();
        if (pfn) {
            UINT dpiX = 96, dpiY = 96;
            if (SUCCEEDED(pfn(hmonitor, MDT_EFFECTIVE_DPI, &dpiX, &dpiY))) {
                scale = static_cast<double>(dpiX) / 96.0;
            }
        }
    }

    // 如果有 DPI 缩放，需要调整坐标
    int x = static_cast<int>(rect.x() * scale);
    int y = static_cast<int>(rect.y() * scale);
    int width = static_cast<int>(rect.width() * scale);
    int height = static_cast<int>(rect.height() * scale);

    if (width <= 0 || height <= 0) {
        return QImage();
    }

    HDC hdcMem = CreateCompatibleDC(hdcScreen_);
    HBITMAP hBitmap = CreateCompatibleBitmap(hdcScreen_, width, height);
    HGDIOBJ old = SelectObject(hdcMem, hBitmap);

    // 设置高质量模式
    SetStretchBltMode(hdcMem, HALFTONE);
    SetBrushOrgEx(hdcMem, 0, 0, nullptr);

    BOOL ret = BitBlt(hdcMem, 0, 0, width, height,
                      hdcScreen_, x, y, SRCCOPY | CAPTUREBLT);

    if (ret) {
        QImage result(width, height, QImage::Format_ARGB32);

        BITMAPINFO bmi = {};
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bmi.bmiHeader.biWidth = width;
        bmi.bmiHeader.biHeight = -height;  // 顶部向下
        bmi.bmiHeader.biPlanes = 1;
        bmi.bmiHeader.biBitCount = 32;
        bmi.bmiHeader.biCompression = BI_RGB;

        GetDIBits(hdcMem, hBitmap, 0, height,
                   result.bits(), &bmi, DIB_RGB_COLORS);

        SelectObject(hdcMem, old);
        DeleteObject(hBitmap);
        DeleteDC(hdcMem);

        return result;
    }

    SelectObject(hdcMem, old);
    DeleteObject(hBitmap);
    DeleteDC(hdcMem);

    return QImage();
}

double WinScreenCapturer::dpiForWindow(int64_t windowId) const
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    if (!hwnd || !IsWindow(hwnd)) {
        return 1.0;
    }

    UINT dpi = GetDpiForWindow(hwnd);
    return static_cast<double>(dpi) / 96.0;
}

bool WinScreenCapturer::isWindowValid(int64_t windowId) const
{
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    return hwnd != nullptr && IsWindow(hwnd) != 0;
}

QImage WinScreenCapturer::captureWithPrintWindow(HWND hwnd)
{
    // 获取窗口 DPI
    UINT dpi = GetDpiForWindow(hwnd);
    double scale = static_cast<double>(dpi) / 96.0;

    // 获取窗口矩形
    RECT rect;
    if (!GetWindowRect(hwnd, &rect)) {
        return QImage();
    }

    int width = static_cast<int>((rect.right - rect.left) * scale);
    int height = static_cast<int>((rect.bottom - rect.top) * scale);

    if (width <= 0 || height <= 0) {
        return QImage();
    }

    // 创建内存 DC
    HDC hdcMem = CreateCompatibleDC(hdcScreen_);
    HBITMAP hBitmap = CreateCompatibleBitmap(hdcScreen_, width, height);
    HGDIOBJ old = SelectObject(hdcMem, hBitmap);

    // 设置高质量模式
    SetStretchBltMode(hdcMem, HALFTONE);
    SetBrushOrgEx(hdcMem, 0, 0, nullptr);

    // 使用 PrintWindow（PW_CLIENTONLY 只截取客户区）
    BOOL result = PrintWindow(hwnd, hdcMem, PW_CLIENTONLY | PW_RENDERFULLCONTENT);

    if (result) {
        // 转换为 QImage
        QImage qimage(width, height, QImage::Format_ARGB32);

        BITMAPINFO bmi = {};
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bmi.bmiHeader.biWidth = width;
        bmi.bmiHeader.biHeight = -height;  // 顶部向下
        bmi.bmiHeader.biPlanes = 1;
        bmi.bmiHeader.biBitCount = 32;
        bmi.bmiHeader.biCompression = BI_RGB;

        int lines = GetDIBits(hdcMem, hBitmap, 0, height,
                               qimage.bits(), &bmi, DIB_RGB_COLORS);

        SelectObject(hdcMem, old);
        DeleteObject(hBitmap);
        DeleteDC(hdcMem);

        if (lines > 0) {
            return qimage;
        }
    }

    SelectObject(hdcMem, old);
    DeleteObject(hBitmap);
    DeleteDC(hdcMem);

    return QImage();
}

QImage WinScreenCapturer::captureWithBitBlt(HWND hwnd)
{
    // 获取窗口客户区 DC
    HDC hdcWindow = GetDC(hwnd);
    if (!hdcWindow) {
        return QImage();
    }

    // 获取窗口客户区矩形（逻辑坐标）
    RECT clientRect;
    if (!GetClientRect(hwnd, &clientRect)) {
        ReleaseDC(hwnd, hdcWindow);
        return QImage();
    }

    int width = clientRect.right - clientRect.left;
    int height = clientRect.bottom - clientRect.top;

    if (width <= 0 || height <= 0) {
        ReleaseDC(hwnd, hdcWindow);
        return QImage();
    }

    // 获取窗口 DPI 缩放因子
    UINT dpi = GetDpiForWindow(hwnd);
    double scale = static_cast<double>(dpi) / 96.0;

    // 目标尺寸（物理像素）
    int targetWidth = static_cast<int>(width * scale);
    int targetHeight = static_cast<int>(height * scale);

    if (targetWidth <= 0 || targetHeight <= 0) {
        ReleaseDC(hwnd, hdcWindow);
        return QImage();
    }

    // 创建内存 DC 并截取
    HDC hdcMem = CreateCompatibleDC(hdcScreen_);
    HBITMAP hBitmap = CreateCompatibleBitmap(hdcScreen_, targetWidth, targetHeight);
    HGDIOBJ old = SelectObject(hdcMem, hBitmap);

    // 设置高质量缩放模式
    SetStretchBltMode(hdcMem, HALFTONE);
    SetBrushOrgEx(hdcMem, 0, 0, nullptr);

    // 将窗口内容复制到内存 DC
    // 注意：StretchBlt 需要源坐标和目标坐标匹配
    // hdcWindow 是客户区 DC（MM_TEXT 映射模式，1:1 像素）
    // 因此源矩形应该是逻辑坐标 (0, 0, width, height)
    BOOL result = StretchBlt(hdcMem, 0, 0, targetWidth, targetHeight,
                             hdcWindow, 0, 0,
                             width, height,
                             SRCCOPY);

    if (result) {
        QImage qimage(targetWidth, targetHeight, QImage::Format_ARGB32);

        BITMAPINFO bmi = {};
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bmi.bmiHeader.biWidth = targetWidth;
        bmi.bmiHeader.biHeight = -targetHeight;
        bmi.bmiHeader.biPlanes = 1;
        bmi.bmiHeader.biBitCount = 32;
        bmi.bmiHeader.biCompression = BI_RGB;

        int lines = GetDIBits(hdcMem, hBitmap, 0, targetHeight,
                               qimage.bits(), &bmi, DIB_RGB_COLORS);

        SelectObject(hdcMem, old);
        DeleteObject(hBitmap);
        DeleteDC(hdcMem);
        ReleaseDC(hwnd, hdcWindow);

        if (lines > 0) {
            return qimage;
        }
    }

    SelectObject(hdcMem, old);
    DeleteObject(hBitmap);
    DeleteDC(hdcMem);
    ReleaseDC(hwnd, hdcWindow);

    return QImage();
}

