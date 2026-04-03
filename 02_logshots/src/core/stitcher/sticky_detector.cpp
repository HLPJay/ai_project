#include "sticky_detector.h"

#include <algorithm>

StickyResult StickyDetector::detect(const std::vector<cv::Mat>& frames, double tolerance) {
    StickyResult result;

    if (frames.size() < 3) {
        return result;
    }

    result.headerHeight = detectHeader(frames, tolerance);
    result.footerHeight = detectFooter(frames, tolerance);

    return result;
}

int StickyDetector::detectHeader(const std::vector<cv::Mat>& frames, double tolerance) {
    if (frames.size() < 3) {
        return 0;
    }

    const cv::Mat& frame0 = frames[0];
    const cv::Mat& frame1 = frames[1];
    const cv::Mat& frame2 = frames[2];

    if (frame0.empty() || frame1.empty() || frame2.empty()) {
        return 0;
    }

    if (frame0.size() != frame1.size() || frame0.size() != frame2.size()) {
        return 0;
    }

    // 从 10 到 200 递增搜索最佳 header 高度
    for (int height = 10; height <= 200; ++height) {
        if (height > frame0.rows) {
            break;
        }

        // 检查前三帧的顶部 height 行是否完全一致
        if (regionsIdentical(frame0, frame1, 0, height, tolerance) &&
            regionsIdentical(frame0, frame2, 0, height, tolerance)) {
            // 确认是 sticky：继续搜索更大高度
            for (int h = height + 1; h <= 200 && h <= frame0.rows; ++h) {
                if (!regionsIdentical(frame0, frame1, 0, h, tolerance) ||
                    !regionsIdentical(frame0, frame2, 0, h, tolerance)) {
                    break;
                }
                height = h;
            }
            return height;
        }
    }

    return 0;
}

int StickyDetector::detectFooter(const std::vector<cv::Mat>& frames, double tolerance) {
    if (frames.size() < 3) {
        return 0;
    }

    const cv::Mat& frame0 = frames[0];
    const cv::Mat& frame1 = frames[1];
    const cv::Mat& frame2 = frames[2];

    if (frame0.empty() || frame1.empty() || frame2.empty()) {
        return 0;
    }

    if (frame0.size() != frame1.size() || frame0.size() != frame2.size()) {
        return 0;
    }

    // 从 10 到 200 递增搜索最佳 footer 高度
    for (int height = 10; height <= 200; ++height) {
        if (height > frame0.rows) {
            break;
        }

        int startY = frame0.rows - height;

        // 检查前三帧的底部 height 行是否完全一致
        if (regionsIdentical(frame0, frame1, startY, height, tolerance) &&
            regionsIdentical(frame0, frame2, startY, height, tolerance)) {
            return height;
        }
    }

    return 0;
}

bool StickyDetector::regionsIdentical(const cv::Mat& frameA,
                                        const cv::Mat& frameB,
                                        int startY,
                                        int height,
                                        double tolerance) {
    if (frameA.empty() || frameB.empty()) {
        return false;
    }

    if (startY < 0 || height <= 0 || startY + height > frameA.rows) {
        return false;
    }

    if (frameA.size() != frameB.size() || frameA.channels() != frameB.channels()) {
        return false;
    }

    cv::Mat regionA = frameA(cv::Rect(0, startY, frameA.cols, height));
    cv::Mat regionB = frameB(cv::Rect(0, startY, frameB.cols, height));

    double diff = computeRegionDifference(regionA, regionB);
    return diff <= tolerance;
}

double StickyDetector::computeRegionDifference(const cv::Mat& regionA,
                                                const cv::Mat& regionB) {
    if (regionA.empty() || regionB.empty()) {
        return 1.0;
    }

    if (regionA.size() != regionB.size()) {
        return 1.0;
    }

    cv::Mat grayA, grayB;

    if (regionA.channels() > 1) {
        cv::cvtColor(regionA, grayA, cv::COLOR_BGR2GRAY);
    } else {
        grayA = regionA;
    }

    if (regionB.channels() > 1) {
        cv::cvtColor(regionB, grayB, cv::COLOR_BGR2GRAY);
    } else {
        grayB = regionB;
    }

    // 计算像素差异
    cv::Mat diff;
    cv::absdiff(grayA, grayB, diff);

    // 计算差异像素占比
    double diffSum = cv::sum(diff)[0];
    double totalPixels = grayA.cols * grayA.rows * 255.0; // 归一化到 0-1
    double diffRatio = diffSum / totalPixels;

    return diffRatio;
}
