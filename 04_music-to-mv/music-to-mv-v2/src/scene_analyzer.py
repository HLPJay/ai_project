"""
scene_analyzer.py — SRT 场景分析器

纯 Python 实现，替代原版 scripts/analyze_srt.py（1143 行）。
无需 bash，直接调用 LLMClient。

功能：
  - 解析 SRT 文件 → [(index, start, end, text)]
  - 分析歌曲结构（重复检测 = 副歌）
  - 动态场景划分（目标每段 7-12 秒，10-22 场景）
  - 场景标签 + 英文描述生成（本地 + LLM 双策略）
  - 场景变体描述生成（重复段 > 4s）
  - scenes.json 输出

用法：
    from src.scene_analyzer import SceneAnalyzer
    analyzer = SceneAnalyzer(project_dir)
    result = analyzer.analyze()
"""

import json
import os
import re
import math
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from src.config_manager import ConfigManager
from src.llm.client import LLMClient, RetryConfig
from src.style_map import (
    ART_STYLES, get_art_style, get_mood_desc, get_fallback_desc,
    get_label, get_music_style_desc, THEME_VISUALS,
)


# ════════════════════════════════════════════════════════════
# 全局统一画质后缀
# ════════════════════════════════════════════════════════════

QUALITY_SUFFIX = (
    ", 8k, ultra detailed, soft cinematic lighting, delicate color grading, "
    "clean MV frame style, high resolution, fine texture, film soft focus, "
    "minimal composition, no text, no logo, no clutter"
)


# ════════════════════════════════════════════════════════════
# 变体类型定义
# ════════════════════════════════════════════════════════════

VARIANT_TYPES = [
    ("emotion", "emotion focus: distinct facial expression or reaction"),
    ("action", "action focus: different gentle activity or pose"),
    ("camera", "camera focus: different angle or composition"),
    ("motion", "motion focus: different slow movement or stillness"),
    ("environment", "environment focus: different foreground object, weather detail, or spatial layer"),
    ("lighting", "lighting focus: different light direction, time fragment, or atmosphere density"),
]


# ════════════════════════════════════════════════════════════
# 旧模板检测
# ════════════════════════════════════════════════════════════

OLD_TEMPLATES = [
    "A cute child looking around with wonder",
    "A cute child exploring nature",
    "A cute child watching small animals",
    "A cute child singing and dancing",
    "A cute child making new friends",
    "A cute child gazing at the warm sunshine",
]

TRUNCATED_PREFIXES = [
    "the user wants me to create",
    "user wants me to create",
    "let me analyze the requirements",
    "here is the",
    "output only 20-25 word",
    "professional mv cinematic designer",
    "analyzing the requirements",
    "creating a 20-25",
    "let me analyze what i need",
    "they gave a detailed request",
    "we have to produce a description",
    "i need to create a subtle variant",
    "the user wants a professional mv cinematic designer",
]

LYRIC_KEYWORDS = frozenset([
    "rain", "guitar", "road", "coffee", "city", "tears", "memory",
    "sunset", "river", "solo", "nostalgic", "amber", "cafe",
    "heart", "whisper", "empty", "silent", "dance", "dream",
    "light", "sky", "wind", "song", "love", "star", "night",
])

FOCUS_KEYWORDS = {
    "character": (
        "i ", "you ", "we ", "he ", "she ", "they ", "face", "eyes",
        "hand", "smile", "kiss", "walk", "run", "dance", "embrace",
    ),
    "environment": (
        "sky", "sea", "river", "rain", "wind", "street", "station",
        "city", "room", "window", "night", "sunset", "mountain", "road",
    ),
    "object": (
        "letter", "chair", "bench", "lamp", "phone", "cup", "coffee",
        "train", "bicycle", "guitar", "door", "mirror", "flower",
    ),
    "symbolic": (
        "memory", "dream", "shadow", "echo", "silence", "absence",
        "goodbye", "waiting", "time", "summer", "winter", "lonely",
    ),
}

SHOT_TYPE_KEYWORDS = {
    "empty_space": ("empty", "silent", "absence", "alone"),
    "close_detail": ("eyes", "hand", "letter", "coffee", "tears", "whisper"),
    "establishing": ("city", "street", "station", "sky", "sea", "mountain"),
    "symbolic_insert": ("memory", "dream", "shadow", "echo", "time"),
}


# ════════════════════════════════════════════════════════════
# 场景分析器
# ════════════════════════════════════════════════════════════

class SceneAnalyzerError(Exception):
    """场景分析错误"""
    pass


class SceneAnalyzer:
    """SRT 场景分析器

    处理 SRT 解析 → 结构分析 → 场景命名 → 描述生成 → 变体描述

    Usage:
        analyzer = SceneAnalyzer(project_dir)
        result = analyzer.analyze()
    """

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.metadata_dir = self.project_dir / "metadata"
        self.audio_dir = self.project_dir / "audio"

        self.cfg = ConfigManager()
        self.client = LLMClient(project_dir=str(self.project_dir))

        # 项目配置
        self._theme = ""
        self._style = "动漫风"
        self._mood = "欢快"
        self._music_style = "流行"
        self._char_prompt = ""
        self._song_title = ""
        self._narrative_mode = "mixed"
        self._visual_mode = "mixed"
        self._character_policy = "optional protagonist"
        self._chorus_energy = "lifted"
        self._load_project_config()

    def _load_project_config(self):
        """加载项目配置"""
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text(encoding="utf-8"))
            self._theme = info.get("theme", "")
            self._style = info.get("style", "动漫风")
            self._mood = info.get("mood", "欢快")
            self._music_style = info.get("music_style", "流行")
            self._song_title = info.get("song_title", "")
            self._narrative_mode = info.get("narrative_mode", "mixed")
            self._visual_mode = info.get("visual_mode", "mixed")
            self._character_policy = info.get("character_policy", "optional protagonist")
            self._chorus_energy = info.get("chorus_energy", "lifted")

        base_char_path = self.metadata_dir / "base_char.json"
        if base_char_path.exists():
            bc = json.loads(base_char_path.read_text(encoding="utf-8"))
            self._char_prompt = bc.get("prompt", "")

    # ══════════════════════════════════════════════════════
    # 公开 API
    # ══════════════════════════════════════════════════════

    def analyze(self, srt_file: str = "") -> Dict[str, Any]:
        """完整场景分析流水线

        1. parse_srt → 2. analyze_structure → 3. name_scenes
        → 4. generate_labels → 5. generate_descs (LLM) → 6. generate_variants

        Args:
            srt_file: 可选的 SRT 文件路径，不传则用默认 {audio_dir}/song.srt

        Returns:
            {"scenes": [...], "scene_count": int,
             "total_duration": float, "desc_source": str}
        """
        srt_path = srt_file or str(self.audio_dir / "song.srt")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT 文件不存在: {srt_path}")

        # 1. 解析 SRT
        segments = self.parse_srt(srt_path)
        if not segments:
            raise SceneAnalyzerError("SRT 解析结果为空")

        print(f"  [解析] SRT: {len(segments)} 条歌词")

        # 2. 结构分析
        paragraphs = self.analyze_structure(segments)
        print(f"  [结构] {len(paragraphs)} 个段落")

        # 3. 场景命名
        scenes = self.name_scenes(paragraphs)
        print(f"  [命名] {len(scenes)} 个场景")

        # 4. 生成 label
        for s in scenes:
            s["label"] = self.generate_label(
                s["name"], self._theme, self._mood, s["text_preview"]
            )
            self._populate_scene_semantics(s)

        # 5. 生成 desc（策略：LLM batch → local fallback）
        desc_source = self._generate_scene_descs(scenes)

        for s in scenes:
            self._populate_scene_semantics(s)

        visual_bible = self._generate_visual_bible(scenes)

        # 6. 生成变体 desc
        self._generate_variant_descs(scenes)

        # 写入 scenes.json
        self._write_scenes(scenes)
        self._write_visual_bible(visual_bible)

        total_duration = sum(s.get("duration", 0) for s in scenes)

        print(f"  [完成] {len(scenes)} 个场景, {total_duration:.0f}s, desc来源={desc_source}")

        return {
            "scenes": scenes,
            "scene_count": len(scenes),
            "total_duration": total_duration,
            "desc_source": desc_source,
            "visual_bible": visual_bible,
        }

    # ══════════════════════════════════════════════════════
    # SRT 解析
    # ══════════════════════════════════════════════════════

    @staticmethod
    def parse_srt(srt_path: str) -> List[Tuple[int, float, float, str]]:
        """解析 SRT 文件，返回 [(idx, start, end, text)]"""
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT file not found: {srt_path}")

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 按空行分割
        if "\n\n" in content:
            blocks = content.strip().split("\n\n")
        else:
            lines = content.strip().split("\n")
            blocks, current = [], []
            for line in lines:
                s = line.strip()
                if s.isdigit():
                    if current:
                        blocks.append("\n".join(current))
                    current = [s]
                else:
                    current.append(line)
            if current:
                blocks.append("\n".join(current))

        segments = []
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            # 时间戳行
            ts_match = re.match(
                r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})",
                lines[1].strip()
            )
            if not ts_match:
                continue

            def _ts_to_sec(ts_str: str) -> float:
                ts_str = ts_str.replace(",", ".")
                h, m, s = ts_str.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)

            start = _ts_to_sec(ts_match.group(1))
            end = _ts_to_sec(ts_match.group(2))
            text = "\n".join(lines[2:]).strip()

            segments.append((int(lines[0].strip()), start, end, text))

        return segments

    # ══════════════════════════════════════════════════════
    # 结构分析
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _clean(text: str) -> str:
        """提取可比的干净文本"""
        return re.sub(r"[^\w\u4e00-\u9fff]", "", text)

    @staticmethod
    def _calc_target_count(n: int, total: float) -> int:
        """根据总时长和段落数确定目标场景数（10-22）"""
        if total < 60:
            target = 10
        elif total < 100:
            target = 14
        elif total < 140:
            target = 18
        else:
            target = 22
        return min(target, n)

    @staticmethod
    def _detect_repeated_segs(
        segments: List[Tuple[int, float, float, str]]
    ) -> tuple:
        """检测重复歌词行，返回 (fp_idx, repeated_segs)"""
        fp_idx: dict = {}
        for i, (_, _, _, text) in enumerate(segments):
            fp = SceneAnalyzer._clean(text)[:20]
            fp_idx.setdefault(fp, []).append(i)

        repeated_segs: set = set()
        for idxs in fp_idx.values():
            if len(idxs) >= 2:
                repeated_segs.update(idxs)

        return fp_idx, repeated_segs

    @staticmethod
    def _build_boundaries(n: int, target: int, fp_idx: dict) -> List[int]:
        """等宽切分 + 插入重复歌词锚点，返回排序后的边界点列表"""
        boundaries = [int(n * k / target) for k in range(target + 1)]
        boundaries[0] = 0
        boundaries[-1] = n

        anchors = {0, n}
        for idxs in fp_idx.values():
            if len(idxs) >= 2:
                anchors.add(idxs[0])

        return sorted(set(boundaries) | anchors)

    @staticmethod
    def _adjust_boundaries(
        all_points: List[int],
        segments: List[Tuple[int, float, float, str]],
        n: int,
        total: float,
        target: int,
    ) -> List[int]:
        """先合并过近点，再通过合并/分裂把边界数调整到 target+1"""
        def seg_time(idx: int) -> float:
            return segments[idx][1] if idx < n else total

        # 合并间隔 < 3s 的相邻点
        merged = [all_points[0]]
        for pt in all_points[1:]:
            if seg_time(pt) - seg_time(merged[-1]) < 3 and len(merged) > 1:
                merged[-1] = pt
            else:
                merged.append(pt)

        # 超过目标数 → 合并最小间隔段
        while len(merged) - 1 > target:
            gaps = sorted(
                (seg_time(merged[i]) - seg_time(merged[i - 1]), i)
                for i in range(1, len(merged))
            )
            _, idx = next((g for g in gaps if g[1] > 1), (gaps[-1][0], len(merged) - 1))
            merged.pop(idx)

        # 不足目标数 → 分裂最大间隔段
        prev_len = -1
        while len(merged) - 1 < target:
            if len(merged) == prev_len:
                break
            prev_len = len(merged)
            max_gap, max_i = 0, 1
            for i in range(1, len(merged)):
                gap = seg_time(merged[i]) - seg_time(merged[i - 1])
                if gap > max_gap:
                    max_gap, max_i = gap, i
            mid = int(round((seg_time(merged[max_i - 1]) + seg_time(merged[max_i])) / 2))
            merged.insert(max_i, mid)
            merged = sorted(set(merged))

        return merged

    @staticmethod
    def _build_paragraphs(
        merged: List[int],
        segments: List[Tuple[int, float, float, str]],
        repeated_segs: set,
        total: float,
    ) -> List[Dict]:
        """从边界点构建段落字典列表"""
        paragraphs = []
        for bi in range(len(merged) - 1):
            si, ei = merged[bi], merged[bi + 1]
            segs = segments[si:ei]
            if not segs:
                continue
            start = segs[0][1]
            end = segs[-1][2]
            paragraphs.append({
                "start_seg": si,
                "end_seg": ei,
                "start": start,
                "end": end,
                "duration": max(0.1, end - start),
                "text": " ".join(s[3] for s in segs),
                "is_repeated": any(i in repeated_segs for i in range(si, ei)),
                "segment_count": ei - si,
            })
        return paragraphs

    @staticmethod
    def analyze_structure(
        segments: List[Tuple[int, float, float, str]]
    ) -> List[Dict]:
        """分析歌曲结构，返回段落列表"""
        n = len(segments)
        if n == 0:
            return []

        total = max(0.1, segments[-1][2] - segments[0][1])
        target = SceneAnalyzer._calc_target_count(n, total)
        fp_idx, repeated_segs = SceneAnalyzer._detect_repeated_segs(segments)
        all_points = SceneAnalyzer._build_boundaries(n, target, fp_idx)
        merged = SceneAnalyzer._adjust_boundaries(all_points, segments, n, total, target)
        return SceneAnalyzer._build_paragraphs(merged, segments, repeated_segs, total)

    # ══════════════════════════════════════════════════════
    # 场景命名
    # ══════════════════════════════════════════════════════

    @staticmethod
    def name_scenes(paragraphs: List[Dict]) -> List[Dict]:
        """为段落分配歌曲结构名称（支持重复段落的后缀，如 chorus2, chorus3）

        命名策略（优先级从高到低）：
          1. 首段 (i==0) → "intro"（无条件）
          2. 重复段落 (is_repeated=True) → "chorus" 或 "chorus2", "chorus3" 等（有计数）
          3. 末段 (i==last, 且非重复) → "outro"
          4. 长段落 (duration>28) → "chorus"（如果还未分配过）
          5. 默认分配 → "verse1", "prechorus", "verse2", "bridge", "extraN"
        """
        result = []
        used_counts = {}  # 计数而非布尔值：{"chorus": 2, "verse1": 1, ...}

        for i, p in enumerate(paragraphs):
            # 优先级 1: 首段 — 无条件命名为 intro
            if i == 0:
                name = "intro"
                used_counts[name] = used_counts.get(name, 0) + 1

            # 优先级 2: 重复段落（副歌）— 即使是最后一段也优先
            elif p["is_repeated"]:
                base_name = "chorus"
                count = used_counts.get(base_name, 0) + 1
                if count == 1:
                    name = "chorus"
                else:
                    name = f"chorus{count}"
                used_counts[base_name] = count

            # 优先级 3: 末段（非重复段落）
            elif i == len(paragraphs) - 1:
                name = "outro"
                used_counts[name] = used_counts.get(name, 0) + 1

            # 优先级 4: 时长判断（长段落可能是副歌）
            elif p["duration"] > 28 and "chorus" not in used_counts:
                name = "chorus"
                used_counts[name] = used_counts.get(name, 0) + 1

            # 优先级 4: 默认分配（按优先顺序）
            elif "verse1" not in used_counts:
                name = "verse1"
                used_counts[name] = used_counts.get(name, 0) + 1

            elif "prechorus" not in used_counts and p["duration"] < 22:
                name = "prechorus"
                used_counts[name] = used_counts.get(name, 0) + 1

            elif "chorus" not in used_counts:
                name = "chorus"
                used_counts[name] = used_counts.get(name, 0) + 1

            elif "verse2" not in used_counts:
                name = "verse2"
                used_counts[name] = used_counts.get(name, 0) + 1

            elif "bridge" not in used_counts:
                name = "bridge"
                used_counts[name] = used_counts.get(name, 0) + 1

            else:
                # 最后的兜底方案
                extra_idx = len(used_counts) + 1
                name = f"extra{extra_idx}"
                used_counts[name] = used_counts.get(name, 0) + 1

            result.append({
                "id": i + 1,
                "name": name,
                "display_name": name,
                "start": round(p["start"], 2),
                "end": round(p["end"], 2),
                "duration": round(p["duration"], 2),
                "text_preview": p["text"][:80],
                "is_repeated": p["is_repeated"],
                "segment_count": p["segment_count"],
            })

        return result

    # ══════════════════════════════════════════════════════
    # 标签生成
    # ══════════════════════════════════════════════════════

    @staticmethod
    def generate_label(name: str, theme: str, mood: str,
                       text_preview: str) -> str:
        """生成场景中文标签（方案三：主题+情绪智能组合）

        匹配 THEME_VISUALS 主题词，组合为标签
        """
        full_context = f"{theme}{text_preview}"
        matched_keywords = []

        # 第一步：匹配 theme 中的关键词
        for keyword in THEME_VISUALS:
            if keyword in theme and len(matched_keywords) < 2:
                matched_keywords.append(keyword)

        # 第二步：补充匹配 text_preview 中的关键词
        if len(matched_keywords) < 2:
            for keyword in THEME_VISUALS:
                if keyword in text_preview and keyword not in matched_keywords:
                    matched_keywords.append(keyword)
                    if len(matched_keywords) >= 2:
                        break

        if matched_keywords:
            theme_label = "".join(matched_keywords)
            return f"{theme_label}-{mood}"

        # 未匹配 → 默认标签
        name_label_map = {
            "intro": "序幕",
            "verse1": "故事",
            "prechorus": "蓄势",
            "chorus": "高潮",
            "verse2": "延续",
            "bridge": "转折",
            "outro": "尾声",
            "extra1": "插曲",
            "extra2": "间章",
        }
        return name_label_map.get(name, "片段")

    # ══════════════════════════════════════════════════════
    # 场景描述生成（LLM + 本地 fallback）
    # ══════════════════════════════════════════════════════

    def _generate_scene_descs(self, scenes: List[Dict]) -> str:
        """批量生成场景描述

        策略：
          1. LLM batch (MiniMax) → 解析 JSON
          2. 局部 fallback（LLM 失败的场景）
          3. 全部 fallback（LLM 完全失败时）

        Returns:
            "llm" 或 "local"
        """
        llm_descs = self._call_llm_batch_descs(scenes)

        if llm_descs:
            # LLM 结果填充
            llm_count = 0
            for s in scenes:
                sid = s["id"]
                if sid in llm_descs and llm_descs[sid].get("desc"):
                    desc = llm_descs[sid]["desc"]
                    if self._is_valid_desc(desc, s.get("text_preview", "")):
                        s["desc"] = desc + QUALITY_SUFFIX
                        for key in (
                            "visual_focus", "shot_type", "character_needed",
                            "symbolic_objects", "motion_hint",
                        ):
                            if llm_descs[sid].get(key) is not None:
                                s[key] = llm_descs[sid][key]
                        llm_count += 1
                        continue
                # LLM 没生成或无效 → local fallback
                s["desc"] = self._generate_local_desc(s)

            if llm_count > 0:
                return "llm"

        # LLM 完全失败 → 全部 local
        for s in scenes:
            s["desc"] = self._generate_local_desc(s)

        return "local"

    def _call_llm_batch_descs(self, scenes: List[Dict]) -> Dict[int, Dict]:
        """调用 LLM 批量生成场景描述

        注意：LLM 返回内容常含 markdown 代码块、思考标签、前缀噪音等，
        使用 _parse_json_response 进行鲁棒解析。
        """
        try:
            cfg = ConfigManager()
            token = cfg.get("minimax_token", "")
            if not token:
                return {}

            art_style = get_art_style(self._style)
            music_visual = get_music_style_desc(self._music_style)

            # 构建歌词段列表
            lyric_lines = []
            for s in scenes:
                time_range = f"{int(s['start'])}s-{int(s['end'])}s"
                lyric_lines.append(f"[{time_range}] {s['text_preview']}")

            lyric_section = "\n".join(lyric_lines)

            # 使用 PromptRegistry 渲染 scene_desc prompt
            try:
                from src.llm.registry import PromptRegistry
                registry = PromptRegistry()
                do_not_do = self._load_do_not_do()
                prompt = registry.render("image.scene_desc", {
                    "char_prompt": self._char_prompt,
                    "theme": self._theme,
                    "mood": self._mood,
                    "style": self._style,
                    "music_style": self._music_style,
                    "art_style": art_style,
                    "music_visual": music_visual,
                    "lyric_section": lyric_section,
                    "character_policy": self._character_policy,
                    "visual_mode": self._visual_mode,
                    "narrative_mode": self._narrative_mode,
                    "chorus_energy": self._chorus_energy,
                    "do_not_do": do_not_do,
                })
            except (ImportError, KeyError) as e:
                print(f"  [scene_desc] registry 渲染失败: {e}，使用硬编码 fallback")
                do_not_do_str = self._load_do_not_do()
                prompt = (
                    f"You are a senior MV storyboard & cinematic visual artist.\n"
                    f"Generate unified, poetic, cinematic English image prompts for lyric-driven music video scenes.\n"
                    f"\n"
                    f"Character continuity reference (only use when a human subject is genuinely needed): {self._char_prompt}\n"
                    f"Overall Theme: {self._theme}\n"
                    f"Core Emotion Mood: {self._mood}\n"
                    f"Art Style: {self._style}\n"
                    f"Music Style: {self._music_style}\n"
                    f"Visual Style Details: {art_style}\n"
                    f"Music Visual Atmosphere: {music_visual}\n"
                    f"Character Policy: {self._character_policy}\n"
                    f"Visual Mode: {self._visual_mode}\n"
                    f"Narrative Mode: {self._narrative_mode}\n"
                    f"Chorus Energy: {self._chorus_energy}\n"
                    + (f"Do Not Do: {do_not_do_str}\n" if do_not_do_str else "")
                    + f"\n"
                    f"Lyric segments with timestamp:\n"
                    f"{lyric_section}\n"
                    f"\n"
                    f"Requirements:\n"
                    f"- Each prompt 28-40 concise but evocative English words.\n"
                    f"- Interpret the lyric meaning, subtext, memory, metaphor, and emotional atmosphere instead of illustrating words literally.\n"
                    f"- Do not make every scene character-centered. Mix wide environment shots, symbolic still life, empty space, detail shots, over-the-shoulder shots, and only some human-centered frames.\n"
                    f"- At least 40 percent of scenes should avoid a centered human face or full-body protagonist.\n"
                    f"- If a recurring protagonist appears, keep continuity, but let the environment, objects, distance, framing, and emotional symbolism carry the scene.\n"
                    f"- Ensure full video style coherence without repetitive composition.\n"
                    f"- Output pure valid JSON array only.\n"
                    f'- For each scene also provide: visual_focus (character/environment/object/symbolic/mixed), shot_type, character_needed, symbolic_objects, motion_hint.\n'
                    f'Format: [{{"id": 1, "desc": "scene visual description", "visual_focus": "environment", "shot_type": "wide", "character_needed": false, "symbolic_objects": ["wind", "station"], "motion_hint": "slow drift"}}, ...]'
                )

            api_url = "https://api.minimaxi.com/v1/chat/completions"
            payload = json.dumps({
                "model": cfg.get("llm_model", "MiniMax-M2.7"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
            }).encode("utf-8")

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp_data = self.client._call_raw_api(
                api_url, payload, headers,
                prompt_key="scene_desc_batch",
                model=cfg.get("llm_model", "MiniMax-M2.7"),
                prompt_text=prompt,
            )

            raw = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            results = self._parse_json_response(raw)
            if not results:
                print(f"  [LLM batch descs] 解析失败，使用 local fallback")
                return {}

            ret = {}
            for item in results:
                sid = item.get("id")
                desc = self._strip_think(item.get("desc", ""))
                if sid and desc:
                    ret[sid] = {
                        "desc": desc,
                        "visual_focus": item.get("visual_focus"),
                        "shot_type": item.get("shot_type"),
                        "character_needed": item.get("character_needed"),
                        "symbolic_objects": item.get("symbolic_objects"),
                        "motion_hint": item.get("motion_hint"),
                    }

            return ret

        except Exception as e:
            print(f"  [LLM batch descs] 失败: {e}")
            return {}

    def _call_llm_batch_variants(
        self, variant_scenes: List[Dict], all_scenes: List[Dict]
    ) -> Dict[int, List[str]]:
        """调用 LLM 批量生成变体描述"""
        try:
            cfg = ConfigManager()
            token = cfg.get("minimax_token", "")
            if not token:
                return {}

            art_style = get_art_style(self._style)

            # 构建变体请求列表
            var_requests = []
            for s in variant_scenes:
                n_needed = max(2, min(3, -(-int(s["duration"]) // 5))) - 1
                for vi in range(1, n_needed + 1):
                    vtype, vrule = VARIANT_TYPES[vi % len(VARIANT_TYPES)]
                    var_requests.append({
                        "scene_id": s["id"],
                        "variant_idx": vi,
                        "vtype": vtype,
                        "base_desc": s.get("desc", ""),
                        "lyrics": s.get("text_preview", ""),
                        "rule": vrule,
                    })

            if not var_requests:
                return {}

            var_section = "\n".join(
                f'[scene {r["scene_id"]} var{r["variant_idx"]}] '
                f'Original: {r["base_desc"][:60]}... '
                f'Lyrics: {r["lyrics"]} '
                f'Variation type: {r["vtype"]}'
                for r in var_requests
            )

            # 使用 PromptRegistry 渲染 shot_variants prompt
            try:
                from src.llm.registry import PromptRegistry
                registry = PromptRegistry()
                prompt = registry.render("image.shot_variants", {
                    "visual_bible": self._get_visual_bible_summary(),
                    "char_prompt": self._char_prompt,
                    "style": self._style,
                    "mood": self._mood,
                    "music_style": self._music_style,
                    "variant_tasks": var_section,
                })
            except (ImportError, KeyError) as e:
                print(f"  [variants] registry 渲染失败: {e}，使用硬编码 fallback")
                prompt = (
                    f"Generate coherent but materially distinct variant prompts for repeated chorus MV scenes.\n"
                    f"\n"
                    f"Character continuity reference (only when a person appears): {self._char_prompt}\n"
                    f"Global Fixed Style: {self._style}\n"
                    f"Core Mood Tone: {self._mood}\n"
                    f"Unified Art Design: {art_style}\n"
                    f"Music: {self._music_style}\n"
                    f"\n"
                    f"Each variant must feel like a different usable shot, not a duplicate with swapped adjectives.\n"
                    f"Allow meaningful change in shot distance, composition, foreground objects, environmental detail, lighting direction, emotional beat, or symbolic focus.\n"
                    f"Keep the same lyrical core, world, and style. Do not mutate into a different story.\n"
                    f"Do not output nearly identical prompts.\n"
                    f"\n"
                    f"Variant production tasks:\n"
                    f"{var_section}\n"
                    f"\n"
                    f"Standard: 26-40 English words per description.\n"
                    f"Output pure JSON array only: "
                    f'[{{"scene_id": 1, "desc": "..."}}, ...]'
                )

            api_url = "https://api.minimaxi.com/v1/chat/completions"
            payload = json.dumps({
                "model": cfg.get("llm_model", "MiniMax-M2.7"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
            }).encode("utf-8")

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp_data = self.client._call_raw_api(
                api_url, payload, headers,
                prompt_key="variant_desc_batch",
                model=cfg.get("llm_model", "MiniMax-M2.7"),
                prompt_text=prompt,
            )

            raw = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            results = self._parse_json_response(raw)
            if not results:
                print(f"  [LLM batch variants] 解析失败，使用 local fallback")
                return {}

            merged = {}
            for item in results:
                sid = item.get("scene_id")
                desc = self._strip_think(item.get("desc", ""))
                if sid and desc:
                    if sid not in merged:
                        merged[sid] = []
                    merged[sid].append(desc)

            return merged

        except Exception as e:
            print(f"  [LLM batch variants] 失败: {e}")
            return {}

    def _generate_local_desc(self, scene: Dict) -> str:
        """本地 fallback 场景描述"""
        mood_desc = get_mood_desc(self._mood)
        art_style = get_art_style(self._style)
        full_desc = get_fallback_desc(
            scene["name"], self._char_prompt, self._theme,
            scene["text_preview"], mood_desc, art_style,
        )
        full_desc += (
            ", cinematic storytelling frame, lyrical visual metaphor, "
            "cohesive palette, varied subject focus"
        )
        return full_desc + QUALITY_SUFFIX

    def _generate_variant_descs(self, scenes: List[Dict]):
        """生成变体描述（重复段 > 4s 的场景）"""
        variant_scenes = []
        for s in scenes:
            if s.get("is_repeated") and s.get("duration", 0) > 4:
                n_needed = max(2, min(3, -(-int(s["duration"]) // 5)))
                current_variants = s.get("variants", [])
                if len(current_variants) < n_needed - 1:
                    variant_scenes.append(s)

        if not variant_scenes:
            return

        # LLM batch
        llm_variants = self._call_llm_batch_variants(variant_scenes, scenes)

        for s in variant_scenes:
            sid = s["id"]
            n_needed = max(2, min(3, -(-int(s["duration"]) // 5))) - 1

            # LLM 生成的变体
            if sid in llm_variants and llm_variants[sid]:
                s["variants"] = []
                for vi, desc in enumerate(llm_variants[sid][:n_needed]):
                    if self._is_valid_desc(desc, s.get("text_preview", "")):
                        s["variants"].append(desc + QUALITY_SUFFIX)
                    else:
                        s["variants"].append(
                            self._generate_local_variant(s, vi + 1)
                        )
            else:
                # local fallback
                s["variants"] = [
                    self._generate_local_variant(s, vi + 1)
                    for vi in range(n_needed)
                ]

    def _generate_local_variant(self, scene: Dict, variant_idx: int) -> str:
        """本地变体描述 fallback"""
        base = scene.get("desc", "")
        vtype, _ = VARIANT_TYPES[variant_idx % len(VARIANT_TYPES)]
        suffix_map = {
            "emotion": ", different emotional beat, changed reaction or body language",
            "action": ", different action focus, alternate gesture or activity",
            "camera": ", different shot distance, framing, and camera angle",
            "motion": ", different motion rhythm, pause, or transitional stillness",
            "environment": ", different environmental layer, foreground element, or weather cue",
            "lighting": ", different light direction, atmosphere density, or time-of-day nuance",
        }
        suffix = suffix_map.get(vtype, ", distinct alternate visual treatment")
        return base + suffix

    # ══════════════════════════════════════════════════════
    # 描述有效性检查
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _is_valid_desc(desc: str, text_preview: str) -> bool:
        """检测 desc 是否为有效的 AI 生成描述（启发式规则，不依赖特定模型输出）"""
        if not desc or len(desc) < 15:
            return False

        # JSON / 代码块残留
        if desc.strip().startswith(("[", "{")):
            return False

        # 词数合理（8-45 词）
        word_count = len(desc.split())
        if word_count < 8 or word_count > 45:
            return False

        # 元指令泄漏（模型思考过程误输出）
        lower = desc.lower()
        meta_signals = (
            "user want", "let me", "i need to", "i will ",
            "analyzing", "requirement", "output only",
            "here is the", "create a description", "produce a",
        )
        if any(s in lower for s in meta_signals):
            return False

        # 至少 3 个有意义词（长度 > 2）
        return sum(1 for w in desc.split() if len(w) > 2) >= 3

    # ══════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _strip_think(raw: str) -> str:
        """移除 LLM 的思考标签"""
        return re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.DOTALL).strip()

    @staticmethod
    def _extract_json_array(raw_text: str) -> str:
        """从文本中精准提取 JSON 数组"""
        match = re.search(r"\[\s*\{[\s\S]*\}\s*\]", raw_text, re.DOTALL)
        if match:
            return match.group()
        return raw_text

    @staticmethod
    def _parse_json_response(raw_text: str) -> Optional[List[Dict]]:
        """鲁棒解析 LLM 返回的 JSON 响应

        步骤 1：移除 <think> 标签，提取 markdown 代码块内容
        步骤 2：定位 JSON 数组边界，尝试解析（含换行修复）
        """
        if not raw_text or not raw_text.strip():
            return None

        # 步骤 1: 清理包装
        text = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.DOTALL).strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        # 步骤 2: 定位 JSON 边界
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end < start:
            # 单个对象兜底
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end < start:
                return None
            text = text[start:end + 1]
            try:
                return [json.loads(text)]
            except json.JSONDecodeError:
                return None

        json_str = text[start:end + 1]

        # 尝试解析（原始 → 修复换行 → 兜底单对象）
        for candidate in [
            json_str,
            re.sub(r'"(?:[^"\\]|\\.)*"',
                   lambda m: m.group(0).replace("\n", " ").replace("\r", ""),
                   json_str),
        ]:
            try:
                result = json.loads(candidate)
                return result if isinstance(result, list) else [result]
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _pick_visual_focus(text: str) -> str:
        lower = f" {text.lower()} "
        scores = {}
        for focus, keywords in FOCUS_KEYWORDS.items():
            scores[focus] = sum(1 for kw in keywords if kw in lower)

        best_focus = max(scores, key=scores.get)
        if scores[best_focus] <= 0:
            return "mixed"
        return best_focus

    @staticmethod
    def _pick_shot_type(text: str, visual_focus: str) -> str:
        lower = f" {text.lower()} "
        for shot_type, keywords in SHOT_TYPE_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return shot_type

        if visual_focus == "environment":
            return "wide"
        if visual_focus == "object":
            return "close_detail"
        if visual_focus == "character":
            return "medium"
        if visual_focus == "symbolic":
            return "symbolic_insert"
        return "wide"

    @staticmethod
    def _extract_symbolic_objects(text: str) -> List[str]:
        lower = f" {text.lower()} "
        found = []
        object_pool = (
            "rain", "wind", "window", "station", "street", "bench", "lamp",
            "coffee", "train", "guitar", "river", "sunset", "shadow", "letter",
            "bicycle", "door", "mirror", "flower", "sky", "night", "light",
        )
        for token in object_pool:
            if token in lower and token not in found:
                found.append(token)
            if len(found) >= 3:
                break
        return found

    def _populate_scene_semantics(self, scene: Dict):
        text = " ".join(
            part for part in [
                scene.get("text_preview", ""),
                scene.get("desc", ""),
                self._theme,
                scene.get("name", ""),
            ] if part
        )

        visual_focus = self._pick_visual_focus(text)
        shot_type = self._pick_shot_type(text, visual_focus)
        symbolic_objects = self._extract_symbolic_objects(text)
        character_needed = visual_focus in {"character", "mixed"}

        # 根据 Creative Brief 策略调整
        if self._character_policy == "no fixed protagonist":
            character_needed = False
            if visual_focus == "character":
                visual_focus = "environment"
        elif self._character_policy == "fixed protagonist":
            visual_focus = "character"
            character_needed = True
        # "optional protagonist": 保持 LLM 决定，不做调整

        if self._visual_mode == "environment-led":
            if visual_focus == "mixed":
                visual_focus = "environment"
                character_needed = False
        elif self._visual_mode == "symbolic":
            if visual_focus in ("character", "mixed"):
                visual_focus = "symbolic"
                character_needed = False
        # "mixed" 或 "character-led": 保持 LLM 决定

        if shot_type in {"empty_space", "symbolic_insert"}:
            character_needed = False

        if scene.get("is_repeated"):
            continuity = "strong"
        elif character_needed:
            continuity = "medium"
        else:
            continuity = "soft"

        motion_hint = "slow drift"
        lower = text.lower()
        if any(token in lower for token in ("run", "dance", "train", "drive")):
            motion_hint = "gentle travel motion"
        elif any(token in lower for token in ("wind", "rain", "shadow", "light")):
            motion_hint = "atmospheric movement"

        raw_character_needed = scene.get("character_needed", character_needed)
        if isinstance(raw_character_needed, str):
            raw_character_needed = raw_character_needed.strip().lower() in {"1", "true", "yes"}

        scene["visual_focus"] = scene.get("visual_focus") or visual_focus
        scene["shot_type"] = scene.get("shot_type") or shot_type
        scene["character_needed"] = bool(raw_character_needed)
        scene["continuity"] = scene.get("continuity") or continuity
        scene["symbolic_objects"] = scene.get("symbolic_objects") or symbolic_objects
        scene["motion_hint"] = scene.get("motion_hint") or motion_hint

    def _load_do_not_do(self) -> str:
        """从 info.json 加载 do_not_do 数组，返回逗号分隔字符串"""
        info_path = self.metadata_dir / "info.json"
        if info_path.exists():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
                dnd = info.get("do_not_do", [])
                if isinstance(dnd, list) and dnd:
                    return " | ".join(dnd)
            except Exception:
                pass
        return ""

    def _get_visual_bible_summary(self) -> str:
        """返回 visual bible 的摘要字符串（供变体 prompt 使用）"""
        bible_path = self.metadata_dir / "visual_bible.json"
        if bible_path.exists():
            try:
                bible = json.loads(bible_path.read_text(encoding="utf-8"))
                parts = []
                if bible.get("world_style"):
                    parts.append(f"World: {bible['world_style']}")
                palette = bible.get("palette") or []
                if palette:
                    parts.append("Palette: " + ", ".join(palette[:3]))
                if bible.get("lighting"):
                    parts.append(f"Lighting: {bible['lighting']}")
                if bible.get("texture"):
                    parts.append(f"Texture: {bible['texture']}")
                if bible.get("camera_language"):
                    parts.append(f"Camera: {bible['camera_language']}")
                if bible.get("do_not_break"):
                    parts.append("Rules: " + "; ".join(bible["do_not_break"][:3]))
                return " | ".join(parts)
            except Exception:
                pass
        return f"Style: {self._style}, Mood: {self._mood}, Theme: {self._theme}"

    def _generate_visual_bible(self, scenes: List[Dict]) -> Dict[str, Any]:
        llm_bible = self._call_llm_visual_bible(scenes)
        if llm_bible:
            return llm_bible
        return self._build_local_visual_bible(scenes)

    def _call_llm_visual_bible(self, scenes: List[Dict]) -> Optional[Dict[str, Any]]:
        try:
            token = self.cfg.get("minimax_token", "")
            if not token:
                return None

            scene_lines = []
            for scene in scenes[:8]:
                scene_lines.append(
                    f'- scene {scene["id"]}: focus={scene.get("visual_focus", "mixed")}, '
                    f'shot={scene.get("shot_type", "wide")}, '
                    f'lyrics="{scene.get("text_preview", "")[:60]}", '
                    f'desc="{scene.get("desc", "")[:80]}"'
                )

            # 使用 PromptRegistry 渲染 visual_bible prompt
            try:
                from src.llm.registry import PromptRegistry
                registry = PromptRegistry()
                prompt = registry.render("image.visual_bible", {
                    "theme": self._theme,
                    "mood": self._mood,
                    "style": self._style,
                    "music_style": self._music_style,
                    "char_prompt": self._char_prompt,
                    "scene_samples": "\n".join(scene_lines),
                })
            except (ImportError, KeyError) as e:
                print(f"  [visual_bible] registry 渲染失败: {e}，使用硬编码 fallback")
                prompt = (
                    "You are defining a global visual bible for a lyric-driven music video.\n"
                    "Return one compact JSON object only.\n"
                    f"Theme: {self._theme}\n"
                    f"Mood: {self._mood}\n"
                    f"Style: {self._style}\n"
                    f"Music Style: {self._music_style}\n"
                    f"Character continuity reference: {self._char_prompt}\n"
                    "Scene samples:\n"
                    + "\n".join(scene_lines)
                    + "\n"
                    "Output keys: world_style, palette, lighting, texture, camera_language, "
                    "continuity_subject, do_not_break.\n"
                    "palette and do_not_break must be arrays.\n"
                )

            api_url = "https://api.minimaxi.com/v1/chat/completions"
            payload = json.dumps({
                "model": self.cfg.get("llm_model", "MiniMax-M2.7"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
            }).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp_data = self.client._call_raw_api(
                api_url, payload, headers,
                prompt_key="visual_bible",
                model=self.cfg.get("llm_model", "MiniMax-M2.7"),
                prompt_text=prompt,
            )
            raw = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json_response(raw)
            if parsed and isinstance(parsed, list) and parsed:
                candidate = parsed[0]
                if isinstance(candidate, dict):
                    candidate["source"] = "llm"
                    return candidate
            try:
                candidate = json.loads(self._extract_json_array(raw))
                if isinstance(candidate, list):
                    candidate = candidate[0] if candidate else None
                if isinstance(candidate, dict):
                    candidate["source"] = "llm"
                    return candidate
            except Exception:
                return None
            return None
        except Exception:
            return None

    def _build_local_visual_bible(self, scenes: List[Dict]) -> Dict[str, Any]:
        focus_counts = {}
        for scene in scenes:
            focus = scene.get("visual_focus", "mixed")
            focus_counts[focus] = focus_counts.get(focus, 0) + 1

        dominant_focus = max(focus_counts, key=focus_counts.get) if focus_counts else "mixed"
        repeated_count = sum(1 for scene in scenes if scene.get("is_repeated"))
        character_scenes = sum(1 for scene in scenes if scene.get("character_needed"))

        palette = self._infer_palette()
        lighting = self._infer_lighting()
        camera_language = self._infer_camera_language(dominant_focus, repeated_count)
        continuity_subject = (
            "recurring protagonist appears selectively across emotionally important shots"
            if character_scenes
            else "continuity comes from environment, palette, and symbolic objects rather than a fixed person"
        )

        return {
            "source": "local",
            "world_style": f"{self._style} MV world shaped by {self._theme or self._song_title or 'the song'}",
            "palette": palette,
            "lighting": lighting,
            "texture": "soft cinematic detail, airy atmosphere, clean frame discipline",
            "camera_language": camera_language,
            "continuity_subject": continuity_subject,
            "do_not_break": [
                "do not turn every shot into a centered portrait",
                "do not break the palette family abruptly",
                "do not abandon lyrical symbolism for generic poses",
            ],
        }

    def _infer_palette(self) -> List[str]:
        mood = self._mood.lower()
        theme = self._theme.lower()
        if any(token in mood for token in ("sad", "nostalg", "伤", "旧", "回忆")):
            return ["warm gold", "faded teal", "dusky blue"]
        if any(token in mood for token in ("happy", "bright", "快", "甜")):
            return ["sunlit yellow", "soft sky blue", "fresh green"]
        if any(token in theme for token in ("night", "city", "夜", "城")):
            return ["deep navy", "muted cyan", "street amber"]
        return ["soft cream", "warm gray", "muted blue"]

    def _infer_lighting(self) -> str:
        mood = self._mood.lower()
        if any(token in mood for token in ("sad", "nostalg", "柔", "静")):
            return "soft backlight haze with restrained contrast"
        if any(token in mood for token in ("happy", "bright", "快")):
            return "clear natural light with gentle glow"
        return "cinematic soft light with controlled atmosphere"

    @staticmethod
    def _infer_camera_language(dominant_focus: str, repeated_count: int) -> str:
        if dominant_focus == "environment":
            base = "wide drifting frames with occasional close inserts"
        elif dominant_focus == "object":
            base = "detail-driven compositions with measured cut-ins"
        elif dominant_focus == "character":
            base = "intimate medium shots balanced by breathing room"
        else:
            base = "mixed cinematic framing, alternating environment and intimate details"

        if repeated_count:
            base += ", repeated chorus sections should vary by shot distance, lighting, and foreground"
        return base

    def _write_visual_bible(self, visual_bible: Dict[str, Any]):
        output_path = self.metadata_dir / "visual_bible.json"
        output_path.write_text(
            json.dumps(visual_bible, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_scenes(self, scenes: List[Dict]):
        """写入 scenes.json"""
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.metadata_dir / "scenes.json"
        output_path.write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  [写入] scenes.json: {len(scenes)} 场景")
