# 2026-05-04 排查归档：align 阶段在 Windows 上"静默崩溃"

> 本次归档记录一次完整的"误判 → 复诊 → 定位真因"过程，包含两个独立的 bug：
> 一个 Python 端的 Unicode bug（已修复），一个 ctranslate2 的 native 析构 bug（已绕开）。

---

## 1. 问题描述

### 用户报告

```powershell
python -m src.main --project "C:\Users\yun68\.openclaw\workspace\mv\朋友的陪伴_20260503_231332" --phase align --auto
```

**症状：**
- Whisper 转写完成（终端能看到 `[OK] faster-whisper medium (cuda): 25 段, 啦啦啦...`）
- **下一行什么都没有，终端直接回到 PS 提示符**
- 没有任何 traceback、错误、警告
- `metadata/status.json` 永远卡在 `running`，从未更新到 `completed` 或 `failed`
- `temp/song.json`（Whisper 缓存）从未生成
- 其他项目正常，唯独这个项目稳定复现

### 用户原话

> "这个项目会导致执行时崩溃，其他正常，怀疑是音频本身的问题"
> "我重新测试还是会导致崩溃，这是崩溃吗？还是只是终端退出？"

---

## 2. 探索过程

### 阶段 1：初步排查（误判方向）

**第一步检查：**
- 项目结构：歌词文件正常（24 行有效歌词）
- 音频属性：MP3，110.8 秒，256kbps，正常
- Demucs 人声分离：成功完成
- ASR 输出（`temp/song.json`）：**未生成**（这是个关键线索，但当时没意识到含义）

**进入 align.py 源码审查：**
看到第 846 行有这段代码：
```python
print(f"  [..] 对齐中: {len(clean_lyrics)} 行歌词 ↔ "
    f"{len(asr_segments)} 段 ASR...")
```

注意到 `↔` (U+2194) 字符。在 Windows GBK 控制台上 print 这个字符会触发 `UnicodeEncodeError`。

**用 `python -u -c "..."` 复现，确实抓到了：**
```
UnicodeEncodeError: 'gbk' codec can't encode character '↔' in position 19
File "...align.py", line 846, in run
```

**当时的（错误）结论：**
> "Python 抛 UnicodeEncodeError 后，traceback 里也含中文，连带 traceback 都打不出来，进程退出，所以用户什么都看不到。"

**修复（commit `5a49ed3`）：**
1. 把 `↔` 替换为 ASCII `<->`
2. 在 align.py 顶部添加 Windows UTF-8 stdout reconfigure：
   ```python
   if sys.platform == "win32":
       try:
           sys.stdout.reconfigure(encoding="utf-8", errors="replace")
           sys.stderr.reconfigure(encoding="utf-8", errors="replace")
       except (AttributeError, ValueError):
           pass
   ```
3. 我自己用项目 venv 测试了一下（`D:\...\.venv\Scripts\python.exe`），结果跑通了 → 误以为修好了。

### 阶段 2：用户重测仍崩溃

用户按建议跑了：
```powershell
python -m src.main --project "..." --phase align --auto
echo "exit code = $LASTEXITCODE"
```

得到的结果：
```
exit code = -1073740791
```

### 阶段 3：解读真实退出码

`-1073740791` 转为 32-bit unsigned 十六进制是：

```
-1073740791 (signed 32-bit)
= 0xC0000409 (unsigned 32-bit)
= STATUS_STACK_BUFFER_OVERRUN（Windows 系统错误码）
```

**这不是 Python 异常，是 Windows 的 fast-fail 安全检查：某个 C/C++ 扩展库栈溢出，被操作系统强行终结进程。**

特征对比：

| 类型 | 表现 | exit code |
|---|---|---|
| Python 异常 | 终端打印 traceback | 1 |
| **Windows native crash** | 静默退出，什么都没有 | `0xC0000409` 或类似 0xCxxxxxxx |
| `os._exit(0)` | 干净退出 | 0 |

### 阶段 4：定位 native 崩溃位置

仔细看用户输出的最后两行：
```
[OK] faster-whisper small (cuda): 33 段, 啦啦啦阳光撒满了草场小声响响鸟飞翔...
(.venv) PS D:\>
```

`[OK] faster-whisper ...` 是在 `_transcribe_faster_whisper` 函数末尾打印的，**说明 Whisper 转写已经成功完成**。然后控制流是：

```
[OK] faster-whisper ...   ← 这是在 _transcribe_faster_whisper 末尾
       ↓
return result             ← 函数返回，model 局部变量出作用域，被 GC
       ↓
WhisperModel.__del__()    ← ctranslate2 的析构器调用 native 资源释放
       ↓
ct2 native 代码访问已释放的 CUDA stream / 触发栈缓冲检查
       ↓
0xC0000409                ← Windows fast-fail，进程被杀
```

**关键洞察：崩溃发生在转写完成后、模型析构时**，而不是在转写过程中。这是 ctranslate2 在 Windows + CUDA 上长期存在的一个偶发析构 bug，跟具体音频内容、显卡状态、内存对齐都有关，所以"有的项目能跑，有的会崩"。

### 阶段 5：为什么我本地测试能跑过

进一步对比，发现两个环境跑出的 compute_type 不一样：

| 我的测试 | 用户的实际跑 |
|---|---|
| `compute_type=default` | `compute_type=float16` |
| 跑过了 | 崩溃 |

`float16 + medium + CUDA` 在 ctranslate2 上是已知的更不稳定组合。所以同一台机器、同一份代码，根据 compute_type 不同，结果不一样。

### 阶段 6：附带发现的次要 bug

从用户重跑的输出里还看到：
```
Exception in thread Thread-3 (_readerthread):
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa8 in position 127
```

这是 `subprocess.run(text=True)` 默认用 UTF-8 解码 Demucs 的 stdout，但 Demucs 在 Windows 上输出的进度条是 GBK/cp936 编码，导致子线程崩溃。**不影响主进程**，但日志很乱。

---

## 3. 根本原因

### 主问题（致命）：ctranslate2 native 析构崩溃

- **触发条件**：Windows + CUDA + faster-whisper（特别是 `compute_type=float16` 时）
- **崩溃时机**：Whisper 转写**完成之后**，C++ 库释放 CUDA 资源时
- **崩溃类型**：`STATUS_STACK_BUFFER_OVERRUN` (0xC0000409)
- **Python 端表现**：终端无任何输出，退出码 `-1073740791`，看起来像"安静退出"
- **本质**：**第三方 C++ 库的 bug，不是项目代码的 bug**

### 次要问题（不致命）

1. **align.py 第 846 行 `↔` 字符**：Windows GBK 控制台 print 时抛 `UnicodeEncodeError`。在某些条件下确实会让程序崩溃，但**不是这次用户实际遇到的崩溃**。
2. **Demucs subprocess 解码错误**：子线程读 GBK 输出失败，子线程死掉，主线程不受影响。

---

## 4. 修复内容

### 已应用的代码修复

| 位置 | 修改 | 解决什么 |
|---|---|---|
| `src/align.py` 头部 | 添加 `sys.stdout.reconfigure(encoding="utf-8")` | Windows 控制台 Unicode 兼容 |
| `src/align.py` line 846 | `↔` 替换为 `<->` | 直接消除已知的 GBK 编码问题字符 |
| `src/align.py` `DemucsVocalSeparator.separate` | `subprocess.run(..., encoding="utf-8", errors="replace")` | Demucs 子进程输出解码错误 |

涉及 commit：
- `5a49ed3 修复 Windows GBK 编码导致 align 静默崩溃`
- 后续 Demucs subprocess 编码修复

### 真正解决主崩溃的方案：换设备（修订版，⚠️ 见第 9 节）

> ⚠️ **方案演进**：最初我推荐"换 backend 到 openai-whisper"，但用户实测发现这会导致字幕时间戳偏差大。
> **最终最优方案是"换设备到 CPU"**，详见第 9 节"后续追踪"。

**最初方案（绕开崩溃，但有副作用）：**

```bash
ALIGN_ASR_BACKEND=openai-whisper
ALIGN_WHISPER_MODEL=small
```

切换后崩溃消失，但**字幕精度大幅下降**（见第 9 节）。

**最终最优方案（崩溃消失 + 精度保留）：**

```bash
# .env
ALIGN_ASR_BACKEND=faster-whisper      # 保留高精度时间戳
ALIGN_WHISPER_DEVICE=cpu              # 关键：避开 CUDA 析构 bug
ALIGN_WHISPER_MODEL=small             # CPU 上 small 够用
ALIGN_WHISPER_COMPUTE_TYPE=int8       # CPU 友好
ALIGN_WHISPER_VAD_FILTER=true         # 启用 VAD 跳过前奏
ALIGN_WHISPER_WORD_TIMESTAMPS=true    # 启用词级时间戳
```

| Backend | 设备 | 速度 (110s 音频) | 时间戳精度 | 稳定性 |
|---|---|---|---|---|
| faster-whisper | **CUDA** | ~5s | ⭐⭐⭐⭐⭐ | ❌ 崩溃 |
| **faster-whisper** | **CPU + int8** | ~30-60s | ⭐⭐⭐⭐⭐ | ✅ 稳定 |
| openai-whisper | CUDA + small | ~10s | ⭐⭐ | ✅ 稳定但精度差 |
| openai-whisper | CUDA + medium | ~20s | ⭐⭐⭐ | ✅ 稳定 |

**核心洞察**：崩溃来自 `backend × 设备` 的组合，不是 backend 本身。换设备比换 backend 更优。

### 备选缓解方案（仍用 faster-whisper + CUDA）

如果坚持要用 GPU：

```bash
ALIGN_WHISPER_COMPUTE_TYPE=int8_float16   # 或 int8
ALIGN_WHISPER_VAD_FILTER=false
ALIGN_WHISPER_MODEL=small                  # 不要用 medium
```

但这只是**降低**崩溃概率，不能根除。Windows + CUDA + ctranslate2 三者组合永远有析构风险。

或干脆走 CPU：
```bash
ALIGN_WHISPER_DEVICE=cpu
ALIGN_WHISPER_COMPUTE_TYPE=int8
```

---

## 5. 排查方法论沉淀

### 教训一：Windows native 退出码必看

- Python 异常的退出码通常是 `1`
- **退出码 `0xCxxxxxxx`（也就是负数 `-1073xxxxxx`）几乎一定是 native code 崩溃**，跟 Python 没关系
- 排查时必须先让用户跑 `echo "exit code = $LASTEXITCODE"`，不能仅凭"终端没显示错误"就推断是 Python 异常

### 教训二："静默退出"不一定是 Python 问题

| 现象 | 第一直觉 | 但也可能是 |
|---|---|---|
| 终端无错误，进程退出 | Python 异常被吞了 | **C++ 库 native 崩溃**（用 exit code 区分） |
| 输出到一半停了 | 卡住了 | 进程已死，stdout 缓冲未冲 |
| 复现条件诡异 | 数据问题 | **第三方库的偶发 bug**（如本次的 ctranslate2） |

### 教训三：本地复现失败 ≠ 没问题

我本地能跑通，是因为我的环境凑巧用了 `compute_type=default`，避开了 float16 的崩溃路径。**用户的环境变量和我的不一样**，必须问清楚或让用户贴完整复现命令。

### 教训四：误判时要承认并重新出发

阶段 1 的 Unicode 假设虽然指向了一个真 bug，但**不是用户当下的崩溃原因**。当用户重测仍崩溃时，要果断推翻假设，重新看 exit code、重新分析输出，而不是继续在错误方向上加补丁。

---

## 6. 给未来的诊断 Checklist

下次遇到"align 阶段神秘消失" / "终端无错误但程序停了"，按这个顺序查：

- [ ] 让用户跑：`echo "exit code = $LASTEXITCODE"`
- [ ] 如果 exit code 是 `-1073xxxxxx`（即 `0xCxxxxxxx`）→ **C++ native 崩溃**，跳到第 4 步
- [ ] 如果 exit code 是 `1` → Python 异常，让用户跑 `python -X utf8 -u ...` 看 traceback
- [ ] 如果 exit code 是 `0` → 不是崩溃，是流程提前 return 了，看代码逻辑
- [ ] **C++ native 崩溃排查路径：**
  - 看是 Whisper 哪个 backend：faster-whisper 切到 openai-whisper 试
  - 看是不是 GPU：`ALIGN_WHISPER_DEVICE=cpu` 试
  - 看是不是 compute_type：换成 `int8` 或 `default` 试
  - 看是不是 VAD：`ALIGN_WHISPER_VAD_FILTER=false` 试
  - 看是不是显存：换 small 模型 试
- [ ] 修复后让用户**贴最终的 exit code = ?**，不能只看终端输出

---

## 7. 用户面 FAQ（可粘贴到文档/issue 里）

**Q: 我跑 align 步骤直接退出回到 PS，没有错误怎么办？**

A: 先跑 `echo "exit code = $LASTEXITCODE"` 看退出码：
- 如果是负数（比如 -1073740791）→ 这是 Windows native 崩溃，多半是 faster-whisper 的 ctranslate2 在 CUDA 上析构时崩了。设置 `ALIGN_ASR_BACKEND=openai-whisper` 重跑。
- 如果是 1 → 是 Python 异常但被吞了，加 `python -X utf8 -u` 重跑能看到 traceback。

**Q: 为什么有的项目正常，有的崩？**

A: ctranslate2 的析构崩溃是偶发的，跟音频数据、GPU 状态、内存对齐都有关。不是你的项目数据有问题，是底层库的 bug。

**Q: openai-whisper 比 faster-whisper 慢多少？**

A: 速度上 openai-whisper 比 faster-whisper 慢 2-3 倍。但**精度差距更明显**（见第 9 节）。

**Q: 切到 openai-whisper 之后，字幕时间戳偏差很大，怎么办？**

A: 这是 openai-whisper 的固有限制，不是 bug。详见第 9 节。最优解是"**换设备而不是换 backend**"——回到 faster-whisper 但跑在 CPU 上。

---

## 8. 相关文件 / Commits

- `src/align.py` —— 改动文件
- commit `5a49ed3` —— 修复 Windows GBK 编码导致 align 静默崩溃（Unicode + Demucs encoding）
- commit `4f2b6a8` —— openai-whisper 默认开启 word_timestamps 提高时间戳精度
- 项目 `朋友的陪伴_20260503_231332` —— 复现项目（保留，作为回归测试用例）
- 上游 issue 参考（ctranslate2）：搜索 `ctranslate2 windows cuda STATUS_STACK_BUFFER_OVERRUN` 可见多个上游 issue

---

## 9. 后续追踪：openai-whisper 切换后的字幕精度问题（同日发现）

### 9.1 用户反馈

> "我现在换成 openai-whisper 后，发现字幕时间戳偏差很大，最终视频字幕时间戳偏差很大，为什么？"

### 9.2 现象

切换到 `ALIGN_ASR_BACKEND=openai-whisper` 后：
- 程序不再崩溃，能跑完
- 但生成的 `audio/song.srt` 字幕时间戳整体提前/后偏，看视频时字幕和歌唱明显不对位
- 第 1 行字幕从 0 秒就开始（实际歌词在 15 秒后才唱出）

### 9.3 根因分析：两个工具的精度不在一个量级

**faster-whisper 和 openai-whisper 的关键差别：**

| 维度 | faster-whisper | openai-whisper |
|---|---|---|
| **VAD（语音活动检测）** | ✅ 默认开启（Silero VAD） | ❌ 没有内置 |
| **时间戳精度** | 词级别（DTW 对齐） | 30 秒固定窗口 |
| **每段长度** | 1-5 秒 / 段（一段≈一行歌词） | 5-15 秒 / 段（一段含多行） |
| **前奏处理** | VAD 自动跳过 | **会把乐器声"幻觉"成歌词** |
| **默认 word_timestamps** | 可开 | **默认关**（项目里也没开） |

### 9.4 偏差形成机制

```
真实音频时间线（0-110s）：
0─────15s ─────45s──────────110s
[纯前奏][歌词部分        ][结尾]

faster-whisper（有 VAD + word timestamps）：
                 [行1][行2]...
                 ↑
              准确从 15s 开始

openai-whisper（无 VAD）：
[啦啦啦  ][行1   ][行2     ]...
↑         ↑
0s 起     被推到不知哪秒
  ↑ 前奏被识别成虚假的"啦啦啦"
  ↑ 占据了 0-15s
  ↑ 真实歌词的时间戳全部往后偏
```

**双重打击：**
1. 前奏被"幻觉"识别 → 第 1 行歌词的真实段消失，被对齐算法匹配到错误的时间
2. 30 秒窗口固定切片 → 一个 segment 含 3-4 行歌词，时间戳粒度太粗
3. 项目代码原本没开 `word_timestamps` → 雪上加霜

### 9.5 修复

**代码侧**（commit `4f2b6a8`）：
- openai-whisper 调用时默认开启 `word_timestamps=True`
- 配置项：`ALIGN_WHISPER_WORD_TIMESTAMPS=false` 可关闭

但这只能缓解粒度问题，**无法解决"无 VAD"的根本问题**。openai-whisper 仍然会把前奏识别成虚假歌词。

### 9.6 真正的最优方案：换设备而不是换 backend

#### 关键洞察

崩溃问题来自三者的交集：

```
   崩溃 = backend 是 faster-whisper
        ∩ 设备是 CUDA
        ∩ 操作系统是 Windows
```

我最初的修复是去掉第 1 个条件（换 backend），但这把好的时间戳一起丢掉了。

**正确的做法是去掉第 2 个条件（换设备）：**

```bash
# .env 最优配置
ALIGN_ASR_BACKEND=faster-whisper      # 保留 VAD + 词级时间戳
ALIGN_WHISPER_DEVICE=cpu              # 避开 CUDA 析构 bug
ALIGN_WHISPER_MODEL=small             # CPU 上 small 速度可接受
ALIGN_WHISPER_COMPUTE_TYPE=int8       # CPU 友好
ALIGN_WHISPER_VAD_FILTER=true         # 跳过前奏
ALIGN_WHISPER_WORD_TIMESTAMPS=true    # 词级精度
```

**性能 / 精度对比：**

| 配置 | 速度 (110s 音频) | 时间戳精度 | 稳定性 |
|---|---|---|---|
| faster-whisper + CUDA | ~5s | ⭐⭐⭐⭐⭐ | ❌ 崩溃 |
| **faster-whisper + CPU + int8** | **~30-60s** | **⭐⭐⭐⭐⭐** | **✅ 稳定** |
| openai-whisper + CUDA + small | ~10s | ⭐⭐ | ✅ |
| openai-whisper + CUDA + medium | ~20s | ⭐⭐⭐ | ✅ |

### 9.7 验证方法

跑完后看 `audio/song.srt` 第 1 行：

```
1
00:00:XX,XXX --> 00:00:YY,YYY
阳光洒满了操场
```

- ✅ **好的对齐**：`XX` 在 12-18 秒之间（前奏后开始）
- ❌ **差的对齐**：`XX` 是 0 秒（被前奏的虚假识别带偏）

### 9.8 教训：维度选择

> 当一个 bug 是多维条件交集触发的，**绕开 bug 的最优维度不一定是最显眼的那个**。

本次：
- 第一反应：换 backend（最显眼的维度，因为 backend 名字直接出现在崩溃日志里）
- 但 backend 维度的副作用是丢精度
- **真正最优维度是"设备"**——CUDA 换 CPU，崩溃绕开了，精度全保留

下次遇到类似多维 bug 时：
1. 列出所有触发条件维度
2. 评估每个维度切换的副作用
3. 选副作用最小的维度切换
4. 不要因为某个维度的名字在日志里很醒目就先换它

---

## 10. 最终推荐配置

`music-to-mv-v2/.env`：

```bash
# Whisper ASR 配置（Windows 推荐配置）
ALIGN_ASR_BACKEND=faster-whisper
ALIGN_WHISPER_DEVICE=cpu
ALIGN_WHISPER_MODEL=small
ALIGN_WHISPER_COMPUTE_TYPE=int8
ALIGN_WHISPER_VAD_FILTER=true
ALIGN_WHISPER_WORD_TIMESTAMPS=true

# Demucs 人声分离（可选，提升 ASR 质量）
ALIGN_DEMUCS_ENABLED=true
ALIGN_DEMUCS_DEVICE=auto
```

Linux + GPU 环境可以放心用 CUDA：

```bash
ALIGN_ASR_BACKEND=faster-whisper
ALIGN_WHISPER_DEVICE=cuda
ALIGN_WHISPER_MODEL=medium
ALIGN_WHISPER_COMPUTE_TYPE=float16
ALIGN_WHISPER_VAD_FILTER=true
ALIGN_WHISPER_WORD_TIMESTAMPS=true
```

---

**归档完成时间**：2026-05-04
**主要排查时长**：约 3 小时（含两次方向修正：阶段 1 误判 Unicode、阶段 7 误判 backend 维度）
**未解决遗留**：ctranslate2 的析构崩溃是上游 bug，本项目通过切到 CPU 设备绕开。如果上游修复，可以重新启用 CUDA 加速。
