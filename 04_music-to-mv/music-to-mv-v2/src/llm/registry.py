"""
registry.py — Prompt 注册表和版本管理

核心功能：
1. 注册提示词模板（从文件加载）
2. 版本管理（registry.yaml）
3. 变量替换（支持 Jinja2 和 f-string 两种方式）
4. 按版本渲染（version pinning）

用法：
    registry = PromptRegistry()
    template = registry.get_template("lyrics.generation", version="v2.0")
    prompt = template.render({"theme": "春天", "style": "国风"})
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime


class PromptTemplate:
    """提示词模板（不可变）"""

    def __init__(self, content: str, key: str, version: str,
                 metadata: Dict = None):
        self.content = content
        self.key = key
        self.version = version
        self.metadata = metadata or {}
        self._variables = self._extract_variables()

    def render(self, variables: Dict[str, str], engine: str = "jinja2") -> str:
        """渲染模板"""
        # 始终尝试 Jinja2
        result = self._render_jinja2(variables)
        # Jinja2 不可用或结果未变时，使用内置渲染
        if result == self.content and "{{" in self.content:
            result = self._render_internal(variables)
        return result

    def _render_jinja2(self, variables: Dict[str, str]) -> str:
        """使用 Jinja2 渲染"""
        try:
            from jinja2 import Environment
            env = Environment(autoescape=False)
            template = env.from_string(self.content)
            return template.render(**variables)
        except ImportError:
            return self.content

    def _render_internal(self, variables: Dict[str, str]) -> str:
        """内置渲染引擎（支持 {{ }} 和 {% if %}）"""
        result = self.content

        # Step 1: 处理 {% if var %}...{% endif %} 块
        pattern = r'\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}'
        def if_replacer(m):
            var_name = m.group(1)
            content = m.group(2)
            if variables.get(var_name, ""):
                return content
            return ""
        result = re.sub(pattern, if_replacer, result, flags=re.DOTALL)

        # Step 2: 替换所有 {{ variable }}
        for key, value in variables.items():
            result = result.replace("{{ " + key + " }}", str(value))
            result = result.replace("{{" + key + "}}", str(value))

        # Step 3: 清除剩余未替换占位符
        result = re.sub(r'\{\{[^}]*\}\}', '', result)

        return result

    def _render_fstring(self, variables: Dict[str, str]) -> str:
        """手动替换变量（兼容模式）- 已弃用，使用 _render_internal 替代"""
        return self._render_internal(variables)

    def _extract_variables(self) -> List[str]:
        """提取模板中的变量名"""
        return re.findall(r'\{\{\s*(\w+)\s*\}\}', self.content)

    def __repr__(self):
        return f"<PromptTemplate: {self.key}@{self.version}>"


class PromptRegistry:
    """Prompt 注册表"""

    _instance = None

    def __new__(cls, prompts_dir: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init(prompts_dir)
        return cls._instance

    def _init(self, prompts_dir: str = None):
        self.prompts_dir = Path(prompts_dir or self._find_prompts_dir())
        self.registry_path = self.prompts_dir / "registry.yaml"
        self._templates: Dict[str, PromptTemplate] = {}

        # 加载 registry.yaml
        self._registry = self._load_registry()

        # 加载所有模板
        self._load_all_templates()

    @staticmethod
    def _find_prompts_dir() -> Path:
        """从多个可能位置找到 prompts 目录"""
        candidates = [
            Path.cwd() / "prompts",
            Path.cwd() / "../prompts",
            Path(__file__).parent.parent.parent.parent / "prompts",
        ]
        for c in candidates:
            if c.exists():
                return c
        # 如果不存在就创建
        prompts_dir = Path.cwd() / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        return prompts_dir

    def _load_registry(self) -> Dict:
        """加载 registry.yaml"""
        if not self.registry_path.exists():
            return {}
        try:
            import yaml
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _load_all_templates(self):
        """加载所有模板文件"""
        for prompt_key, config in self._registry.get("prompts", {}).items():
            versions = config.get("versions", {})
            default_version = config.get("default_version", "")

            for ver_name, ver_config in versions.items():
                file_path = ver_config.get("file", "")
                template_path = self.prompts_dir / file_path

                if template_path.exists():
                    content = template_path.read_text(encoding="utf-8")
                    metadata = {
                        "description": ver_config.get("description", ""),
                        "model": ver_config.get("model", ""),
                        "is_default": (ver_name == default_version),
                        "status": ver_config.get("status", "active"),
                    }
                    template = PromptTemplate(content, prompt_key, ver_name, metadata)
                    cache_key = f"{prompt_key}:{ver_name}"
                    self._templates[cache_key] = template

                    # 如果是默认版本，也注册无版本号的 key
                    if metadata["is_default"]:
                        self._templates[prompt_key] = template

    # ── 注册 API ────────────────────────────────────────

    def register(self, key: str, content: str, version: str = "v1.0",
                 metadata: Dict = None) -> PromptTemplate:
        """直接注册模板（用于测试或动态注册）"""
        template = PromptTemplate(content, key, version, metadata)
        cache_key = f"{key}:{version}"
        self._templates[cache_key] = template
        self._templates[key] = template  # 默认版本
        return template

    def get_template(self, key: str, version: str = None) -> Optional[PromptTemplate]:
        """获取模板

        关键解析逻辑：
        - 如果 key 包含 ":"，直接查找 "key:version"
        - 否则，如果 version 指定，查 "key:version"
        - 否则查注册表默认版本，再 fallback 到无版本 key
        """
        if ":" in key:
            return self._templates.get(key)

        if version:
            cache_key = f"{key}:{version}"
            if cache_key in self._templates:
                return self._templates[cache_key]

        # 从注册表找默认版本
        prompts_config = self._registry.get("prompts", {})
        prompt_config = prompts_config.get(key, {})
        default_ver = prompt_config.get("default_version", "")
        if default_ver:
            default_key = f"{key}:{default_ver}"
            if default_key in self._templates:
                return self._templates[default_key]

        # Fallback 到无版本 key
        return self._templates.get(key)

    def render(self, key: str, variables: Dict[str, str],
               version: str = None, engine: str = "jinja2") -> str:
        """一键获取并渲染模板"""
        template = self.get_template(key, version)
        if not template:
            raise KeyError(f"Prompt template not found: {key} (version={version})")
        return template.render(variables, engine)

    def list_templates(self) -> List[Dict]:
        """列出所有已加载的模板"""
        result = []
        for key, template in sorted(self._templates.items()):
            result.append({
                "key": template.key,
                "version": template.version,
                "cache_key": key,
                "is_default": template.metadata.get("is_default", False),
                "status": template.metadata.get("status", "active"),
                "variables": template._variables,
                "file": template.metadata.get("file", ""),
            })
        return result

    def list_registry(self) -> Dict:
        """列出 registry 配置"""
        return self._registry

    def __repr__(self):
        return f"<PromptRegistry: {len(self._templates)} templates loaded>"
