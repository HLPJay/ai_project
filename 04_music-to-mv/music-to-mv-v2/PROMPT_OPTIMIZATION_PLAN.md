# 📋 Prompt 优化计划 - P1 + P2 批次

> 继Quick Wins A/B/C (已完成 +20-35%) 之后的第一批核心优化  
> **预期收益**: +30-40% | **预计时间**: 8-10 小时

---

## 📦 P1 优化（4 小时，+15-20%）

### P1.1: 场景描述上下文感知 (Scene Context Injection)
**文件**: `src/scene_analyzer.py` → `_generate_local_desc()`  
**问题**: 场景描述生成时没有考虑前后场景的连贯性，导致转场突兀  
**优化**: 在生成场景描述时注入前一个场景的视觉信息和后一个场景的预期视觉信息

**代码位置**: 第 1100-1150 行  
**实现步骤**:
1. 修改 `_generate_local_desc(scene, prev_scene=None, next_scene=None)` 签名
2. 如果存在 prev_scene，注入 "transitioning from [prev_visual]"
3. 如果存在 next_scene，注入 "leading to [next_visual]"
4. 调用位置增加前后场景参数

**期望结果**: 场景转场更流畅，视觉连贯性 +15-20%

---

### P1.2: 角色一致性增强 (Character Consistency Anchor)
**文件**: `src/style_map.py` → `build_char_prompt()`  
**问题**: 当前角色描述是静态的，不考虑场景情感或场景类型  
**优化**: 根据场景的 `visual_focus` 和 `narrative_phase` 调整角色描述中的行为和表情

**代码位置**: 第 668-700 行  
**实现步骤**:
1. 修改 `build_char_prompt(char_name, visual_focus=None, emotion=None)` 
2. 如果 visual_focus == "character"，强调面部表情细节
3. 如果 narrative_phase == "chorus_peak"，注入能量/运动描述
4. 如果 emotion 是悲伤，注入身体语言线索

**期望结果**: 角色行为更符合场景情感，连贯性 +10-15%

---

### P1.3: 视觉平衡约束 (Visual Balance Constraints)
**文件**: `src/scene_generator.py` → `_build_scene_prompt()`  
**问题**: Prompt 没有约束图片的视觉平衡（主体位置、前景背景比例）  
**优化**: 根据前一个场景的构图添加平衡约束

**代码位置**: 第 1470-1490 行  
**实现步骤**:
1. 跟踪前一场景的主体位置（left/center/right）
2. 如果前一场景是中心构图，当前场景倾向非中心
3. 注入约束: "avoid centering the subject identically to the last frame"
4. 添加光影平衡约束

**期望结果**: 画面流畅感提升，避免重复构图，+8-12%

---

## 📦 P2 优化（4-6 小时，+15-20%）

### P2.1: 情感弧线映射 (Emotional Arc Mapping)
**文件**: `src/scene_analyzer.py` → 新增 `_map_emotion_to_visual()`  
**问题**: 场景描述没有直接映射歌词的情感强度  
**优化**: 基于歌词情感强度（1-10 分）生成相应的视觉强度描述

**代码位置**: 新增方法，在 `analyze()` 中调用  
**实现步骤**:
1. 从歌词提取情感强度（高兴/伤心/愤怒等）
2. 映射到视觉属性：
   - 高情感 → 高对比度、鲜艳色彩、动态构图
   - 低情感 → 柔和、单调色、静态构图
3. 在场景描述中注入情感强度指示

**期望结果**: 视觉与情感对齐，观众投入感 +12-18%

---

### P2.2: 颜色调色板动态注入 (Dynamic Palette Injection)
**文件**: `src/scene_generator.py` + `src/scene_analyzer.py`  
**问题**: Visual Bible 的调色板是全局固定的，不随情感弧线变化  
**优化**: 根据场景的情感弧线动态调整调色板

**代码位置**: `_build_scene_prompt()` 中的颜色注入部分  
**实现步骤**:
1. 在 visual_bible 中增加 `emotional_palette_range`
2. 根据当前场景的情感强度，在调色板范围内选择
3. 注入约束: "lean towards [warm/cool] tones based on emotional intensity"
4. 避免连续场景的颜色跳跃

**期望结果**: 调色板与叙事匹配，视觉统一性 +12-15%

---

### P2.3: 镜头焦点清晰化 (Focus Clarity Enhancement)
**文件**: `src/scene_generator.py` → `_build_scene_prompt()`  
**问题**: Prompt 中焦点范围模糊，导致 AI 生成分散的画面  
**优化**: 明确指定主焦点、焦点距离、背景清晰度

**代码位置**: 第 1470-1490 行的 do_not_do 列表附近  
**实现步骤**:
1. 根据 `shot_type` 添加焦点约束：
   - close_detail: "sharp focus on [subject], blurred background"
   - establishing: "deep focus from foreground to far background"
   - empty_space: "soft focus, no single focal point"
2. 生成焦点深度指示
3. 约束 DOF (景深)

**期望结果**: 画面主体清晰，引导性更强，+10-15%

---

## 🎯 实现优先级

```
立即开始 → P1.1 (Scene Context) → P1.2 (Character) → P1.3 (Balance)
        ↓
      P2.1 (Emotion Arc) → P2.2 (Palette) → P2.3 (Focus)
```

**并行机会**:
- P1.1 和 P1.2 可独立实现（不同文件）
- P2.1 必须在 P1 之后（依赖情感数据）

---

## ✅ 验收标准

### P1 验收
- [ ] 场景描述包含前后场景转场提示
- [ ] 角色描述根据 visual_focus 变化
- [ ] 构图约束动态应用（不重复前一构图）
- [ ] 生成 3 个测试 MV，验证转场流畅性

### P2 验收
- [ ] 情感强度映射到视觉属性
- [ ] 调色板随情感弧线变化
- [ ] 焦点约束清晰、生效
- [ ] 生成 3 个测试 MV，验证整体视觉连贯

---

## 📈 预期收益总结

| 优化项 | 预期收益 | 实现难度 | 耗时 |
|-------|---------|--------|------|
| Quick Wins A/B/C | +20-35% | 低 | 2-3h |
| P1.1 Scene Context | +8-12% | 中 | 1.5h |
| P1.2 Character | +10-15% | 中 | 1.5h |
| P1.3 Balance | +8-12% | 低 | 1h |
| **P1 小计** | **+15-20%** | - | **4h** |
| P2.1 Emotion Arc | +12-18% | 中 | 2h |
| P2.2 Palette | +12-15% | 中 | 1.5h |
| P2.3 Focus | +10-15% | 低 | 1h |
| **P2 小计** | **+15-20%** | - | **4.5h** |
| **总计** | **+50-75%** | - | **10.5h** |

---

## 📝 分支管理

```
feat/prompt-p1-context      → 实现 P1.1 + P1.2 + P1.3
feat/prompt-p2-emotional    → 实现 P2.1 + P2.2 + P2.3
```

各自完成后 PR 到 `dev` 分支进行集成测试。
