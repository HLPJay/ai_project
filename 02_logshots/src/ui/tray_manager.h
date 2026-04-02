#pragma once
#include <QObject>
#include <QSystemTrayIcon>
#include <QMenu>
#include <memory>

class MainWindow;

/**
 * @brief System tray manager for LongShot
 *
 * Manages the system tray icon, context menu, and window visibility toggle.
 */
class TrayManager : public QObject {
    Q_OBJECT
public:
    /**
     * @brief Construct the tray manager
     * @param mainWindow Pointer to the main window (not owned)
     * @param parent Parent QObject (default nullptr)
     */
    explicit TrayManager(MainWindow* mainWindow, QObject* parent = nullptr);

    /**
     * @brief Destructor
     */
    ~TrayManager() override;

    /**
     * @brief Show the system tray icon
     */
    void show();

    /**
     * @brief Hide the system tray icon
     */
    void hide();

private slots:
    /// @brief Show the main window
    void onShowTriggered();

    /// @brief Close (minimize to tray) the main window
    void onCloseTriggered();

    /// @brief Exit the application
    void onExitTriggered();

    /// @brief Handle tray icon activation
    void onTrayActivated(QSystemTrayIcon::ActivationReason reason);

private:
    std::unique_ptr<QSystemTrayIcon> trayIcon_;  ///< System tray icon
    std::unique_ptr<QMenu> trayMenu_;            ///< Context menu
    MainWindow* mainWindow_ = nullptr;            ///< Main window (not owned)
    bool isVisible_ = true;                       ///< Window visibility state
};