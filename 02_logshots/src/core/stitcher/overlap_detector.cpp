#include "overlap_detector.h"

#include <vector>
#include <cmath>

OverlapResult OverlapDetector::detect(const cv::Mat& frameA,
                                      const cv::Mat& frameB,
                                      int minOverlap,
                                      int maxOverlap,
                                      double threshold) {
    // 优先使用行哈希快速检测
    OverlapResult result = detectByRowHash(frameA, frameB, minOverlap, maxOverlap, threshold);

    // 如果行哈希未找到有效重叠，尝试模板匹配
    if (!result.found) {
        result = detectByTemplateMatch(frameA, frameB, minOverlap, maxOverlap, threshold);
    }

    return result;
}

OverlapResult OverlapDetector::detectByRowHash(const cv::Mat& frameA,
                                                const cv::Mat& frameB,
                                                int minOverlap,
                                                int maxOverlap,
                                                double threshold) {
    OverlapResult result;

    if (frameA.empty() || frameB.empty()) {
        return result;
    }

    // 确保两帧宽度一致
    if (frameA.cols != frameB.cols) {
        return result;
    }

    // 限制最大搜索范围
    int searchHeight = std::min(maxOverlap, std::min(frameA.rows, frameB.rows));
    if (searchHeight < minOverlap) {
        return result;
    }

    // 提取底部/顶部区域并转为灰度
    cv::Mat bottomA = frameA(cv::Rect(0, frameA.rows - searchHeight, frameA.cols, searchHeight));
    cv::Mat topB = frameB(cv::Rect(0, 0, frameB.cols, searchHeight));

    cv::Mat grayA, grayB;
    cv::cvtColor(bottomA, grayA, cv::COLOR_BGR2GRAY);
    cv::cvtColor(topB, grayB, cv::COLOR_BGR2GRAY);

    // 计算行哈希序列
    std::vector<double> hashesA = computeRowHashes(grayA);
    std::vector<double> hashesB = computeRowHashes(grayB);

    // 滑动窗口匹配
    int matchPos = findBestMatchPosition(hashesA, hashesB, minOverlap, searchHeight);

    if (matchPos < 0) {
        return result;
    }

    // 计算重叠像素数
    int overlapPx = static_cast<int>(hashesA.size()) - matchPos;
    if (overlapPx < minOverlap) {
        return result;
    }

    // 用模板匹配精确验证
    cv::Mat regionA = grayA(cv::Rect(0, matchPos, grayA.cols, overlapPx));
    cv::Mat regionB = grayB(cv::Rect(0, 0, grayB.cols, overlapPx));

    double confidence = verifyWithTemplateMatch(regionA, regionB);

    if (confidence >= threshold) {
        result.overlapPx = overlapPx;
        result.confidence = confidence;
        result.found = true;
    }

    return result;
}

OverlapResult OverlapDetector::detectByTemplateMatch(const cv::Mat& frameA,
                                                      const cv::Mat& frameB,
                                                      int minOverlap,
                                                      int maxOverlap,
                                                      double threshold) {
    OverlapResult result;

    if (frameA.empty() || frameB.empty()) {
        return result;
    }

    if (frameA.cols != frameB.cols) {
        return result;
    }

    int searchHeight = std::min(maxOverlap, std::min(frameA.rows, frameB.rows));
    if (searchHeight < minOverlap) {
        return result;
    }

    // 取帧 B 顶部 N 行作为模板
    cv::Mat topB = frameB(cv::Rect(0, 0, frameB.cols, searchHeight));
    cv::Mat bottomA = frameA(cv::Rect(0, frameA.rows - searchHeight, frameA.cols, searchHeight));

    // 转灰度
    cv::Mat grayB, grayA;
    cv::cvtColor(topB, grayB, cv::COLOR_BGR2GRAY);
    cv::cvtColor(bottomA, grayA, cv::COLOR_BGR2GRAY);

    // 模板匹配
    cv::Mat matchResult;
    cv::matchTemplate(grayA, grayB, matchResult, cv::TM_CCOEFF_NORMED);

    // 找最佳匹配位置
    double minVal, maxVal;
    cv::Point minLoc, maxLoc;
    cv::minMaxLoc(matchResult, &minVal, &maxVal, &minLoc, &maxLoc);

    // maxVal 是匹配置信度
    if (maxVal >= threshold) {
        // 计算重叠行数：最佳匹配位置 + 模板高度
        // maxLoc.y 是匹配位置（从 frameA 底部往上的偏移）
        int matchFromBottom = maxLoc.y;
        int overlapPx = searchHeight - matchFromBottom;

        if (overlapPx >= minOverlap) {
            result.overlapPx = overlapPx;
            result.confidence = maxVal;
            result.found = true;
        }
    }

    return result;
}

double OverlapDetector::computeRowHash(const cv::Mat& grayRow) {
    // 计算单行像素的均值哈希
    if (grayRow.empty()) {
        return 0.0;
    }

    double sum = 0.0;
    int count = 0;

    if (grayRow.channels() == 1) {
        sum = cv::sum(grayRow)[0];
        count = grayRow.cols;
    } else {
        // 多通道：转灰度后再计算均值
        // 使用 BGR 转灰度的标准公式：0.114*B + 0.587*G + 0.299*R
        // 为效率，直接用灰度系数计算
        const double B_coeff = 0.114;
        const double G_coeff = 0.587;
        const double R_coeff = 0.299;

        for (int x = 0; x < grayRow.cols; ++x) {
            cv::Vec3b pixel = grayRow.at<cv::Vec3b>(0, x);
            sum += B_coeff * pixel[0] + G_coeff * pixel[1] + R_coeff * pixel[2];
        }
        count = grayRow.cols;
    }

    return (count > 0) ? (sum / count) : 0.0;
}

std::vector<double> OverlapDetector::computeRowHashes(const cv::Mat& grayImage) {
    std::vector<double> hashes;
    hashes.reserve(grayImage.rows);

    for (int y = 0; y < grayImage.rows; ++y) {
        cv::Mat row = grayImage.row(y);
        hashes.push_back(computeRowHash(row));
    }

    return hashes;
}

int OverlapDetector::findBestMatchPosition(const std::vector<double>& hashesA,
                                            const std::vector<double>& hashesB,
                                            int minOverlap,
                                            int maxOverlap) {
    if (hashesA.empty() || hashesB.empty()) {
        return -1;
    }

    int nA = static_cast<int>(hashesA.size());
    int nB = static_cast<int>(hashesB.size());
    // overlap 不能超过 nA，否则 posA = nA - overlap < 0 导致越界
    int searchRange = std::min(maxOverlap, std::min(nA, nB));

    if (searchRange < minOverlap) {
        return -1;
    }

    double bestScore = -1.0;
    int bestPos = -1;

    // 检查哈希序列的方差，如果太接近常数（方差 < 阈值），则无法可靠匹配
    double meanA = 0.0, meanB = 0.0;
    for (double h : hashesA) meanA += h;
    for (double h : hashesB) meanB += h;
    meanA /= hashesA.size();
    meanB /= hashesB.size();

    double varA = 0.0, varB = 0.0;
    for (double h : hashesA) varA += (h - meanA) * (h - meanA);
    for (double h : hashesB) varB += (h - meanB) * (h - meanB);
    varA /= hashesA.size();
    varB /= hashesB.size();

    const double minVariance = 1.0; // 灰度方差阈值，小于此值认为是常数图像
    if (varA < minVariance || varB < minVariance) {
        // 至少有一个是常数图像，行哈希匹配不可靠
        return -1;
    }

    // 滑动窗口：尝试不同的重叠行数
    for (int overlap = minOverlap; overlap <= searchRange; ++overlap) {
        // hashesB 的前 overlap 行对应 hashesA 的后 overlap 行
        // 匹配位置 = nA - overlap
        int posA = nA - overlap;
        int posB = 0;

        // posA 必须非负（posA < 0 意味着 overlap > nA，越界）
        if (posA < 0) {
            continue;
        }

        // 计算相似度（余弦相似度）
        double dotProduct = 0.0;
        double normA = 0.0;
        double normB = 0.0;

        for (int i = 0; i < overlap; ++i) {
            double a = hashesA[posA + i];
            double b = hashesB[posB + i];
            dotProduct += a * b;
            normA += a * a;
            normB += b * b;
        }

        double score = (normA > 0 && normB > 0) ? (dotProduct / (std::sqrt(normA) * std::sqrt(normB))) : 0.0;

        if (score > bestScore) {
            bestScore = score;
            bestPos = posA;
        }
    }

    return bestPos;
}

double OverlapDetector::verifyWithTemplateMatch(const cv::Mat& regionA,
                                                 const cv::Mat& regionB) {
    if (regionA.empty() || regionB.empty()) {
        return 0.0;
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

    // 确保尺寸一致
    if (grayA.size() != grayB.size()) {
        cv::resize(grayB, grayB, grayA.size());
    }

    cv::Mat result;
    cv::matchTemplate(grayA, grayB, result, cv::TM_CCOEFF_NORMED);

    double maxVal;
    cv::Point maxLoc;
    cv::minMaxLoc(result, nullptr, &maxVal, nullptr, &maxLoc);

    return maxVal;
}
