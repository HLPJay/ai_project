#pragma once

#include <opencv2/opencv.hpp>
#include <vector>

/**
 * @brief Sticky 元素检测结果
 */
struct StickyResult {
    int headerHeight = 0;   // Sticky header 高度（0 表示无）
    int footerHeight = 0;   // Sticky footer 高度（0 表示无）
};

/**
 * @brief Sticky Header/Footer 检测器
 *
 * 检测多帧序列中的 sticky header 和 sticky footer。
 * 原理：比较前 3 帧的顶部/底部区域，如果完全一致则为 sticky。
 */
class StickyDetector {
public:
    /**
     * @brief 检测 sticky header 和 footer
     * @param frames 帧序列（cv::Mat）
     * @param tolerance 容差（0-1），默认 0.01 表示 1% 像素差异可接受
     * @return StickyResult 检测结果
     */
    StickyResult detect(const std::vector<cv::Mat>& frames, double tolerance = 0.01);

    /**
     * @brief 检测 sticky header
     * @param frames 帧序列
     * @param tolerance 容差
     * @return int header 高度，0 表示无
     */
    int detectHeader(const std::vector<cv::Mat>& frames, double tolerance = 0.01);

    /**
     * @brief 检测 sticky footer
     * @param frames 帧序列
     * @param tolerance 容差
     * @return int footer 高度，0 表示无
     */
    int detectFooter(const std::vector<cv::Mat>& frames, double tolerance = 0.01);

private:
    /**
     * @brief 比较两帧的指定区域是否完全一致
     */
    static bool regionsIdentical(const cv::Mat& frameA,
                                 const cv::Mat& frameB,
                                 int startY,
                                 int height,
                                 double tolerance);

    /**
     * @brief 逐行比较两个区域的像素差异
     */
    static double computeRegionDifference(const cv::Mat& regionA,
                                          const cv::Mat& regionB);
};
