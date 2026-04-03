#include "window_picker.h"

#include <QApplication>
#include <QScreen>
#include <QMouseEvent>
#include <QPainter>
#include <QKeyEvent>
#include <QDebug>

#ifdef Q_OS_WIN
#include <windows.h>
#endif

WindowPickerOverlay::WindowPickerOverlay(QWidget* parent)
    : QWidget(parent)
{
    // 设置为覆盖层窗口标志
    // 使用 Qt::Tool 使其不在任务栏显示，且层级较高
    setWindowFlags(Qt::FramelessWindowHint |
                   Qt::Tool);
    // 设置透明背景属性
    setAttribute(Qt::WA_TranslucentBackground);
    // 不设置 WA_DeleteOnClose，由父对象管理生命周期

    // 安装事件过滤器以追踪鼠标移动
    qApp->installEventFilter(this);
}

WindowPickerOverlay::~WindowPickerOverlay()
{
    qApp->removeEventFilter(this);
}

void WindowPickerOverlay::setWindowEnumerator(IWindowEnumerator* enumerator)
{
    windowEnumerator_ = enumerator;
}

void WindowPickerOverlay::showFullscreen()
{
    // 每次显示前清除旧缓存，避免窗口移动/关闭后使用过期数据
    windowRectCache_.clear();
    windowTitleCache_.clear();
    windowClassCache_.clear();
    hoveredWindowId_ = 0;
    hoveredWindowRect_ = QRect();

    // 获取所有屏幕的联合区域（多显示器支持）
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

void WindowPickerOverlay::showEvent(QShowEvent* event)
{
    QWidget::showEvent(event);
    captureBackground();
}

void WindowPickerOverlay::captureBackground()
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
        // 使用 WId(0) 或 -1 抓取整个桌面（所有屏幕）
        QImage screenGrab = screen->grabWindow(WId(0)).toImage();
        if (!screenGrab.isNull()) {
            // 计算相对坐标（转换为以 totalRect 左上角为原点的坐标系）
            QPoint relativePos = screen->geometry().topLeft() - backgroundOffset_;
            painter.drawImage(relativePos, screenGrab);
        }
    }
    painter.end();
}

bool WindowPickerOverlay::eventFilter(QObject* watched, QEvent* event)
{
    Q_UNUSED(watched);

    if (event->type() == QEvent::MouseMove || event->type() == QEvent::MouseButtonPress) {
        QPoint globalPos = QCursor::pos();
        int64_t windowId = getWindowAtPoint(globalPos);

        if (windowId != hoveredWindowId_) {
            hoveredWindowId_ = windowId;
            if (windowId != 0) {
                hoveredWindowRect_ = getWindowRect(windowId);
            } else {
                hoveredWindowRect_ = QRect();
            }
            update();  // 触发重绘
        }

        // 处理点击事件
        if (event->type() == QEvent::MouseButtonPress) {
            QMouseEvent* mouseEvent = static_cast<QMouseEvent*>(event);
            if (mouseEvent->button() == Qt::LeftButton) {
                // 如果点击时鼠标下有有效窗口
                if (hoveredWindowId_ != 0) {
                    emit windowSelected(hoveredWindowId_);
                } else {
                    emit cancelled();
                }
                close();
            }
        }
    }
    return false;  // 不过滤事件，让它继续传递
}

void WindowPickerOverlay::paintEvent(QPaintEvent* event)
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

    // 2. 如果有高亮窗口，绘制高亮边框
    if (hoveredWindowId_ != 0 && !hoveredWindowRect_.isNull()) {
        drawHighlight(painter, hoveredWindowRect_);
    }

    // 3. 绘制十字光标
    QPoint cursorPos = mapFromGlobal(QCursor::pos());
    drawCrossCursor(painter, cursorPos);
}

void WindowPickerOverlay::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        if (hoveredWindowId_ != 0) {
            emit windowSelected(hoveredWindowId_);
        } else {
            emit cancelled();
        }
        close();
    }
}

void WindowPickerOverlay::keyPressEvent(QKeyEvent* event)
{
    if (event->key() == Qt::Key_Escape) {
        emit cancelled();
        close();
    }
}

int64_t WindowPickerOverlay::getWindowAtPoint(const QPoint& globalPos)
{
#ifdef Q_OS_WIN
    // 验证坐标有效性
    if (globalPos.isNull() || globalPos.x() < -10000 || globalPos.y() < -10000
        || globalPos.x() > 10000 || globalPos.y() > 10000) {
        return 0;
    }

    // 获取自身句柄，用于在 Z-order 遍历中跳过
    HWND selfHwnd = reinterpret_cast<HWND>(effectiveWinId());

    // ChildWindowFromPointEx(GetDesktopWindow(), ...) 只能找到桌面的直接子窗口中最顶层的那个，
    // 而那个最顶层的窗口正是我们自己的透明覆盖层，因此总是返回覆盖层或 0。
    // 正确做法：从覆盖层在 Z-order 中的下一个窗口开始向后遍历，找第一个包含光标的可见顶层窗口。
    POINT point = {globalPos.x(), globalPos.y()};

    HWND hwnd = selfHwnd ? GetWindow(selfHwnd, GW_HWNDNEXT) : GetTopWindow(nullptr);
    while (hwnd) {
        if (hwnd != selfHwnd && IsWindow(hwnd) && IsWindowVisible(hwnd)) {
            RECT winRect;
            if (GetWindowRect(hwnd, &winRect)) {
                if (point.x >= winRect.left && point.x < winRect.right &&
                    point.y >= winRect.top  && point.y < winRect.bottom) {
                    // 找到第一个包含光标点的可见顶层窗口
                    return reinterpret_cast<int64_t>(hwnd);
                }
            }
        }
        hwnd = GetWindow(hwnd, GW_HWNDNEXT);
    }

    return 0;
#elif defined(Q_OS_MAC)
    // macOS: 使用 CGWindowListCopyWindowInfo 获取鼠标下的窗口
    Q_UNUSED(globalPos);
    // TODO: macOS 实现
    return 0;
#else
    return 0;
#endif
}

QRect WindowPickerOverlay::getWindowRect(int64_t windowId)
{
    // 检查缓存
    if (windowRectCache_.contains(windowId)) {
        return windowRectCache_[windowId];
    }

    QRect rect;

#ifdef Q_OS_WIN
    HWND hwnd = reinterpret_cast<HWND>(windowId);
    RECT winRect;
    if (GetWindowRect(hwnd, &winRect)) {
        rect = QRect(winRect.left, winRect.top,
                     winRect.right - winRect.left,
                     winRect.bottom - winRect.top);
    }

    // 获取窗口标题
    wchar_t title[512] = {0};
    if (GetWindowTextW(hwnd, title, 512) > 0) {
        windowTitleCache_[windowId] = QString::fromWCharArray(title);
    }

    // 获取窗口类名
    wchar_t className[256] = {0};
    if (GetClassNameW(hwnd, className, 256) > 0) {
        windowClassCache_[windowId] = QString::fromWCharArray(className);
    }
#elif defined(Q_OS_MAC)
    // macOS: 从窗口枚举器获取
    Q_UNUSED(windowId);
#endif

    // 缓存结果
    windowRectCache_[windowId] = rect;
    return rect;
}

void WindowPickerOverlay::drawHighlight(QPainter& painter, const QRect& rect)
{
    // 绘制半透明蓝色背景
    QColor fillColor(0, 120, 215, 40);  // 蓝色半透明
    painter.fillRect(rect, fillColor);

    // 绘制边框
    QPen borderPen(QColor(0, 120, 215, 255), 2);
    painter.setPen(borderPen);
    painter.drawRect(rect.adjusted(1, 1, -1, -1));

    // 绘制四角装饰
    const int cornerSize = 8;
    QColor cornerColor(0, 120, 215, 255);
    painter.setPen(cornerColor);

    // 左上角
    painter.drawLine(rect.topLeft(), rect.topLeft() + QPoint(cornerSize, 0));
    painter.drawLine(rect.topLeft(), rect.topLeft() + QPoint(0, cornerSize));

    // 右上角
    painter.drawLine(rect.topRight(), rect.topRight() - QPoint(cornerSize, 0));
    painter.drawLine(rect.topRight(), rect.topRight() + QPoint(0, cornerSize));

    // 左下角
    painter.drawLine(rect.bottomLeft(), rect.bottomLeft() + QPoint(cornerSize, 0));
    painter.drawLine(rect.bottomLeft(), rect.bottomLeft() - QPoint(0, cornerSize));

    // 右下角
    painter.drawLine(rect.bottomRight(), rect.bottomRight() - QPoint(cornerSize, 0));
    painter.drawLine(rect.bottomRight(), rect.bottomRight() - QPoint(0, cornerSize));

    // 绘制窗口信息标签
    if (hoveredWindowId_ != 0) {
        QString title = windowTitleCache_.value(hoveredWindowId_, QStringLiteral("未知窗口"));
        QString className = windowClassCache_.value(hoveredWindowId_, QStringLiteral(""));
        QString info = title;
        if (!className.isEmpty()) {
            info += QStringLiteral(" - %1").arg(className);
        }
        info += QStringLiteral(" (%1 x %2)").arg(rect.width()).arg(rect.height());

        // 计算标签位置（在高亮框下方，如果下方空间不够则显示在上方）
        QPoint labelPos = rect.bottomLeft() + QPoint(0, 5);
        QFontMetrics fm(painter.font());
        QRect textRect = fm.boundingRect(info);
        textRect.translate(labelPos);

        // 如果下方超出屏幕，放到上方
        if (textRect.bottom() > painter.viewport().height()) {
            labelPos = rect.topLeft() - QPoint(0, textRect.height() + 5);
        }

        // 绘制标签背景
        painter.setPen(Qt::NoPen);
        QColor labelBg(0, 0, 0, 180);
        painter.fillRect(textRect.adjusted(-5, -2, 5, 2), labelBg);

        // 绘制标签文字
        painter.setPen(Qt::white);
        painter.drawText(labelPos, info);
    }
}

void WindowPickerOverlay::drawCrossCursor(QPainter& painter, const QPoint& pos)
{
    const int crossSize = 20;
    const int crossGap = 5;

    QPen cursorPen(QColor(255, 255, 255, 255), 2);
    QPen shadowPen(QColor(0, 0, 0, 128), 2);
    painter.setPen(shadowPen);

    // 绘制阴影
    painter.drawLine(pos.x() - crossSize, pos.y(), pos.x() - crossGap, pos.y());
    painter.drawLine(pos.x() + crossGap, pos.y(), pos.x() + crossSize, pos.y());
    painter.drawLine(pos.x(), pos.y() - crossSize, pos.x(), pos.y() - crossGap);
    painter.drawLine(pos.x(), pos.y() + crossGap, pos.x(), pos.y() + crossSize);

    // 绘制十字
    painter.setPen(cursorPen);
    painter.drawLine(pos.x() - crossSize, pos.y(), pos.x() - crossGap, pos.y());
    painter.drawLine(pos.x() + crossGap, pos.y(), pos.x() + crossSize, pos.y());
    painter.drawLine(pos.x(), pos.y() - crossSize, pos.x(), pos.y() - crossGap);
    painter.drawLine(pos.x(), pos.y() + crossGap, pos.x(), pos.y() + crossSize);
}
