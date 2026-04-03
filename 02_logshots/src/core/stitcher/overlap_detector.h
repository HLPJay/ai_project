#pragma once

#include <opencv2/opencv.hpp>
#include <QString>

/**
 * @brief 重叠检测算法结果
 */
struct OverlapResult {
    int overlapPx = 0;          // 检测到的重叠像素（0 表示无重叠）
    double confidence = 0.0;   // 匹配置信度 (0-1)
    bool found = false;         // 是否找到有效重叠
};

/**
 * @brief 重叠检测器
 *
 * 使用两种算法检测两帧之间的重叠区域：
 * 1. 行哈希 + 滑动窗口匹配（快速）
 * 2. cv::matchTemplate 精确匹配（准确）
 */
class OverlapDetector {
public:
    /**
     * @brief 检测两帧之间的重叠像素
     * @param frameA 当前帧
     * @param frameB 下一帧
     * @param minOverlap 最小重叠像素
     * @param maxOverlap 最大搜索范围
     * @param threshold 匹配阈值 (0-1)
     * @return OverlapResult 重叠检测结果
     */
    OverlapResult detect(const cv::Mat& frameA,
                         const cv::Mat& frameB,
                         int minOverlap = 20,
                         int maxOverlap = 500,
                         double threshold = 0.95);

    /**
     * @brief 使用行哈希算法检测重叠（快速）
     */
    OverlapResult detectByRowHash(const cv::Mat& frameA,
                                   const cv::Mat& frameB,
                                   int minOverlap,
                                   int maxOverlap,
                                   double threshold);

    /**
     * @brief 使用模板匹配算法检测重叠（精确）
     */
    OverlapResult detectByTemplateMatch(const cv::Mat& frameA,
                                          const cv::Mat& frameB,
                                          int minOverlap,
                                          int maxOverlap,
                                          double threshold);

private:
    /**
     * @brief 计算单行像素的哈希值（基于像素均值）
     */
    static double computeRowHash(const cv::Mat& grayRow);

    /**
     * @brief 将图片转换为行哈希序列
     */
    static std::vector<double> computeRowHashes(const cv::Mat& grayImage);

    /**
     * @brief 滑动窗口匹配，找最佳匹配位置
     */
    static int findBestMatchPosition(const std::vector<double>& hashesA,
                                      const std::vector<double>& hashesB,
                                      int minOverlap,
                                      int maxOverlap);

    /**
     * @brief 用 cv::matchTemplate 精确验证候选重叠区域
     */
    static double verifyWithTemplateMatch(const cv::Mat& regionA,
                                           const cv::Mat& regionB);
};
