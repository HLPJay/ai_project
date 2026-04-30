"""Read original generate_llm_report.py"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
with open('D:/claude_code/我的github项目落地/ai_project/04_music-to-mv/scripts/generate_llm_report.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(min(115, len(lines))):
    print(lines[i], end='')
