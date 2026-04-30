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
    "minimal composition, no extra characters, no text, no logo, no clutter"
)


# ════════════════════════════════════════════════════════════
# 变体类型定义
# ════════════════════════════════════════════════════════════

VARIANT_TYPES = [
    ("emotion", "emotion focus: distinct facial expression or reaction"),
    ("action", "action focus: different gentle activity or pose"),
    ("camera", "camera focus: different angle or composition"),
    ("motion", "motion focus: different slow movement or stillness"),
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

        # 5. 生成 desc（策略：LLM batch → local fallback）
        desc_source = self._generate_scene_descs(scenes)

        # 6. 生成变体 desc
        self._generate_variant_descs(scenes)

        # 写入 scenes.json
        self._write_scenes(scenes)

        total_duration = sum(s.get("duration", 0) for s in scenes)

        print(f"  [完成] {len(scenes)} 个场景, {total_duration:.0f}s, desc来源={desc_source}")

        return {
            "scenes": scenes,
            "scene_count": len(scenes),
            "total_duration": total_duration,
            "desc_source": desc_source,
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
    def analyze_structure(
        segments: List[Tuple[int, float, float, str]]
    ) -> List[Dict]:
        """分析歌曲结构，返回段落列表

        关键步骤：
          1. 动态确定场景数（10-22, 目标每段 7-12 秒）
          2. 检测重复歌词 → 标记 is_repeated
          3. 等宽切分 + 重复锚点调整 + 合并/分裂
        """
        n = len(segments)
        if n == 0:
            return []

        first_start = segments[0][1]
        last_end = segments[-1][2]
        total = max(0.1, last_end - first_start)

        # 场景数按总时长分布
        if total < 60:
            target = 10
        elif total < 100:
            target = 14
        elif total < 140:
            target = 18
        else:
            target = 22

        target = min(target, n)  # 不超过歌词行数

        # 找重复歌词 → is_repeated
        fp_idx = {}
        for i, (_, _, _, text) in enumerate(segments):
            fp = SceneAnalyzer._clean(text)[:20]
            if fp not in fp_idx:
                fp_idx[fp] = []
            fp_idx[fp].append(i)

        repeated_segs = set()
        for fp, idxs in fp_idx.items():
            if len(idxs) >= 2:
                repeated_segs.update(idxs)

        # 等宽切分
        boundaries = []
        for k in range(target + 1):
            pos = int(n * k / target)
            boundaries.append(pos)
        boundaries[0] = 0
        boundaries[-1] = n

        # 重复锚点
        anchors = {0, n}
        for fp, idxs in fp_idx.items():
            if len(idxs) >= 2:
                anchors.add(idxs[0])

        all_points = sorted(set(boundaries + list(anchors)))

        # 合并太近的点
        merged = [all_points[0]]
        for pt in all_points[1:]:
            prev_time = segments[merged[-1]][1] if merged[-1] < n else total
            curr_time = segments[pt][1] if pt < n else total
            if curr_time - prev_time < 3 and len(merged) > 1:
                merged[-1] = pt
            else:
                merged.append(pt)

        # 超过目标数 → 合并最小间隔段
        while len(merged) - 1 > target:
            gaps = []
            for i in range(1, len(merged)):
                s = segments[merged[i - 1]][1] if merged[i - 1] < n else 0
                e = segments[merged[i]][1] if merged[i] < n else total
                gaps.append((e - s, i))
            gaps.sort()
            _, idx = next(
                (g for g in gaps if g[1] > 1),
                (gaps[-1][0], len(merged) - 1),
            )
            merged.pop(idx)

        # 不足目标数 → 分裂最大间隔段
        prev_len = -1
        while len(merged) - 1 < target:
            if len(merged) == prev_len:
                break
            prev_len = len(merged)
            max_gap, max_i = 0, 1
            for i in range(1, len(merged)):
                s = segments[merged[i - 1]][1] if merged[i - 1] < n else 0
                e = segments[merged[i]][1] if merged[i] < n else total
                if e - s > max_gap:
                    max_gap, max_i = e - s, i
            mid_raw = (
                segments[merged[max_i - 1]][1]
                + segments[merged[max_i]][1]
            ) / 2
            mid = int(round(mid_raw))
            merged.insert(max_i, mid)
            merged = sorted(set(merged))

        # 构建段落
        paragraphs = []
        for bi in range(len(merged) - 1):
            si, ei = merged[bi], merged[bi + 1]
            segs = segments[si:ei]
            if not segs:
                continue
            start = segs[0][1]
            end = segs[-1][2]
            dur = max(0.1, end - start)
            text = " ".join(s[3] for s in segs)
            is_rep = any(i in repeated_segs for i in range(si, ei))

            paragraphs.append({
                "start_seg": si,
                "end_seg": ei,
                "start": start,
                "end": end,
                "duration": dur,
                "text": text,
                "is_repeated": is_rep,
                "segment_count": ei - si,
            })

        return paragraphs

    # ══════════════════════════════════════════════════════
    # 场景命名
    # ══════════════════════════════════════════════════════

    @staticmethod
    def name_scenes(paragraphs: List[Dict]) -> List[Dict]:
        """为段落分配歌曲结构名称"""
        result = []
        used = {}

        for i, p in enumerate(paragraphs):
            if p["is_repeated"] and "chorus" not in used:
                name = "chorus"
            elif i == 0:
                name = "intro"
            elif i == len(paragraphs) - 1:
                name = "outro"
            elif p["duration"] > 28 and "chorus" not in used:
                name = "chorus"
            elif "verse1" not in used:
                name = "verse1"
            elif "prechorus" not in used and p["duration"] < 22:
                name = "prechorus"
            elif "chorus" not in used:
                name = "chorus"
            elif "verse2" not in used:
                name = "verse2"
            elif "bridge" not in used:
                name = "bridge"
            else:
                name = f"extra{len(used) + 1}"

            used[name] = True
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

            prompt = (
                f"You are a senior MV storyboard & cinematic visual artist.\n"
                f"Generate unified coherent English image prompts for lyric-driven music video scenes.\n"
                f"\n"
                f"Character reference: {self._char_prompt}\n"
                f"Overall Theme: {self._theme}\n"
                f"Core Emotion Mood: {self._mood}\n"
                f"Art Style: {self._style}\n"
                f"Music Style: {self._music_style}\n"
                f"Visual Style Details: {art_style}\n"
                f"Music Visual Atmosphere: {music_visual}\n"
                f"\n"
                f"Lyric segments with timestamp:\n"
                f"{lyric_section}\n"
                f"\n"
                f"Requirements:\n"
                f"- Each prompt 20-25 concise English words.\n"
                f"- Fit lyric artistic conception and emotional atmosphere.\n"
                f"- Ensure full video style coherence, no style jumping.\n"
                f"- Output pure valid JSON array only.\n"
                f'Format: [{{"id": 1, "desc": "scene visual description"}}, ...]'
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
                    ret[sid] = {"desc": desc}

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

            prompt = (
                f"Generate unified subtle variant prompts for repeated chorus MV scenes.\n"
                f"\n"
                f"Character reference: {self._char_prompt}\n"
                f"Global Fixed Style: {self._style}\n"
                f"Core Mood Tone: {self._mood}\n"
                f"Unified Art Design: {art_style}\n"
                f"Music: {self._music_style}\n"
                f"\n"
                f"Only allow tiny adjustment: emotion / gentle action / camera angle.\n"
                f"No weather change, no background replacement, no style mutation.\n"
                f"\n"
                f"Variant production tasks:\n"
                f"{var_section}\n"
                f"\n"
                f"Standard: 20-25 English words per description.\n"
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
        full_desc += ", clean cinematic frame, fixed character appearance, unified color tone"
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
            "emotion": ", different emotional expression, subtle facial change",
            "action": ", different gentle pose or activity",
            "camera": ", different camera angle and composition",
            "motion": ", different subtle movement state",
        }
        suffix = suffix_map.get(vtype, ", subtle variation")
        return base + suffix

    # ══════════════════════════════════════════════════════
    # 描述有效性检查
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _is_valid_desc(desc: str, text_preview: str) -> bool:
        """检测 desc 是否为有效的 AI 生成描述"""
        if not desc or len(desc) < 15:
            return False
        if desc in OLD_TEMPLATES:
            return False

        desc_lower = desc.strip().lower()
        for p in TRUNCATED_PREFIXES:
            if desc_lower.startswith(p):
                return False

        word_count = len(desc.split())
        if word_count < 8 or word_count > 45:
            return False

        matches = sum(1 for kw in LYRIC_KEYWORDS if kw.lower() in desc.lower())
        if matches >= 1 or word_count >= 8:
            return True

        return False

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

        处理常见的 LLM 输出问题：
        - 思考标签 <think>...</think>
        - markdown 代码块 ```json ... ```
        - 前缀/后缀噪音文本
        - 非标准空白字符
        - 字段名/值中的转义问题

        Returns:
            解析成功返回 list[dict]，失败返回 None
        """
        if not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()

        # 1. 移除思考标签
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL).strip()

        # 2. 尝试多种提取策略
        strategies = [
            # 策略 A: 提取 markdown 代码块中的 JSON
            lambda t: re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.DOTALL),
            # 策略 B: 提取 JSON 数组
            lambda t: re.search(r"\[\s*\{[\s\S]*?\}\s*\]", t, re.DOTALL),
            # 策略 C: 提取 JSON 对象数组（松散匹配）
            lambda t: re.search(r"\[\s*[\s\S]*?\]", t, re.DOTALL),
        ]

        json_str = None
        for strategy in strategies:
            m = strategy(text)
            if m:
                candidate = m.group(1) if m.lastindex else m.group()
                candidate = candidate.strip()
                # 移除可能的包装 ``` 标记
                candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
                candidate = re.sub(r"\s*```$", "", candidate)
                json_str = candidate
                break

        if not json_str:
            return None

        # 3. 清理常见噪音
        # 移除非 JSON 前缀（直到第一个 [ 或 {）
        first_brace = min(
            (json_str.find(c) for c in ("[", "{") if c in json_str),
            default=-1
        )
        if first_brace > 0:
            json_str = json_str[first_brace:]

        # 移除尾随非 JSON 字符
        last_brace = max(
            (json_str.rfind(c) for c in ("]", "}") if c in json_str),
            default=-1
        )
        if last_brace > 0 and last_brace < len(json_str) - 1:
            json_str = json_str[:last_brace + 1]

        # 4. 尝试 JSON 解析，带修复
        if not json_str:
            return None

        # 尝试标准解析
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 尝试修复：引号内的换行符
        try:
            # 压缩字符串值中的换行
            fixed = re.sub(r'"(?:[^"\\]|\\.)*"',
                           lambda m: m.group(0).replace("\n", " ").replace("\r", ""),
                           json_str)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 尝试修复：对象数组如果最外层是 {}
        try:
            if json_str.strip().startswith("{"):
                return [json.loads(json_str)]
        except json.JSONDecodeError:
            pass

        return None

    def _write_scenes(self, scenes: List[Dict]):
        """写入 scenes.json"""
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.metadata_dir / "scenes.json"
        output_path.write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  [写入] scenes.json: {len(scenes)} 场景")
