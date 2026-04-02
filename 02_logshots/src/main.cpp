#include <QApplication>
#include <QCoreApplication>
#include "app/application.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QCoreApplication::setOrganizationName("LongShot");
    QCoreApplication::setApplicationName("LongShot");
    QCoreApplication::setApplicationVersion("1.0.0");
    Application::instance().init();
    return QApplication::exec();
}
