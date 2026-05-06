"""
test_align.py — 对齐模块（align.py）单元测试

覆盖:
  - SRT 时间戳格式化/解析
  - SRT 块验证（索引序列、时间戳升序、格式正确）
  - SRT 内容整体验证
  - 歌词文件解析
  - LyricsAligner 静态方法
  - LyricsAligner 幻觉段过滤
  - WhisperTranscriber.is_available（不依赖网络）
  - DemucsVocalSeparator.is_available（不依赖网络）
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.align import (
    format_srt_time,
    parse_srt_time,
    _validate_srt_block,
    validate_srt_content,
    parse_lyrics,
    WhisperTranscriber,
    DemucsVocalSeparator,
    LyricsAligner,
)


# ════════════════════════════════════════════════════════════
# SRT 时间戳
# ════════════════════════════════════════════════════════════


class TestSrtTimeFormatting:
    def test_format_srt_time_basic(self):
        assert format_srt_time(0.0) == "00:00:00,000"
        assert format_srt_time(1.5) == "00:00:01,500"
        assert format_srt_time(61.0) == "00:01:01,000"
        assert format_srt_time(3661.123) == "01:01:01,123"
        assert format_srt_time(36090.999) == "10:01:30,999"

    def test_format_srt_time_fractional_ms(self):
        # 毫秒精度截断
        assert format_srt_time(1.2345) == "00:00:01,234"
        assert format_srt_time(1.9999) == "00:00:01,999"


class TestSrtTimeParsing:
    def test_parse_srt_time_basic(self):
        assert parse_srt_time("00:00:00,000") == pytest.approx(0.0)
        assert parse_srt_time("00:00:01,500") == pytest.approx(1.5)
        assert parse_srt_time("00:01:01,000") == pytest.approx(61.0)
        assert parse_srt_time("01:01:01,123") == pytest.approx(3661.123)

    def test_parse_srt_time_decimal_separator(self):
        # 有些 SRT 用 '.' 而非 ','
        assert parse_srt_time("00:00:01.500") == pytest.approx(1.5)


# ════════════════════════════════════════════════════════════
# SRT 块验证
# ════════════════════════════════════════════════════════════


class TestValidateSrtBlock:
    def test_valid_block(self):
        valid, err = _validate_srt_block("1\n00:00:00,000 --> 00:00:02,500\nhello")
        assert valid, err
        assert err == ""

    def test_block_too_few_lines(self):
        valid, err = _validate_srt_block("1\n00:00:00,000 --> 00:00:02,500")
        assert not valid
        assert "行数不足" in err

    def test_invalid_index_non_integer(self):
        valid, err = _validate_srt_block("abc\n00:00:00,000 --> 00:00:02,500\nhello")
        assert not valid
        assert "格式错误" in err

    def test_invalid_index_zero(self):
        valid, err = _validate_srt_block("0\n00:00:00,000 --> 00:00:02,500\nhello")
        assert not valid
        assert "正整数" in err

    def test_invalid_index_negative(self):
        valid, err = _validate_srt_block("-1\n00:00:00,000 --> 00:00:02,500\nhello")
        assert not valid
        assert "正整数" in err

    def test_missing_arrow(self):
        valid, err = _validate_srt_block("1\n00:00:00,000 00:00:02,500\nhello")
        assert not valid
        assert "-->" in err or "缺少" in err

    def test_end_before_start(self):
        valid, err = _validate_srt_block("1\n00:00:05,000 --> 00:00:02,500\nhello")
        assert not valid
        assert "结束时间" in err or "大于" in err

    def test_end_equals_start(self):
        valid, err = _validate_srt_block("1\n00:00:02,000 --> 00:00:02,000\nhello")
        assert not valid

    def test_invalid_timestamp_format(self):
        valid, err = _validate_srt_block("1\ninvalid --> 00:00:02,500\nhello")
        assert not valid
        assert "时间戳" in err


# ════════════════════════════════════════════════════════════
# SRT 内容验证
# ════════════════════════════════════════════════════════════


class TestValidateSrtContent:
    def _make_srt(self, blocks):
        """将 [(index, start, end, text), ...] 转换为 SRT 字符串"""
        lines = []
        for idx, start, end, text in blocks:
            lines.append(f"{idx}\n{start} --> {end}\n{text}")
        return "\n\n".join(lines)

    def test_valid_full_srt(self):
        srt = self._make_srt([
            (1, "00:00:00,000", "00:00:02,500", "第一句歌词"),
            (2, "00:00:02,500", "00:00:05,000", "第二句歌词"),
            (3, "00:00:05,000", "00:00:08,000", "第三句歌词"),
        ])
        ok, err, indices = validate_srt_content(srt)
        assert ok, err
        assert indices == [1, 2, 3]

    def test_missing_arrow_in_block(self):
        srt = self._make_srt([
            (1, "00:00:00,000", "00:00:02,500", "OK"),
            (2, "INVALID", "00:00:05,000", "Bad"),
        ])
        ok, err, indices = validate_srt_content(srt)
        assert not ok
        assert "块2" in err

    def test_skip_empty_blocks(self):
        srt = "1\n00:00:00,000 --> 00:00:02,500\nA\n\n\n\n2\n00:00:02,500 --> 00:00:05,000\nB"
        ok, err, indices = validate_srt_content(srt)
        assert ok
        assert indices == [1, 2]

    def test_index_sequence_gap(self):
        srt = self._make_srt([
            (1, "00:00:00,000", "00:00:02,500", "A"),
            (3, "00:00:02,500", "00:00:05,000", "C"),  # 跳过了 2
        ])
        ok, err, indices = validate_srt_content(srt)
        assert not ok
        assert "索引号" in err
        assert indices == [1, 3]


# ════════════════════════════════════════════════════════════
# 歌词解析
# ════════════════════════════════════════════════════════════


class TestParseLyrics:
    def test_parse_basic(self, tmp_path):
        lyrics_file = tmp_path / "lyrics.txt"
        lyrics_file.write_text(
            "## 第1段\n第一句歌词\n第二句歌词\n## 第2段\n第三句歌词\n",
            encoding="utf-8",
        )
        all_lines, clean_lines = parse_lyrics(str(lyrics_file))
        # ## 标记行不进入 all_lines
        assert "## 第1段" not in all_lines
        assert "第一句歌词" in all_lines
        assert "第一句歌词" in clean_lines
        # [标签] 格式的行被过滤
        assert "##" not in clean_lines[0]

    def test_parse_empty_lines_stripped(self, tmp_path):
        lyrics_file = tmp_path / "lyrics.txt"
        lyrics_file.write_text("  \n第一句\n  \n第二句\n", encoding="utf-8")
        _, clean = parse_lyrics(str(lyrics_file))
        assert "第一句" in clean
        assert "第二句" in clean


# ════════════════════════════════════════════════════════════
# WhisperTranscriber.is_available
# ════════════════════════════════════════════════════════════


class TestWhisperAvailable:
    def test_is_available_returns_bool(self):
        result = WhisperTranscriber.is_available()
        assert isinstance(result, bool)


# ════════════════════════════════════════════════════════════
# DemucsVocalSeparator.is_available
# ════════════════════════════════════════════════════════════


class TestDemucsAvailable:
    def test_is_available_returns_bool(self):
        result = DemucsVocalSeparator.is_available()
        assert isinstance(result, bool)


# ════════════════════════════════════════════════════════════
# LyricsAligner 静态方法
# ════════════════════════════════════════════════════════════


class TestLyricsAlignerStaticMethods:
    def test_load_project_audio_duration_missing(self, tmp_path):
        duration = LyricsAligner._load_project_audio_duration(tmp_path)
        assert duration == 0.0

    def test_load_project_audio_duration_invalid_json(self, tmp_path):
        metadata = tmp_path / "metadata"
        metadata.mkdir()
        info = metadata / "info.json"
        info.write_text("not json", encoding="utf-8")
        duration = LyricsAligner._load_project_audio_duration(tmp_path)
        assert duration == 0.0

    def test_load_project_audio_duration_valid(self, tmp_path):
        metadata = tmp_path / "metadata"
        metadata.mkdir()
        info = metadata / "info.json"
        info.write_text(json.dumps({"audio_duration_sec": 180.5}), encoding="utf-8")
        duration = LyricsAligner._load_project_audio_duration(tmp_path)
        assert duration == pytest.approx(180.5)

    def test_build_whisper_prompt(self):
        prompt = LyricsAligner._build_whisper_prompt(["歌词1", "歌词2"])
        assert "歌词" in prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# ════════════════════════════════════════════════════════════
# LyricsAligner 幻觉段过滤
# ════════════════════════════════════════════════════════════


class TestFilterMisrecognizedAsr:
    def _make_seg(self, text, start, end, no_speech=0.0):
        return {"text": text, "start": start, "end": end, "no_speech_prob": no_speech}

    def _make_lyrics(self, *lyrics):
        return list(lyrics)

    def test_empty_asr_returns_unchanged(self):
        aligner = LyricsAligner()
        result = aligner._filter_misrecognized_asr([], ["歌词"])
        assert result == []

    def test_empty_lyrics_returns_unchanged(self):
        aligner = LyricsAligner()
        segs = [self._make_seg("hello", 0, 2)]
        result = aligner._filter_misrecognized_asr(segs, [])
        assert result == segs

    def test_normal_segments_kept(self):
        aligner = LyricsAligner()
        lyrics = self._make_lyrics("你好世界", "春天来了")
        segs = [
            self._make_seg("你 好 世 界", 0, 3),
            self._make_seg("春 天 来 了", 4, 7),
        ]
        result = aligner._filter_misrecognized_asr(segs, lyrics)
        assert len(result) == 2

    def test_pure_nonsense_filtered(self):
        aligner = LyricsAligner()
        lyrics = self._make_lyrics("你好世界")
        # 重复无意义音节 + 高 no_speech_prob → 过滤
        segs = [
            self._make_seg("啊啊啊啊", 0, 2, no_speech=0.9),
            self._make_seg("嘿嘿嘿嘿", 2, 4, no_speech=0.95),
            self._make_seg("你好世界", 4, 7, no_speech=0.1),
        ]
        result = aligner._filter_misrecognized_asr(segs, lyrics)
        assert len(result) == 1
        assert result[0]["text"] == "你好世界"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
