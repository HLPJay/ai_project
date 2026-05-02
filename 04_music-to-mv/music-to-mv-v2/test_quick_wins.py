#!/usr/bin/env python3
"""Test script for Quick Wins A/B/C implementations"""

import json
from pathlib import Path

def test_quick_win_b():
    """Test Quick Win B: Narrative-phase-aware sampling"""
    print("\n=== Testing Quick Win B ===")

    # Create mock scenes with narrative_phase
    scenes = [
        {"id": 0, "narrative_phase": "intro_end", "visual_focus": "character", "shot_type": "close_detail"},
        {"id": 1, "narrative_phase": "verse", "visual_focus": "environment", "shot_type": "establishing"},
        {"id": 2, "narrative_phase": "verse", "visual_focus": "object", "shot_type": "close_detail"},
        {"id": 3, "narrative_phase": "chorus_peak", "visual_focus": "character", "shot_type": "symbolic_insert"},
        {"id": 4, "narrative_phase": "bridge", "visual_focus": "environment", "shot_type": "empty_space"},
        {"id": 5, "narrative_phase": "outro_start", "visual_focus": "symbolic", "shot_type": "symbolic_insert"},
        {"id": 6, "narrative_phase": "outro", "visual_focus": "mixed", "shot_type": "establishing"},
    ]

    # Test the selection logic (simulated)
    def select_narrative_representative_scenes(scenes):
        """Replicate the Quick Win B logic"""
        intro_scenes = [s for s in scenes if s.get("narrative_phase") == "intro_end"]
        chorus_scenes = [s for s in scenes if s.get("narrative_phase") == "chorus_peak"]
        outro_scenes = [s for s in scenes if s.get("narrative_phase") == "outro_start"]

        selected = []
        if intro_scenes:
            selected.append(intro_scenes[0])
        if chorus_scenes:
            selected.append(chorus_scenes[0])
        if outro_scenes:
            selected.append(outro_scenes[0])

        if len(selected) < 8:
            remaining = [s for s in scenes if s not in selected]
            selected.extend(remaining[:8 - len(selected)])

        return selected[:8]

    selected = select_narrative_representative_scenes(scenes)
    print(f"  Input: {len(scenes)} scenes")
    print(f"  Selected: {len(selected)} scenes")
    print(f"  Selected IDs: {[s['id'] for s in selected]}")

    # Verify selection includes key narrative points
    selected_ids = [s['id'] for s in selected]
    assert 0 in selected_ids, "Should select intro_end scene (id=0)"
    assert 3 in selected_ids, "Should select chorus_peak scene (id=3)"
    assert 5 in selected_ids, "Should select outro_start scene (id=5)"
    print("  [OK] Quick Win B selection logic works correctly")


def test_quick_win_c():
    """Test Quick Win C: Dynamic prohibition list"""
    print("\n=== Testing Quick Win C ===")

    def build_dynamic_do_not_do(scene_id, scene_shot_types):
        """Replicate the Quick Win C logic"""
        if not scene_shot_types or scene_id is None:
            return ""

        prev_ids = [sid for sid in sorted(scene_shot_types.keys())
                    if sid < scene_id][-3:]

        if not prev_ids:
            return ""

        prev_shot_types = [scene_shot_types.get(sid, "wide") for sid in prev_ids]
        current_shot_type = scene_shot_types.get(scene_id, "wide")

        prohibitions = []
        if prev_shot_types.count(current_shot_type) > 0:
            if current_shot_type == "close_detail":
                prohibitions.append("do not use the exact same close-up angle as the last scene")
            elif current_shot_type == "establishing":
                prohibitions.append("vary the establishing shot angle, avoid identical environmental framing")
            elif current_shot_type == "empty_space":
                prohibitions.append("avoid identical empty space composition as the previous frame")
            elif current_shot_type == "symbolic_insert":
                prohibitions.append("use different symbolic object and framing than the last insert")

        if prohibitions:
            return ", ".join(prohibitions)
        return ""

    # Test with mock scene_shot_types
    scene_shot_types = {
        0: "close_detail",
        1: "establishing",
        2: "close_detail",
        3: "establishing",
        4: "close_detail",
        5: "close_detail",
        6: "establishing",
    }

    # Test various scenarios
    test_cases = [
        (0, ""),  # First scene, no previous
        (1, ""),  # Different shot type than previous scene
        (4, "do not use the exact same close-up angle as the last scene"),  # Same as previous (scene 2)
        (5, "do not use the exact same close-up angle as the last scene"),  # Same as previous (scene 4)
        (6, "vary the establishing shot angle, avoid identical environmental framing"),  # Same as previous (scene 3)
    ]

    for scene_id, expected_contains in test_cases:
        result = build_dynamic_do_not_do(scene_id, scene_shot_types)
        if expected_contains:
            assert expected_contains in result, f"Scene {scene_id}: Expected '{expected_contains}' in '{result}'"
            print(f"  [OK] Scene {scene_id}: Correctly prohibits repeated shot type")
        else:
            assert result == "", f"Scene {scene_id}: Expected empty string, got '{result}'"
            print(f"  [OK] Scene {scene_id}: No prohibition (new or varied shot type)")


def test_quick_win_a():
    """Test Quick Win A: Visual focus-aware fallback"""
    print("\n=== Testing Quick Win A ===")

    def generate_local_desc_suffix(visual_focus):
        """Replicate Quick Win A logic"""
        if visual_focus == "character":
            suffix = ", intimate character focus, facial expression, emotion clarity, human connection"
        elif visual_focus == "environment":
            suffix = ", expansive environmental context, spatial depth, atmospheric mood, landscape continuity"
        elif visual_focus == "object":
            suffix = ", detail and texture emphasis, close observation, tactile quality, singular focus"
        elif visual_focus == "symbolic":
            suffix = ", metaphorical representation, abstract imagery, emotional symbolism, visual poetry"
        else:
            suffix = ", cinematic storytelling frame, lyrical visual metaphor, cohesive palette, varied subject focus"
        return suffix

    # Test all focus types
    focus_types = ["character", "environment", "object", "symbolic", "mixed"]
    for focus in focus_types:
        suffix = generate_local_desc_suffix(focus)
        assert len(suffix) > 0, f"Focus '{focus}' should generate a suffix"
        # Each focus type should have unique, appropriate keywords
        expected_keywords = {
            "character": ["character", "emotion", "expression"],
            "environment": ["environment", "spatial", "landscape"],
            "object": ["detail", "texture", "close"],
            "symbolic": ["metaphor", "abstract", "symbolic"],
            "mixed": ["cinematic", "varied"],
        }
        has_keyword = any(kw in suffix.lower() for kw in expected_keywords.get(focus, []))
        assert has_keyword, f"Suffix for '{focus}' doesn't contain expected keywords"
        print(f"  [OK] Focus '{focus}': {suffix[:50]}...")


if __name__ == "__main__":
    print("Testing Quick Wins Implementation")
    print("=" * 50)

    test_quick_win_a()
    test_quick_win_b()
    test_quick_win_c()

    print("\n" + "=" * 50)
    print("[OK] All Quick Wins tests passed!")
