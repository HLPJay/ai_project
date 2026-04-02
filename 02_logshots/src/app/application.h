#pragma once
#include <QObject>
#include <memory>

class MainWindow;
class TrayManager;

/**
 * @brief Application singleton - manages global application lifecycle
 */
class Application : public QObject {
    Q_OBJECT
public:
    /**
     * @brief Get the singleton instance
     * @return Reference to the Application instance
     */
    static Application& instance();

    /**
     * @brief Initialize the application
     */
    void init();

    /**
     * @brief Create and show the main window with system tray
     */
    void createMainWindow();

    /**
     * @brief Get the main window instance
     * @return Pointer to MainWindow, or nullptr if not created
     */
    MainWindow* mainWindow() const { return mainWindow_.get(); }

private:
    Application() = default;
    ~Application() override = default;
    Application(const Application&) = delete;
    Application& operator=(const Application&) = delete;

    std::unique_ptr<MainWindow> mainWindow_;
    std::unique_ptr<TrayManager> trayManager_;
};