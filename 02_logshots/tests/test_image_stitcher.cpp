#include <QCoreApplication>
#include <QtTest>
#include <QTemporaryDir>
#include <QDir>

#include "../src/core/stitcher/image_stitcher.h"
#include "../src/core/stitcher/sticky_detector.h"

class TestImageStitcher : public QObject {
    Q_OBJECT

private slots:
    void initTestCase() {}
    void cleanupTestCase() {}

    /**
     * @brief 单帧 → 直接返回原图
     */
    void testSingleFrame() {
        ImageStitcher stitcher;
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        // 创建单帧测试图片
        cv::Mat frame(100, 200, CV_8UC3, cv::Scalar(255, 0, 0));
        QString framePath = tempDir.filePath("frame_0.png");
        cv::imwrite(framePath.toStdString(), frame);

        QStringList framePaths;
        framePaths.append(framePath);

        StitchResult result;
        QObject::connect(&stitcher, &ImageStitcher::stitchFinished, this, [&result](const StitchResult& r) {
            result = r;
        });

        StitchConfig config;
        stitcher.stitch(framePaths, config);

        // 等待异步完成
        QTest::qWait(500);

        QVERIFY(result.totalFrames == 1);
        QVERIFY(!result.wasSplit);
        QVERIFY(!result.image.isNull());
        QVERIFY(result.image.width() == 200);
        QVERIFY(result.image.height() == 100);
    }

    /**
     * @brief 两帧完全不重叠 → 直接堆叠
     */
    void testNoOverlapFrames() {
        ImageStitcher stitcher;
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        // 创建两帧完全不重叠的图片
        cv::Mat frame0(100, 200, CV_8UC3, cv::Scalar(255, 0, 0));   // 蓝色
        cv::Mat frame1(100, 200, CV_8UC3, cv::Scalar(0, 255, 0));   // 绿色

        QString framePath0 = tempDir.filePath("frame_0.png");
        QString framePath1 = tempDir.filePath("frame_1.png");
        cv::imwrite(framePath0.toStdString(), frame0);
        cv::imwrite(framePath1.toStdString(), frame1);

        QStringList framePaths;
        framePaths.append(framePath0);
        framePaths.append(framePath1);

        StitchResult result;
        QObject::connect(&stitcher, &ImageStitcher::stitchFinished, this, [&result](const StitchResult& r) {
            result = r;
        });

        StitchConfig config;
        config.minOverlapPx = 20;
        config.maxOverlapPx = 500;
        config.matchThreshold = 0.95;
        stitcher.stitch(framePaths, config);

        QTest::qWait(500);

        QVERIFY(result.totalFrames == 2);
        QVERIFY(!result.wasSplit);
        QVERIFY(!result.image.isNull());
        // 高度应该是两帧之和（如果没有检测到重叠）
        QVERIFY(result.image.height() >= 200);
    }

    /**
     * @brief 两帧有 100px 重叠 → 正确去重
     */
    void testWithOverlap() {
        ImageStitcher stitcher;
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        // 创建两帧，底部 100px 相同
        cv::Mat frame0(300, 400, CV_8UC3, cv::Scalar(255, 0, 0));
        cv::Mat frame1(300, 400, CV_8UC3, cv::Scalar(0, 255, 0));

        // 设置底部 100 像素为相同内容
        cv::Mat roi = frame0(cv::Rect(0, 200, 400, 100));
        cv::Mat src = frame1(cv::Rect(0, 0, 400, 100));
        src.copyTo(roi);

        QString framePath0 = tempDir.filePath("frame_0.png");
        QString framePath1 = tempDir.filePath("frame_1.png");
        cv::imwrite(framePath0.toStdString(), frame0);
        cv::imwrite(framePath1.toStdString(), frame1);

        QStringList framePaths;
        framePaths.append(framePath0);
        framePaths.append(framePath1);

        StitchResult result;
        QObject::connect(&stitcher, &ImageStitcher::stitchFinished, this, [&result](const StitchResult& r) {
            result = r;
        });

        StitchConfig config;
        config.minOverlapPx = 20;
        config.maxOverlapPx = 500;
        config.matchThreshold = 0.95;
        stitcher.stitch(framePaths, config);

        QTest::qWait(500);

        QVERIFY(result.totalFrames == 2);
        QVERIFY(result.removedOverlapPx > 0);
    }

    /**
     * @brief 空帧序列 → 优雅报错
     */
    void testEmptyFrameSequence() {
        ImageStitcher stitcher;

        QStringList emptyPaths;
        bool errorReceived = false;

        QObject::connect(&stitcher, &ImageStitcher::stitchError, this, [&errorReceived](const QString&) {
            errorReceived = true;
        });

        StitchConfig config;
        stitcher.stitch(emptyPaths, config);

        QTest::qWait(100);

        QVERIFY(errorReceived);
    }

    /**
     * @brief 带 sticky header 的 3 帧序列 → header 只出现一次
     */
    void testStickyHeader() {
        // 准备测试帧
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        // 3 帧，每帧 200x400
        // header 高度 30px，前 3 帧 header 完全一致
        const int headerHeight = 30;
        const int frameHeight = 200;
        const int frameWidth = 400;

        for (int i = 0; i < 3; ++i) {
            cv::Mat frame(frameHeight, frameWidth, CV_8UC3, cv::Scalar(0, 0, 255)); // 蓝色背景

            // header 区域（顶部 30px）画成红色
            cv::Rect headerRect(0, 0, frameWidth, headerHeight);
            cv::Mat headerRoi = frame(headerRect);
            headerRoi = cv::Scalar(0, 255, 255); // 黄色 header

            // 内容区域画不同颜色以区分
            cv::Rect contentRect(0, headerHeight, frameWidth, frameHeight - headerHeight);
            cv::Mat contentRoi = frame(contentRect);
            contentRoi = cv::Scalar(i * 80, 100, 100); // 每帧不同颜色

            QString path = tempDir.filePath(QString("frame_%1.png").arg(i));
            cv::imwrite(path.toStdString(), frame);
        }

        // 加载并检测
        std::vector<cv::Mat> frames;
        for (int i = 0; i < 3; ++i) {
            QString path = tempDir.filePath(QString("frame_%1.png").arg(i));
            frames.push_back(cv::imread(path.toStdString()));
        }

        StickyDetector stickyDetector;
        StickyResult sticky = stickyDetector.detect(frames);

        QVERIFY(sticky.headerHeight > 0);
        QVERIFY(sticky.headerHeight <= headerHeight + 10); // 允许一些误差
    }

    /**
     * @brief 单帧图片 → 正确处理
     */
    void testSingleFrameHandling() {
        ImageStitcher stitcher;
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        cv::Mat frame(150, 250, CV_8UC3, cv::Scalar(128, 128, 128));
        QString framePath = tempDir.filePath("single.png");
        cv::imwrite(framePath.toStdString(), frame);

        QStringList framePaths;
        framePaths.append(framePath);

        StitchResult result;
        QObject::connect(&stitcher, &ImageStitcher::stitchFinished, this, [&result](const StitchResult& r) {
            result = r;
        });

        StitchConfig config;
        stitcher.stitch(framePaths, config);

        QTest::qWait(500);

        QVERIFY(result.totalFrames == 1);
        QVERIFY(result.image.width() == 250);
        QVERIFY(result.image.height() == 150);
    }

    /**
     * @brief 测试 sticky footer 检测
     */
    void testStickyFooter() {
        QTemporaryDir tempDir;
        QVERIFY(tempDir.isValid());

        const int footerHeight = 30;
        const int frameHeight = 200;
        const int frameWidth = 400;

        for (int i = 0; i < 3; ++i) {
            cv::Mat frame(frameHeight, frameWidth, CV_8UC3, cv::Scalar(100, 100, 100));

            // footer 区域（底部 30px）画成绿色
            cv::Rect footerRect(0, frameHeight - footerHeight, frameWidth, footerHeight);
            cv::Mat footerRoi = frame(footerRect);
            footerRoi = cv::Scalar(0, 255, 0); // 绿色 footer

            // 内容区域不同颜色
            cv::Rect contentRect(0, 0, frameWidth, frameHeight - footerHeight);
            cv::Mat contentRoi = frame(contentRect);
            contentRoi = cv::Scalar(i * 80, 50, 50);

            QString path = tempDir.filePath(QString("footer_frame_%1.png").arg(i));
            cv::imwrite(path.toStdString(), frame);
        }

        // 加载并检测
        std::vector<cv::Mat> frames;
        for (int i = 0; i < 3; ++i) {
            QString path = tempDir.filePath(QString("footer_frame_%1.png").arg(i));
            frames.push_back(cv::imread(path.toStdString()));
        }

        StickyDetector stickyDetector;
        StickyResult sticky = stickyDetector.detect(frames);

        QVERIFY(sticky.footerHeight > 0);
        QVERIFY(sticky.footerHeight <= footerHeight + 10);
    }
};

QTEST_MAIN(TestImageStitcher)
#include "test_image_stitcher.moc"
