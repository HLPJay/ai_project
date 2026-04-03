#pragma once

#include <QObject>
#include <QStringList>
#include <QImage>
#include <QtGlobal>

/**
 * @brief 拼接配置参数
 */
struct StitchConfig {
    int minOverlapPx = 20;        // 最小重叠像素
    int maxOverlapPx = 500;       // 最大重叠搜索范围
    double matchThreshold = 0.95; // 像素匹配阈值 (0-1)
    bool detectStickyHeader = true;
    bool detectStickyFooter = true;
    int maxOutputHeight = 65535;  // PNG 规范限制
};

/**
 * @brief 拼接结果
 */
struct StitchResult {
    QImage image;                 // 拼接后的图片
    int totalFrames = 0;          // 总帧数
    int removedOverlapPx = 0;     // 去除的总重叠像素
    bool wasSplit = false;        // 是否因超长而分片
    QStringList splitPaths;       // 分片文件路径（如果分片）
};

/**
 * @brief 拼接引擎接口
 *
 * 定义拼接器的标准接口，用于将多帧截图智能拼接为一张无缝长图。
 * 处理重叠区域检测、sticky 元素识别和超长图片分片。
 */
class IStitcher {
public:
    virtual ~IStitcher() = default;

    /**
     * @brief 执行拼接操作
     * @param framePaths 帧图片路径列表（按从上到下顺序）
     * @param config 拼接配置
     */
    virtual void stitch(const QStringList& framePaths, const StitchConfig& config) = 0;

    /**
     * @brief 停止拼接
     */
    virtual void stop() = 0;
};
