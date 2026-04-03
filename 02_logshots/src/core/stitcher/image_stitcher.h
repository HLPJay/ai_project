#pragma once

#include "i_stitcher.h"
#include "overlap_detector.h"
#include "sticky_detector.h"

#include <QThread>
#include <QMutex>
#include <atomic>

/**
 * @brief 图片拼接执行器
 *
 * 实现 IStitcher 接口，执行实际的图片拼接操作。
 * 使用流式处理避免内存峰值，支持 sticky header/footer 检测和超长图片分片。
 */
class ImageStitcher : public QObject, public IStitcher {
    Q_OBJECT

public:
    explicit ImageStitcher(QObject* parent = nullptr);
    ~ImageStitcher() override;

    /**
     * @brief 执行拼接操作
     * @param framePaths 帧图片路径列表（按从上到下顺序）
     * @param config 拼接配置
     */
    void stitch(const QStringList& framePaths, const StitchConfig& config) override;

    /**
     * @brief 停止拼接
     */
    void stop() override;

signals:
    void stitchProgress(int current, int total);
    void stitchFinished(const StitchResult& result);
    void stitchError(const QString& message);

private slots:
    void onStitchThreadStarted();
    void onStitchThreadFinished();

private:
    /**
     * @brief 线程入口实现
     */
    void stitchingThreadImpl();

    /**
     * @brief 安全发射 stitchFinished 信号
     */
    void emitStitchFinished(const StitchResult& result);

    /**
     * @brief 安全发射 stitchError 信号
     */
    void emitStitchError(const QString& error);

    /**
     * @brief 加载单帧图片
     */
    cv::Mat loadFrame(const QString& path);

    /**
     * @brief 计算拼接后的总高度
     */
    int calculateTotalHeight(const std::vector<cv::Mat>& frames,
                             const std::vector<int>& overlaps,
                             int headerHeight,
                             int footerHeight);

    /**
     * @brief 执行拼接
     */
    StitchResult performStitch(const QStringList& framePaths,
                                const StitchConfig& config,
                                int headerHeight,
                                int footerHeight);

    /**
     * @brief 分片处理超长图片
     */
    QStringList splitImage(const cv::Mat& image, const QString& basePath);

    QMutex mutex_;
    std::atomic<bool> stopRequested_{false};
    std::unique_ptr<QThread> workerThread_;

    // 深拷贝参数到成员变量，避免 lambda 捕获 this
    QStringList framePaths_;
    StitchConfig config_;
};