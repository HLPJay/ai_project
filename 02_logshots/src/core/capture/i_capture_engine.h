#pragma once

#include <QObject>
#include <QString>
#include <QStringList>
#include <QImage>

namespace longshot {
namespace core {

/**
 * @brief 截屏模式
 */
enum class CaptureMode { Web, Window, Region };

/**
 * @brief 截屏请求参数
 */
struct CaptureRequest {
    /** 截屏模式 */
    CaptureMode mode = CaptureMode::Web;
    /** 目标 URL（网页场景）或窗口标题（窗口场景） */
    QString target;
    /** 窗口句柄: Win32 HWND (int64_t) / macOS CGWindowID (uint64_t) */
    int64_t windowHandle = 0;
    /** 窗口类名（用于场景检测） */
    QString windowClassName;
    /** 区域坐标（Region 模式） */
    QRect regionRect;
    /** 帧文件保存目录 */
    QString framesDir;
    /** 滚动时相邻帧重叠像素数 */
    int overlapPixels = 100;
    /** 滚动后等待渲染时间（毫秒） */
    int scrollDelayMs = 300;
    /** 安全上限，防止无限滚动 */
    int maxFrames = 200;
};

/**
 * @brief 截屏结果
 */
struct CaptureResult {
    /** 帧序列文件路径，按拍摄顺序排列 */
    QStringList framePaths;
    /** 错误信息，空表示成功 */
    QString error;
};

/**
 * @brief 截屏引擎抽象接口
 *
 * 定义所有截屏实现（网页/窗口/区域）必须遵循的接口。
 * 截屏操作在独立工作线程执行，通过信号报告进度和结果。
 */
class ICaptureEngine : public QObject {
    Q_OBJECT

public:
    explicit ICaptureEngine(QObject* parent = nullptr) : QObject(parent) {}
    ~ICaptureEngine() override = default;

    /**
     * @brief 开始截屏
     * @param request 截屏参数
     */
    virtual void startCapture(const CaptureRequest& request) = 0;

    /**
     * @brief 停止截屏
     */
    virtual void stopCapture() = 0;

signals:
    /**
     * @brief 帧截取完成
     * @param index 帧序号（从0开始）
     * @param image 帧图片（由 FrameSaver 保存到磁盘）
     */
    void frameReady(int index, const QImage& image);

    /**
     * @brief 截屏进度更新
     * @param current 当前帧序号
     * @param estimatedTotal 预估总帧数
     */
    void captureProgress(int current, int estimatedTotal);

    /**
     * @brief 截屏完成
     * @param result 截屏结果
     */
    void captureFinished(const CaptureResult& result);

    /**
     * @brief 截屏错误
     * @param message 错误信息
     */
    void captureError(const QString& message);
};

}  // namespace core
}  // namespace longshot
