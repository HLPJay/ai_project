#include <QtTest/QtTest>

class TestStitcher : public QObject {
    Q_OBJECT

private slots:
    void initTestCase() {}
    void cleanupTestCase() {}
    void testPlaceholder() {
        QVERIFY(true);
    }
};

QTEST_MAIN(TestStitcher)
#include "test_stitcher.moc"
