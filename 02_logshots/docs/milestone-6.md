# Milestone 6: VideoFrameExtractor — 录屏转长图（P2）

## 目标
从屏幕录制视频中提取关键帧，去除重复帧后交给 Stitcher 拼接为长图。

## 前置依赖
- Milestone 3（Stitcher 可用）
- Milestone 5（UI 提供入口）

## 交付清单

### 6.1 FFmpeg 集成
- 使用 FFmpeg C API 直接链接（libavformat, libavcodec, libswscale）
- 不使用 QProcess 调用 FFmpeg CLI（避免二进制分发问题）
- vcpkg.json 中添加 ffmpeg 依赖
- CMakeLists 中 find_package(FFmpeg) 并链接

**注意：LGPL 合规**
- FFmpeg 默认 LGPL 许可，与项目兼容
- 禁止启用 --enable-gpl 选项的编解码器（如 libx264）
- 仅使用 LGPL 兼容的解码器即可（读取视频不需要编码器）

### 6.2 帧提取器
- src/core/video/frame_extractor.h/cpp

```cpp
struct FrameExtractionConfig {
    double ssimThreshold = 0.92;    // 帧间相似度阈值，低于此值认为是新帧
    int sampleIntervalMs = 500;     // 采样间隔（不是每帧都分析）
    int maxKeyFrames = 200;         // 关键帧数量上限
    QSize resizeTo = {0, 0};        // 分析时缩放尺寸（0=原始尺寸）
};

struct ExtractionResult {
    QStringList keyFramePaths;      // 关键帧文件路径列表
    int totalFramesAnalyzed;
    int keyFramesExtracted;
    double videoDurationSec;
};
```

**提取流程：**
1. 使用 `avformat_open_input` 打开视频文件
2. 找到视频流（`avformat_find_stream_info`）
3. 按 sampleIntervalMs 间隔 seek 到采样点
4. 解码帧并转为 QImage（通过 swscale 转 RGB）
5. 与上一个保留帧计算 SSIM 相似度
6. 如果 SSIM < ssimThreshold，保留为关键帧
7. 关键帧保存到临时目录
8. 提取完成后，将关键帧路径列表交给 Stitcher

**SSIM 计算：**
- 使用 OpenCV 的 `cv::quality::QualitySSIM::compute()`
- 或手动实现简化版：缩放到 256px 宽度后逐像素比较，性能更好
- 建议两种都实现，默认用简化版，config 中可切换

### 6.3 UI 入口
- 点击"录屏转长图"按钮 → QFileDialog 选择视频文件
- 支持格式：MP4, WebM, MKV, AVI, MOV
- 选择后显示视频基本信息（时长、分辨率、帧数）
- 可调整 SSIM 阈值（滑块：0.8 - 0.99）
- 开始提取 → 进度条显示分析进度
- 提取完成 → 预览关键帧缩略图列表，用户可手动勾选/取消帧
- 确认后触发 Stitcher 拼接 → 进入预览窗口

### 6.4 性能优化
- 帧分析在独立工作线程中执行
- 分析时使用缩放后的小图计算 SSIM（256px 宽），确认为关键帧后再保存原始尺寸
- 内存中最多保留 2 帧（当前帧 + 上一关键帧），及时释放解码缓冲

## 完成标准
- [ ] 能正确打开并解析 MP4/WebM 视频
- [ ] 关键帧提取结果合理（滚动内容的录屏应提取每个新内容区域）
- [ ] 1 分钟 1080p 视频的分析时间 < 30 秒
- [ ] 提取的关键帧交给 Stitcher 后能正确拼接
- [ ] 内存占用可控，不会因为视频过长而 OOM
