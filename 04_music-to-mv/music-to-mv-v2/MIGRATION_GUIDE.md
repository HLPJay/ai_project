# 📚 Token 拆分架构迁移指南

> **更新时间**: 2026-05-03  
> **版本**: v2.1  
> **主题**: MiniMax API Token 拆分（LLM vs 图片生成）

---

## 🎯 什么是 Token 拆分？

**问题现状：**
```
单一 Token (MINIMAX_TOKEN)
├─ LLM 调用 (歌词、音乐、场景分析)
└─ 图片生成 (主参考图、场景图)
问题：互相竞争额度，图片失败浪费月度套餐额度
```

**解决方案：**
```
两个独立 Token
├─ MINIMAX_TOKEN_LLM (Plus 极速版，月度)
│  └─ 歌词、音乐、场景分析
│
└─ MINIMAX_TOKEN_IMAGE (按量计费)
   └─ 图片生成
```

**优势：**
- ✅ LLM 有充足的月度额度（1500 次）
- ✅ 图片生成独立计费（可控成本）
- ✅ 互不影响，策略灵活
- ✅ 预测成本准确

---

## 📋 迁移步骤

### 步骤 1：申请新 Token

1. **保留现有的月度 Token**
   - 访问: https://www.minimaxi.com/user-center/api-keys
   - 记下你的 **Plus 极速版 Token** (用于 LLM)
   - 格式: `sk-cp-xxxxxxxxxxxxxxx`

2. **申请按量计费 Token**
   - 在同一页面，选择 "按量计费"
   - 创建新的 API Key
   - 记下这个 Token (用于图片)
   - 格式: `sk-cp-yyyyyyyyyyyyyyy`

### 步骤 2：更新 .env 配置

**方案 A：完全拆分（推荐）**

```bash
# 编辑 .env 文件，添加新的配置
cat >> .env << 'EOF'

# === MiniMax Token 拆分 ===
# LLM 专用（月度 Plus 极速版）
MINIMAX_TOKEN_LLM=sk-cp-xxxxxxxxxxxx

# 图片专用（按量计费）
MINIMAX_TOKEN_IMAGE=sk-cp-yyyyyyyyyyyy
EOF
```

**方案 B：逐步迁移（保险）**

```bash
# 保留旧 Token，添加新 Token
cat >> .env << 'EOF'

# === 新的拆分 Token ===
MINIMAX_TOKEN_LLM=sk-cp-xxxxxxxxxxxx      # 新建
MINIMAX_TOKEN_IMAGE=sk-cp-yyyyyyyyyyyy    # 新建

# 旧 Token（暂时保留，作为后备）
# MINIMAX_TOKEN=sk-cp-old_token
EOF
```

**方案 C：仅 LLM 拆分**

如果你只想拆分 LLM Token，保持图片用旧 token：

```bash
# 只添加 LLM 专用 Token
cat >> .env << 'EOF'

MINIMAX_TOKEN_LLM=sk-cp-xxxxxxxxxxxx
# MINIMAX_TOKEN 继续用于图片生成
EOF
```

### 步骤 3：验证配置

```bash
# 检查 .env 配置
grep -E "MINIMAX_TOKEN" .env

# 应该输出：
# MINIMAX_TOKEN=sk-cp-old_token (可选)
# MINIMAX_TOKEN_LLM=sk-cp-xxxxxxxxxxxx
# MINIMAX_TOKEN_IMAGE=sk-cp-yyyyyyyyyyyy
```

### 步骤 4：测试 LLM 调用（验证 LLM Token）

```bash
# 只测试提示词生成（不消耗图片 API）
python -m src.main --theme "测试主题" --test-reference prompt
```

**预期输出：**
```
✅ 成功生成提示词
📁 测试项目目录: .../测试主题_xxxxxxxx
[Step④ 主参考图 Prompt]
...
```

### 步骤 5：测试图片生成（验证图片 Token）

```bash
# 测试参考图生成（消耗 1 次图片 API 调用）
python -m src.main --theme "测试主题" --test-reference image
```

**预期输出：**
```
✅ 生成参考图成功
[OK] 68KB 图片已保存
```

### 步骤 6：生成完整 MV（端对端测试）

```bash
# 完整流程测试
python -m src.main --theme "测试主题" --mood "欢快" --auto
```

**预期进度：**
```
[Step ①] 歌词生成...        (使用 MINIMAX_TOKEN_LLM) ✅
[Step ②] 音乐生成...        (使用 MINIMAX_TOKEN_LLM) ✅
[Step ③] 对齐...            (本地处理) ✅
[Step ④] 基础描述...        (使用 MINIMAX_TOKEN_LLM) ✅
[Step ⑤-⑦] 图片生成...      (使用 MINIMAX_TOKEN_IMAGE) ✅
[Step ⑧-⑪] 视频处理...      (本地处理) ✅
```

---

## 🔄 向后兼容性

**重要：** 新的拆分架构完全向后兼容！

```python
# 配置优先级
优先级 1: MINIMAX_TOKEN_LLM     (新拆分 LLM token)
优先级 2: MINIMAX_TOKEN          (旧兼容 token) 
          ↓ 回退

优先级 1: MINIMAX_TOKEN_IMAGE    (新拆分图片 token)
优先级 2: MINIMAX_TOKEN          (旧兼容 token)
          ↓ 回退
```

**这意味着：**
- ✅ 如果你只设置 `MINIMAX_TOKEN`，系统继续工作（向后兼容）
- ✅ 如果你设置了新的拆分 Token，系统优先使用
- ✅ 可以逐步迁移，无需一次性更改所有配置

---

## 💡 使用建议

### 推荐配置方案

#### 方案 1：产品环境（成本最优）🌟

```env
# LLM：使用月度 Plus 极速版
MINIMAX_TOKEN_LLM=sk-cp-xxxxx (月度，1500 次)

# 图片：使用按量计费
MINIMAX_TOKEN_IMAGE=sk-cp-yyyyy (按量计费)
IMAGE_API_PROVIDER=minimax

# 预期月成本：
# - Plus 极速版: $99
# - 图片: 100 MV × 15张 = 1500张 × $0.02 ≈ $30-40
# 总计: ~$130-140/月
```

#### 方案 2：测试环境（成本降低）

```env
# LLM：使用月度 Plus 极速版
MINIMAX_TOKEN_LLM=sk-cp-xxxxx (月度)

# 图片：使用免费的 Pollinations
IMAGE_API_PROVIDER=pollinations

# 预期月成本：
# - Plus 极速版: $99
# 总计: $99/月 (图片免费)
```

#### 方案 3：开发环境（最低成本）

```env
# LLM：使用月度 Plus 极速版
MINIMAX_TOKEN_LLM=sk-cp-xxxxx (月度)

# 图片：使用本地 ComfyUI
IMAGE_API_PROVIDER=comfyui
IMAGE_API_URL_COMFYUI=http://127.0.0.1:8188

# 预期月成本：
# - Plus 极速版: $99
# 总计: $99/月 (图片本地)
```

---

## 📊 成本对比

```
场景: 生成 100 个完整 MV (每个 15 张图)

旧方案（混用，容易超额）：
├─ MiniMax Plus 额度消耗完后超额计费
├─ 预期月成本: $100-200+ (不可控)
└─ ❌ 问题：图片失败浪费月度额度

新方案（拆分）：
├─ LLM：Plus 极速版 $99
├─ 图片：按量计费 $30-40
├─ 总计：$130-140/月
└─ ✅ 优势：成本可控，互不影响

新方案（拆分 + Pollinations）：
├─ LLM：Plus 极速版 $99
├─ 图片：Pollinations 免费
├─ 总计：$99/月
└─ ✅ 最优：完全免费图片，仅付 LLM 费用
```

---

## 🚨 常见问题

### Q1: 我只有一个 Token，可以使用吗？

**A:** 是的！系统完全向后兼容。
```bash
# 仅设置旧 Token，系统继续工作
MINIMAX_TOKEN=sk-cp-xxxxxxxxxxxx

# 系统会自动用同一个 Token 处理 LLM 和图片
```

### Q2: 迁移会破坏现有工作吗？

**A:** 不会。所有改动都是向后兼容的。
```
✅ 现有配置继续工作
✅ 新配置优先使用
✅ 可以逐步迁移
```

### Q3: 两个 Token 可以相同吗？

**A:** 可以，但不推荐。
```bash
# 不推荐：同一个 token 两用
MINIMAX_TOKEN_LLM=sk-cp-same
MINIMAX_TOKEN_IMAGE=sk-cp-same
# 问题：没有起到拆分作用

# 推荐：使用不同的 token
MINIMAX_TOKEN_LLM=sk-cp-monthly_plan
MINIMAX_TOKEN_IMAGE=sk-cp-payasyougo
```

### Q4: 图片生成如何选择 Provider？

**A:** 根据你的需求：

```
MiniMax (按量计费)  → 质量最高，成本最低
  优点：质量好，3倍速度
  成本：$0.02/张

Pollinations (免费) → 质量好，完全免费
  优点：免费，稳定
  缺点：网络延迟
  
ComfyUI (本地)      → 完全控制，零成本
  优点：本地，自定义，零成本
  缺点：需装模型，显卡要求高
```

### Q5: 如何回滚到旧配置？

**A:** 简单。删除新 Token，系统自动降级：

```bash
# 删除这两行
# MINIMAX_TOKEN_LLM=...
# MINIMAX_TOKEN_IMAGE=...

# 系统自动使用旧的 MINIMAX_TOKEN
```

---

## 🔐 安全建议

### Token 管理最佳实践

```bash
# 1. 不要提交 .env 到 Git
echo ".env" >> .gitignore

# 2. 区分 Token 用途
MINIMAX_TOKEN_LLM=sk-cp-xxx-llm-only
MINIMAX_TOKEN_IMAGE=sk-cp-xxx-image-only

# 3. 定期轮换 Token（可选）
# 如果 Token 泄露，立即重新生成

# 4. 限制 Token 权限（在 MiniMax 控制台）
# 为每个 Token 设置最小必要权限
```

---

## 📈 迁移时间表

```
Day 1：申请新 Token + 更新配置 (30 分钟)
Day 2：验证 LLM Token (5 分钟)
Day 3：验证图片 Token (5 分钟)
Day 4：生成测试 MV (30-60 分钟)
Day 5：正式上线使用
```

---

## ✅ 迁移检查清单

- [ ] 申请 LLM Token（月度 Plus 极速版）
- [ ] 申请图片 Token（按量计费）
- [ ] 更新 .env 文件
- [ ] 验证 LLM 调用 (`--test-reference prompt`)
- [ ] 验证图片生成 (`--test-reference image`)
- [ ] 生成完整测试 MV (`--auto`)
- [ ] 检查成本明细（MiniMax 控制台）
- [ ] 备份旧 Token（以防回滚）

---

## 🆘 故障排除

### LLM Token 错误

```
错误: ValueError: MINIMAX_TOKEN_LLM 未设置
解决：
  1. 检查 .env 是否有 MINIMAX_TOKEN_LLM
  2. 检查 Token 值是否正确
  3. 运行 grep MINIMAX_TOKEN_LLM .env
```

### 图片 Token 错误

```
错误: API 返回 401 Unauthorized
解决：
  1. 检查 MINIMAX_TOKEN_IMAGE 是否设置
  2. 检查 Token 是否有效（在 MiniMax 控制台验证）
  3. 考虑切换到 Pollinations（免费备选）
```

### 混用 Token

```
问题: 不确定用的是哪个 Token
调试：
  python -c "from src.config_manager import ConfigManager; \
             cfg = ConfigManager(); \
             print(f'LLM Token: {cfg.get_llm_token()[:20]}...'); \
             print(f'Image Token: {cfg.get_image_token()[:20]}...')"
```

---

## 📞 支持

如有问题，请检查：
1. .env 配置是否正确
2. Token 是否有效（在 MiniMax 控制台验证）
3. 查看完整的 VERIFICATION_REPORT.md

---

**迁移完成后，你将享受：**
- ✅ 月度 1500 次 LLM 调用（Plus 极速版）
- ✅ 灵活的图片生成策略（按量 / 免费 / 本地）
- ✅ 可预测的成本（$99-140/月）
- ✅ 更好的稳定性（互不影响）
