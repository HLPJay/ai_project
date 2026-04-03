#include "win_window_enum.h"

#include <psapi.h>
#include <tlhelp32.h>
#include <string>

WinWindowEnumerator::WinWindowEnumerator(QObject* parent)
    : IWindowEnumerator(parent)
{
}

WinWindowEnumerator::~WinWindowEnumerator() = default;

QList<WindowInfo> WinWindowEnumerator::enumerateWindows()
{
    lastResult_.clear();

    // 使用 EnumWindows 遍历所有顶层窗口
    // 第三个参数是 LPARAM，我们传入 this 指针
    if (!EnumWindows(enumWindowsCallback, reinterpret_cast<LPARAM>(this))) {
        qWarning("[WinWindowEnumerator] EnumWindows failed with error: %lu", GetLastError());
    }

    return lastResult_;
}

BOOL CALLBACK WinWindowEnumerator::enumWindowsCallback(HWND hwnd, LPARAM lparam)
{
    auto* enumerator = reinterpret_cast<WinWindowEnumerator*>(lparam);
    if (!enumerator) {
        return FALSE;
    }

    if (!enumerator->shouldExclude(hwnd)) {
        WindowInfo info = enumerator->getWindowInfo(hwnd);
        // 只有满足最小尺寸要求的窗口才添加
        if (info.geometry.width() >= enumerator->minWindowSize_ ||
            info.geometry.height() >= enumerator->minWindowSize_) {
            enumerator->lastResult_.append(info);
        }
    }

    return TRUE;  // 继续枚举
}

bool WinWindowEnumerator::shouldExclude(HWND hwnd) const
{
    // 1. 检查窗口是否可见
    if (!IsWindowVisible(hwnd)) {
        return true;
    }

    // 2. 获取窗口类名
    wchar_t className[256] = {0};
    if (GetClassNameW(hwnd, className, 256) == 0) {
        return true;
    }

    // 3. 排除桌面窗口 (Progman, WorkerW)
    if (wcscmp(className, L"Progman") == 0 || wcscmp(className, L"WorkerW") == 0) {
        return true;
    }

    // 4. 排除任务栏和系统托盘
    if (wcscmp(className, L"Shell_TrayWnd") == 0 ||
        wcscmp(className, L"Shell_SecondaryTrayWnd") == 0 ||
        wcscmp(className, L"NotifyIconOverflowWindow") == 0) {
        return true;
    }

    // 5. 排除开始菜单和 Cortana
    if (wcscmp(className, L"Windows.UI.Core.CoreWindow") == 0) {
        // 进一步检查是否是 Cortana 等系统 UI
        wchar_t title[512] = {0};
        if (GetWindowTextW(hwnd, title, 512) > 0) {
            std::wstring titleStr(title);
            if (titleStr.find(L"Search") != std::wstring::npos ||
                titleStr.find(L"Cortana") != std::wstring::npos) {
                return true;
            }
        }
    }

    // 6. 排除 DV2LightweightVectorwindow (某些系统 UI)
    if (wcscmp(className, L"DV2LightweightVectorwindow") == 0) {
        return true;
    }

    // 7. UWP 应用外壳 (ApplicationFrameWindow)
    // 注意：UWP 应用如微信、QQ、钉钉等使用此外壳。
    // 不再排除，后续截屏时会尝试使用 PrintWindow 捕获内容。
    // 如果捕获失败，窗口选择器仍会显示，用户可手动框选。

    // 8. 排除自身窗口
    if (excludedWindow_ != 0 && reinterpret_cast<int64_t>(hwnd) == excludedWindow_) {
        return true;
    }

    // 9. 获取窗口矩形，检查是否有效
    RECT rect;
    if (!GetWindowRect(hwnd, &rect)) {
        return true;
    }

    // 10. 排除最小化的窗口（RECT 可能有效，但面积为 0）
    if (rect.right <= rect.left || rect.bottom <= rect.top) {
        return true;
    }

    return false;
}

WindowInfo WinWindowEnumerator::getWindowInfo(HWND hwnd) const
{
    WindowInfo info;
    info.windowId = reinterpret_cast<int64_t>(hwnd);
    info.isVisible = IsWindowVisible(hwnd) != 0;

    // 获取窗口标题
    wchar_t title[512] = {0};
    if (GetWindowTextW(hwnd, title, 512) > 0) {
        info.title = QString::fromWCharArray(title);
    }

    // 获取窗口类名
    wchar_t className[256] = {0};
    if (GetClassNameW(hwnd, className, 256) > 0) {
        info.className = QString::fromWCharArray(className);
    }

    // 获取窗口几何信息
    RECT rect;
    if (GetWindowRect(hwnd, &rect)) {
        info.geometry = QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top);
    }

    // 获取进程 ID
    DWORD processId = 0;
    GetWindowThreadProcessId(hwnd, &processId);
    info.processId = static_cast<int>(processId);

    // 获取进程路径和名称
    if (processId != 0) {
        HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, processId);
        if (hProcess) {
            wchar_t processPath[MAX_PATH] = {0};
            DWORD size = MAX_PATH;
            if (QueryFullProcessImageNameW(hProcess, 0, processPath, &size) && size > 0) {
                info.processPath = QString::fromWCharArray(processPath);
                // 提取进程名
                QString fullPath = info.processPath;
                int lastSlash = fullPath.lastIndexOf('\\');
                if (lastSlash >= 0) {
                    info.processName = fullPath.mid(lastSlash + 1);
                } else {
                    info.processName = fullPath;
                }
            } else {
                // QueryFullProcessImageNameW 失败时，使用进程名作为后备
                info.processPath = info.className;  // 使用类名作为后备显示
            }
            CloseHandle(hProcess);
        }
    }

    // 检查窗口状态
    if (IsIconic(hwnd)) {
        info.isMinimized = true;
    }
    if (IsZoomed(hwnd)) {
        info.isMaximized = true;
    }

    return info;
}

void WinWindowEnumerator::setExcludedWindow(int64_t windowId)
{
    excludedWindow_ = windowId;
}

int64_t WinWindowEnumerator::excludedWindow() const
{
    return excludedWindow_;
}

void WinWindowEnumerator::setMinWindowSize(int minSize)
{
    minWindowSize_ = minSize;
}

int WinWindowEnumerator::minWindowSize() const
{
    return minWindowSize_;
}
