#include <QtTest/QtTest>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QDebug>
#include <QSignalSpy>

#include "../src/ui/window_picker.h"

class TestWindowPicker : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void testWindowPickerCreation();
    void testWindowPickerSignals();
    void cleanupTestCase();

private:
    WindowPickerOverlay* picker_ = nullptr;
};

void TestWindowPicker::initTestCase()
{
    // 检查是否有显示设备（无头环境跳过）
    if (QGuiApplication::screens().isEmpty()) {
        qWarning() << "No display available, skipping test";
        QSKIP("No display available");
    }
}

void TestWindowPicker::testWindowPickerCreation()
{
    picker_ = new WindowPickerOverlay(nullptr);
    QVERIFY(picker_ != nullptr);

    // 验证初始状态
    QVERIFY(picker_->windowFlags().testFlag(Qt::FramelessWindowHint));
    QVERIFY(picker_->windowFlags().testFlag(Qt::Tool));
    QVERIFY(picker_->testAttribute(Qt::WA_TranslucentBackground));
}

void TestWindowPicker::testWindowPickerSignals()
{
    picker_ = new WindowPickerOverlay(nullptr);
    QVERIFY(picker_ != nullptr);

    // 测试 windowSelected 信号
    QSignalSpy spyWindowSelected(picker_, &WindowPickerOverlay::windowSelected);
    QVERIFY(spyWindowSelected.isValid());

    // 测试 cancelled 信号
    QSignalSpy spyCancelled(picker_, &WindowPickerOverlay::cancelled);
    QVERIFY(spyCancelled.isValid());

    qDebug() << "WindowPicker signals are properly defined";
}

void TestWindowPicker::cleanupTestCase()
{
    delete picker_;
    picker_ = nullptr;
}

QTEST_MAIN(TestWindowPicker)
#include "test_window_picker.moc"
