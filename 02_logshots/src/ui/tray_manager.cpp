#include "tray_manager.h"
#include "main_window.h"
#include <QAction>
#include <QApplication>
#include <QStyle>
#include <QCoreApplication>
#include <QDebug>

TrayManager::TrayManager(MainWindow* mainWindow, QObject* parent)
    : QObject(parent)
    , mainWindow_(mainWindow)
{
    trayMenu_ = std::make_unique<QMenu>();

    auto* actionShow = new QAction("显示主窗口", trayMenu_.get());
    auto* actionClose = new QAction("关闭", trayMenu_.get());
    auto* actionExit = new QAction("退出", trayMenu_.get());

    trayMenu_->addAction(actionShow);
    trayMenu_->addAction(actionClose);
    trayMenu_->addSeparator();
    trayMenu_->addAction(actionExit);

    trayIcon_ = std::make_unique<QSystemTrayIcon>(this);
    trayIcon_->setIcon(QApplication::style()->standardIcon(QStyle::SP_ComputerIcon));
    trayIcon_->setContextMenu(trayMenu_.get());
    trayIcon_->setToolTip("LongShot - 长截屏工具");

    connect(actionShow, &QAction::triggered, this, &TrayManager::onShowTriggered);
    connect(actionClose, &QAction::triggered, this, &TrayManager::onCloseTriggered);
    connect(actionExit, &QAction::triggered, this, &TrayManager::onExitTriggered);
    connect(trayIcon_.get(), &QSystemTrayIcon::activated, this, &TrayManager::onTrayActivated);
}

TrayManager::~TrayManager() = default;

void TrayManager::show()
{
    trayIcon_->show();
}

void TrayManager::hide()
{
    trayIcon_->hide();
}

void TrayManager::onShowTriggered()
{
    mainWindow_->show();
    mainWindow_->activateWindow();
    isVisible_ = true;
    qDebug() << "[TrayManager] Main window shown";
}

void TrayManager::onCloseTriggered()
{
    mainWindow_->hide();
    isVisible_ = false;
    qDebug() << "[TrayManager] Main window closed (minimized to tray)";
}

void TrayManager::onExitTriggered()
{
    qDebug() << "[TrayManager] Exit requested";
    QCoreApplication::quit();
}

void TrayManager::onTrayActivated(QSystemTrayIcon::ActivationReason reason)
{
    if (reason == QSystemTrayIcon::Trigger) {
        if (isVisible_) {
            onCloseTriggered();
        } else {
            onShowTriggered();
        }
    }
}