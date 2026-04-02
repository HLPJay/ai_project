#include "application.h"
#include "config.h"
#include "../ui/main_window.h"
#include "../ui/tray_manager.h"
#include <QDebug>

Application& Application::instance()
{
    static Application instance;
    return instance;
}

void Application::init()
{
    qInfo() << "LongShot starting...";
    Config::instance();
    createMainWindow();
}

void Application::createMainWindow()
{
    mainWindow_ = std::make_unique<MainWindow>();
    mainWindow_->show();

    trayManager_ = std::make_unique<TrayManager>(mainWindow_.get());
    trayManager_->show();

    qInfo() << "LongShot initialized";
}