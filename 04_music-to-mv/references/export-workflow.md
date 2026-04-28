# Export Workflow

> ⚠️ **已废弃（Deprecated）** — 此文档描述的功能已被整合到 `merge_and_export.sh`（Steps ⑨-⑪）。保留仅作为 FFmpeg 字幕参数参考。
> 
> 当前主流水线：
> ```
> produce_mv.sh       → Steps ④-⑧（图片 + KB 片段）
> merge_and_export.sh → Steps ⑨-⑪（合并 + 导出）
> ```

## Assembling Final MV

```bash
FFMPEG="/home/hlp/.openclaw/bin/ffmpeg"
WORKDIR="/path/to/project"

cd $WORKDIR

# Build concat list: segment + black + segment + black + ...
cat > final_list.txt << 'EOF'
file 'seg0_final.mp4'
file 'black_1s.mp4'
file 'seg1_final.mp4'
file 'black_1s.mp4'
file 'seg2_final.mp4'
file 'black_1s.mp4'
file 'seg3_final.mp4'
file 'black_1s.mp4'
file 'seg4_final.mp4'
file 'black_1s.mp4'
file 'seg5_final.mp4'
file 'black_1s.mp4'
file 'seg6_final.mp4'
EOF

# Concatenate all segments
$FFMPEG -y -f concat -safe 0 -i final_list.txt -c copy mv_raw.mp4

# Add audio (with fade) + soft subtitles (MKV)
$FFMPEG -y \
  -i mv_raw.mp4 \
  -i audio_final.mp3 \
  -i song.srt \
  -c:v copy -c:a copy -c:s copy \
  -map 0:v -map 1:a -map 2:s \
  song_final.mkv
```

## Hard-Burn Subtitles (for TikTok)

**SRT subtitle filter with style:**

```bash
# 16:9 horizontal (1280x720)
$FFMPEG -y \
  -i song_final.mkv \
  -vf "subtitles=song.srt:force_style='FontName=Microsoft YaHei,FontSize=32,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=20'" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a copy \
  song_tiktok.mp4
```

**Subtitle parameters explained:**
| Parameter | Value | Meaning |
|-----------|-------|---------|
| FontName | Microsoft YaHei | Windows Chinese font |
| FontSize | 32 | ~2/3 of 48pt default |
| PrimaryColour | &HFFFFFF | White text |
| OutlineColour | &H000000 | Black outline |
| Outline | 2 | 2px black border |
| Bold | 1 | Bold text |
| Alignment | 2 | Bottom center |
| MarginV | 20 | 20px from bottom |

## Vertical 9:16 Export

```bash
# Scale 16:9 to fit 9:16, pad sides with black
$FFMPEG -y \
  -i song_tiktok.mp4 \
  -vf "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a copy \
  song_vertical.mp4
```

**Note:** Font size may need adjustment for 9:16. Test with 5-second sample before full render.

## Quick Test (5 seconds)

```bash
# Extract 5-second sample with subtitles
$FFMPEG -y \
  -ss 16 -i song_final.mkv \
  -vf "subtitles=song.srt:force_style='FontName=Microsoft YaHei,FontSize=32,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=20'" \
  -t 5 \
  -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p \
  test_subtitle.mp4
```

## Output Summary

| File | Resolution | Subtitles | Use |
|------|-----------|-----------|-----|
| `song_final.mkv` | 1280x720 | Soft (SRT) | Local playback, archiving |
| `song_tiktok.mp4` | 1280x720 | Hard-burn | TikTok, YouTube |
| `song_vertical.mp4` | 1080x1920 | Hard-burn | TikTok vertical |
| `song.srt` | - | - | Reusable subtitle file |
