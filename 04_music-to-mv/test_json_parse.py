"""Test and fix scene_analyzer.py LLM batch JSON parsing"""
import sys, json, re

# Simulate what MiniMax might return
test_cases = [
    # Case 1: normal JSON array
    '[{"id": 1, "desc": "test"}]',

    # Case 2: wrapped in ```json
    '```json\n[{"id": 1, "desc": "test"}]\n```',

    # Case 3: wrapped in ``` (no json)
    '```\n[{"id": 1, "desc": "test"}]\n```',

    # Case 4: with thinking tag
    '<think>thinking...</think>\n[{"id": 1, "desc": "test"}]',

    # Case 5: everything combined
    '<think>Let me analyze...</think>\n```json\n[{"id": 1, "desc": "test"}]\n```',

    # Case 6: multiline JSON
    '```json\n[\n  {"id": 1, "desc": "test"}\n]\n```',

    # Case 7: with trailing text
    '[{"id": 1, "desc": "test"}] That was the output.',
]

from src.scene_analyzer import SceneAnalyzer

for i, case in enumerate(test_cases):
    stripped = SceneAnalyzer._strip_think(case)
    extracted = SceneAnalyzer._extract_json_array(stripped)
    # Handle markdown
    if extracted.startswith("```"):
        lines = extracted.split("\n")
        extracted = "\n".join(lines[1:-1])
        extracted = SceneAnalyzer._extract_json_array(extracted)
    try:
        result = json.loads(extracted)
        print(f"Case {i+1}: OK -> {result}")
    except Exception as e:
        print(f"Case {i+1}: FAIL {e}")
        print(f"  extracted chars: {extracted[:100]}")
