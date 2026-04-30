---
title: LLM 交互核心系统 - 具体实施指南
date: 2026-04-28
---

# Music-to-MV LLM 交互系统 - 具体实施指南

## 一、快速开始（Day 1-2）

### 步骤 1.1：创建 Prompt Registry 和模板结构

```bash
# 创建目录
mkdir -p prompts/{lyrics,music,image/base_character,image/scene_image,scene_analysis}
mkdir -p lib/llm
mkdir -p tests/llm

# 创建 prompts/registry.yaml
cat > prompts/registry.yaml << 'EOF'
# Music-to-MV Prompt Registry (v1.0)
# 所有 prompt 的中心索引

prompts:
  lyrics_generation:
    description: "Generate song lyrics for music video"
    default_version: v2.0
    versions:
      v1.0:
        model: MiniMax-M2.6
        file: lyrics/v1.0.md
        status: deprecated
        avg_quality: 7.2
        created_at: 2026-01-15
      v2.0:
        model: MiniMax-M2.7
        file: lyrics/v2.0.md
        status: active
        avg_quality: 8.5
        created_at: 2026-03-10
  
  music_generation:
    description: "Generate background music based on lyrics"
    default_version: v1.2
    versions:
      v1.0:
        model: MiniMax-Music-2.6
        file: music/v1.0.md
        status: deprecated
        created_at: 2026-01-20
      v1.2:
        model: MiniMax-Music-2.6
        file: music/v1.2.md
        status: active
        created_at: 2026-03-01
  
  image_generation:
    subtypes:
      base_character:
        description: "Generate main character for the video"
        default_version: v1.5
        versions:
          v1.0:
            model: MiniMax-Image-01
            file: image/base_character/v1.0.md
            status: deprecated
          v1.5:
            model: MiniMax-Image-01
            file: image/base_character/v1.5.md
            status: active
      
      scene_image:
        description: "Generate scene background images"
        default_version: v2.0
        versions:
          v1.0:
            model: MiniMax-Image-01
            file: image/scene_image/v1.0.md
            status: deprecated
          v2.0:
            model: MiniMax-Image-01
            file: image/scene_image/v2.0.md
            status: active

  scene_analysis:
    description: "Analyze SRT and extract scene information"
    default_version: v2.0
    versions:
      v1.0:
        model: MiniMax-M2.6
        file: scene_analysis/v1.0.md
        status: deprecated
      v2.0:
        model: MiniMax-M2.7
        file: scene_analysis/v2.0.md
        status: active
EOF
```

### 步骤 1.2：编写核心 Prompt 模板

```bash
# lyrics/v2.0.md
cat > prompts/lyrics/v2.0.md << 'EOF'
# 任务：为音乐视频生成歌词

## 背景信息
- **主题**：{{ theme }}
- **画面风格**：{{ style | default('不指定') }}
- **音乐风格**：{{ music_style | default('流行') }}
- **情绪基调**：{{ mood | default('温柔') }}
- **语言**：{{ language | default('中文') }}

## 歌词要求
1. **长度**：3-4分钟（约 150-250 字）
2. **结构**：
   - **Intro**（20秒）：建立氛围
   - **Verse 1**（30秒）：主体故事
   - **Chorus**（30秒）：核心主题
   - **Verse 2**（30秒）：发展
   - **Bridge**（20秒）：转折
   - **Outro**（20秒）：收尾

3. **风格特性**（根据音乐风格调整）：
   {% if music_style == '说唱' %}
   - 强韵脚，每句 8-12 字
   - 保持节奏感
   {% elif music_style == '民谣' %}
   - 叙事性强，简朴自然
   - 重复短语创造记忆点
   {% else %}
   - 朗朗上口
   - 易于记忆
   {% endif %}

4. **视觉化关键词**：
   - 提取 3-5 个主要的视觉关键词
   - 便于后续的图像生成

## 输出格式（必须是有效的 JSON）
```json
{
  "title": "歌曲标题（中文，8 字以内）",
  "theme": "{{ theme }}",
  "lyrics": "完整歌词（用 \\n 分行）",
  "structure": {
    "intro": {
      "duration_sec": 20,
      "content": "开场歌词"
    },
    "verse1": {
      "duration_sec": 30,
      "content": "第一段歌词"
    },
    "chorus": {
      "duration_sec": 30,
      "content": "副歌"
    },
    "verse2": {
      "duration_sec": 30,
      "content": "第二段歌词"
    },
    "bridge": {
      "duration_sec": 20,
      "content": "桥段"
    },
    "outro": {
      "duration_sec": 20,
      "content": "结尾"
    }
  },
  "metadata": {
    "music_style": "{{ music_style }}",
    "mood": "{{ mood }}",
    "visual_keywords": ["关键词1", "关键词2", "关键词3"],
    "note": "创作笔记或特殊之处"
  }
}
```

## 评估标准
- ✅ 长度符合要求（150-250 字）
- ✅ JSON 格式正确，包含所有字段
- ✅ 歌词具有主题相关性
- ✅ 结构清晰、有叙事性
- ✅ 包含视觉化关键词
EOF
```

### 步骤 1.3：实现 LLMLogger 核心类

```python
# lib/llm/llm_logger.py

import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
import logging

@dataclass
class LLMCallRecord:
    """LLM 调用记录"""
    timestamp: datetime
    prompt_key: str
    prompt_version: str
    rendered_prompt: str
    model: str
    request_params: Dict
    response: str
    raw_response: str
    tokens: Dict  # {prompt_tokens, completion_tokens, total_tokens}
    latency_ms: float
    cost_usd: float
    evaluation: Optional[Dict] = None
    status: str = "success"
    error: Optional[str] = None

class LLMLogger:
    """
    LLM 日志系统（单例模式）
    
    使用方式：
        logger = LLMLogger(project_dir="/path/to/project")
        logger.record_call(record)
        stats = logger.get_stats()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, project_dir: str = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(project_dir)
        return cls._instance
    
    def _init(self, project_dir: str):
        self.project_dir = project_dir
        self.log_dir = os.path.join(project_dir, "metadata", "llm_calls")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "responses"), exist_ok=True)
        
        self.calls_file = os.path.join(self.log_dir, "calls.jsonl")
        self.errors_file = os.path.join(self.log_dir, "errors.jsonl")
        self.evals_file = os.path.join(self.log_dir, "evaluations.jsonl")
        self.stats_file = os.path.join(self.log_dir, "stats.json")
        self.versions_file = os.path.join(self.log_dir, "versions.json")
        
        self._file_lock = threading.Lock()
        
        # 初始化日志文件
        for f in [self.calls_file, self.errors_file, self.evals_file]:
            if not os.path.exists(f):
                open(f, 'a').close()
    
    def record_call(self, record: LLMCallRecord):
        """记录一次 LLM 调用（线程安全）"""
        with self._file_lock:
            # 1. 保存完整响应到单独文件
            response_file = self._save_full_response(record)
            
            # 2. 记录调用摘要到 calls.jsonl
            call_summary = {
                "timestamp": record.timestamp.isoformat(),
                "prompt_key": record.prompt_key,
                "prompt_version": record.prompt_version,
                "model": record.model,
                "request_params": record.request_params,
                "tokens": record.tokens,
                "latency_ms": record.latency_ms,
                "cost_usd": record.cost_usd,
                "status": record.status,
                "response_file": response_file,  # 完整响应的路径
                "evaluation": record.evaluation
            }
            self._append_jsonl(self.calls_file, call_summary)
            
            # 3. 如果失败，记录错误
            if record.status == "failed":
                self._append_jsonl(self.errors_file, {
                    "timestamp": record.timestamp.isoformat(),
                    "prompt_key": record.prompt_key,
                    "prompt_version": record.prompt_version,
                    "error": record.error,
                    "model": record.model
                })
            
            # 4. 记录评估结果
            if record.evaluation:
                self._append_jsonl(self.evals_file, {
                    "timestamp": record.timestamp.isoformat(),
                    "prompt_key": record.prompt_key,
                    "prompt_version": record.prompt_version,
                    "evaluation": record.evaluation
                })
            
            # 5. 更新统计信息
            self._update_stats(record)
            
            # 6. 更新版本使用记录
            self._update_versions(record)
    
    def _save_full_response(self, record: LLMCallRecord) -> str:
        """保存完整的响应内容（包括 prompt 和 response）"""
        ts = record.timestamp.isoformat().replace(":", "-")
        filename = f"{ts}__{record.prompt_key}.json"
        filepath = os.path.join(self.log_dir, "responses", filename)
        
        full_record = {
            "timestamp": record.timestamp.isoformat(),
            "prompt_key": record.prompt_key,
            "prompt_version": record.prompt_version,
            "model": record.model,
            "rendered_prompt": record.rendered_prompt,
            "request_params": record.request_params,
            "response": record.response,
            "raw_response": record.raw_response,
            "tokens": record.tokens,
            "latency_ms": record.latency_ms,
            "cost_usd": record.cost_usd
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(full_record, f, ensure_ascii=False, indent=2)
        
        return filename
    
    def _update_stats(self, record: LLMCallRecord):
        """更新汇总统计"""
        stats = self._load_json(self.stats_file) or self._init_stats()
        
        # 更新全局统计
        stats["total_calls"] += 1
        stats["total_tokens"] += record.tokens.get("total_tokens", 0)
        stats["total_cost_usd"] += record.cost_usd
        stats["updated_at"] = datetime.utcnow().isoformat()
        
        # 按 prompt_key 统计
        key = record.prompt_key
        if key not in stats["by_prompt_key"]:
            stats["by_prompt_key"][key] = {
                "call_count": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "versions_used": [],
                "success_count": 0,
                "error_count": 0,
                "avg_quality_score": 0.0
            }
        
        key_stats = stats["by_prompt_key"][key]
        key_stats["call_count"] += 1
        key_stats["total_tokens"] += record.tokens.get("total_tokens", 0)
        key_stats["total_cost_usd"] += record.cost_usd
        
        # 更新平均延迟
        n = key_stats["call_count"]
        key_stats["avg_latency_ms"] = (
            (key_stats["avg_latency_ms"] * (n - 1) + record.latency_ms) / n
        )
        
        # 更新成功/失败计数
        if record.status == "success":
            key_stats["success_count"] += 1
        else:
            key_stats["error_count"] += 1
        
        # 更新平均质量分数
        if record.evaluation and "overall_score" in record.evaluation:
            score = record.evaluation["overall_score"]
            key_stats["avg_quality_score"] = (
                (key_stats["avg_quality_score"] * (n - 1) + score) / n
            )
        
        # 记录版本使用
        if record.prompt_version not in key_stats["versions_used"]:
            key_stats["versions_used"].append(record.prompt_version)
        
        self._save_json(self.stats_file, stats)
    
    def _update_versions(self, record: LLMCallRecord):
        """更新版本使用记录"""
        versions = self._load_json(self.versions_file) or {}
        
        key = f"{record.prompt_key}:{record.prompt_version}"
        if key not in versions:
            versions[key] = {
                "prompt_key": record.prompt_key,
                "version": record.prompt_version,
                "model": record.model,
                "usage_count": 0,
                "first_used_at": record.timestamp.isoformat(),
                "last_used_at": record.timestamp.isoformat()
            }
        
        versions[key]["usage_count"] += 1
        versions[key]["last_used_at"] = record.timestamp.isoformat()
        
        self._save_json(self.versions_file, versions)
    
    def _init_stats(self) -> Dict:
        """初始化统计结构"""
        return {
            "total_calls": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "by_prompt_key": {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    def _append_jsonl(self, filepath: str, record: Dict):
        """追加 JSONL 记录"""
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    def _save_json(self, filepath: str, data: Dict):
        """保存 JSON 文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_json(self, filepath: str) -> Optional[Dict]:
        """加载 JSON 文件"""
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_stats(self) -> Dict:
        """获取当前统计信息"""
        return self._load_json(self.stats_file) or self._init_stats()
    
    def get_calls_for_key(self, prompt_key: str, limit: int = 50) -> List[Dict]:
        """获取某个 prompt_key 的最近调用"""
        calls = []
        if os.path.exists(self.calls_file):
            with open(self.calls_file, 'r', encoding='utf-8') as f:
                for line in f:
                    call = json.loads(line)
                    if call["prompt_key"] == prompt_key:
                        calls.append(call)
        return calls[-limit:]
    
    def generate_summary_report(self) -> str:
        """生成统计摘要（文本形式）"""
        stats = self.get_stats()
        
        report = f"""
╔═══════════════════════════════════════════════════════════╗
║           LLM 调用统计摘要                                   ║
╚═══════════════════════════════════════════════════════════╝

总调用次数: {stats.get('total_calls', 0)}
总 Token: {stats.get('total_tokens', 0):,}
总成本: ${stats.get('total_cost_usd', 0):.2f}

按 Prompt 类型统计:
"""
        for key, data in stats.get("by_prompt_key", {}).items():
            report += f"""
  {key}:
    - 调用次数: {data['call_count']}
    - 成功/失败: {data['success_count']}/{data['error_count']}
    - 平均延迟: {data['avg_latency_ms']:.0f}ms
    - 平均质量: {data['avg_quality_score']:.1f}/10
    - 总成本: ${data['total_cost_usd']:.2f}
"""
        
        return report
    
    def print_summary(self):
        """打印摘要到控制台"""
        print(self.generate_summary_report())
```

### 步骤 1.4：实现 PromptRegistry

```python
# lib/llm/prompt_registry.py

import os
import yaml
from typing import Dict, Optional, List
from dataclasses import dataclass

@dataclass
class PromptMetadata:
    """Prompt 元数据"""
    version: str
    model: str
    file: str
    status: str  # active / deprecated / experimental
    avg_quality: Optional[float] = None
    created_at: Optional[str] = None
    description: Optional[str] = None

class PromptRegistry:
    """
    Prompt 注册表
    
    使用方式：
        registry = PromptRegistry(registry_path="prompts/registry.yaml")
        template = registry.load_template("lyrics_generation", "v2.0")
        model = registry.get_model("lyrics_generation", "v2.0")
    """
    
    def __init__(self, registry_path: str = "prompts/registry.yaml"):
        self.registry_path = registry_path
        self.base_dir = os.path.dirname(registry_path)
        self.registry = self._load_registry()
    
    def _load_registry(self) -> Dict:
        """加载 registry.yaml"""
        with open(self.registry_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def load_template(self, prompt_key: str, version: str = None) -> str:
        """
        加载 Prompt 模板（Markdown 格式）
        
        Args:
            prompt_key: e.g., "lyrics_generation"
            version: e.g., "v2.0"，如果为 None 使用默认版本
        
        Returns:
            模板内容（字符串）
        """
        if version is None:
            version = self.get_default_version(prompt_key)
        
        meta = self.get_metadata(prompt_key, version)
        template_path = os.path.join(self.base_dir, meta.file)
        
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def get_metadata(self, prompt_key: str, version: str) -> PromptMetadata:
        """获取 Prompt 的元数据"""
        config = self.registry["prompts"]
        
        # 处理嵌套的 subtypes（如 image_generation 包含 base_character）
        if prompt_key not in config:
            raise KeyError(f"Unknown prompt key: {prompt_key}")
        
        prompt_config = config[prompt_key]
        
        # 如果有 subtypes，取第一个子类型的默认版本
        if "subtypes" in prompt_config:
            subtype_key = list(prompt_config["subtypes"].keys())[0]
            prompt_config = prompt_config["subtypes"][subtype_key]
        
        if version not in prompt_config.get("versions", {}):
            raise KeyError(f"Version {version} not found for {prompt_key}")
        
        version_config = prompt_config["versions"][version]
        
        return PromptMetadata(
            version=version,
            model=version_config.get("model"),
            file=version_config.get("file"),
            status=version_config.get("status"),
            avg_quality=version_config.get("avg_quality"),
            created_at=version_config.get("created_at"),
            description=version_config.get("description")
        )
    
    def get_default_version(self, prompt_key: str) -> str:
        """获取默认版本"""
        config = self.registry["prompts"][prompt_key]
        return config.get("default_version", "v1.0")
    
    def get_model(self, prompt_key: str, version: str = None) -> str:
        """获取该版本使用的模型"""
        meta = self.get_metadata(prompt_key, version or self.get_default_version(prompt_key))
        return meta.model
    
    def get_all_versions(self, prompt_key: str) -> List[str]:
        """获取某个 prompt_key 的所有版本"""
        config = self.registry["prompts"][prompt_key]
        if "subtypes" in config:
            # 如果有 subtypes，返回第一个的版本
            subtype_key = list(config["subtypes"].keys())[0]
            config = config["subtypes"][subtype_key]
        
        return list(config.get("versions", {}).keys())
    
    def update_metric(self, prompt_key: str, version: str, metric_name: str, value: float):
        """更新版本的质量指标"""
        config = self.registry["prompts"][prompt_key]
        if "subtypes" in config:
            subtype_key = list(config["subtypes"].keys())[0]
            config = config["subtypes"][subtype_key]
        
        config["versions"][version][metric_name] = value
        
        # 保存回文件
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.registry, f, allow_unicode=True)
```

---

## 二、与现有代码的集成点（Day 3-4）

### 2.1：改造 LLMClient 调用处

**当前流程（generate_lyrics.sh）：**
```bash
curl -X POST https://api.minimaxi.com/v1/lyrics_generation \
  -H "Authorization: Bearer $MINIMAX_TOKEN" \
  -d '{"theme":"...", ...}'
```

**新流程：**
```python
# scripts/generate_lyrics.py (新)

from lib.llm.llm_client import LLMClient
from lib.llm.llm_logger import LLMLogger
import json

def main(project_dir, theme, style, music_style, mood, language):
    logger = LLMLogger(project_dir)
    client = LLMClient(logger=logger)
    
    context = {
        "theme": theme,
        "style": style,
        "music_style": music_style,
        "mood": mood,
        "language": language
    }
    
    response = client.generate(
        prompt_key="lyrics_generation",
        context=context,
        temperature=0.85,
        max_tokens=2048
    )
    
    # 保存结果
    with open(f"{project_dir}/audio/lyrics.txt", 'w', encoding='utf-8') as f:
        f.write(response.content)
    
    # logger 已自动记录了所有细节
    # 无需手动调用 logger.record_call()
```

### 2.2：改造 status 更新

**当前做法：**
```bash
python3 -c "
import json
with open('info.json') as f: d = json.load(f)
d['pipeline']['lyrics'] = 'completed'
with open('info.json', 'w') as f: json.dump(d, f)
"
```

**新做法：**
```python
from lib.project_manager import ProjectManager

pm = ProjectManager(project_dir)
pm.update_step("① lyrics", "completed", detail="quality=8.5")
```

---

## 三、关键的 Prompt 模板示例

### 3.1：scene_analysis/v2.0.md（场景分析提示词）

```markdown
# 任务：从歌词 SRT 提取视觉场景和关键词

## 输入
歌词内容：
{{ lyrics }}

## 任务描述
1. 将歌词分成 8-12 个视觉场景
2. 每个场景对应 SRT 中的时间段
3. 生成每个场景的英文视觉描述（用于 AI 图像生成）
4. 标记重复或相似的场景（便于生成变体图）

## 输出格式（严格遵循 JSON）
```json
{
  "scenes": [
    {
      "scene_id": 0,
      "start_time": "00:00:00",
      "end_time": "00:00:20",
      "duration_sec": 20,
      "lyrics_snippet": "开场歌词",
      "label": "开场晨光",
      "description": "早晨的山区，第一缕阳光照亮山峰，雾气缭绕，cinematographic quality, warm color grading",
      "visual_keywords": ["晨光", "山峰", "雾气"],
      "is_repeated": false,
      "emotion": "希望"
    },
    ...
  ],
  "repeated_segments": [
    {
      "segment_name": "副歌",
      "first_occurrence_id": 2,
      "other_occurrences": [5, 8],
      "should_generate_variants": true
    }
  ]
}
```

## 评估标准
- ✅ 场景数量 8-12
- ✅ 每个场景都有英文描述
- ✅ 时间戳准确
- ✅ JSON 格式正确
```

---

## 四、测试清单（Day 5）

### 4.1：单元测试

```python
# tests/llm/test_llm_logger.py

import unittest
import tempfile
import json
from datetime import datetime
from lib.llm.llm_logger import LLMLogger, LLMCallRecord

class TestLLMLogger(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.logger = LLMLogger(self.temp_dir)
    
    def test_record_call(self):
        """测试记录调用"""
        record = LLMCallRecord(
            timestamp=datetime.utcnow(),
            prompt_key="lyrics_generation",
            prompt_version="v2.0",
            rendered_prompt="你好",
            model="MiniMax-M2.7",
            request_params={},
            response='{"title": "test"}',
            raw_response='{"title": "test"}',
            tokens={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            latency_ms=1000,
            cost_usd=0.01
        )
        
        self.logger.record_call(record)
        stats = self.logger.get_stats()
        
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["total_tokens"], 30)
    
    def test_stats_aggregation(self):
        """测试统计聚合"""
        for i in range(5):
            record = LLMCallRecord(
                timestamp=datetime.utcnow(),
                prompt_key="lyrics_generation",
                prompt_version="v2.0",
                rendered_prompt=f"prompt_{i}",
                model="MiniMax-M2.7",
                request_params={},
                response='{"title": "test"}',
                raw_response='',
                tokens={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                latency_ms=1000 + i*100,
                cost_usd=0.01
            )
            self.logger.record_call(record)
        
        stats = self.logger.get_stats()
        key_stats = stats["by_prompt_key"]["lyrics_generation"]
        
        self.assertEqual(key_stats["call_count"], 5)
        self.assertEqual(key_stats["total_tokens"], 150)
        self.assertTrue(1000 < key_stats["avg_latency_ms"] < 1400)

if __name__ == '__main__':
    unittest.main()
```

### 4.2：集成测试

```bash
#!/bin/bash
# tests/integration/test_lyrics_flow.sh

set -e

PROJECT_DIR=$(mktemp -d)
echo "Testing lyrics generation in $PROJECT_DIR"

# 初始化项目
python3 -c "
from lib.project_manager import ProjectManager
pm = ProjectManager.init_new('测试主题', '$PROJECT_DIR')
"

# 运行生成
python3 scripts/generate_lyrics.py \
  --project-dir "$PROJECT_DIR" \
  --theme "春天" \
  --style "动漫风" \
  --music-style "流行" \
  --mood "温柔"

# 验证输出
if [ ! -f "$PROJECT_DIR/audio/lyrics.txt" ]; then
  echo "❌ 歌词文件生成失败"
  exit 1
fi

# 验证日志
if [ ! -f "$PROJECT_DIR/metadata/llm_calls/calls.jsonl" ]; then
  echo "❌ 日志文件生成失败"
  exit 1
fi

# 检查统计
python3 -c "
from lib.llm.llm_logger import LLMLogger
logger = LLMLogger('$PROJECT_DIR')
stats = logger.get_stats()
assert stats['total_calls'] > 0, '没有记录调用'
assert stats['total_cost_usd'] > 0, '成本未记录'
print('✅ 集成测试通过')
"

rm -rf "$PROJECT_DIR"
```

---

## 五、成功验收标准

| 里程碑 | 验收条件 |
|--------|---------|
| **Day 2 结束** | ✅ 所有 Prompt 模板编写完成，registry.yaml 可用 |
| **Day 3 结束** | ✅ LLMLogger 可以记录、查询、聚合调用数据 |
| **Day 4 结束** | ✅ PromptRegistry 能加载模板并渲染 |
| **Day 5 结束** | ✅ 所有单元测试通过，集成测试通过 |
| **Week 2** | ✅ 在真实流程中测试 5 个完整的 MV 生成，日志完整 |

---

## 常见问题

### Q: 为什么要单独保存完整响应？

**A:** 因为：
1. 调试时需要看完整的 response 内容
2. 评估质量需要深入分析
3. 但 calls.jsonl 只记录摘要，保持文件体积小
4. 完整响应存到 responses/ 目录，便于搜索

### Q: Token 计数怎么实现？

**A:** 
```python
def count_tokens(model, prompt, response):
    # 使用 tiktoken（OpenAI）或 MiniMax 提供的 API
    # 简单实现：word_count * 1.3（中文）
    return len(prompt.split()) * 1.3 + len(response.split()) * 1.3
```

### Q: 如何追踪 Prompt 版本变动对质量的影响？

**A:** 
1. 每个版本都记录了使用次数和平均质量
2. 用 PromptAnalyzer 对比版本性能
3. 生成对比报告，展示质量和成本的权衡

