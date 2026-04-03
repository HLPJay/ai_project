#include <QCoreApplication>
#include <QtTest>

#include "../src/core/stitcher/overlap_detector.h"

class TestOverlapDetector : public QObject {
    Q_OBJECT

private slots:
    void initTestCase() {}
    void cleanupTestCase() {}

    /**
     * @brief 两帧完全不重叠 → 直接返回 0
     */
    void testNoOverlap() {
        OverlapDetector detector;

        // 创建两帧完全不重叠的图片（使用不同的伪随机模式）
        cv::Mat frameA(300, 400, CV_8UC3);
        cv::Mat frameB(300, 400, CV_8UC3);
        for (int y = 0; y < 300; ++y) {
            // 使用不同的函数确保内容完全不同
            uchar valA = static_cast<uchar>((y * 17 + y * y) % 256);
            uchar valB = static_cast<uchar>((y * 31 + y / 2) % 256);
            frameA.row(y) = cv::Scalar(valA, valA * 2 % 256, valA * 3 % 256);
            frameB.row(y) = cv::Scalar(valB, valB * 2 % 256, valB * 3 % 256);
        }

        OverlapResult result = detector.detect(frameA, frameB, 20, 500, 0.95);

        QVERIFY(!result.found);
        QVERIFY(result.overlapPx == 0);
    }

    /**
     * @brief 两帧有 100px 重叠 → 正确检测
     */
    void testWithOverlap() {
        OverlapDetector detector;

        // 创建两帧，底部 100px 相同（有实际内容）
        cv::Mat frameA(300, 400, CV_8UC3);
        cv::Mat frameB(300, 400, CV_8UC3);
        for (int y = 0; y < 300; ++y) {
            frameA.row(y) = cv::Scalar(y % 256, (y * 2) % 256, (y * 3) % 256);
            frameB.row(y) = cv::Scalar((y + 100) % 256, (y * 2 + 50) % 256, (y * 3 + 75) % 256);
        }

        // 设置底部 100 像素为相同内容
        cv::Mat roiA = frameA(cv::Rect(0, 200, 400, 100));
        cv::Mat roiB = frameB(cv::Rect(0, 0, 400, 100));
        roiB.copyTo(roiA);

        OverlapResult result = detector.detect(frameA, frameB, 20, 500, 0.95);

        QVERIFY(result.found);
        QVERIFY(result.overlapPx > 0);
        QVERIFY(result.confidence > 0.9);
    }

    /**
     * @brief 空帧 → 优雅返回
     */
    void testEmptyFrames() {
        OverlapDetector detector;
        cv::Mat empty;

        OverlapResult result = detector.detect(empty, empty, 20, 500, 0.95);

        QVERIFY(!result.found);
        QVERIFY(result.overlapPx == 0);
    }

    /**
     * @brief 宽度不同 → 不检测重叠
     */
    void testDifferentWidth() {
        OverlapDetector detector;

        cv::Mat frameA(300, 400, CV_8UC3, cv::Scalar(255, 0, 0));
        cv::Mat frameB(300, 300, CV_8UC3, cv::Scalar(0, 255, 0));

        OverlapResult result = detector.detect(frameA, frameB, 20, 500, 0.95);

        QVERIFY(!result.found);
    }

    /**
     * @brief 测试行哈希算法
     */
    void testRowHashAlgorithm() {
        OverlapDetector detector;

        // 使用渐变图片有实际内容
        cv::Mat frameA(200, 400, CV_8UC3);
        cv::Mat frameB(200, 400, CV_8UC3);
        for (int y = 0; y < 200; ++y) {
            frameA.row(y) = cv::Scalar(y % 256, (y * 2) % 256, (y * 3) % 256);
            frameB.row(y) = cv::Scalar((y + 50) % 256, (y * 2 + 25) % 256, (y * 3 + 75) % 256);
        }

        // 底部 50px 相同
        cv::Mat roiA = frameA(cv::Rect(0, 150, 400, 50));
        cv::Mat roiB = frameB(cv::Rect(0, 0, 400, 50));
        roiB.copyTo(roiA);

        OverlapResult result = detector.detectByRowHash(frameA, frameB, 20, 100, 0.9);

        QVERIFY(result.found);
        QVERIFY(result.overlapPx >= 20);
    }

    /**
     * @brief 测试模板匹配算法
     */
    void testTemplateMatchAlgorithm() {
        OverlapDetector detector;

        cv::Mat frameA(200, 400, CV_8UC3, cv::Scalar(100, 100, 100));
        cv::Mat frameB(200, 400, CV_8UC3, cv::Scalar(200, 200, 200));

        // 底部 50px 相同
        cv::Mat roiA = frameA(cv::Rect(0, 150, 400, 50));
        cv::Mat roiB = frameB(cv::Rect(0, 0, 400, 50));
        roiB.copyTo(roiA);

        OverlapResult result = detector.detectByTemplateMatch(frameA, frameB, 20, 100, 0.9);

        QVERIFY(result.found);
    }
};

QTEST_MAIN(TestOverlapDetector)
#include "test_overlap_detector.moc"
