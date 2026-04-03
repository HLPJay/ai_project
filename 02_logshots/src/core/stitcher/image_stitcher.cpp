#include "image_stitcher.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QThread>
#include <QPointer>
#include <memory>

ImageStitcher::ImageStitcher(QObject* parent)
    : QObject(parent) {
}

ImageStitcher::~ImageStitcher() {
    stopRequested_ = true;

    // 等待旧线程结束（最多 5 秒超时，避免永久阻塞）
    if (workerThread_ && workerThread_->isRunning()) {
        workerThread_->quit();
        if (!workerThread_->wait(5000)) {
            qWarning() << "[ImageStitcher] Worker thread did not finish in time, terminating";
            workerThread_->terminate();
            workerThread_->wait(1000);
        }
    }

    // unique_ptr 自动清理线程对象
}

void ImageStitcher::stitch(const QStringList& framePaths, const StitchConfig& config) {
    QMutexLocker locker(&mutex_);

    if (framePaths.isEmpty()) {
        StitchResult result;
        result.totalFrames = 0;
        emitStitchError(QStringLiteral("帧序列为空"));
        return;
    }

    // 若上一次拼接尚未结束，等待完成再开始新的
    if (workerThread_ && workerThread_->isRunning()) {
        qDebug() << "[ImageStitcher] Previous stitch still running, waiting...";
        workerThread_->quit();
        workerThread_->wait(5000);
    }

    // 保存参数（深拷贝，避免 lambda 捕获引用）
    framePaths_ = framePaths;
    config_ = config;
    stopRequested_ = false;

    // 创建新线程（使用 unique_ptr 管理生命周期）
    workerThread_ = std::make_unique<QThread>();

    // 使用静态成员函数 + 安全的信号发射
    connect(workerThread_.get(), &QThread::started, this, &ImageStitcher::onStitchThreadStarted);
    connect(workerThread_.get(), &QThread::finished, this, &ImageStitcher::onStitchThreadFinished);

    workerThread_->start();
}

void ImageStitcher::onStitchThreadStarted() {
    // 线程入口点（运行在工作线程）
    stitchingThreadImpl();
}

void ImageStitcher::onStitchThreadFinished() {
    qDebug() << "[ImageStitcher] Worker thread finished";
}

void ImageStitcher::stitchingThreadImpl() {
    // 使用成员变量（已在主线程通过深拷贝保存）
    QStringList paths = framePaths_;
    StitchConfig cfg = config_;

    try {
        if (paths.size() == 1) {
            // 单帧直接返回原图
            cv::Mat frame = loadFrame(paths[0]);
            if (frame.empty()) {
                emitStitchError(QStringLiteral("无法加载图片: %1").arg(paths[0]));
                return;
            }

            StitchResult result;
            cv::Mat rgbFrame;
            cv::cvtColor(frame, rgbFrame, cv::COLOR_BGR2RGB);
            result.image = QImage(rgbFrame.data, rgbFrame.cols, rgbFrame.rows,
                                  rgbFrame.step, QImage::Format_RGB888).copy();
            result.totalFrames = 1;
            result.wasSplit = false;
            emitStitchFinished(result);
            return;
        }

        // 流式加载前 3 帧用于 sticky 检测
        std::vector<cv::Mat> previewFrames;
        previewFrames.reserve(3);

        for (int i = 0; i < std::min(3, static_cast<int>(paths.size())); ++i) {
            cv::Mat frame = loadFrame(paths[i]);
            if (frame.empty()) {
                emitStitchError(QStringLiteral("无法加载帧: %1").arg(paths[i]));
                return;
            }
            previewFrames.push_back(frame);
        }

        // 检测 sticky header/footer
        int headerHeight = 0;
        int footerHeight = 0;

        if (cfg.detectStickyHeader || cfg.detectStickyFooter) {
            StickyDetector stickyDetector;
            StickyResult sticky = stickyDetector.detect(previewFrames);

            if (cfg.detectStickyHeader) {
                headerHeight = sticky.headerHeight;
            }
            if (cfg.detectStickyFooter) {
                footerHeight = sticky.footerHeight;
            }
        }

        // 释放预览帧
        previewFrames.clear();

        // 执行拼接
        StitchResult result = performStitch(paths, cfg, headerHeight, footerHeight);

        emitStitchFinished(result);

    } catch (const std::exception& e) {
        emitStitchError(QStringLiteral("拼接异常: %1").arg(e.what()));
    } catch (...) {
        emitStitchError(QStringLiteral("拼接发生未知异常"));
    }
}

void ImageStitcher::emitStitchFinished(const StitchResult& result) {
    // 检查 QCoreApplication 是否还存在（应用可能正在退出）
    if (QCoreApplication::closingDown()) {
        qDebug() << "[ImageStitcher] QCoreApplication is closing, skipping stitchFinished signal";
        return;
    }
    emit stitchFinished(result);
}

void ImageStitcher::emitStitchError(const QString& error) {
    if (QCoreApplication::closingDown()) {
        qDebug() << "[ImageStitcher] QCoreApplication is closing, skipping stitchError signal";
        return;
    }
    emit stitchError(error);
}

void ImageStitcher::stop() {
    stopRequested_ = true;
}

cv::Mat ImageStitcher::loadFrame(const QString& path) {
    cv::Mat frame = cv::imread(path.toStdString());
    return frame;
}

int ImageStitcher::calculateTotalHeight(const std::vector<cv::Mat>& frames,
                                         const std::vector<int>& overlaps,
                                         int headerHeight,
                                         int footerHeight) {
    int totalHeight = 0;

    for (size_t i = 0; i < frames.size(); ++i) {
        int frameHeight = frames[i].rows;

        if (i == 0) {
            frameHeight -= headerHeight;
        }
        if (i == frames.size() - 1) {
            frameHeight -= footerHeight;
        }

        totalHeight += frameHeight;

        if (i < overlaps.size()) {
            totalHeight -= overlaps[i];
        }
    }

    return totalHeight;
}

StitchResult ImageStitcher::performStitch(const QStringList& framePaths,
                                           const StitchConfig& config,
                                           int headerHeight,
                                           int footerHeight) {
    StitchResult result;
    result.totalFrames = framePaths.size();

    OverlapDetector overlapDetector;

    cv::Mat prevFrame;
    cv::Mat currentFrame;

    std::vector<int> validHeights;
    std::vector<int> overlaps;

    for (int i = 0; i < framePaths.size(); ++i) {
        emit stitchProgress(i + 1, framePaths.size());

        currentFrame = loadFrame(framePaths[i]);
        if (currentFrame.empty()) {
            continue;
        }

        int validH = currentFrame.rows;

        if (i == 0) {
            validH -= headerHeight;
        }
        if (i == framePaths.size() - 1) {
            validH -= footerHeight;
        }

        if (i > 0 && !prevFrame.empty()) {
            OverlapResult overlap = overlapDetector.detect(
                prevFrame, currentFrame,
                config.minOverlapPx, config.maxOverlapPx, config.matchThreshold);

            if (overlap.found && overlap.overlapPx > 0) {
                int frameHeight = currentFrame.rows;

                if (overlap.overlapPx > frameHeight * 9 / 10) {
                    qWarning() << "[ImageStitcher] Detected overlap" << overlap.overlapPx
                               << ">(" << frameHeight << "*0.9) - frames nearly identical,"
                               << "using minOverlap" << config.minOverlapPx << "to preserve content";
                    overlaps.push_back(config.minOverlapPx);
                    validH -= config.minOverlapPx;
                } else if (overlap.overlapPx < config.minOverlapPx / 2) {
                    qWarning() << "[ImageStitcher] Detected overlap" << overlap.overlapPx
                               << "too small, using config minOverlap" << config.minOverlapPx;
                    overlaps.push_back(config.minOverlapPx);
                    validH -= config.minOverlapPx;
                } else {
                    overlaps.push_back(overlap.overlapPx);
                    validH -= overlap.overlapPx;
                }
            } else {
                qWarning() << "[ImageStitcher] Overlap detection failed, using config minOverlap"
                           << config.minOverlapPx << "as fallback";
                overlaps.push_back(config.minOverlapPx);
                validH -= config.minOverlapPx;
            }
        } else {
            overlaps.push_back(0);
        }

        validHeights.push_back(validH);
        prevFrame = currentFrame;
    }

    int totalHeight = 0;
    for (size_t i = 0; i < validHeights.size(); ++i) {
        totalHeight += validHeights[i];
    }

    if (totalHeight > config.maxOutputHeight) {
        result.wasSplit = true;
        cv::Mat accumulator;
        int accHeight = 0;
        int partStart = 0;
        std::vector<cv::Mat> partFrames;

        for (size_t i = 0; i < validHeights.size(); ++i) {
            partFrames.push_back(loadFrame(framePaths[i]));
            accHeight += validHeights[i];

            if (accHeight >= config.maxOutputHeight || i == validHeights.size() - 1) {
                cv::Mat partImage;
                if (!partFrames.empty()) {
                    int partWidth = partFrames[0].cols;
                    partImage.create(accHeight, partWidth, CV_8UC3);

                    int destY = 0;
                    for (size_t j = 0; j < partFrames.size(); ++j) {
                        int globalIdx = partStart + static_cast<int>(j);
                        cv::Mat src = partFrames[j];
                        int copyH = validHeights[globalIdx];

                        int srcY = 0;
                        if (globalIdx == 0) {
                            srcY = headerHeight;
                        } else if (globalIdx > 0) {
                            srcY = overlaps[globalIdx - 1];
                        }

                        cv::Mat roi = partImage(cv::Rect(0, destY, partWidth, copyH));
                        src(cv::Rect(0, srcY, partWidth, copyH)).copyTo(roi);
                        destY += copyH;
                    }
                }

                QString partPath = QStringLiteral("%1/longshot_part_%2.png")
                                       .arg(QFileInfo(framePaths[0]).absolutePath())
                                       .arg(result.splitPaths.size());
                cv::imwrite(partPath.toStdString(), partImage);
                result.splitPaths.append(partPath);

                partFrames.clear();
                partStart = static_cast<int>(i) + 1;
                accHeight = 0;
            }
        }

        {
            cv::Mat preview = partFrames.empty() ? loadFrame(framePaths[0]) : partFrames[0];
            cv::Mat rgbPreview;
            cv::cvtColor(preview, rgbPreview, cv::COLOR_BGR2RGB);
            result.image = QImage(rgbPreview.data, rgbPreview.cols, rgbPreview.rows,
                                  rgbPreview.step, QImage::Format_RGB888).copy();
        }
    } else {
        int width = loadFrame(framePaths[0]).cols;
        cv::Mat outputImage(totalHeight, width, CV_8UC3);

        int destY = 0;
        int totalRemovedOverlap = 0;

        for (qsizetype i = 0; i < framePaths.size(); ++i) {
            cv::Mat frame = loadFrame(framePaths[i]);
            if (frame.empty()) {
                continue;
            }

            int srcY = (i == 0) ? headerHeight
                                 : (i > 0 && static_cast<size_t>(i - 1) < overlaps.size() ? overlaps[i - 1] : 0);
            int copyH = validHeights[i];

            if (srcY < 0) srcY = 0;
            if (copyH <= 0) continue;
            if (srcY + copyH > frame.rows) {
                copyH = frame.rows - srcY;
                if (copyH <= 0) continue;
            }
            if (destY + copyH > outputImage.rows) {
                copyH = outputImage.rows - destY;
                if (copyH <= 0) continue;
            }

            cv::Mat roi = outputImage(cv::Rect(0, destY, width, copyH));
            frame(cv::Rect(0, srcY, width, copyH)).copyTo(roi);

            totalRemovedOverlap += (i < static_cast<qsizetype>(overlaps.size()) ? overlaps[i] : 0);
            destY += copyH;
        }

        cv::Mat rgbOutput;
        cv::cvtColor(outputImage, rgbOutput, cv::COLOR_BGR2RGB);
        result.image = QImage(rgbOutput.data, rgbOutput.cols, rgbOutput.rows,
                              rgbOutput.step, QImage::Format_RGB888).copy();
        result.removedOverlapPx = totalRemovedOverlap;
    }

    return result;
}

QStringList ImageStitcher::splitImage(const cv::Mat& image, const QString& basePath) {
    QStringList paths;

    int maxHeight = 60000;
    int numParts = (image.rows + maxHeight - 1) / maxHeight;

    QString dir = QFileInfo(basePath).absolutePath();
    QString name = QFileInfo(basePath).baseName();

    for (int i = 0; i < numParts; ++i) {
        int startY = i * maxHeight;
        int endY = std::min(startY + maxHeight, image.rows);

        cv::Mat part = image(cv::Rect(0, startY, image.cols, endY - startY));

        QString partPath = QStringLiteral("%1/%2_part%3.png")
                                .arg(dir)
                                .arg(name)
                                .arg(i + 1);
        cv::imwrite(partPath.toStdString(), part);
        paths.append(partPath);
    }

    return paths;
}