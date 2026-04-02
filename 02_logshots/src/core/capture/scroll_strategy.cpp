#include "scroll_strategy.h"

#include <QtMath>

namespace longshot {
namespace core {

ScrollStrategy::ScrollStrategy(const ScrollConfig& config, QObject* parent)
    : QObject(parent), config_(config) {}

QString ScrollStrategy::generateInitScript() const {
    QStringList scripts;

    // 禁用平滑滚动，确保滚动立即生效
    if (config_.disableSmoothScroll) {
        scripts.append(R"(
            (function() {
                var style = document.createElement('style');
                style.textContent = 'html, body { scroll-behavior: auto !important; }';
                document.head.appendChild(style);
            })();
        )");
    }

    // 移除 overflow:hidden，确保页面可以正常滚动
    scripts.append(R"(
        (function() {
            var html = document.documentElement;
            var body = document.body;
            var htmlStyle = window.getComputedStyle(html).overflow;
            var bodyStyle = window.getComputedStyle(body).overflow;
            if (htmlStyle === 'hidden') { html.style.overflow = 'visible'; }
            if (bodyStyle === 'hidden') { body.style.overflow = 'visible'; }
        })();
    )");

    // 获取页面基本信息（带 fallback，防止 scrollHeight/innerHeight 为 0）
    scripts.append(R"(
        (function() {
            var sh = Math.max(
                document.documentElement.scrollHeight || 0,
                document.body ? (document.body.scrollHeight || 0) : 0
            );
            var vh = window.innerHeight
                  || document.documentElement.clientHeight
                  || document.body.clientHeight
                  || 0;
            var st = document.documentElement.scrollTop
                  || window.pageYOffset
                  || 0;
            return JSON.stringify({
                scrollHeight: sh,
                viewportHeight: vh,
                scrollTop: st
            });
        })();
    )");

    return scripts.join("\n");
}

QString ScrollStrategy::generateScrollScript(int currentScrollTop) const {
    Q_UNUSED(currentScrollTop);

    return QString(R"(
        (function() {
            var viewportHeight = window.innerHeight;
            var scrollBy = viewportHeight - %1;
            window.scrollBy(0, scrollBy);
            return document.documentElement.scrollTop;
        })();
    )").arg(config_.overlapPixels);
}

QString ScrollStrategy::generateGetScrollTopScript() const {
    return R"(
        (function() {
            var sh = Math.max(
                document.documentElement.scrollHeight || 0,
                document.body ? (document.body.scrollHeight || 0) : 0
            );
            var vh = window.innerHeight
                  || document.documentElement.clientHeight
                  || document.body.clientHeight
                  || 0;
            var st = document.documentElement.scrollTop
                  || window.pageYOffset
                  || 0;
            return JSON.stringify({
                scrollTop: st,
                scrollHeight: sh,
                viewportHeight: vh
            });
        })();
    )";
}

int ScrollStrategy::estimateTotalFrames(int scrollHeight, int viewportHeight) const {
    if (viewportHeight <= 0 || scrollHeight <= 0) {
        return 0;
    }

    int effectiveOffset = frameOffset(viewportHeight);
    if (effectiveOffset <= 0) {
        return 1;
    }

    // ceil((scrollHeight - viewportHeight) / effectiveOffset) + 1
    int scrollableDistance = scrollHeight - viewportHeight;
    int frames = qCeil(static_cast<qreal>(scrollableDistance) / effectiveOffset) + 1;

    return qMin(frames, config_.maxFrames);
}

int ScrollStrategy::frameOffset(int viewportHeight) const {
    int offset = viewportHeight - config_.overlapPixels;
    return qMax(offset, 1);  // 至少移动 1 像素
}

bool ScrollStrategy::isAtBottom(int scrollTop, int scrollHeight, int viewportHeight) const {
    // 到达底部条件：scrollTop + viewportHeight >= scrollHeight
    return (scrollTop + viewportHeight) >= scrollHeight;
}

QString ScrollStrategy::generateLazyLoadTriggerScript() const {
    if (!config_.handleLazyLoad) {
        // 返回空脚本
        return QString();
    }

    // IntersectionObserver JS：触发所有懒加载图片
    // 处理 data-src、data-lazy-src、loading="lazy" 等常见懒加载模式
    return R"(
        (function() {
            var results = [];

            // 1. 处理 data-src 图片（常用懒加载模式）
            var imgObserver = new IntersectionObserver(function(entries) {
                entries.forEach(function(entry) {
                    if (entry.isIntersecting) {
                        var img = entry.target;
                        var src = img.dataset.src || img.dataset.lazySrc || img.dataset.original;
                        if (src) {
                            img.src = src;
                            results.push(src);
                        }
                        imgObserver.unobserve(img);
                    }
                });
            }, { rootMargin: '100px' });

            document.querySelectorAll('img[data-src], img[data-lazy-src], img[data-original]').forEach(function(img) {
                imgObserver.observe(img);
            });

            // 2. 触发已加载但未显示的图片
            document.querySelectorAll('img[src][loading="lazy"]').forEach(function(img) {
                var rect = img.getBoundingClientRect();
                if (rect.top < window.innerHeight && rect.bottom > 0) {
                    results.push(img.src);
                }
            });

            // 3. 触发 background-image 懒加载
            document.querySelectorAll('[data-bg-src], [data-background-image]').forEach(function(el) {
                var bgSrc = el.dataset.bgSrc || el.dataset.backgroundImage;
                if (bgSrc) {
                    el.style.backgroundImage = 'url(' + bgSrc + ')';
                    results.push(bgSrc);
                }
            });

            return JSON.stringify({ triggered: results.length, sources: results });
        })();
    )";
}

}  // namespace core
}  // namespace longshot
