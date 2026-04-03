#pragma once
#include <QMainWindow>
#include <QMouseEvent>
#include <QPushButton>
#include <QRect>
#include <QThread>
#include <memory>

#include "core/stitcher/i_stitcher.h"
#include "core/capture/i_capture_engine.h"
#include "platform/interface/i_screen_capturer.h"
#include "platform/interface/i_scroll_input.h"

class CaptureCore;
class ImageStitcher;
class IWindowEnumerator;
class WindowPickerOverlay;
class RegionSelectorOverlay;
class QLabel;

namespace longshot {
namespace core {
class FrameSaver;
}  // namespace core
}  // namespace longshot

using longshot::core::ICaptureEngine;
using longshot::core::FrameSaver;

/**
 * @brief Main floating control window for LongShot
 *
 * A frameless, always-on-top window with capture controls.
 * Supports drag-to-move via mouse events.
 */
class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    /**
     * @brief Construct the main window
     * @param parent Parent widget (default nullptr)
     */
    explicit MainWindow(QWidget* parent = nullptr);

    /**
     * @brief Destructor
     */
    ~MainWindow() override;

protected:
    /// @brief Mouse press handler for drag detection
    void mousePressEvent(QMouseEvent* event) override;

    /// @brief Mouse move handler for window dragging
    void mouseMoveEvent(QMouseEvent* event) override;

    /// @brief Mouse release handler to end drag
    void mouseReleaseEvent(QMouseEvent* event) override;

    /// @brief Close event: minimize to tray instead of quitting
    void closeEvent(QCloseEvent* event) override;

private slots:
    /// @brief Handle web capture button click
    void onWebCaptureClicked();

    /// @brief Handle window capture button click
    void onWindowCaptureClicked();

    /// @brief Handle region capture button click
    void onRegionCaptureClicked();

    /// @brief Handle record button click
    void onRecordClicked();

    /// @brief Handle settings button click
    void onSettingsClicked();

    /// @brief Handle capture completion
    void onCaptureFinished(const QString& framesDir);

    /// @brief Handle capture failure
    void onCaptureFailed(const QString& error);

    /// @brief Handle real-time capture progress
    void onCaptureProgress(int current, int estimated);

    /// @brief Handle stop button click
    void onStopCaptureClicked();

    /// @brief Handle stitching completion
    void onStitchFinished(const StitchResult& result);

    /// @brief Handle stitching failure
    void onStitchFailed(const QString& error);

    /// @brief Handle stitching progress
    void onStitchProgress(int current, int total);

    /// @brief Handle window selected from picker
    void onWindowSelected(int64_t windowId);

    /// @brief Handle region selected from selector
    void onRegionSelected(const QRect& rect);

    /// @brief Handle picker/selector cancelled
    void onPickerCancelled();

    /// @brief Handle window capture finished
    void onWindowCaptureFinished(const longshot::core::CaptureResult& result);

    /// @brief Handle window capture error
    void onWindowCaptureError(const QString& error);

    /// @brief Handle window capture progress
    void onWindowCaptureProgress(int current, int estimated);

    /// @brief Handle region capture finished
    void onRegionCaptureFinished(const longshot::core::CaptureResult& result);

    /// @brief Handle region capture error
    void onRegionCaptureError(const QString& error);

    /// @brief Handle region capture progress
    void onRegionCaptureProgress(int current, int estimated);

    /// @brief Initialize window capture components
    void initWindowCapture();

    /// @brief Initialize region capture components
    void initRegionCapture();

private:
    void startWindowCapture(int64_t windowId);
    void startWindowCaptureWithClass(int64_t windowId, const QString& className);
    void startRegionCapture(const QRect& rect);

    /// @brief 截屏开始时禁用捕获按钮，结束时恢复
    void setCaptureButtonsEnabled(bool enabled);

    QPoint dragPosition_;          ///< Starting position for drag operation
    bool isDragging_ = false;     ///< Whether window is being dragged
    QLabel* progressLabel_ = nullptr;            ///< Real-time progress display
    QPushButton* btnStop_ = nullptr;             ///< Stop capture button (shown during capture)
    QPushButton* btnWeb_ = nullptr;              ///< Web capture button
    QPushButton* btnWindow_ = nullptr;           ///< Window capture button
    QPushButton* btnRegion_ = nullptr;           ///< Region capture button
    std::unique_ptr<CaptureCore> captureCore_;  ///< Capture engine instance
    std::unique_ptr<ImageStitcher> stitcher_;    ///< Image stitcher instance
    QString lastFramesDir_;        ///< Last frames directory for stitching
    IWindowEnumerator* windowEnumerator_ = nullptr;  ///< Window enumerator for picker
    std::unique_ptr<WindowPickerOverlay> windowPicker_;    ///< Window picker overlay
    std::unique_ptr<RegionSelectorOverlay> regionSelector_; ///< Region selector overlay

    // Window capture support
    std::unique_ptr<ICaptureEngine> windowCapture_;  ///< Window capture engine
    std::unique_ptr<IScreenCapturer> windowScreenCapturer_;  ///< Platform screen capturer for window
    std::unique_ptr<IScrollInput> scrollInput_;  ///< Platform scroll input
    QThread windowCaptureThread_;  ///< Worker thread for window capture
    FrameSaver* windowFrameSaver_ = nullptr;  ///< Frame saver for window capture
    QString windowFramesDir_;  ///< Frames directory for window capture

    // Region capture support
    std::unique_ptr<ICaptureEngine> regionCapture_;  ///< Region capture engine
    std::unique_ptr<IScreenCapturer> regionScreenCapturer_;  ///< Platform screen capturer for region
    QString regionFramesDir_;  ///< Frames directory for region capture
};
