#pragma once

#include "i_capture_engine.h"
#include "scroll_strategy.h"

#include <QObject>
#include <QThread>
#include <QImage>
#include <QWaitCondition>
#include <QMutex>
#include <QStandardPaths>
#include <memory>

namespace longshot {
namespace core {

class WebCapture;

/**
 * @brief 帧保存器（工作线程）
 *
 * 运行在独立工作线程，接收 QImage 并保存到磁盘。
 * 通过信号槽与主线程的 WebCapture 通信。
 */
class FrameSaver : public QObject {
    Q_OBJECT

public:
    explicit FrameSaver(const QString& tempDir, QObject* parent = nullptr);
    ~FrameSaver() override;

    /**
     * @brief 获取已保存的帧文件路径列表（线程安全）
     */
    QStringList savedPaths() const;

public slots:
    /**
     * @brief 保存帧（从主线程通过 QueuedConnection 调用）
     * @param index 帧序号
     * @param image 帧图片
     */
    void saveFrame(int index, const QImage& image);

    /**
     * @brief 停止保存
     */
    void stop();

    /**
     * @brief 清理临时文件（在截屏完成后由外部调用）
     */
    void cleanup();

    /**
     * @brief 重置状态，准备新一轮截屏（清空路径列表、恢复 stopRequested）
     */
    void reset();

signals:
    /**
     * @brief 帧保存完成
     * @param index 帧序号
     * @param path 文件路径
     */
    void frameSaved(int index, const QString& path);

    /**
     * @brief 所有帧保存完成
     * @param paths 文件路径列表
     */
    void allFramesSaved(const QStringList& paths);

    /**
     * @brief 保存失败
     * @param error 错误信息
     */
    void saveFailed(const QString& error);

    /**
     * @brief 清理完成
     */
    void cleanupDone();

public:
    /**
     * @brief 获取临时目录路径
     */
    QString tempDir() const { return tempDir_; }

private:
    QString tempDir_;
    QStringList savedPaths_;
    bool stopRequested_ = false;
    mutable QMutex mutex_;
    QWaitCondition waitCondition_;
};

/**
 * @brief 截屏运行器（工作线程封装）
 *
 * 协调 WebCapture（主线程）和 FrameSaver（工作线程），
 * 实现截屏流程在独立工作线程运行的架构要求。
 *
 * 架构：
 * - WebCapture 在主线程（QWebEngineView 限制）
 * - FrameSaver 在独立工作线程（帧保存）
 * - 通过 Qt::QueuedConnection 实现跨线程通信
 */
class CaptureRunner : public ICaptureEngine {
    Q_OBJECT

public:
    /**
     * @brief 构造截屏运行器
     * @param config 滚动配置
     * @param parent 父对象
     */
    explicit CaptureRunner(const ScrollConfig& config, QObject* parent = nullptr);

    ~CaptureRunner() override;

    void startCapture(const CaptureRequest& request) override;
    void stopCapture() override;

private slots:
    void onFrameReady(int index, const QImage& image);
    void onCaptureFinished(const CaptureResult& result);
    void onCaptureError(const QString& message);

private:
    /**
     * @brief 创建 WebCapture（主线程）
     */
    void createWebCapture();

    ScrollConfig config_;
    std::unique_ptr<WebCapture> webCapture_;
    QThread workerThread_;
    FrameSaver* frameSaver_ = nullptr;

    bool isCapturing_ = false;
};

}  // namespace core
}  // namespace longshot
