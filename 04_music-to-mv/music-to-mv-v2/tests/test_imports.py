"""导入测试 — 验证所有模块可正常加载"""
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_config_manager():
    from src.config_manager import ConfigManager
    cfg = ConfigManager()
    assert cfg is not None
    print(f"  [OK] ConfigManager: provider={cfg.get('image_api_provider')}")


def test_project_manager():
    from src.project_manager import ProjectManager

    tmpdir = tempfile.mkdtemp()
    try:
        pm = ProjectManager.init_new("测试", "国风", "民谣", "温柔",
                                     workspace_root=tmpdir)
        assert pm.theme == "测试"
        assert pm.style == "国风"
        assert pm.music_style == "民谣"
        assert pm.mood == "温柔"
        assert len(pm.info["pipeline"]) == 9  # 9 steps

        # 测试暂停点
        pm.require_approval("test_step", {"a": "A", "b": "B"})
        assert pm.is_awaiting_approval is True
        pm.approve("a")
        assert pm.is_awaiting_approval is False
        assert pm.get_user_choice("test_step") == "a"

        # 测试步骤状态
        pm.update_step("① lyrics", "running", "测试中")
        assert pm.get_step_status("① lyrics")["status"] == "running"
        pm.update_step("① lyrics", "completed", "完成")
        assert pm.is_step_completed("① lyrics") is True

        print(f"  [OK] ProjectManager: {pm.project_name} ({pm.project_dir.name})")
    finally:
        shutil.rmtree(tmpdir)


def test_llm_logger():
    from src.llm.logger import LLMLogger

    tmpdir = tempfile.mkdtemp()
    try:
        logger = LLMLogger(tmpdir)

        # 记录成功调用
        logger.log_api_call("test", "model-x", "test prompt",
                           {"result": "ok"})

        # 记录失败调用
        logger.log_api_call("test", "model-x", "test prompt 2",
                           error="timeout")

        stats = logger.get_stats()
        assert stats["total_calls"] == 2
        print(f"  [OK] LLMLogger: {stats['total_calls']} calls, "
              f"{stats['total_tokens']} tokens")
    finally:
        shutil.rmtree(tmpdir)


def test_prompt_registry():
    from src.llm.registry import PromptRegistry

    reg = PromptRegistry()
    count = len(reg._templates)

    # 尝试获取 lyrics.generation
    template = reg.get_template("lyrics.generation")
    if template:
        print(f"  [OK] PromptRegistry: {count} templates loaded")
        print(f"     Default lyrics version: {template.version}")

        # 测试渲染
        rendered = template.render({
            "theme": "春天",
            "style": "国风",
            "music_style": "民谣",
            "mood": "温柔",
            "language": "中文",
        })
        assert "春天" in rendered
        assert "国风" in rendered
        print(f"     Render test OK ({len(rendered)} chars)")
    else:
        # 注册表没配时，手动注册
        reg.register("test.template", "Hello {{ name }}!", "v1.0")
        template = reg.get_template("test.template")
        rendered = template.render({"name": "World"})
        assert rendered == "Hello World!"
        print(f"  [OK] PromptRegistry: {count + 1} templates (fallback mode)")


def test_user_interaction():
    from src.project_manager import ProjectManager
    from src.interaction import UserInteraction
    import tempfile, shutil

    tmpdir = tempfile.mkdtemp()
    try:
        pm = ProjectManager.init_new("测试交互", workspace_root=tmpdir)

        # 设置暂停点
        UserInteraction.pause_step2(pm)
        assert pm.is_awaiting_approval is True

        # 处理用户选择
        action = UserInteraction.handle_choice(pm, "continue")
        assert action == "continue"
        assert pm.is_awaiting_approval is False

        # 再次设置，测试"自动模式"
        UserInteraction.pause_step2(pm)
        action = UserInteraction.handle_choice(pm, "a")
        assert action == "continue"

        print(f"  [OK] UserInteraction: handle_choice OK")
    finally:
        shutil.rmtree(tmpdir)


def test_mvpipeline_create():
    from src.pipeline import MVPipeline
    import tempfile, shutil

    tmpdir = tempfile.mkdtemp()
    try:
        pipeline = MVPipeline.create_new(
            theme="测试",
            style="国风",
            music_style="民谣",
            mood="温柔",
            auto_mode=True,
        )
        assert pipeline.pm is not None
        assert pipeline.pm.theme == "测试"
        assert pipeline.auto_mode is True
        print(f"  [OK] MVPipeline: created for '{pipeline.pm.project_name}'")
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    print("\n=== Music-to-MV v2 模块导入/功能测试 ===\n")

    tests = [
        ("ConfigManager", test_config_manager),
        ("ProjectManager", test_project_manager),
        ("LLMLogger", test_llm_logger),
        ("PromptRegistry", test_prompt_registry),
        ("UserInteraction", test_user_interaction),
        ("MVPipeline", test_mvpipeline_create),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            print(f"\n── {name} ──")
            func()
            print(f"  [PASS] {name} 通过")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name} 失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)
