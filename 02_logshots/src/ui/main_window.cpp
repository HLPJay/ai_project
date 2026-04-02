#include "main_window.h"
#include "../core/capture/capture_core.h"
#include <QPushButton>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QLabel>
#include <QWidget>
#include <QFrame>
#include <QMessageBox>
#include <QCloseEvent>
#include <QDesktopServices>
#include <QUrl>
#include <QDebug>

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("LongShot");
    setFixedSize(400, 86);
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    setAttribute(Qt::WA_TranslucentBackground);

    auto* centralWidget = new QFrame(this);
    centralWidget->setObjectName("centralWidget");
    centralWidget->setStyleSheet(R"(
        QFrame#centralWidget {
            background-color: #2d2d2d;
            border-radius: 8px;
            border: 1px solid #444;
        }
        QPushButton {
            background-color: #3d3d3d;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: 13px;
            min-width: 60px;
        }
        QPushButton:hover {
            background-color: #4d4d4d;
        }
        QPushButton:pressed {
            background-color: #2d2d2d;
        }
        QLabel#progressLabel {
            color: #aaa;
            font-size: 12px;
        }
    )");

    auto* outerLayout = new QVBoxLayout(centralWidget);
    outerLayout->setContentsMargins(10, 8, 10, 6);
    outerLayout->setSpacing(4);

    auto* btnLayout = new QHBoxLayout();
    btnLayout->setSpacing(8);

    auto* btnWeb = new QPushButton("网页", centralWidget);
    auto* btnWindow = new QPushButton("窗口", centralWidget);
    auto* btnRegion = new QPushButton("区域", centralWidget);
    auto* btnRecord = new QPushButton("录屏", centralWidget);
    auto* btnSettings = new QPushButton("设置", centralWidget);

    btnStop_ = new QPushButton("停止", centralWidget);
    btnStop_->setStyleSheet(R"(
        QPushButton {
            background-color: #c0392b;
            color: #fff;
        }
        QPushButton:hover {
            background-color: #e74c3c;
        }
        QPushButton:pressed {
            background-color: #a93226;
        }
    )");
    btnStop_->hide();

    btnLayout->addWidget(btnWeb);
    btnLayout->addWidget(btnWindow);
    btnLayout->addWidget(btnRegion);
    btnLayout->addWidget(btnRecord);
    btnLayout->addWidget(btnSettings);
    btnLayout->addWidget(btnStop_);

    progressLabel_ = new QLabel(centralWidget);
    progressLabel_->setObjectName("progressLabel");
    progressLabel_->setAlignment(Qt::AlignCenter);
    progressLabel_->hide();

    outerLayout->addLayout(btnLayout);
    outerLayout->addWidget(progressLabel_);

    setCentralWidget(centralWidget);

    captureCore_ = std::make_unique<CaptureCore>();

    connect(btnWeb, &QPushButton::clicked, this, &MainWindow::onWebCaptureClicked);
    connect(btnWindow, &QPushButton::clicked, this, &MainWindow::onWindowCaptureClicked);
    connect(btnRegion, &QPushButton::clicked, this, &MainWindow::onRegionCaptureClicked);
    connect(btnRecord, &QPushButton::clicked, this, &MainWindow::onRecordClicked);
    connect(btnSettings, &QPushButton::clicked, this, &MainWindow::onSettingsClicked);
    connect(btnStop_, &QPushButton::clicked, this, &MainWindow::onStopCaptureClicked);

    connect(captureCore_.get(), &CaptureCore::captureFinished,
            this, &MainWindow::onCaptureFinished, Qt::QueuedConnection);
    connect(captureCore_.get(), &CaptureCore::captureFailed,
            this, &MainWindow::onCaptureFailed, Qt::QueuedConnection);
    connect(captureCore_.get(), &CaptureCore::captureProgress,
            this, &MainWindow::onCaptureProgress, Qt::QueuedConnection);
}

void MainWindow::mousePressEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        isDragging_ = true;
        dragPosition_ = event->globalPosition().toPoint() - frameGeometry().topLeft();
        event->accept();
    }
}

void MainWindow::mouseMoveEvent(QMouseEvent* event)
{
    if (event->buttons() & Qt::LeftButton && isDragging_) {
        move(event->globalPosition().toPoint() - dragPosition_);
        event->accept();
    }
}

void MainWindow::mouseReleaseEvent(QMouseEvent* event)
{
    if (event->button() == Qt::LeftButton) {
        isDragging_ = false;
    }
}

void MainWindow::onWebCaptureClicked()
{
    qDebug() << "[MainWindow] Web capture clicked";
    btnStop_->show();
    captureCore_->startCapture();
}

void MainWindow::onWindowCaptureClicked()
{
    qDebug() << "[MainWindow] Window capture clicked";
}

void MainWindow::onRegionCaptureClicked()
{
    qDebug() << "[MainWindow] Region capture clicked";
}

void MainWindow::onRecordClicked()
{
    qDebug() << "[MainWindow] Record clicked";
}

void MainWindow::onSettingsClicked()
{
    qDebug() << "[MainWindow] Settings clicked";
}

void MainWindow::onCaptureFinished(const QString& framesDir)
{
    progressLabel_->hide();
    btnStop_->hide();
    qDebug() << "[MainWindow] Capture finished, frames dir:" << framesDir;

    // 自动打开文件夹，让用户直接看到帧文件
    if (!framesDir.isEmpty()) {
        QDesktopServices::openUrl(QUrl::fromLocalFile(framesDir));
    }

    QMessageBox::information(this, "截屏完成",
        QString("截屏完成，帧文件已保存到：\n%1").arg(framesDir));
}

void MainWindow::onCaptureFailed(const QString& error)
{
    progressLabel_->hide();
    btnStop_->hide();
    qDebug() << "[MainWindow] Capture failed:" << error;
    QMessageBox::warning(this, "截屏失败", error);
}

void MainWindow::onStopCaptureClicked()
{
    qDebug() << "[MainWindow] Stop capture clicked";
    captureCore_->stopCapture();
    progressLabel_->hide();
    btnStop_->hide();
}

void MainWindow::onCaptureProgress(int current, int estimated)
{
    progressLabel_->show();
    progressLabel_->setText(
        QString("第 %1 帧 / 预估 %2 帧").arg(current + 1).arg(estimated));
}

void MainWindow::closeEvent(QCloseEvent* event)
{
    hide();
    event->ignore();
    qDebug() << "[MainWindow] Minimized to tray";
}

MainWindow::~MainWindow() = default;
