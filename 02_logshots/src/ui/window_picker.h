#pragma once

#include <QWidget>
#include <QImage>
#include <QRect>
#include <QCursor>
#include <QPoint>
#include <QMap>

class IWindowEnumerator;

/**
 * @brief 窗口选择器覆盖层
 *
 * 全屏透明覆盖层，实现类似 Spy++ 的窗口选择功能：
 * 1. 光标变为十字准星
 * 2. 鼠标移动时高亮当前窗口（蓝色边框）
 * 3. 点击确认选择，Esc 取消
 */
class WindowPickerOverlay : public QWidget {
    Q_OBJECT

public:
    /**
     * @brief Construct overlay
     * @param parent Parent widget (should be nullptr for fullscreen)
     */
    explicit WindowPickerOverlay(QWidget* parent = nullptr);

    ~WindowPickerOverlay() override;

    /**
     * @brief 设置窗口枚举器（用于获取窗口信息）
     */
    void setWindowEnumerator(IWindowEnumerator* enumerator);

    /**
     * @brief 显示覆盖层（全屏）
     */
    void showFullscreen();

signals:
    /**
     * @brief 窗口选择完成
     * @param windowId 选中的窗口 ID (HWND 或 CGWindowID)
     */
    void windowSelected(int64_t windowId);

    /**
     * @brief 选择取消
     */
    void cancelled();

protected:
    /// @brief 事件过滤器，追踪鼠标移动
    bool eventFilter(QObject* watched, QEvent* event) override;

    /// @brief 显示事件：捕获背景并显示覆盖层
    void showEvent(QShowEvent* event) override;

    /// @brief 绘制事件：绘制背景遮罩和高亮边框
    void paintEvent(QPaintEvent* event) override;

    /// @brief 鼠标按下事件
    void mousePressEvent(QMouseEvent* event) override;

    /// @brief 键盘事件（处理 Esc）
    void keyPressEvent(QKeyEvent* event) override;

private:
    /**
     * @brief 捕获全屏背景截图
     */
    void captureBackground();

    /**
     * @brief 获取鼠标下的窗口句柄
     */
    int64_t getWindowAtPoint(const QPoint& globalPos);

    /**
     * @brief 获取窗口几何信息
     */
    QRect getWindowRect(int64_t windowId);

    /**
     * @brief 绘制高亮边框
     */
    void drawHighlight(QPainter& painter, const QRect& rect);

    /**
     * @brief 绘制十字光标
     */
    void drawCrossCursor(QPainter& painter, const QPoint& pos);

    /// 全屏背景截图
    QImage backgroundScreenshot_;

    /// 背景截图的偏移量（处理负坐标屏幕）
    QPoint backgroundOffset_;

    /// 当前高亮的窗口句柄
    int64_t hoveredWindowId_ = 0;

    /// 当前高亮窗口的几何矩形
    QRect hoveredWindowRect_;

    /// 窗口枚举器
    IWindowEnumerator* windowEnumerator_ = nullptr;

    /// 缓存窗口几何信息（避免频繁调用 GetWindowRect）
    QMap<int64_t, QRect> windowRectCache_;

    /// 缓存窗口标题信息
    QMap<int64_t, QString> windowTitleCache_;

    /// 缓存窗口类名信息
    QMap<int64_t, QString> windowClassCache_;
};
