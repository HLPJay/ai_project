"""Add Python v2 fallback to run_merge_and_export in scripts_bridge.py"""
with open('src/scripts_bridge.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''def run_merge_and_export(project_dir: str, step: str = None, timeout: int = 600) -> subprocess.CompletedProcess:
    """调用 merge_and_export.sh（Step 09-11）"""
    args = ["--step", step] if step else None
    return run_script("merge_and_export.sh", project_dir, args, timeout=timeout)'''

new_func = '''def run_merge_and_export(project_dir: str, step: str = None, timeout: int = 600) -> subprocess.CompletedProcess:
    """调用 merge_and_export.sh（Step 09-11）

    策略：
      1. 原版 merge_and_export.sh（需要 bash）
      2. Python v2 MVExporter（新实现）
    """
    try:
        args = ["--step", step] if step else None
        return run_script("merge_and_export.sh", project_dir, args, timeout=timeout)
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"  [Bridge] merge_and_export.sh 执行失败 ({type(e).__name__}), 回退到 Python v2...")

    try:
        from src.exporter import MVExporter
        exporter = MVExporter(project_dir)
        exporter.export_all()
        return subprocess.CompletedProcess(
            args=["python3", "-m", "src.exporter"],
            returncode=0,
        )
    except Exception as e2:
        raise RuntimeError(f"所有导出策略失败: {e2}") from e2'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open('src/scripts_bridge.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: run_merge_and_export updated with v2 fallback')
else:
    print('ERROR: pattern not found')
    idx = content.find('def run_merge_and_export')
    if idx >= 0:
        print(content[idx:idx+250])
