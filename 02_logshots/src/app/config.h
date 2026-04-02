#pragma once
#include <QObject>
#include <QVariant>

/**
 * @brief Configuration manager using QSettings
 *
 * Singleton that provides access to application configuration stored in QSettings.
 */
class Config : public QObject {
    Q_OBJECT
public:
    /**
     * @brief Get the singleton instance
     * @return Reference to the Config instance
     */
    static Config& instance();

    /**
     * @brief Get a configuration value
     * @param key Configuration key (e.g., "capture/scrollDelay")
     * @param defaultValue Default value if key not found
     * @return The configured value or default
     */
    QVariant get(const QString& key, const QVariant& defaultValue = QVariant()) const;

    /**
     * @brief Set a configuration value
     * @param key Configuration key
     * @param value Value to set
     */
    void set(const QString& key, const QVariant& value);

private:
    Config();
    ~Config() = default;
    Config(const Config&) = delete;
    Config& operator=(const Config&) = delete;
};