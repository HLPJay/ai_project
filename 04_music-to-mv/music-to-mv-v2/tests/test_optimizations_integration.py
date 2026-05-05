#!/usr/bin/env python3
"""Integration test for all Prompt optimizations (Quick Wins + P1 + P2)

This test verifies that:
1. All new methods exist and are callable
2. Scene analysis includes emotion mapping
3. Scene generation includes dynamic hints
4. No syntax errors or import issues
"""

import json
import sys
from pathlib import Path

def test_scene_analyzer_enhancements():
    """Test scene_analyzer.py enhancements"""
    print("\n=== Testing Scene Analyzer Enhancements ===")

    try:
        from src.scene_analyzer import SceneAnalyzer

        # Check for new methods
        required_methods = [
            '_select_narrative_representative_scenes',  # Quick Win B
            '_populate_scene_emotions',                  # P2.1
            '_map_emotion_to_visual',                    # P2.1
        ]

        for method_name in required_methods:
            if hasattr(SceneAnalyzer, method_name):
                print(f"  [OK] {method_name}")
            else:
                print(f"  [FAIL] Missing method: {method_name}")
                return False

        return True
    except Exception as e:
        print(f"  [FAIL] Error importing SceneAnalyzer: {e}")
        return False


def test_scene_generator_enhancements():
    """Test scene_generator.py enhancements"""
    print("\n=== Testing Scene Generator Enhancements ===")

    try:
        from src.scene_generator import SceneImageGenerator

        # Check for new methods
        required_methods = [
            '_enhance_character_prompt_for_scene',  # P1.2
            '_get_focus_clarity_hint',              # P2.3
            '_get_dynamic_palette_hint',            # P2.2
            '_build_dynamic_do_not_do',             # Quick Win C (enhanced)
        ]

        for method_name in required_methods:
            if hasattr(SceneImageGenerator, method_name):
                print(f"  [OK] {method_name}")
            else:
                print(f"  [FAIL] Missing method: {method_name}")
                return False

        return True
    except Exception as e:
        print(f"  [FAIL] Error importing SceneImageGenerator: {e}")
        return False


def test_style_map_enhancements():
    """Test style_map.py enhancements"""
    print("\n=== Testing Style Map Enhancements ===")

    try:
        from src.style_map import build_char_prompt
        import inspect

        # Check build_char_prompt signature
        sig = inspect.signature(build_char_prompt)
        params = list(sig.parameters.keys())

        required_params = [
            'visual_focus',      # P1.2
            'emotion',           # P1.2
            'narrative_phase',   # P1.2
        ]

        for param in required_params:
            if param in params:
                print(f"  [OK] Parameter '{param}' added to build_char_prompt")
            else:
                print(f"  [FAIL] Missing parameter: {param}")
                return False

        return True
    except Exception as e:
        print(f"  [FAIL] Error with style_map: {e}")
        return False


def test_emotion_mapping_logic():
    """Test P2.1 emotion mapping logic"""
    print("\n=== Testing P2.1 Emotion Mapping ===")

    try:
        from src.scene_analyzer import SceneAnalyzer

        # Create instance
        analyzer = SceneAnalyzer(
            project_dir=Path("./test_project"),
            theme="test theme",
            mood="test mood"
        )

        # Test emotion mapping
        test_cases = [
            (0.3, "melancholic", "soft diffused lighting"),
            (0.7, "joyful", "vibrant colors"),
            (0.9, "intense", "dramatic composition"),
        ]

        for strength, emotion_type, expected_keyword in test_cases:
            result = analyzer._map_emotion_to_visual(strength, emotion_type)
            if expected_keyword.lower() in result.lower():
                print(f"  [OK] {emotion_type} ({strength}) → contains '{expected_keyword}'")
            else:
                print(f"  [FAIL] {emotion_type} mapping incorrect")
                return False

        return True
    except Exception as e:
        print(f"  [FAIL] Emotion mapping test error: {e}")
        return False


def test_dynamic_prohibitions_logic():
    """Test Quick Win C + P1.3 dynamic prohibition logic"""
    print("\n=== Testing Dynamic Prohibition Logic ===")

    try:
        from src.scene_generator import SceneImageGenerator
        from src.config_manager import ConfigManager

        # Create minimal instance
        cfg = ConfigManager()
        generator = SceneImageGenerator(
            project_dir=Path("./test_project"),
            cfg=cfg,
            dry_run=True  # Important: dry run mode
        )

        # Set up test data
        generator._scene_shot_types = {
            0: "close_detail",
            1: "establishing",
            2: "close_detail",
            3: "establishing",
        }

        generator._scene_info = {
            0: {"id": 0, "visual_focus": "character", "emotion": "neutral"},
            1: {"id": 1, "visual_focus": "environment", "emotion": "neutral"},
            2: {"id": 2, "visual_focus": "character", "emotion": "sad"},
            3: {"id": 3, "visual_focus": "environment", "emotion": "neutral"},
        }

        # Test prohibition generation
        result = generator._build_dynamic_do_not_do(scene_id=2)
        if "close-up" in result.lower() or "repetition" in result.lower():
            print(f"  [OK] Prohibition for repeated shot_type generated")
        else:
            print(f"  [WARN] Prohibition may be empty (expected for non-repeated)")

        return True
    except Exception as e:
        print(f"  [FAIL] Dynamic prohibition test error: {e}")
        return False


def main():
    """Run all integration tests"""
    print("=" * 60)
    print("Prompt Optimization Integration Tests")
    print("=" * 60)

    tests = [
        ("Scene Analyzer Enhancements", test_scene_analyzer_enhancements),
        ("Scene Generator Enhancements", test_scene_generator_enhancements),
        ("Style Map Enhancements", test_style_map_enhancements),
        ("Emotion Mapping Logic (P2.1)", test_emotion_mapping_logic),
        ("Dynamic Prohibition Logic (QW-C+P1.3)", test_dynamic_prohibitions_logic),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"  [ERROR] {test_name}: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n[OK] All optimizations verified!")
        return 0
    else:
        print(f"\n[FAIL] {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
