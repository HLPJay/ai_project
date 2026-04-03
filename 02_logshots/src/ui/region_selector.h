#pragma once

#include <QWidget>
#include <QRect>
#include <QPoint>
#include <QImage>
#include <QVector>

/**
 * @brief 区域选择器覆盖层
 *
 * 全屏覆盖层，实现区域框选功能：
 * 1. 全屏半透明遮罩
 * 2. 鼠标拖拽绘制矩形选区
 * 3. 选区边缘和角上有拖拽手柄，可调整大小
 * 4. 双击或按 Enter 确认，Esc 取消
 * 5. 选区旁显示尺寸标注
 */
class RegionSelectorOverlay : public QWidget {
    Q_OBJECT

public:
    /**
     * @brief Construct overlay
     * @param parent Parent widget
     */
    explicit RegionSelectorOverlay(QWidget* parent = nullptr);

    ~RegionSelectorOverlay() override;

signals:
    /**
     * @brief 区域选择完成
     * @param rect 选中的区域（屏幕坐标）
     */
    void regionSelected(const QRect& rect);

    /**
     * @brief 选择取消
     */
    void cancelled();

public slots:
    /**
     * @brief 显示覆盖层（全屏）
     */
    void showFullscreen();

protected:
    /// @brief 显示事件：捕获背景并显示覆盖层
    void showEvent(QShowEvent* event) override;

    /// @brief 绘制事件
    void paintEvent(QPaintEvent* event) override;

    /// @brief 鼠标按下事件
    void mousePressEvent(QMouseEvent* event) override;

    /// @brief 鼠标移动事件
    void mouseMoveEvent(QMouseEvent* event) override;

    /// @brief 鼠标释放事件
    void mouseReleaseEvent(QMouseEvent* event) override;

    /// @brief 鼠标双击事件
    void mouseDoubleClickEvent(QMouseEvent* event) override;

    /// @brief 键盘事件
    void keyPressEvent(QKeyEvent* event) override;

private:
    /**
     * @brief 捕获全屏背景截图
     */
    void captureBackground();

    /**
     * @brief 判断点是否在某个手柄内
     * @return -1 表示不在任何手柄内，0-7 表示手柄索引
     */
    int hitHandle(const QPoint& pos);

    /**
     * @brief 绘制选区遮罩
     */
    void drawSelection(QPainter& painter);

    /**
     * @brief 绘制调整手柄
     */
    void drawHandles(QPainter& painter);

    /// 拖拽状态枚举
    enum DragState {
        None,           // 无拖拽
        NewSelection,   // 新建选区
        MoveSelection,  // 移动选区
        ResizeHandle    // 调整大小
    };

    /// 全屏背景截图
    QImage backgroundScreenshot_;

    /// 背景截图的偏移量（处理负坐标屏幕）
    QPoint backgroundOffset_;

    /// 当前选区矩形
    QRect selectionRect_;

    /// 拖拽状态
    DragState dragState_ = None;

    /// 当前悬停的手柄索引（-1 表示无）
    int hoveredHandle_ = -1;

    /// 拖拽起点
    QPoint dragStartPos_;

    /// 拖拽前的选区矩形（用于移动和调整大小时恢复）
    QRect selectionRectBeforeDrag_;

    /// 手柄矩形列表（8个：四角 + 四边中点）
    QVector<QRect> handleRects_;

    /// 手柄大小
    static const int HandleSize = 8;

    /// 最小选区尺寸
    static const int MinSelectionSize = 10;
};
