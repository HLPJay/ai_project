# Alignment Workflow (Step ③)

## Overview

Lyric-to-audio alignment: maps each lyric line to its timestamps in the audio.

```
song.mp3 → [Demucs] → vocals.wav → [Whisper] → segments[] → [Two-pass alignment] → song.srt
```

## Sub-steps

### ③-a Demucs Vocal Separation (Optional)

**Purpose:** Remove background music, isolate vocal track. Significantly improves Whisper accuracy.

**Command:**
```bash
demucs --two-stems vocals -o /path/to/output /path/to/song.mp3
```

**Output:** `{output}/htdemucs/separated/{basename}/vocals.wav`

**Fallback:** If Demucs is unavailable or OOM, skip and use original `song.mp3`.

**Models available:**
- `htdemucs` (default, best quality, ~2GB RAM)
- `htdemucs_ft` (fine-tuned, higher quality but slower)
- `sdxl` (highest quality, requires more RAM)

### ③-b Whisper Transcription

**Purpose:** Convert audio to timestamped text segments.

**Command:**
```bash
# Primary: small model (best accuracy)
whisper vocals.wav --model small --language zh \
  --output_format json --output_dir /path/to/temp

# Fallback: base model (faster, less RAM)
whisper vocals.wav --model base --language zh \
  --output_format json --output_dir /path/to/temp
```

**Output:** `{temp}/song.json` — array of segments with `start`, `end`, `text`.

**Memory adaptation:** If `small` model OOMs, script auto-falls back to `base`.

### ③-c Two-Pass Alignment Algorithm

**Purpose:** Map each ASR segment to the most likely lyric line.

#### Pass 1: Sequential Greedy Matching

```
For each ASR segment (in order):
  Search window: next 8 lyric lines (not yet matched)
  Scoring: max(similarity, chinese_char_overlap * 1.2)
  Threshold: 0.25
  If best_score >= threshold:
    Assign ASR timestamps to that lyric line
    Mark lyric as matched, advance lyric_index
```

#### Pass 2: Gap-Filling

```
For each unmatched lyric line:
  Search all unmatched ASR segments
  Lowered threshold: 0.20
  Assign best available match
```

#### Similarity Functions

```python
def similarity(a, b):
    """Sequence similarity on cleaned text"""
    a = re.sub(r'[^\w\s]', '', a.lower())
    b = re.sub(r'[^\w\s]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def chinese_overlap(a, b):
    """Chinese character set overlap ratio"""
    ca = set(re.findall(r'[\u4e00-\u9fff]', a))
    cb = set(re.findall(r'[\u4e00-\u9fff]', b))
    if not ca: return 0
    return len(ca & cb) / len(ca)
```

### ③-d Post-Processing Fixes

**Fix 1: First line missing timestamp**
- If lyric line 1 has no timestamp but first ASR segment exists
- Assign first ASR segment's timestamps to line 1

**Fix 2: Gap filling (consecutive unmatched lines)**
- When 2+ consecutive lyric lines are unmatched
- Use linear interpolation between previous and next matched lines
- Gap duration divided equally among skipped lines

## Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Alignment threshold (pass 1) | 0.25 | First matching pass |
| Alignment threshold (pass 2) | 0.20 | Gap-filling pass |
| Search window (pass 1) | 8 lyric lines | Forward-only, no backtracking |
| Whisper model | small → base | OOM fallback |
| Demucs model | htdemucs | CPU, ~2GB RAM |
| Min text length | 2 chars | Skip shorter ASR segments |

## Output Format

SRT (SubRip) format:

```
1
00:00:06,900 --> 00:00:08,900
细细的雨丝像彩带

2
00:00:08,900 --> 00:00:15,669
在天空轻轻地摇摆
...
```

## Troubleshooting

### Alignment rate < 80%

**Symptoms:** Many lyric lines missing timestamps.

**Causes:**
1. ASR quality too low (background music interference)
2. Lyrics don't match actual singing (model didn't follow input lyrics)
3. Song has long instrumental sections

**Solutions:**
1. Ensure Demucs vocal separation was used
2. Check `temp/song.json` ASR segments — if many contain garbage text, the model may have generated different lyrics
3. Lower threshold to 0.20 (in `align_lyrics.sh`)

### "詞曲 XXX" garbage text in ASR

**Cause:** Whisper hallucinating on instrumental/no-vocal sections.

**Solution:** This is expected. The alignment algorithm's similarity scoring filters these out (< 0.25 match score).

### OOM during Whisper

**Cause:** Insufficient RAM for `small` model.

**Solution:** Script auto-fallback to `base` model. If still OOM, audio may be too long (> 3 min per segment). Consider splitting audio into chunks.

## Key Differences from Old Approach

| Aspect | Old (v1) | New (v2) |
|--------|----------|----------|
| Preprocessing | None | Demucs vocal separation |
| Alignment | Single-pass greedy | Two-pass greedy |
| Threshold | 0.45 | 0.25 / 0.20 |
| Window size | 20 | 8 |
| Post-processing | None | First-line fix + gap interpolation |
| Injection safety | heredoc risk (`"""` → `$var`) | Python urllib (no shell substitution) |
| Whisper fallback | None | small → base |
| Repeated lyrics | Kept first match only | Sequential priority assignment |
