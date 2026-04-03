#pragma once

#include <QObject>
#include <QString>
#include <QRect>
#include <QList>

/**
 * @brief 窗口信息结构
 *
 * 描述一个顶层窗口的元数据。
 * 注意: windowId 在 Windows 上是 HWND (int64_t)，在 macOS 上是 CGWindowID (uint32_t)
 */
struct WindowInfo {
    /** 窗口句柄/ID */
    int64_t windowId = 0;

    /** 窗口标题 */
    QString title;

    /** 窗口类名（Windows）/ Owner name（macOS） */
    QString className;

    /** 窗口所属进程的可执行文件路径 */
    QString processPath;

    /** 窗口在屏幕上的几何位置（像素坐标） */
    QRect geometry;

    /** 窗口是否可见 */
    bool isVisible = false;

    /** 窗口所属进程的 PID */
    int processId = 0;

    /** 窗口所属进程名 */
    QString processName;

    /** 窗口是否最小化 */
    bool isMinimized = false;

    /** 窗口是否最大化 */
    bool isMaximized = false;
};

/**
 * @brief 窗口枚举器接口
 *
 * 定义窗口枚举的标准接口，用于获取系统中所有可见顶层窗口列表。
 * 平台相关实现分别在 WinWindowEnumerator 和 MacWindowEnumerator 中。
 */
class IWindowEnumerator : public QObject {
    Q_OBJECT

public:
    explicit IWindowEnumerator(QObject* parent = nullptr) : QObject(parent) {}
    ~IWindowEnumerator() override = default;

    /**
     * @brief 枚举所有顶层窗口
     * @return 窗口信息列表（已过滤非法窗口）
     */
    virtual QList<WindowInfo> enumerateWindows() = 0;

    /**
     * @brief 设置要排除的窗口（用于排除自身窗口）
     * @param windowId 要排除的窗口 ID，0 表示不排除任何窗口
     */
    virtual void setExcludedWindow(int64_t windowId) = 0;

    /**
     * @brief 获取要排除的窗口 ID
     */
    virtual int64_t excludedWindow() const = 0;

    /**
     * @brief 设置最小窗口尺寸过滤（宽度或高度小于此值将被忽略）
     * @param minSize 最小尺寸（像素），默认 100
     */
    virtual void setMinWindowSize(int minSize) = 0;

    /**
     * @brief 获取当前最小窗口尺寸过滤值
     */
    virtual int minWindowSize() const = 0;
};
