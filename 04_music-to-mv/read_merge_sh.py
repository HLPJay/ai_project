"""Read merge_and_export.sh structure"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:/claude_code/我的github项目落地/ai_project/04_music-to-mv/scripts/merge_and_export.sh', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith('#'):
        print(f'L{i+1}: {s[:100]}')
    if 'function ' in s or '() {' in s:
        print(f'L{i+1}: {s[:80]}')
    if s == '# ═══════' or s.startswith('main()'):
        print(f'L{i+1}: {s}')
