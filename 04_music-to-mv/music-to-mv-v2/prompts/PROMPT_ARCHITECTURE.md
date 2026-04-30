# Music-to-MV Multi-Stage Prompt Architecture

This document defines a maintainable prompt system for the Music-to-MV pipeline.
The goal is to move from isolated prompt strings to a staged creative workflow
where each model step has a clear responsibility, stable input, and structured output.

## 1. Core Principle

The system should not treat every model step as "generate more text".
Each step should do exactly one kind of work:

1. Define the song's creative intent.
2. Interpret lyrics into visual meaning.
3. Turn meaning into shot planning.
4. Turn shot planning into image prompts.
5. Generate variants that are different shots, not tiny pose changes.

Consistency should come from global visual anchors.
Diversity should come from shot-level planning.
Do not force consistency by making every frame character-centered.

## 2. End-to-End Flow

### Stage A. Creative Brief

Purpose:
- Capture what the user wants the song and MV to feel like.

Inputs:
- theme
- mood
- style
- music_style
- language
- audience
- narrative_mode
- visual_mode
- character_policy

Recommended extra fields:
- `narrative_mode`: story / memory / mood / abstract / mixed
- `visual_mode`: character-led / environment-led / symbolic / mixed
- `character_policy`: fixed protagonist / optional protagonist / no fixed protagonist
- `chorus_energy`: restrained / lifted / explosive

Output:
- normalized creative brief object

Example:

```json
{
  "theme": "summer memories and parting",
  "mood": "nostalgic, warm, slightly sad",
  "style": "anime",
  "music_style": "indie pop",
  "language": "Chinese",
  "narrative_mode": "memory",
  "visual_mode": "mixed",
  "character_policy": "optional protagonist",
  "chorus_energy": "lifted"
}
```

### Stage B. Lyrics Generation

Purpose:
- Generate singable lyrics and a structured creative interpretation.

Prompt responsibility:
- Write lyrics.
- Mark sections.
- Summarize emotional arc.
- Extract recurring imagery and symbolic anchors.

Required outputs:
1. final lyrics text
2. song structure
3. section-level emotional arc
4. recurring imagery list
5. visual direction hints

Recommended schema:

```json
{
  "lyrics": "...",
  "sections": [
    {
      "label": "verse1",
      "emotion": ["gentle", "curious"],
      "imagery": ["sunlight", "old street", "bicycle"],
      "visual_hint": "memory fragments, warm environment, sparse human presence"
    }
  ],
  "global_imagery": ["wind", "old station", "summer light"],
  "visual_language": "poetic realism with soft transitions"
}
```

### Stage C. Music Generation

Purpose:
- Generate audio and expose music attributes that matter for visual pacing.

Prompt responsibility:
- Specify style, arrangement, pacing, and energy contour.

Desired outputs after generation:
- final audio
- optional music metadata

Recommended metadata:

```json
{
  "tempo_feel": "mid-slow",
  "energy_curve": [
    {"label": "intro", "energy": 0.25},
    {"label": "verse1", "energy": 0.42},
    {"label": "chorus", "energy": 0.78}
  ],
  "arrangement_keywords": ["airy guitar", "soft drums", "nostalgic synth wash"]
}
```

### Stage D. Subtitle Alignment

Purpose:
- Align lyrics with audio timing.

This is not an LLM task.

Outputs:
- line timestamps
- optional phrase-level timing

### Stage E. Lyric-to-Visual Interpretation

Purpose:
- Convert timed lyrics into visual meaning.

This is the most important LLM stage for downstream image quality.
It should not directly output final image prompts.

Prompt responsibility:
- Interpret semantics, subtext, and metaphor.
- Decide whether the segment needs a person, environment, object, or empty space.
- Decide shot type and symbolic focus.

Required fields per segment:

```json
{
  "segment_id": 3,
  "start": 12.4,
  "end": 18.7,
  "lyric": "风吹过空荡的站台",
  "emotion": ["lonely", "suspended", "restrained"],
  "imagery": ["wind", "platform", "absence", "waiting"],
  "visual_focus": "environment",
  "shot_type": "wide empty establishing shot",
  "character_needed": false,
  "continuity": "soft",
  "symbolic_objects": ["empty bench", "flickering station light"],
  "motion_hint": "slow drift",
  "repeat_group": null
}
```

Visual focus should be one of:
- `character`
- `environment`
- `object`
- `symbolic`
- `mixed`

Shot type should be one of:
- establishing
- wide
- medium
- close_detail
- over_shoulder
- silhouette
- empty_space
- symbolic_insert

Rules:
- Do not make every segment character-centered.
- At least part of the song should use environment, object, or symbolic shots.
- Use repeated chorus sections to define controlled variant groups.

### Stage F. Global Visual Bible

Purpose:
- Define what stays consistent across the whole MV.

Prompt responsibility:
- Summarize world, palette, light, texture, camera behavior, and continuity rules.

Recommended schema:

```json
{
  "world_style": "nostalgic summer anime realism",
  "palette": ["warm gold", "faded teal", "soft cream"],
  "lighting": "late afternoon haze with gentle backlight",
  "texture": "soft film grain, airy atmosphere",
  "camera_language": "slow drifting frames, occasional detail inserts",
  "continuity_subject": "young protagonist appears intermittently, not every shot",
  "do_not_break": [
    "do not switch era",
    "do not introduce harsh neon",
    "do not turn every frame into a portrait"
  ]
}
```

This stage becomes the source of consistency.
It replaces the old strategy of injecting full character description into every image prompt.

### Stage G. Anchor Images

Purpose:
- Create reusable visual anchors.

Anchor types:
1. protagonist anchor
2. environment anchor
3. symbolic anchor
4. palette anchor

Not every song needs all four.
Character-led songs may need protagonist anchors.
Atmospheric songs may rely more on environment and symbolic anchors.

### Stage H. Shot Prompt Generation

Purpose:
- Convert segment interpretation into final image prompt text.

Prompt inputs:
- global visual bible
- optional character anchor
- segment interpretation object
- style constraints

Prompt responsibility:
- Produce the final image-generation prompt for one shot.

Generation rules:
- Inject character continuity only if `character_needed=true`.
- Preserve global palette and world rules.
- Make shot composition explicit.
- Surface symbolic objects when relevant.
- Prefer cinematic language over generic descriptive stacking.

Prompt shape:

```json
{
  "segment_id": 3,
  "final_prompt": "empty rural station platform at dusk, wind lifting paper scraps, warm faded summer palette, soft backlight haze, lyrical loneliness, wide cinematic frame, no centered protagonist, nostalgic anime realism"
}
```

### Stage I. Variant Prompt Generation

Purpose:
- Generate alternate usable shots for repeated segments.

This stage should not create near-duplicates.

Allowed variation axes:
- shot distance
- framing
- foreground object
- lighting direction
- atmosphere density
- symbolic object emphasis
- subject presence / absence
- environmental layer

Disallowed variation axes:
- changing world setting
- changing era
- changing core palette family
- changing protagonist identity
- changing song meaning

Recommended schema:

```json
{
  "segment_id": 8,
  "base_intent": "chorus release with longing",
  "variants": [
    {
      "variant_id": 1,
      "change_axis": "environment",
      "prompt": "..."
    },
    {
      "variant_id": 2,
      "change_axis": "lighting",
      "prompt": "..."
    }
  ]
}
```

## 3. Prompt Families

The prompt system should be organized into families instead of one-off files.

### Family 1. Brief prompts
- collect and normalize user intent

### Family 2. Lyrics prompts
- generate lyrics
- generate section analysis

### Family 3. Visual interpretation prompts
- lyric meaning extraction
- segment visual planning

### Family 4. Visual bible prompts
- global world/style consistency

### Family 5. Anchor prompts
- protagonist anchor
- environment anchor
- symbolic anchor

### Family 6. Shot prompts
- segment-to-image prompt

### Family 7. Variant prompts
- repeated chorus and long-duration segment variants

## 4. Mapping to Current Codebase

### Existing modules

- `src/scene_analyzer.py`
  - should own Stage E
  - may partially own variant planning

- `src/scene_generator.py`
  - should own Stage H and Stage I execution
  - should stop assuming all scenes require full character anchor injection

- `src/style_map.py`
  - should support Stage F defaults and fallback language
  - should reduce hidden bias toward "single character" output

- `prompts/lyrics/*.txt`
  - should be extended to output both lyrics and section metadata

- `prompts/scene_analysis/*.txt`
  - should shift from plain scene description to structured visual interpretation

## 5. Recommended File Layout

```text
prompts/
  registry.yaml
  PROMPT_ARCHITECTURE.md
  brief/
    creative_brief_v1.txt
  lyrics/
    v3.0.txt
  music/
    v2.0.txt
  visual_interpretation/
    segment_planner_v1.txt
    visual_bible_v1.txt
  image/
    base_character_v2.txt
    environment_anchor_v1.txt
    symbolic_anchor_v1.txt
    shot_prompt_v1.txt
    shot_variants_v1.txt
```

## 6. Quality Rules

### A. Diversity rules

- Not all scenes should contain a human subject.
- Repeated chorus shots must vary by shot logic, not tiny pose changes.
- Environment and symbolic shots should be intentionally planned.

### B. Consistency rules

- Keep one coherent world, palette, and lighting grammar.
- Reuse protagonist identity only when the scene actually needs a person.
- Do not let fallback templates silently force portrait bias.

### C. Meaning rules

- Every image should answer: why this frame for this lyric?
- Prompt design should reflect lyric subtext, not only literal nouns.
- Symbolic imagery should be used when literal depiction is weak.

## 7. Rollout Plan

### Phase 1. Prompt architecture only

Goal:
- define schemas
- define prompt responsibilities
- define registry additions

### Phase 2. Structured scene analysis

Changes:
- update `scene_analyzer.py`
- emit richer `scenes.json`
- add explicit fields such as `visual_focus`, `character_needed`, `shot_type`, `symbolic_objects`

### Phase 3. Prompt assembly refactor

Changes:
- update `scene_generator.py`
- build final image prompts from structured scene data plus visual bible

### Phase 4. Variant system refactor

Changes:
- convert variants from "minor modifications" to "shot variants"

### Phase 5. Evaluation

Measure:
- percentage of scenes without centered human subject
- visual similarity across repeated segments
- lyric-to-image semantic match quality
- continuity stability when a protagonist is present

## 8. Immediate Next Steps

1. Introduce a new structured output format for scene analysis.
2. Add a visual bible generation step before scene image generation.
3. Add explicit `character_needed` and `visual_focus` fields to each scene.
4. Split image prompting into:
   - global anchor
   - shot prompt
   - variant prompt
5. Update prompt registry to include the new prompt families.

This architecture should be treated as the design reference for the next prompt refactor.
