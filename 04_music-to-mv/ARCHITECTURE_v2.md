---
title: Music-to-MV 架构优化 v2.0
subtitle: 以 LLM 交互为核心的完整重设计
date: 2026-04-28
---

# Music-to-MV 架构优化计划 v2.0
## 以 LLM 交互为核心的系统重设计

---

## 核心认知

**这不是一个视频生成系统，而是一个 LLM 驱动的创意系统。**

- 歌词质量取决于 `lyrics_prompt` 的精妙度
- 音乐质量取决于 `music_prompt` 的完整性  
- 画面质量取决于 `image_prompt` 的准确度
- 场景分析质量取决于 `scene_description_prompt` 的理解力

**因此，整个架构必须以"LLM交互"为核心，其他组件都是为它服务。**

---

## 新的三层架构（LLM-First Design）

```
┌──────────────────────────────────────────────────────────────┐
│                     LLM 交互层（核心）                         │
├──────────────────────────────────────────────────────────────┤
│ Prompt 管理系统                                               │
│  ├─ PromptRegistry（提示词注册表）                            │
│  ├─ PromptTemplate（模板引擎，支持变量填充）                  │
│  ├─ PromptVersion（版本控制）                                 │
│  └─ PromptEvaluation（性能评估）                              │
├─────────────────────────────────────────────────────────────┤
│ LLM 调用层                                                    │
│  ├─ LLMClient（统一的 API 客户端）                            │
│  │  ├─ MiniMaxClient（主力）                                  │
│  │  ├─ OpenAIClient（备选）                                   │
│  │  └─ FallbackStrategy（降级策略）                            │
│  ├─ RequestBuilder（构建请求）                               │
│  ├─ ResponseValidator（验证响应）                            │
│  └─ TokenCounter（Token 消耗统计）                            │
├─────────────────────────────────────────────────────────────┤
│ LLM 日志与可观测性                                            │
│  ├─ LLMLogger（核心日志系统）                                 │
│  ├─ PromptAnalyzer（提示词分析）                              │
│  ├─ ResponseAnalyzer（响应分析）                              │
│  ├─ LLMMetrics（性能指标）                                    │
│  └─ LLMReportGenerator（HTML 报告生成）                       │
├──────────────────────────────────────────────────────────────┤
│                    编排与恢复层                                │
├──────────────────────────────────────────────────────────────┤
│ MVPipeline（编排）  /  UserInteraction（交互）                │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                    底座层                                      │
├──────────────────────────────────────────────────────────────┤
│ ProjectManager / ConfigManager / FileService                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 第一部分：Prompt 管理系统设计

### 1.1 PromptRegistry 提示词注册表

**职责**：集中管理所有 Prompt 模板，支持版本控制、A/B测试、性能评估。

**存储结构**：

```
prompts/
├── registry.yaml          # 所有 prompt 元信息索引
├── lyrics/
│   ├── v1.0.md           # 初版（基础提示词）
│   ├── v1.1.md           # 改进版（加强叙事）
│   ├── v2.0.md           # 重大升级（支持音乐风格）
│   └── metrics.json      # 各版本的质量指标
├── music/
│   ├── v1.0.md
│   └── metrics.json
├── image/
│   ├── base_character/
│   │   ├── v1.0.md
│   │   └── metrics.json
│   ├── scene_image/
│   │   ├── v1.0.md
│   │   └── metrics.json
│   └── variants/
│       └── v1.0.md
└── scene_analysis/
    ├── v1.0.md
    └── metrics.json
```

**registry.yaml 格式**：

```yaml
prompts:
  lyrics_generation:
    default_version: v2.0
    versions:
      v1.0:
        model: MiniMax-M2.6
        description: "Basic lyrics prompt"
        created_at: 2026-01-15
        avg_length: 320
        avg_quality_score: 7.2  # 用户评分
        status: deprecated
      v2.0:
        model: MiniMax-M2.7
        description: "Enhanced with music style conditioning"
        created_at: 2026-03-10
        avg_length: 340
        avg_quality_score: 8.5
        status: active
    
  music_generation:
    default_version: v1.2
    versions:
      v1.0:
        model: MiniMax-Music-2.6
        description: "Basic music"
        status: deprecated
      v1.2:
        model: MiniMax-Music-2.6
        description: "With instrument hints"
        status: active

  image_generation:
    default_version: v2.0
    subtypes:
      base_character:
        default_version: v1.5
        versions:
          v1.0:
            model: MiniMax-Image-01
            description: "Character generation"
            status: deprecated
          v1.5:
            model: MiniMax-Image-01
            description: "With style+mood conditioning"
            status: active
      
      scene_image:
        default_version: v2.0
        versions:
          v1.0:
            model: MiniMax-Image-01
            description: "Scene generation"
            status: deprecated
          v2.0:
            model: MiniMax-Image-01
            description: "Multi-scale Ken Burns friendly"
            status: active

  scene_analysis:
    default_version: v2.0
    versions:
      v1.0:
        model: MiniMax-M2.6
        description: "Basic SRT parsing"
        status: deprecated
      v2.0:
        model: MiniMax-M2.7
        description: "Rich metadata extraction (scenes, variants, emotions)"
        status: active
```

### 1.2 PromptTemplate 模板引擎

**职责**：支持变量填充、条件渲染、部分提示词复用。

```python
class PromptTemplate:
    """
    支持 Jinja2 模板语法的提示词引擎
    """
    
    def __init__(self, template_path: str, registry: PromptRegistry):
        self.template_path = template_path
        self.registry = registry
        self.template = self._load_template()
        self.variables = self._extract_variables()
    
    def render(self, context: Dict[str, Any]) -> str:
        """
        渲染提示词
        
        context 包含：
          - theme: 主题（必填）
          - style: 画面风格（可选）
          - music_style: 音乐风格（可选）
          - mood: 情绪基调（可选）
          - language: 语言（可选）
          - custom_params: 其他参数
        """
        missing = set(self.variables) - set(context.keys())
        if missing:
            raise ValueError(f"Missing variables: {missing}")
        
        # 使用 Jinja2 渲染
        from jinja2 import Template
        t = Template(self.template)
        return t.render(context)
    
    def render_with_defaults(self, context: Dict, use_version: str = None):
        """使用默认值和指定版本"""
        version = use_version or self._get_default_version()
        template = self.registry.load_version(self.template_path, version)
        t = Template(template)
        # 合并默认值
        full_context = self._get_default_context() | context
        return t.render(full_context)
```

**Prompt 模板示例（lyrics/v2.0.md）**：

```markdown
# 任务：生成音乐视频歌词

## 背景
- 主题：{{ theme }}
- 情绪基调：{{ mood | default('温柔') }}
- 音乐风格：{{ music_style | default('流行') }}
- 语言：{{ language | default('中文') }}

## 要求
1. **长度**：3-4分钟的歌词（约180-240字）
2. **结构**：
   - Intro（20秒）：建立氛围，引入主题
   - Verse 1-2（各30秒）：讲述故事/阐述主题
   - Chorus（30秒）：核心主题，易记住
   - Bridge（20秒）：转折或升华
   - Outro（20秒）：收尾，回呼开头

3. **特殊要求**：
   {% if music_style == '说唱' %}
   - 保持韵脚，节奏感强
   - 每句8-12字
   {% elif music_style == '民谣' %}
   - 叙事性强，简朴自然
   - 重复短语创造记忆点
   {% endif %}
   
4. **输出格式**：
   JSON 格式，包含以下字段：
   ```json
   {
     "title": "歌曲标题",
     "theme": "{{ theme }}",
     "lyrics": "完整歌词（\n分行）",
     "structure": {
       "intro": { "duration": 20, "lyrics": "..." },
       "verse1": { "duration": 30, "lyrics": "..." },
       ...
     },
     "metadata": {
       "style": "{{ music_style }}",
       "mood": "{{ mood }}",
       "visual_keywords": ["关键词1", "关键词2", ...]
     }
   }
   ```
```

### 1.3 PromptVersion 版本控制

```python
class PromptVersion:
    """Prompt 版本管理，支持 Git 风格的历史"""
    
    @dataclass
    class VersionMetadata:
        version: str              # e.g., "v2.0"
        model: str               # e.g., "MiniMax-M2.7"
        created_at: datetime
        updated_at: datetime
        created_by: str          # 谁创建的（for audit trail）
        description: str
        status: str              # active / deprecated / experimental
        parent_version: Optional[str]  # 继承自哪个版本
        
        # 质量评分
        avg_quality_score: float
        avg_response_quality: float  # 1-10
        avg_relevance: float         # 1-10
        sample_size: int
        
        # 成本评分
        avg_tokens: int
        avg_latency_ms: int
    
    def get_diff(self, other_version: str) -> str:
        """对比两个版本的差异"""
        v1 = self._load_content(self.version)
        v2 = self._load_content(other_version)
        return unified_diff(v1, v2)
    
    def get_performance_delta(self, other_version: str) -> Dict:
        """对比两个版本的性能差异"""
        meta1 = self.registry.get_metadata(self.version)
        meta2 = self.registry.get_metadata(other_version)
        
        return {
            "quality_delta": meta1.avg_quality_score - meta2.avg_quality_score,
            "token_delta": meta1.avg_tokens - meta2.avg_tokens,
            "latency_delta_ms": meta1.avg_latency_ms - meta2.avg_latency_ms,
            "cost_improvement": (meta1.avg_tokens - meta2.avg_tokens) / meta2.avg_tokens * 100
        }
```

### 1.4 PromptEvaluation 性能评估

```python
class PromptEvaluation:
    """评估 Prompt 的输出质量和成本效益"""
    
    def evaluate_output(self, 
                       prompt_version: str,
                       response: str,
                       ground_truth: Optional[str] = None) -> EvaluationScore:
        """
        评估单次 LLM 输出的质量
        
        指标：
        1. 相关性（Relevance）：输出是否符合要求
        2. 完整性（Completeness）：是否包含所有必需信息
        3. 创意性（Creativity）：是否新颖、有趣
        4. 可用性（Usability）：下游系统是否能处理
        """
        
        metrics = {
            "relevance": self._score_relevance(prompt_version, response),
            "completeness": self._score_completeness(response, prompt_version),
            "creativity": self._score_creativity(response),
            "usability": self._score_usability(response, prompt_version),
            "format_validity": self._check_format_valid(response, prompt_version)
        }
        
        overall_score = weighted_mean(metrics, weights={
            "relevance": 0.3,
            "completeness": 0.25,
            "creativity": 0.2,
            "usability": 0.2,
            "format_validity": 0.05
        })
        
        return EvaluationScore(
            version=prompt_version,
            metrics=metrics,
            overall_score=overall_score,
            timestamp=datetime.utcnow()
        )
    
    def aggregate_performance(self, prompt_version: str, sample_size: int = 50) -> Dict:
        """
        聚合一个 prompt 版本的整体性能
        基于最近 sample_size 次调用的平均值
        """
        recent_evals = self.logger.get_evals_for_version(prompt_version, limit=sample_size)
        
        return {
            "avg_quality": mean([e.overall_score for e in recent_evals]),
            "avg_relevance": mean([e.metrics["relevance"] for e in recent_evals]),
            "p95_relevance": percentile([e.metrics["relevance"] for e in recent_evals], 95),
            "failure_rate": sum(1 for e in recent_evals if e.overall_score < 5) / len(recent_evals),
            "std_dev": stdev([e.overall_score for e in recent_evals])
        }
```

---

## 第二部分：LLM 调用层设计

### 2.1 LLMClient 统一客户端

```python
class LLMClient:
    """统一的 LLM 客户端，支持多个后端（MiniMax, OpenAI等）"""
    
    def __init__(self, provider: str = "minimax", logger: LLMLogger = None):
        self.provider = provider
        self.logger = logger or LLMLogger()
        self.client = self._init_client()
        self.request_builder = RequestBuilder()
        self.response_validator = ResponseValidator()
        self.token_counter = TokenCounter()
    
    def generate(self, 
                prompt_key: str,           # e.g., "lyrics_generation"
                context: Dict,             # 模板变量
                model_override: str = None,
                max_tokens: int = 2048,
                temperature: float = 0.8,
                evaluation_ground_truth: str = None) -> LLMResponse:
        """
        核心生成方法，带完整日志
        
        流程：
        1. 从 registry 加载 prompt 模板（版本）
        2. 渲染模板（填充变量）
        3. 构建请求
        4. 调用 LLM
        5. 验证响应
        6. 评估质量
        7. 记录完整日志（包含成本）
        8. 更新版本指标
        """
        
        # 步骤 1: 加载 Prompt 版本
        prompt_version = self.prompt_registry.get_default_version(prompt_key)
        prompt_template = self.prompt_registry.load_template(prompt_key, prompt_version)
        
        # 步骤 2: 渲染
        rendered_prompt = prompt_template.render(context)
        
        # 步骤 3: 构建请求
        request = self.request_builder.build(
            prompt=rendered_prompt,
            model=model_override or self.prompt_registry.get_model(prompt_key, prompt_version),
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        start_time = time.time()
        
        # 步骤 4: 调用 LLM（带重试）
        try:
            raw_response = self._call_with_retry(request, retries=3)
            latency_ms = (time.time() - start_time) * 1000
        except Exception as e:
            self.logger.log_error(
                prompt_key=prompt_key,
                error=str(e),
                prompt_version=prompt_version
            )
            raise
        
        # 步骤 5: 验证响应
        try:
            validated = self.response_validator.validate(raw_response, prompt_key)
        except ValidationError as e:
            self.logger.log_validation_error(
                prompt_key=prompt_key,
                error=str(e),
                response=raw_response
            )
            raise
        
        # 步骤 6: 评估质量
        evaluation = PromptEvaluation().evaluate_output(
            prompt_version=prompt_version,
            response=validated.content,
            ground_truth=evaluation_ground_truth
        )
        
        # 步骤 7: 计算成本
        tokens_used = self.token_counter.count_tokens(
            prompt=rendered_prompt,
            response=validated.content,
            model=request.model
        )
        cost = self._calculate_cost(tokens_used, request.model)
        
        # 步骤 8: 记录完整日志
        llm_record = LLMCallRecord(
            timestamp=datetime.utcnow(),
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            rendered_prompt=rendered_prompt,
            model=request.model,
            request_params={
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            response=validated.content,
            raw_response=raw_response,  # 用于调试
            tokens={
                "prompt_tokens": tokens_used.prompt,
                "completion_tokens": tokens_used.completion,
                "total_tokens": tokens_used.total
            },
            latency_ms=latency_ms,
            cost_usd=cost,
            evaluation=evaluation,
            status="success"
        )
        
        self.logger.record_call(llm_record)
        
        # 步骤 9: 更新版本指标
        self.prompt_registry.update_metrics(prompt_version, evaluation)
        
        return LLMResponse(
            content=validated.content,
            metadata=llm_record,
            evaluation=evaluation
        )
    
    def _call_with_retry(self, request, retries=3):
        """指数退避重试"""
        for attempt in range(retries):
            try:
                return self.client.complete(request)
            except (RateLimitError, TimeoutError) as e:
                if attempt == retries - 1:
                    raise
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                self.logger.log_retry(
                    attempt=attempt,
                    wait_time=wait_time,
                    error=str(e)
                )
                time.sleep(wait_time)
```

### 2.2 RequestBuilder 请求构建

```python
class RequestBuilder:
    """构建标准化的 LLM 请求"""
    
    def build(self, 
             prompt: str,
             model: str,
             max_tokens: int,
             temperature: float,
             system_prompt: str = None) -> LLMRequest:
        """
        构建请求，同时进行合理性检查
        """
        
        # 检查 prompt 长度
        prompt_len = len(prompt.split())
        if prompt_len > 2000:
            warnings.warn(f"Prompt very long: {prompt_len} words")
        
        # 检查 temperature 合理性
        if temperature < 0 or temperature > 2:
            raise ValueError(f"Invalid temperature: {temperature}")
        
        request = LLMRequest(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or self._get_default_system_prompt(model)
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.95,  # 标准值
            frequency_penalty=0.0,
            presence_penalty=0.0,
            response_format={"type": "json_object"}  # 强制 JSON 格式
        )
        
        return request
    
    def _get_default_system_prompt(self, model: str) -> str:
        """针对不同模型的默认系统提示"""
        if "MiniMax" in model:
            return (
                "你是一个创意音乐视频内容生成助手。"
                "你的任务是生成高质量、富有创意、视觉化程度高的内容。"
                "所有输出必须是有效的 JSON 格式。"
            )
        return "You are a helpful assistant."
```

### 2.3 ResponseValidator 响应验证

```python
class ResponseValidator:
    """验证 LLM 响应的完整性和格式"""
    
    def validate(self, response: str, prompt_key: str) -> ValidatedResponse:
        """
        验证响应
        
        检查项：
        1. 格式（JSON / Plain text）
        2. 必需字段
        3. 字段类型
        4. 值的合理范围
        """
        
        # 步骤 1: 尝试解析 JSON
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            raise ValidationError(f"Invalid JSON: {response[:100]}")
        
        # 步骤 2: 检查必需字段
        required_fields = self._get_required_fields(prompt_key)
        missing = set(required_fields) - set(parsed.keys())
        if missing:
            raise ValidationError(f"Missing fields: {missing}")
        
        # 步骤 3: 检查字段类型
        type_checks = self._get_type_schema(prompt_key)
        for field, expected_type in type_checks.items():
            if field in parsed:
                if not isinstance(parsed[field], expected_type):
                    raise ValidationError(
                        f"Field '{field}' has wrong type: "
                        f"expected {expected_type}, got {type(parsed[field])}"
                    )
        
        # 步骤 4: 检查值的合理性
        self._validate_values(parsed, prompt_key)
        
        return ValidatedResponse(
            content=response,
            parsed=parsed,
            valid=True
        )
    
    def _validate_values(self, parsed: Dict, prompt_key: str):
        """业务逻辑级别的验证"""
        if prompt_key == "lyrics_generation":
            # 歌词长度检查
            lyrics = parsed.get("lyrics", "")
            word_count = len(lyrics.split())
            if word_count < 100:
                raise ValidationError(f"Lyrics too short: {word_count} words")
            if word_count > 500:
                raise ValidationError(f"Lyrics too long: {word_count} words")
        
        elif prompt_key == "scene_analysis":
            # 场景数量检查
            scenes = parsed.get("scenes", [])
            if len(scenes) < 5:
                raise ValidationError(f"Too few scenes: {len(scenes)}")
            if len(scenes) > 30:
                raise ValidationError(f"Too many scenes: {len(scenes)}")
```

---

## 第三部分：LLM 日志与可观测性设计

### 3.1 LLMLogger 核心日志系统

```python
class LLMLogger:
    """
    单例日志系统，记录所有 LLM 交互
    
    存储结构：
    - metadata/llm_calls/
      ├── calls.jsonl           # 所有调用记录（流式追加）
      ├── stats.json           # 汇总统计
      ├── prompt_versions.json # 使用过的 prompt 版本
      ├── errors.jsonl         # 失败记录
      ├── evaluations.jsonl    # 质量评估
      └── reports/
          ├── daily_2026-04-28.html
          └── final_report.html
    """
    
    _instance = None
    
    def __new__(cls, project_dir: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init(project_dir)
        return cls._instance
    
    def _init(self, project_dir: str):
        self.project_dir = project_dir
        self.log_dir = f"{project_dir}/metadata/llm_calls"
        os.makedirs(self.log_dir, exist_ok=True)
        
        self.calls_file = f"{self.log_dir}/calls.jsonl"
        self.errors_file = f"{self.log_dir}/errors.jsonl"
        self.evals_file = f"{self.log_dir}/evaluations.jsonl"
        self.stats_file = f"{self.log_dir}/stats.json"
        
        self._lock = threading.Lock()
    
    def record_call(self, record: LLMCallRecord):
        """记录一次 LLM 调用（线程安全）"""
        with self._lock:
            # 写入原始调用记录
            self._append_jsonl(self.calls_file, {
                "timestamp": record.timestamp.isoformat(),
                "prompt_key": record.prompt_key,
                "prompt_version": record.prompt_version,
                "model": record.model,
                "rendered_prompt": record.rendered_prompt,
                "request_params": record.request_params,
                "response_snippet": record.response[:500],  # 只记录前 500 字
                "full_response_path": self._save_full_response(record),  # 完整响应存到单独文件
                "tokens": record.tokens,
                "latency_ms": record.latency_ms,
                "cost_usd": record.cost_usd,
                "status": record.status
            })
            
            # 写入评估结果
            if record.evaluation:
                self._append_jsonl(self.evals_file, {
                    "timestamp": record.timestamp.isoformat(),
                    "prompt_version": record.prompt_version,
                    "evaluation": record.evaluation.to_dict()
                })
            
            # 更新统计
            self._update_stats(record)
    
    def _save_full_response(self, record: LLMCallRecord) -> str:
        """
        将完整响应保存到单独文件
        返回相对路径供查询
        """
        filename = f"{self.log_dir}/responses/{record.timestamp.isoformat()}__{record.prompt_key}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "prompt_key": record.prompt_key,
                "prompt_version": record.prompt_version,
                "rendered_prompt": record.rendered_prompt,
                "response": record.response,
                "raw_response": record.raw_response,
                "timestamp": record.timestamp.isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        return filename
    
    def _update_stats(self, record: LLMCallRecord):
        """更新统计数据（聚合）"""
        stats = self._load_stats()
        
        # 更新总体统计
        if "total_calls" not in stats:
            stats["total_calls"] = 0
            stats["total_tokens"] = 0
            stats["total_cost_usd"] = 0.0
            stats["by_prompt_key"] = {}
        
        stats["total_calls"] += 1
        stats["total_tokens"] += record.tokens["total_tokens"]
        stats["total_cost_usd"] += record.cost_usd
        stats["updated_at"] = datetime.utcnow().isoformat()
        
        # 更新按 prompt_key 的统计
        key = record.prompt_key
        if key not in stats["by_prompt_key"]:
            stats["by_prompt_key"][key] = {
                "call_count": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_ms": 0,
                "versions_used": set()
            }
        
        stats["by_prompt_key"][key]["call_count"] += 1
        stats["by_prompt_key"][key]["total_tokens"] += record.tokens["total_tokens"]
        stats["by_prompt_key"][key]["total_cost_usd"] += record.cost_usd
        stats["by_prompt_key"][key]["avg_latency_ms"] = (
            (stats["by_prompt_key"][key]["avg_latency_ms"] * 
             (stats["by_prompt_key"][key]["call_count"] - 1) +
             record.latency_ms) / stats["by_prompt_key"][key]["call_count"]
        )
        stats["by_prompt_key"][key]["versions_used"].add(record.prompt_version)
        
        self._save_stats(stats)
    
    def _load_stats(self) -> Dict:
        if os.path.exists(self.stats_file):
            with open(self.stats_file) as f:
                return json.load(f)
        return {}
    
    def _save_stats(self, stats: Dict):
        # 将 set 转为 list（JSON 序列化）
        stats_copy = copy.deepcopy(stats)
        if "by_prompt_key" in stats_copy:
            for key in stats_copy["by_prompt_key"]:
                if "versions_used" in stats_copy["by_prompt_key"][key]:
                    stats_copy["by_prompt_key"][key]["versions_used"] = \
                        list(stats_copy["by_prompt_key"][key]["versions_used"])
        
        with open(self.stats_file, 'w') as f:
            json.dump(stats_copy, f, indent=2, ensure_ascii=False)
    
    def _append_jsonl(self, filepath: str, record: Dict):
        """追加 JSON Lines 格式的记录"""
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    def log_error(self, prompt_key: str, error: str, prompt_version: str):
        """记录错误"""
        self._append_jsonl(self.errors_file, {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt_key": prompt_key,
            "prompt_version": prompt_version,
            "error": error
        })
    
    def log_retry(self, attempt: int, wait_time: float, error: str):
        """记录重试"""
        self._append_jsonl(self.errors_file, {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "retry",
            "attempt": attempt,
            "wait_time": wait_time,
            "error": error
        })
```

### 3.2 PromptAnalyzer 提示词分析

```python
class PromptAnalyzer:
    """分析 Prompt 的质量和有效性"""
    
    def analyze_version_performance(self, prompt_key: str, version: str):
        """分析某个版本的整体表现"""
        
        evals = self._load_evals_for_version(version)
        
        return {
            "version": version,
            "sample_count": len(evals),
            "quality_metrics": {
                "avg_score": mean([e["evaluation"]["overall_score"] for e in evals]),
                "min_score": min([e["evaluation"]["overall_score"] for e in evals]),
                "max_score": max([e["evaluation"]["overall_score"] for e in evals]),
                "std_dev": stdev([e["evaluation"]["overall_score"] for e in evals]),
                "p95": percentile([e["evaluation"]["overall_score"] for e in evals], 95),
                "failure_rate": sum(1 for e in evals if e["evaluation"]["overall_score"] < 5) / len(evals)
            },
            "cost_metrics": {
                "avg_tokens": mean([c["tokens"]["total_tokens"] for c in self._load_calls_for_version(version)]),
                "avg_latency_ms": mean([c["latency_ms"] for c in self._load_calls_for_version(version)]),
                "total_cost_usd": sum([c["cost_usd"] for c in self._load_calls_for_version(version)])
            }
        }
    
    def compare_versions(self, prompt_key: str, versions: List[str]):
        """对比多个版本的性能"""
        comparisons = [self.analyze_version_performance(prompt_key, v) for v in versions]
        
        # 排序：质量优先，成本次之
        return sorted(comparisons, 
                     key=lambda x: (
                         -x["quality_metrics"]["avg_score"],
                         x["cost_metrics"]["avg_tokens"]
                     ))
    
    def find_best_version(self, prompt_key: str, min_sample_size: int = 20) -> str:
        """找到质量最好、成本最低的版本"""
        versions = self.prompt_registry.get_all_versions(prompt_key)
        
        candidates = []
        for v in versions:
            perf = self.analyze_version_performance(prompt_key, v)
            if perf["sample_count"] >= min_sample_size:
                candidates.append(perf)
        
        if not candidates:
            return self.prompt_registry.get_default_version(prompt_key)
        
        # 质量和成本的加权评分
        def score(perf):
            quality_score = perf["quality_metrics"]["avg_score"] * 100
            cost_score = 1000 / perf["cost_metrics"]["avg_tokens"]  # 越低越好
            return quality_score * 0.7 + cost_score * 0.3
        
        best = max(candidates, key=score)
        return best["version"]
```

### 3.3 LLMReportGenerator 报告生成

```python
class LLMReportGenerator:
    """生成 HTML 报告，展示所有 LLM 调用的详细情况"""
    
    def generate_final_report(self, project_dir: str):
        """生成最终的 LLM 调用报告"""
        
        calls = self._load_all_calls(project_dir)
        stats = self._load_stats(project_dir)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>LLM 调用报告 - {project_dir}</title>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .summary {{ background: #f5f5f5; padding: 20px; }}
                .call-record {{ border: 1px solid #ddd; margin: 10px 0; padding: 10px; }}
                .prompt {{ background: #f0f0f0; padding: 5px; }}
                .response {{ background: #e8f5e9; padding: 5px; }}
                .error {{ background: #ffebee; color: #c62828; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
            </style>
        </head>
        <body>
            <h1>LLM 调用报告</h1>
            <div class="summary">
                <h2>汇总统计</h2>
                <table>
                    <tr>
                        <th>指标</th>
                        <th>值</th>
                    </tr>
                    <tr>
                        <td>总调用次数</td>
                        <td>{stats.get("total_calls", 0)}</td>
                    </tr>
                    <tr>
                        <td>总 Token 消耗</td>
                        <td>{stats.get("total_tokens", 0):,}</td>
                    </tr>
                    <tr>
                        <td>总成本</td>
                        <td>${stats.get("total_cost_usd", 0):.2f}</td>
                    </tr>
                </table>
                
                <h3>按 Prompt 类型的统计</h3>
                <table>
                    <tr>
                        <th>Prompt 类型</th>
                        <th>调用次数</th>
                        <th>平均质量</th>
                        <th>平均延迟(ms)</th>
                        <th>总成本</th>
                    </tr>
        """
        
        for key, data in stats.get("by_prompt_key", {}).items():
            avg_score = self._get_avg_score_for_key(key)
            html += f"""
                    <tr>
                        <td>{key}</td>
                        <td>{data["call_count"]}</td>
                        <td>{avg_score:.1f}/10</td>
                        <td>{data["avg_latency_ms"]:.0f}</td>
                        <td>${data["total_cost_usd"]:.2f}</td>
                    </tr>
            """
        
        html += """
                </table>
            </div>
            
            <h2>所有调用记录</h2>
        """
        
        for i, call in enumerate(calls[-50:]):  # 只显示最后 50 条
            html += f"""
            <div class="call-record">
                <h4>调用 #{i+1} - {call["prompt_key"]} ({call["model"]})</h4>
                <p>时间: {call["timestamp"]} | 延迟: {call["latency_ms"]:.0f}ms | Token: {call["tokens"]["total_tokens"]} | 成本: ${call["cost_usd"]:.4f}</p>
                
                <details>
                    <summary>展开详情</summary>
                    <h5>Prompt:</h5>
                    <pre class="prompt">{call["rendered_prompt"][:500]}</pre>
                    
                    <h5>Response:</h5>
                    <pre class="response">{call["response_snippet"]}</pre>
                </details>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        report_path = f"{project_dir}/output/llm_report.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return report_path
```

---

## 第四部分：编排层的改进（支持 LLM 交互）

### 4.1 MVPipeline 编排器

```python
class MVPipeline:
    """
    支持 LLM 交互的统一编排器
    
    关键特性：
    - 每步都通过 LLMClient 调用
    - 完整的提示词版本追踪
    - 质量评估和自适应
    """
    
    def __init__(self, 
                 theme: str,
                 style: str,
                 music_style: str,
                 mood: str,
                 language: str = "中文"):
        
        self.pm = ProjectManager.init_new(theme)
        self.logger = LLMLogger(self.pm.project_dir)
        self.llm_client = LLMClient(logger=self.logger)
        self.prompt_registry = PromptRegistry()
        
        self.context = {
            "theme": theme,
            "style": style,
            "music_style": music_style,
            "mood": mood,
            "language": language
        }
    
    def run(self):
        """主编排流程"""
        try:
            # Step ① 歌词生成
            self.pm.update_step("① lyrics", "running", "calling LLM...")
            lyrics_response = self.llm_client.generate(
                prompt_key="lyrics_generation",
                context=self.context,
                temperature=0.85
            )
            self.pm.save_artifact("lyrics", lyrics_response.content)
            self.pm.update_step("① lyrics", "completed", 
                              f"quality={lyrics_response.evaluation.overall_score:.1f}")
            
            # Step ② 音乐生成
            self.pm.update_step("② music", "running", "calling music API...")
            music_context = self.context | {
                "lyrics": lyrics_response.parsed["lyrics"]
            }
            music_response = self.llm_client.generate(
                prompt_key="music_generation",
                context=music_context,
                temperature=0.7
            )
            self.pm.save_artifact("music", music_response.content)
            self.pm.update_step("② music", "completed",
                              f"tokens={music_response.metadata.tokens['total_tokens']}")
            
            # [暂停点 1] 用户审核歌词和音乐
            UserInteraction.pause_for_approval(
                self.pm, "step_2_review",
                {"continue": "继续后续步骤", "pause": "暂停查看"}
            )
            
            # Step ③ 歌词对齐（支持 A/B/C 选择）
            alignment_options = {
                "A": "Demucs 自动对齐（推荐）",
                "B": "手动 SRT 文件"
            }
            UserInteraction.pause_for_approval(
                self.pm, "step_3_alignment_mode",
                alignment_options
            )
            
            align_mode = self.pm.get_user_choice("step_3_alignment_mode")
            if align_mode == "A":
                self._align_auto()
            else:
                self._align_manual()
            
            # Step ③.5 场景分析
            self.pm.update_step("③.5 scene_analysis", "running", "extracting scenes...")
            scene_response = self.llm_client.generate(
                prompt_key="scene_analysis",
                context=self.context | {
                    "lyrics": lyrics_response.parsed["lyrics"],
                    "music_style": music_style
                },
                max_tokens=4096
            )
            self.pm.save_artifact("scenes", scene_response.content)
            
            # Step ④-⑧ 后续步骤（自动执行）
            self._generate_images()
            self._compose_ken_burns()
            self._assemble_video()
            self._export()
            
            # 最终报告
            self.logger.generate_final_report(self.pm.project_dir)
            self.pm.update_step("_pipeline", "completed", "MV 生成完成")
            
        except Exception as e:
            self.logger.log_error("_pipeline", str(e), "unknown")
            self.pm.update_step("_pipeline", "failed", str(e))
            raise
```

---

## 第五部分：实施路线图

### Phase 1：LLM 交互底座（第1-2周）**[优先级：🔴 必做]**

```bash
Week 1:
  Day 1-2:
    - ✅ 创建 lib/llm/prompt_registry.py
    - ✅ 创建 lib/llm/prompt_template.py
    - ✅ 创建 prompts/ 目录结构
    - ✅ 编写所有 prompt 模板文件
  
  Day 3-4:
    - ✅ 创建 lib/llm/llm_client.py
    - ✅ 创建 lib/llm/request_builder.py
    - ✅ 创建 lib/llm/response_validator.py
  
  Day 5:
    - ✅ 创建 lib/llm/llm_logger.py（核心）
    - ✅ 创建 metadata/llm_calls 目录结构
    - ✅ 集成测试

Week 2:
  - ✅ 创建 lib/llm/prompt_evaluator.py
  - ✅ 创建 lib/llm/prompt_analyzer.py
  - ✅ 集成 LLMLogger 到所有 API 调用处
  - ✅ 生成第一份 llm_report.html
```

### Phase 2：编排层改造（第2-3周）**[优先级：🔴 必做]**

```bash
  - ✅ 创建 lib/mv_pipeline.py（新编排器）
  - ✅ 创建 lib/user_interaction.py（暂停点管理）
  - ✅ 重写 create_mv.sh 调用 MVPipeline
  - ✅ 更新 SKILL.md 交互规范
  - ✅ 端到端测试（5 个完整流程）
```

### Phase 3：质量评估和自适应（第3-4周）**[优先级：🟠 应该做]**

```bash
  - ⚠️ 实现 PromptVersion 版本对比
  - ⚠️ 实现 PromptEvaluation 质量评估
  - ⚠️ 实现自动版本选择（基于历史性能）
  - ⚠️ A/B 测试框架
```

### Phase 4：监控和告警（第4-5周）**[优先级：🟡 可选]**

```bash
  - ⚠️ 实时性能监控面板
  - ⚠️ 成本告警
  - ⚠️ 质量下降告警
  - ⚠️ Token 消耗预测
```

---

## 关键文件清单

### 需要新创建的

```
lib/llm/
├── __init__.py
├── llm_client.py           # LLMClient（核心）
├── llm_logger.py           # LLMLogger（日志系统）
├── prompt_registry.py      # PromptRegistry（提示词管理）
├── prompt_template.py      # PromptTemplate（模板引擎）
├── prompt_version.py       # PromptVersion（版本控制）
├── prompt_evaluator.py     # PromptEvaluation（质量评估）
├── prompt_analyzer.py      # PromptAnalyzer（性能分析）
├── request_builder.py      # RequestBuilder（请求构建）
├── response_validator.py   # ResponseValidator（响应验证）
├── token_counter.py        # TokenCounter（Token 统计）
└── report_generator.py     # LLMReportGenerator（报告生成）

lib/
├── mv_pipeline.py          # MVPipeline（新编排器）
├── user_interaction.py     # UserInteraction（交互管理）
└── project_manager.py      # ProjectManager（已有，需升级）

prompts/
├── registry.yaml           # Prompt 索引
├── lyrics/
│   ├── v1.0.md
│   ├── v2.0.md
│   └── metrics.json
├── music/
│   ├── v1.0.md
│   └── metrics.json
├── image/
│   ├── base_character/
│   ├── scene_image/
│   └── variants/
└── scene_analysis/
    ├── v1.0.md
    └── metrics.json

metadata/
└── llm_calls/              # 日志目录
    ├── calls.jsonl
    ├── errors.jsonl
    ├── evaluations.jsonl
    ├── stats.json
    └── responses/          # 完整响应存储
```

### 需要升级的

```
scripts/create_mv.sh      # 调用新的 MVPipeline
scripts/config.sh         # 集成 LLMLogger
SKILL.md                  # 更新交互规范
```

---

## 成功指标

| 指标 | 目标 | 测量方法 |
|------|------|---------|
| **日志完整性** | 100% LLM 调用都有日志 | 检查 calls.jsonl 记录数 |
| **报告可读性** | llm_report.html 清晰展示每一步 | 人工审查报告 |
| **Prompt 版本化** | 每个 prompt 都有版本号和性能指标 | registry.yaml 的版本数 |
| **响应验证率** | 100% 响应都经过验证 | ResponseValidator 覆盖率 |
| **用户暂停点** | Step②和Step③都有明确的暂停和选择 | 用户交互测试 |
| **成本透明** | 每个项目的总成本都清晰可见 | stats.json 中的 total_cost_usd |
| **质量指标** | 追踪每个版本的平均质量分数 | PromptAnalyzer 报告 |

---

## 工程价值

这个重设计的核心价值：

1. **可观测性** — 每一次 LLM 调用都有完整的审计日志
2. **可重现性** — 知道每个产出是由哪个 prompt 版本生成的
3. **可调优性** — 通过 A/B 测试和版本对比，不断改进 prompt
4. **成本控制** — 精确追踪 Token 消耗和美金成本
5. **质量评估** — 系统化地评估每个版本的输出质量
6. **用户信任** — 透明的日志和报告，用户知道幕后发生了什么

这不仅仅是一个技术改进，而是**把 LLM 调用从黑盒变成白盒**。
