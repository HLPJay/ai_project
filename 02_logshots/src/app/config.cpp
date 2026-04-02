#include "config.h"
#include <QSettings>
#include <QCoreApplication>
#include <QDir>

Config::Config() : QObject()
{
    QSettings settings(QCoreApplication::organizationName(), "LongShot");
    if (!settings.contains("capture/scrollDelay"))
        settings.setValue("capture/scrollDelay", 300);
    if (!settings.contains("capture/format"))
        settings.setValue("capture/format", "png");
    if (!settings.contains("capture/jpegQuality"))
        settings.setValue("capture/jpegQuality", 90);
    if (!settings.contains("storage/savePath"))
        settings.setValue("storage/savePath",
            QDir::homePath() + "/Pictures/LongShot/");
    if (!settings.contains("shortcuts/webCapture"))
        settings.setValue("shortcuts/webCapture", "Ctrl+Shift+L");
    if (!settings.contains("shortcuts/regionCapture"))
        settings.setValue("shortcuts/regionCapture", "Ctrl+Shift+A");
}

Config& Config::instance()
{
    static Config instance;
    return instance;
}

QVariant Config::get(const QString& key, const QVariant& defaultValue) const
{
    QSettings settings(QCoreApplication::organizationName(), "LongShot");
    return settings.value(key, defaultValue);
}

void Config::set(const QString& key, const QVariant& value)
{
    QSettings settings(QCoreApplication::organizationName(), "LongShot");
    settings.setValue(key, value);
}
