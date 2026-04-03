#include <QtTest/QtTest>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QDebug>

// 窗口枚举器实现 - 根据平台选择
#ifdef Q_OS_WIN
#include "../src/platform/win/win_window_enum.h"
#elif defined(Q_OS_MACOS)
#include "../src/platform/mac/mac_window_enum.h"
#endif

class TestWindowEnumerator : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void testEnumerateWindows();
    void testExcludeWindow();
    void testMinWindowSize();
    void cleanupTestCase();

private:
#ifdef Q_OS_WIN
    WinWindowEnumerator* enumerator_ = nullptr;
#elif defined(Q_OS_MACOS)
    MacWindowEnumerator* enumerator_ = nullptr;
#endif
};

void TestWindowEnumerator::initTestCase()
{
    // 检查是否有显示设备（无头环境跳过）
    if (QGuiApplication::screens().isEmpty()) {
        qWarning() << "No display available, skipping test";
        QSKIP("No display available");
    }

#ifdef Q_OS_WIN
    enumerator_ = new WinWindowEnumerator(this);
#elif defined(Q_OS_MACOS)
    enumerator_ = new MacWindowEnumerator(this);
#endif
    QVERIFY(enumerator_ != nullptr);
}

void TestWindowEnumerator::testEnumerateWindows()
{
    // 获取窗口列表
    QList<WindowInfo> windows = enumerator_->enumerateWindows();

    qDebug() << "=== Enumerated Windows ===";
    qDebug() << "Total windows found:" << windows.size();

    for (const WindowInfo& info : windows) {
        qDebug().nospace() << "  ["
            << info.windowId << "] "
            << info.title.left(40).toLocal8Bit().constData()
            << " | className: " << info.className.toLocal8Bit().constData()
            << " | process: " << info.processName.toLocal8Bit().constData()
            << " | geometry: " << info.geometry.width() << "x"
            << info.geometry.height() << "+" << info.geometry.x()
            << "+" << info.geometry.y()
            << " | visible: " << info.isVisible;
    }

    // 验证：应该找到至少一些窗口（桌面窗口管理器等）
    QVERIFY(windows.size() > 0);

    // 验证：所有窗口应该有有效 ID
    for (const WindowInfo& info : windows) {
        QVERIFY(info.windowId != 0);
    }

    // 验证：所有窗口应该可见
    for (const WindowInfo& info : windows) {
        QVERIFY(info.isVisible == true);
    }

    // 验证：窗口几何信息应该有效
    for (const WindowInfo& info : windows) {
        QVERIFY(info.geometry.width() > 0);
        QVERIFY(info.geometry.height() > 0);
    }
}

void TestWindowEnumerator::testExcludeWindow()
{
    // 设置排除窗口为 0（无效窗口），应该不影响枚举
    enumerator_->setExcludedWindow(0);
    QList<WindowInfo> windows1 = enumerator_->enumerateWindows();

    // 设置排除窗口为有效值
    if (!windows1.isEmpty()) {
        int64_t firstWindowId = windows1.first().windowId;
        enumerator_->setExcludedWindow(firstWindowId);
        QList<WindowInfo> windows2 = enumerator_->enumerateWindows();

        // 验证：排除后窗口数应该减少
        QVERIFY(windows2.size() < windows1.size());

        // 验证：排除的窗口不在结果中
        for (const WindowInfo& info : windows2) {
            QVERIFY(info.windowId != firstWindowId);
        }

        qDebug() << "Before exclusion:" << windows1.size() << "windows";
        qDebug() << "After exclusion:" << windows2.size() << "windows";
    }
}

void TestWindowEnumerator::testMinWindowSize()
{
    // 默认最小尺寸是 100
    QVERIFY(enumerator_->minWindowSize() == 100);

    // 获取窗口列表
    QList<WindowInfo> allWindows = enumerator_->enumerateWindows();
    qDebug() << "Default minSize (100):" << allWindows.size() << "windows";

    // 设置较大的最小尺寸
    enumerator_->setMinWindowSize(500);
    QList<WindowInfo> largeWindows = enumerator_->enumerateWindows();
    qDebug() << "minSize (500):" << largeWindows.size() << "windows";

    // 验证：较大的最小尺寸应该得到更少或相等的结果
    QVERIFY(largeWindows.size() <= allWindows.size());

    // 验证：所有大窗口的尺寸都 >= 500
    for (const WindowInfo& info : largeWindows) {
        QVERIFY(info.geometry.width() >= 500 || info.geometry.height() >= 500);
    }

    // 恢复默认
    enumerator_->setMinWindowSize(100);
}

void TestWindowEnumerator::cleanupTestCase()
{
    delete enumerator_;
    enumerator_ = nullptr;
}

QTEST_MAIN(TestWindowEnumerator)
#include "test_window_enumerator.moc"
