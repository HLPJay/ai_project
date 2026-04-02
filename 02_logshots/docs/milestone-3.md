# Milestone 3: Stitcher — 图像拼接引擎

## 目标
将多帧截图智能拼接为一张无缝长图，处理重叠区域和 sticky 元素。

## 前置依赖
- Milestone 2 完成（提供帧序列作为输入）

## 交付清单

### 3.1 接口定义
- src/core/stitcher/i_stitcher.h

```cpp
struct StitchConfig {
    int minOverlapPx = 20;        // 最小重叠像素
    int maxOverlapPx = 500;       // 最大重叠搜索范围
    double matchThreshold = 0.95; // 像素匹配阈值 (0-1)
    bool detectStickyHeader = true;
    bool detectStickyFooter = true;
    int maxOutputHeight = 65535;  // PNG 规范限制
};

struct StitchResult {
    QImage image;                 // 拼接后的图片
    int totalFrames;
    int removedOverlapPx;         // 去除的总重叠像素
    bool wasSplit;                // 是否因超长而分片
    QStringList splitPaths;       // 分片文件路径（如果分片）
};

class IStitcher : public QObject {
    Q_OBJECT
public:
    virtual void stitch(const QStringList& framePaths, const StitchConfig& config) = 0;
signals:
    void stitchProgress(int current, int total);
    void stitchFinished(const StitchResult& result);
    void stitchError(const QString& message);
};
```

### 3.2 重叠检测算法
- src/core/stitcher/overlap_detector.h/cpp
- 核心算法——逐行像素哈希 + 滑动窗口匹配：

**算法流程：**
1. 取帧 A 的底部区域（maxOverlapPx 高度）、帧 B 的顶部区域
2. 将两个区域转为灰度图，对每一行计算哈希值（行像素均值或 CRC32）
3. 用帧 B 的顶部行哈希序列，在帧 A 的底部行哈希序列中做滑动窗口匹配
4. 找到最佳匹配位置后，用 OpenCV `cv::matchTemplate` 对候选区域做精确像素验证
5. 验证通过（相似度 > matchThreshold），返回重叠行数

**备选方案（如果行哈希不够鲁棒）：**
- 使用 OpenCV `cv::matchTemplate(TM_CCOEFF_NORMED)` 直接做模板匹配
- 取帧 B 顶部 N 行作为模板，在帧 A 底部区域搜索
- 性能稍慢但准确度更高

**请你实现时两种方案都写，通过 StitchConfig 切换，并用单元测试对比效果。**

### 3.3 Sticky Header/Footer 检测
- src/core/stitcher/sticky_detector.h/cpp

**检测逻辑：**
1. 取前 3 帧，比较每帧顶部 N 行（N 从 10 到 200 递增搜索）
2. 如果前 3 帧的顶部 N 行像素完全一致（允许 1% 容差），判定为 sticky header，高度为 N
3. 同理检测 sticky footer（比较底部 N 行）
4. 拼接时，第 2 帧起裁掉 sticky header 区域，倒数第 2 帧起裁掉 sticky footer 区域
5. 最终长图中只保留第 1 帧的 header 和最后 1 帧的 footer

### 3.4 拼接执行
- src/core/stitcher/image_stitcher.h/cpp

**拼接流程：**
1. 加载所有帧到 `std::vector<cv::Mat>`
2. 检测 sticky header/footer
3. 逐对检测重叠区域
4. 计算最终图片高度 = Σ(帧高度) - Σ(重叠高度) - sticky 裁切
5. 创建目标 cv::Mat，逐帧 copyTo 到正确位置
6. 如果高度 > maxOutputHeight，自动分片

**内存优化：**
- 不要一次性加载所有帧到内存
- 流式处理：加载帧 A+B → 检测重叠 → 拼接 → 释放帧 A → 加载帧 C → ...
- 使用 cv::Mat 的 ROI（Region of Interest）避免不必要的内存拷贝

### 3.5 单元测试
- tests/test_overlap_detector.cpp
- tests/test_image_stitcher.cpp

**测试用例：**
- 两帧完全不重叠 → 直接堆叠
- 两帧有 100px 重叠 → 正确去重
- 带 sticky header 的 5 帧序列 → header 只出现一次
- 帧序列总高度超过 65535px → 正确分片
- 空帧序列 → 优雅报错
- 单帧 → 直接返回原图

## 完成标准
- [ ] 20 帧拼接耗时 < 5 秒
- [ ] 拼接接缝处肉眼不可见（无重复内容、无断裂）
- [ ] 带 sticky header 的页面，header 在长图中只出现一次
- [ ] 超长图正确分片并提示用户
- [ ] 所有单元测试通过
