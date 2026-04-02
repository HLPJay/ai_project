#pragma once
#include <QMainWindow>
#include <QMouseEvent>
#include <QPushButton>
#include <memory>

class CaptureCore;
class QLabel;

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

private:
    QPoint dragPosition_;          ///< Starting position for drag operation
    bool isDragging_ = false;     ///< Whether window is being dragged
    QLabel* progressLabel_ = nullptr;            ///< Real-time progress display
    QPushButton* btnStop_ = nullptr;             ///< Stop capture button (shown during capture)
    std::unique_ptr<CaptureCore> captureCore_;  ///< Capture engine instance
};
