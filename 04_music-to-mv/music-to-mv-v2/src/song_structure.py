"""
song_structure.py — 歌曲结构选择

根据主题、曲风、情绪和创意简报选择歌词/音乐生成使用的结构提示。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SongStructure:
    """歌词结构提示。"""

    name: str
    sequence: str
    notes: str


STRUCTURES = {
    "classic_pop": SongStructure(
        name="classic_pop",
        sequence="[Intro] -> [Verse 1] -> [Pre-Chorus] -> [Chorus] -> "
                 "[Verse 2] -> [Chorus] -> [Bridge] -> [Final Chorus] -> [Outro]",
        notes="适合旋律抓耳的流行表达；副歌可重复，但 Final Chorus 需要有情绪升级或歌词变化。",
    ),
    "cinematic": SongStructure(
        name="cinematic",
        sequence="[Intro] -> [Verse 1] -> [Instrumental Interlude] -> [Chorus] -> "
                 "[Verse 2] -> [Bridge] -> [Final Chorus] -> [Outro]",
        notes="适合画面感强的 MV；保留器乐间奏，方便视觉叙事和场景转场。",
    ),
    "ancient_poem": SongStructure(
        name="ancient_poem",
        sequence="[Intro] -> [Verse 1] -> [Verse 2] -> [Refrain] -> "
                 "[Instrumental Interlude] -> [Verse 3] -> [Refrain Variation] -> [Outro]",
        notes="适合国风、古风和诗性主题；用 Refrain/叠句替代强流行副歌，第二次叠句要有变化。",
    ),
    "ballad_story": SongStructure(
        name="ballad_story",
        sequence="[Intro] -> [Verse 1] -> [Verse 2] -> [Chorus] -> "
                 "[Verse 3] -> [Bridge] -> [Final Chorus] -> [Outro]",
        notes="适合叙事和回忆感；主歌承担故事推进，副歌不必过早出现。",
    ),
    "ambient_mood": SongStructure(
        name="ambient_mood",
        sequence="[Intro] -> [Verse] -> [Refrain] -> [Instrumental Interlude] -> "
                 "[Verse Variation] -> [Outro]",
        notes="适合梦幻、空灵、氛围向主题；结构更松弛，重复段以意象递进为主。",
    ),
    "rock_build": SongStructure(
        name="rock_build",
        sequence="[Intro] -> [Verse 1] -> [Pre-Chorus] -> [Chorus] -> "
                 "[Verse 2] -> [Chorus] -> [Solo/Break] -> [Final Chorus] -> [Outro]",
        notes="适合摇滚或高能情绪；中段需要 Break/Solo，最后副歌爆发。",
    ),
}


def select_song_structure(
    *,
    theme: str = "",
    music_style: str = "",
    mood: str = "",
    narrative_mode: str = "",
    chorus_energy: str = "",
    mode: str = "adaptive",
    override: str = "",
) -> SongStructure:
    """选择歌曲结构。

    mode:
      - adaptive: 根据输入自动选择
      - classic_pop/cinematic/ancient_poem/...: 强制选择内置结构
      - custom: 使用 override
    """
    if override:
        return SongStructure("custom", override, "使用用户配置的自定义歌曲结构。")

    normalized_mode = (mode or "adaptive").strip().lower()
    if normalized_mode in STRUCTURES:
        return STRUCTURES[normalized_mode]

    text = f"{theme} {music_style} {mood} {narrative_mode} {chorus_energy}".lower()

    if any(k in text for k in ("摇滚", "rock", "燃", "爆发", "热血")):
        return STRUCTURES["rock_build"]
    if any(k in text for k in ("国风", "中国风", "古风", "戏曲", "古典")):
        return STRUCTURES["ancient_poem"]
    if any(k in text for k in ("梦幻", "空灵", "氛围", "ambient", "mood", "abstract")):
        return STRUCTURES["ambient_mood"]
    if any(k in text for k in ("故事", "story", "memory", "回忆", "怀旧", "叙事")):
        return STRUCTURES["ballad_story"]
    if any(k in text for k in ("电影", "cinematic", "史诗", "宏大")):
        return STRUCTURES["cinematic"]

    return STRUCTURES["classic_pop"]
