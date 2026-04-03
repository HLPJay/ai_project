#include "region_selector.h"

#include <QApplication>
#include <QScreen>
#include <QMouseEvent>
#include <QPainter>
#include <QKeyEvent>
#include <QFontMetrics>

RegionSelectorOverlay::RegionSelectorOverlay(QWidget* parent)
    : QWidget(parent)
{
    setWindowFlags(Qt::FramelessWindowHint |
                   Qt::Tool);
    setAttribute(Qt::WA_TranslucentBackground);
    // 不设置 WA_DeleteOnClose，由父对象管理生命周期
}

RegionSelectorOverlay::~RegionSelectorOverlay() = default;

void RegionSelectorOverlay::showFullscreen()
{
    // 获取所有屏幕的联合区域
    QRect totalRect;
    for (QScreen* screen : QApplication::screens()) {
        totalRect = totalRect.united(screen->geometry());
    }

    if (!totalRect.isEmpty()) {
        setGeometry(totalRect);
    }
    show();
    raise();
    activateWindow();
    setCursor(Qt::CrossCursor);
}

void RegionSelectorOverlay::showEvent(QShowEvent* event)
{
    QWidget::showEvent(event);
    captureBackground();
}

void RegionSelectorOverlay::captureBackground()
{
    // 获取所有屏幕的联合区域
    QRect totalRect;
    QList<QScreen*> screens = QApplication::screens();
    for (QScreen* screen : screens) {
        totalRect = totalRect.united(screen->geometry());
    }

    if (totalRect.isEmpty() || screens.isEmpty()) {
        return;
    }

    // 保存偏移量（用于处理负坐标屏幕）
    backgroundOffset_ = totalRect.topLeft();

    // 创建一个足够大的图像来容纳所有屏幕
    backgroundScreenshot_ = QImage(totalRect.size(), QImage::Format_ARGB32);
    backgroundScreenshot_.fill(Qt::black);

    // 分别捕获每个屏幕并拼接到大图中
    QPainter painter(&backgroundScreenshot_);
    for (QScreen* screen : screens) {
        // 使用 WId(0) 抓取整个桌面（所有屏幕）
        QImage screenGrab = screen->grabWindow(WId(0)).toImage();
        if (!screenGrab.isNull()) {
            // 计算相对坐标
            QPoint relativePos = screen->geometry().topLeft() - backgroundOffset_;
            painter.drawImage(relativePos, screenGrab);
        }
    }
    painter.end();
}

void RegionSelectorOverlay::paintEvent(QPaintEvent* event)
{
    Q_UNUSED(event);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // 1. 绘制全屏背景截图
    if (!backgroundScreenshot_.isNull()) {
        painter.drawImage(backgroundOffset_, backgroundScreenshot_);
    } else {
        painter.fillRect(rect(), QColor(0, 0, 0, 80));
    }

    // 2. 绘制半透明灰色遮罩（选区外区域）
    QColor overlayColor(0, 0, 0, 100);
    painter.fillRect(rect(), overlayColor);

    // 3. 如果有选区，清除选区内的遮罩（显示原图）
    if (!selectionRect_.isNull()) {
        painter.setCompositionMode(QPainter::CompositionMode_Clear);
        painter.fillRect(selectionRect_, Qt::transparent);
        painter.setCompositionMode(QPainter::CompositionMode_SourceOver);

        // 绘制选区
        drawSelection(painter);

        // 绘制调整手柄
        drawHandles(painter);

        // 绘制尺寸标注
        QString sizeText = QStringLiteral("%1 x %2")
                              .arg(selectionRect_.width())
                              .arg(selectionRect_.height());

        QFontMetrics fm(painter.font());
        QRect textRect = fm.boundingRect(sizeText);
        int textX = selectionRect_.right() - textRect.width() - 10;
        int textY = selectionRect_.bottom() + textRect.height() + 10;

        // 如果下方空间不够，放到上方
        if (textY + textRect.height() > height()) {
            textY = selectionRect_.top() - textRect.height() - 10;
        }
        // 如果右边空间不够，左对齐
        if (textX < 0) {
            textX = selectionRect_.left() + 10;
        }

        // 绘制尺寸标注背景
        QColor labelBg(0, 0, 0, 160);
        painter.fillRect(textX - 5, textY - textRect.height() - 2,
                         textRect.width() + 10, textRect.height() + 4,
                         labelBg);

        // 绘制尺寸标注文字
        painter.setPen(Qt::white);
        painter.drawText(textX, textY, sizeText);
    }
}

void RegionSelectorOverlay::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        QPoint pos = event->pos();

        // 检查是否点击了手柄
        int handle = hitHandle(pos);
        if (handle >= 0) {
            dragState_ = ResizeHandle;
            hoveredHandle_ = handle;
        } else if (selectionRect_.contains(pos)) {
            // 点击在选区内，开始移动
            dragState_ = MoveSelection;
            hoveredHandle_ = -1;
        } else {
            // 开始新建选区
            dragState_ = NewSelection;
            selectionRect_ = QRect(pos, QSize(0, 0));
            hoveredHandle_ = -1;
        }

        dragStartPos_ = pos;
        selectionRectBeforeDrag_ = selectionRect_;
        update();
    }
}

void RegionSelectorOverlay::mouseMoveEvent(QMouseEvent* event)
{
    QPoint pos = event->pos();

    if (dragState_ == None) {
        // 悬停状态
        int handle = hitHandle(pos);
        if (handle >= 0) {
            hoveredHandle_ = handle;
            // 根据手柄位置改变光标（与 hitHandle 顺时针编号一致）
            if (handle == 0 || handle == 4) {  // 左上、右下 → 左斜
                setCursor(Qt::SizeFDiagCursor);
            } else if (handle == 2 || handle == 6) {  // 右上、左下 → 右斜
                setCursor(Qt::SizeBDiagCursor);
            } else if (handle == 1 || handle == 5) {  // 上中、下中 → 垂直
                setCursor(Qt::SizeVerCursor);
            } else {  // 右中、左中 (3, 7) → 水平
                setCursor(Qt::SizeHorCursor);
            }
        } else if (selectionRect_.contains(pos)) {
            setCursor(Qt::SizeAllCursor);
            hoveredHandle_ = -1;
        } else {
            setCursor(Qt::CrossCursor);
            hoveredHandle_ = -1;
        }
    } else if (dragState_ == NewSelection) {
        // 绘制新选区
        QPoint topLeft = QPoint(
            qMin(dragStartPos_.x(), pos.x()),
            qMin(dragStartPos_.y(), pos.y())
        );
        QPoint bottomRight = QPoint(
            qMax(dragStartPos_.x(), pos.x()),
            qMax(dragStartPos_.y(), pos.y())
        );
        selectionRect_ = QRect(topLeft, bottomRight);
    } else if (dragState_ == MoveSelection) {
        // 移动选区：相对拖动起点的偏移量叠加到拖动前的矩形上，避免累积误差
        selectionRect_ = selectionRectBeforeDrag_.translated(pos - dragStartPos_);
    } else if (dragState_ == ResizeHandle) {
        // 调整选区大小
        QRect newRect = selectionRectBeforeDrag_;

        switch (hoveredHandle_) {
        case 0: // 左上
            newRect.setLeft(qMin(pos.x(), selectionRectBeforeDrag_.right() - MinSelectionSize));
            newRect.setTop(qMin(pos.y(), selectionRectBeforeDrag_.bottom() - MinSelectionSize));
            break;
        case 1: // 上中
            newRect.setTop(qMin(pos.y(), selectionRectBeforeDrag_.bottom() - MinSelectionSize));
            break;
        case 2: // 右上
            newRect.setRight(qMax(pos.x(), selectionRectBeforeDrag_.left() + MinSelectionSize));
            newRect.setTop(qMin(pos.y(), selectionRectBeforeDrag_.bottom() - MinSelectionSize));
            break;
        case 3: // 右中
            newRect.setRight(qMax(pos.x(), selectionRectBeforeDrag_.left() + MinSelectionSize));
            break;
        case 4: // 右下
            newRect.setRight(qMax(pos.x(), selectionRectBeforeDrag_.left() + MinSelectionSize));
            newRect.setBottom(qMax(pos.y(), selectionRectBeforeDrag_.top() + MinSelectionSize));
            break;
        case 5: // 下中
            newRect.setBottom(qMax(pos.y(), selectionRectBeforeDrag_.top() + MinSelectionSize));
            break;
        case 6: // 左下
            newRect.setLeft(qMin(pos.x(), selectionRectBeforeDrag_.right() - MinSelectionSize));
            newRect.setBottom(qMax(pos.y(), selectionRectBeforeDrag_.top() + MinSelectionSize));
            break;
        case 7: // 左中
            newRect.setLeft(qMin(pos.x(), selectionRectBeforeDrag_.right() - MinSelectionSize));
            break;
        }

        selectionRect_ = newRect;
    }

    update();
}

void RegionSelectorOverlay::mouseReleaseEvent(QMouseEvent* event)
{
    Q_UNUSED(event);
    if (event->button() == Qt::LeftButton) {
        dragState_ = None;
    }
}

void RegionSelectorOverlay::mouseDoubleClickEvent(QMouseEvent* event)
{
    Q_UNUSED(event);
    if (event->button() == Qt::LeftButton) {
        if (!selectionRect_.isNull() && selectionRect_.width() > MinSelectionSize
            && selectionRect_.height() > MinSelectionSize) {
            emit regionSelected(selectionRect_);
            close();
        }
    }
}

void RegionSelectorOverlay::keyPressEvent(QKeyEvent* event)
{
    if (event->key() == Qt::Key_Escape) {
        emit cancelled();
        close();
    } else if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
        if (!selectionRect_.isNull() && selectionRect_.width() > MinSelectionSize
            && selectionRect_.height() > MinSelectionSize) {
            emit regionSelected(selectionRect_);
            close();
        }
    }
}

int RegionSelectorOverlay::hitHandle(const QPoint& pos)
{
    if (selectionRect_.isNull()) {
        return -1;
    }

    // 计算手柄位置
    QRect r = selectionRect_;
    QVector<QRect> handles;
    handles.reserve(8);

    // 顺时针排列，与 mouseMoveEvent switch 保持一致：
    // 0=左上, 1=上中, 2=右上, 3=右中, 4=右下, 5=下中, 6=左下, 7=左中
    handles.append(QRect(r.topLeft()    - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 0 左上
    handles.append(QRect(QPoint(r.center().x() - HandleSize/2, r.top()    - HandleSize/2), QSize(HandleSize, HandleSize)));  // 1 上中
    handles.append(QRect(r.topRight()   - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 2 右上
    handles.append(QRect(QPoint(r.right()  - HandleSize/2, r.center().y() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 3 右中
    handles.append(QRect(r.bottomRight()- QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 4 右下
    handles.append(QRect(QPoint(r.center().x() - HandleSize/2, r.bottom() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 5 下中
    handles.append(QRect(r.bottomLeft() - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 6 左下
    handles.append(QRect(QPoint(r.left()   - HandleSize/2, r.center().y() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 7 左中

    for (int i = 0; i < handles.size(); ++i) {
        if (handles[i].contains(pos)) {
            return i;
        }
    }

    return -1;
}

void RegionSelectorOverlay::drawSelection(QPainter& painter)
{
    // 绘制虚线边框
    QPen pen(Qt::white, 1);
    pen.setStyle(Qt::DashLine);
    painter.setPen(pen);
    painter.drawRect(selectionRect_);

    // 绘制实线外框
    pen.setStyle(Qt::SolidLine);
    pen.setColor(QColor(0, 120, 215, 255));
    pen.setWidth(2);
    painter.setPen(pen);
    painter.drawRect(selectionRect_.adjusted(0, 0, -1, -1));
}

void RegionSelectorOverlay::drawHandles(QPainter& painter)
{
    QRect r = selectionRect_;
    QVector<QRect> handles;
    handles.reserve(8);

    // 顺时针排列，与 hitHandle / mouseMoveEvent switch 保持一致：
    // 0=左上, 1=上中, 2=右上, 3=右中, 4=右下, 5=下中, 6=左下, 7=左中
    handles.append(QRect(r.topLeft()    - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 0 左上
    handles.append(QRect(QPoint(r.center().x() - HandleSize/2, r.top()    - HandleSize/2), QSize(HandleSize, HandleSize)));  // 1 上中
    handles.append(QRect(r.topRight()   - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 2 右上
    handles.append(QRect(QPoint(r.right()  - HandleSize/2, r.center().y() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 3 右中
    handles.append(QRect(r.bottomRight()- QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 4 右下
    handles.append(QRect(QPoint(r.center().x() - HandleSize/2, r.bottom() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 5 下中
    handles.append(QRect(r.bottomLeft() - QPoint(HandleSize/2, HandleSize/2), QSize(HandleSize, HandleSize)));  // 6 左下
    handles.append(QRect(QPoint(r.left()   - HandleSize/2, r.center().y() - HandleSize/2), QSize(HandleSize, HandleSize)));  // 7 左中

    // 绘制手柄
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(0, 120, 215, 255));

    for (int i = 0; i < handles.size(); ++i) {
        painter.drawRect(handles[i]);
    }
}
