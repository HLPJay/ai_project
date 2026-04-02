#pragma once

#include <QString>
#include <QObject>

namespace longshot {
namespace core {

/**
 * @brief 滚动配置参数
 */
struct ScrollConfig {
    /** 相邻帧重叠像素数 */
    int overlapPixels = 100;
    /** 滚动后等待渲染时间（毫秒） */
    int scrollDelayMs = 300;
    /** 安全上限，防止无限滚动 */
    int maxFrames = 200;
    /** 注入 JS 禁用 scroll-behavior: smooth */
    bool disableSmoothScroll = true;
    /** 处理懒加载图片（额外等待） */
    bool handleLazyLoad = true;
};

/**
 * @brief 滚动策略抽象
 *
 * 负责生成控制页面滚动的 JavaScript 代码，
 * 并计算滚动参数（总帧数、每帧偏移量等）。
 */
class ScrollStrategy : public QObject {
    Q_OBJECT

public:
    explicit ScrollStrategy(const ScrollConfig& config, QObject* parent = nullptr);
    ~ScrollStrategy() override = default;

    /**
     * @brief 获取滚动配置
     */
    const ScrollConfig& config() const { return config_; }

    /**
     * @brief 生成初始化 JS（禁用平滑滚动、获取页面高度）
     * @return JavaScript 代码
     */
    QString generateInitScript() const;

    /**
     * @brief 生成滚动到下一位置的 JS
     * @param currentScrollTop 当前滚动位置
     * @return JavaScript 代码
     */
    QString generateScrollScript(int currentScrollTop) const;

    /**
     * @brief 生成获取当前滚动位置的 JS
     * @return JavaScript 代码
     */
    QString generateGetScrollTopScript() const;

    /**
     * @brief 生成懒加载图片触发 JS
     *
     * 注入 IntersectionObserver，当 handleLazyLoad=true 时调用。
     * 触发 data-src 或 loading="lazy" 的图片加载。
     * @return JavaScript 代码
     */
    QString generateLazyLoadTriggerScript() const;

    /**
     * @brief 计算预估总帧数
     * @param scrollHeight 页面总高度
     * @param viewportHeight 视口高度
     * @return 预估帧数
     */
    int estimateTotalFrames(int scrollHeight, int viewportHeight) const;

    /**
     * @brief 每帧垂直偏移量（等于视口高度减去重叠区）
     * @param viewportHeight 视口高度
     * @return 偏移量
     */
    int frameOffset(int viewportHeight) const;

    /**
     * @brief 判断是否已滚动到底部
     * @param scrollTop 当前滚动位置
     * @param scrollHeight 页面总高度
     * @param viewportHeight 视口高度
     * @return 是否到底
     */
    bool isAtBottom(int scrollTop, int scrollHeight, int viewportHeight) const;

private:
    ScrollConfig config_;
};

}  // namespace core
}  // namespace longshot
