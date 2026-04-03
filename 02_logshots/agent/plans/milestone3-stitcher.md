# Milestone 3 实现计划 — Stitcher 拼接引擎

## Context

Milestone 2 已完成 CaptureCore 模块，实现网页长截屏功能。Milestone 3 需要实现 Stitcher 模块，将帧序列智能拼接为完整长图，并处理 sticky header/footer 和重叠区域。

## 现有状态

- `src/core/stitcher/` 目录不存在，需新建
- `src/core/capture/` 已完整实现，可提供帧序列
- `src/CMakeLists.txt` 的 APP_SOURCES/APP_HEADERS 中无 stitcher 相关文件
- `tests/` 下仅有占位测试

## 实现文件清单

按依赖顺序实现：

### 第一批：接口和基础工具

1. **`src/core/stitcher/i_stitcher.h`**
   - 定义 `StitchConfig` 和 `StitchResult` 结构
   - 定义 `IStitcher` 纯虚基类
   - 无需修改其他文件（纯新增）

2. **`src/core/stitcher/overlap_detector.h/cpp`** （内联工具函数，不单独创建 utils）
   - 实现两种重叠检测算法（行哈希 + cv::matchTemplate）
   - 通过 `StitchConfig::matchThreshold` 切换

3. **`src/core/stitcher/sticky_detector.h/cpp`**
   - 实现 sticky header/footer 检测
   - 基于像素比对（前 3 帧的顶部/底部 N 行）

4. **`src/core/stitcher/image_stitcher.h/cpp`**
   - 实现 `ImageStitcher` 类，继承 `IStitcher`
   - 流式加载、ROI 拼接、超长分片

### 第二批：单元测试

5. **`tests/test_overlap_detector.cpp`**（新建）
   - 测试两帧不重叠/有 100px 重叠等场景

6. **`tests/test_image_stitcher.cpp`**（替换现有占位测试）
   - 测试 sticky header、带 sticky 的帧序列、分片等

## 关键算法设计

### 重叠检测算法（overlap_detector）

```
算法 A（行哈希）:
1. 取帧 A 底部 maxOverlapPx 高度 → 灰度 → 计算每行哈希（像素均值或 CRC32）
2. 取帧 B 顶部 maxOverlapPx 高度 → 灰度 → 计算每行哈希
3. 帧 B 顶部行哈希序列在帧 A 底部行哈希序列中滑动窗口匹配
4. 找到最佳匹配 → 用 cv::matchTemplate 精确验证
5. 相似度 > matchThreshold → 返回重叠行数

算法 B（直接模板匹配）:
1. 取帧 B 顶部 N 行作为模板
2. cv::matchTemplate(TM_CCOEFF_NORMED) 在帧 A 底部搜索
3. 取最佳匹配位置
```

### Sticky 检测算法（sticky_detector）

```
1. 取前 3 帧，比较每帧顶部 N 行（N 从 10 到 200 递增）
2. 如果前 3 帧的顶部 N 行像素完全一致（允许 1% 容差）→ sticky header，高度 N
3. 同理检测 sticky footer
4. 拼接时：第 2 帧起裁掉 sticky header，倒数第 2 帧起裁掉 sticky footer
```

### 拼接算法（image_stitcher）

```
1. 流式加载：帧 A+B → 检测重叠 → 拼接 → 释放帧 A → 加载帧 C...
2. 检测 sticky header/footer
3. 计算最终高度 = Σ(帧高度) - Σ(重叠高度) - sticky 裁切
4. 创建目标 cv::Mat，逐帧 copyTo 到正确位置
5. 如果高度 > maxOutputHeight，自动分片
```

## 需要修改的现有文件

- **`src/CMakeLists.txt`** — 添加 stitcher 源文件到 APP_SOURCES/APP_HEADERS
- **`tests/CMakeLists.txt`** — 添加新测试文件

## 验证方法

1. 运行 `cmake --build . --parallel` 编译通过
2. 运行 `ctest --output-on-failure` 所有测试通过
3. 性能：20 帧拼接 < 5 秒

## 实现顺序

每个文件独立实现，完成后立即添加对应单元测试，可独立编译验证。
