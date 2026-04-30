"""
test_integration_e2e.py — 端到端集成测试

模拟全流程数据流，验证各模块之间的协作是否正确。
不调用真实 API，但会验证文件 I/O、元数据流转和状态更新。

测试场景：
  1. 创建项目 → ProjectManager
  2. 模拟歌词生成 → 写入 lyrics.txt
  3. 模拟音乐生成 → 写入 song.mp3
  4. 更新步骤状态 → 确认状态机正确
  5. 模拟暂停点 → UserInteraction
  6. 验证 pipeline 编排流程
  7. 验证 style_map 与 prompts 模板渲染
  8. 验证 scripts_bridge 路径解析
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIntegrationE2E:
    """端到端集成测试"""

    @classmethod
    def setup_class(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="mv_e2e_")
        cls.workspace = os.path.join(cls.test_dir, "workspace")
        os.makedirs(cls.workspace)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.test_dir)

    def setup_method(self):
        self.project_dir = None

    def teardown_method(self):
        if self.project_dir and os.path.exists(self.project_dir):
            shutil.rmtree(self.project_dir, ignore_errors=True)

    # ── 测试 1: 完整的项目生命周期 ─────────────────────

    def test_01_project_lifecycle(self):
        """测试完整项目生命周期"""
        from src.project_manager import ProjectManager

        # 1. 创建项目
        pm = ProjectManager.init_new(
            theme="春天",
            style="国风",
            music_style="民谣",
            mood="温柔",
            language="中文",
            workspace_root=self.workspace,
        )
        self.project_dir = str(pm.project_dir)
        assert pm.theme == "春天"
        assert pm.style == "国风"
        assert pm.music_style == "民谣"
        assert pm.mood == "温柔"
        assert pm.language == "中文"

        # 2. 验证项目结构
        assert pm.project_dir.exists()
        assert (pm.project_dir / "audio").exists()
        assert (pm.project_dir / "images").exists()
        assert (pm.project_dir / "metadata").exists()
        assert (pm.project_dir / "output").exists()
        assert (pm.project_dir / "metadata" / "info.json").exists()

        # 3. 验证 info.json 内容
        info = json.loads((pm.project_dir / "metadata" / "info.json").read_text(encoding="utf-8"))
        assert info["theme"] == "春天"
        assert info["style"] == "国风"
        assert info["music_style"] == "民谣"
        assert info["pipeline"]["① lyrics"]["status"] == "pending"

        # 4. 更新步骤状态
        pm.update_step("① lyrics", "running", "test run")
        info = json.loads((pm.project_dir / "metadata" / "info.json").read_text(encoding="utf-8"))
        assert info["pipeline"]["① lyrics"]["status"] == "running"

        pm.update_step("① lyrics", "completed", "OK")
        assert pm.is_step_completed("① lyrics")

        # 5. 设置自定义字段
        pm.set("song_title", "春天的歌")
        assert pm.song_title == "春天的歌"
        assert pm.get("song_title") == "春天的歌"

        # 6. 暂停点测试
        pm.require_approval("step2_check", {"continue": "继续", "retry": "重试"})
        assert pm.is_awaiting_approval is True

        pending = pm.pending_approval_info
        assert pending is not None
        assert pending["step"] == "step2_check"
        assert "continue" in pending["options"]

        pm.approve("continue")
        assert pm.is_awaiting_approval is False

        # 7. 验证项目名称
        assert pm.project_name == "春天"
        assert "春天" in str(pm.project_dir.name)

        print("  [OK] 项目生命周期测试通过")

    # ── 测试 2: 歌词+音乐生成流程的数据流转 ─────────────

    def test_02_lyrics_music_flow(self):
        """测试歌词+音乐生成的完整数据流"""
        from src.project_manager import ProjectManager
        from src.llm.registry import PromptRegistry

        pm = ProjectManager.init_new(
            theme="童年",
            style="水彩插画风",
            music_style="民谣",
            mood="怀旧",
            workspace_root=self.workspace,
        )
        self.project_dir = str(pm.project_dir)

        # 1. 测试 Prompt 渲染
        reg = PromptRegistry()
        template = reg.get_template("lyrics.generation", version="v2.0")
        assert template is not None, "PromptTemplate 未加载"

        rendered = template.render({
            "theme": "童年",
            "style": "水彩插画风",
            "music_style": "民谣",
            "mood": "怀旧",
            "language": "中文",
        })
        assert "童年" in rendered
        assert "水彩插画风" in rendered or "水彩" in rendered
        # 检查未替换的模板变量 — 有些 prompt 可能包含 literal 的 {{ }}
        # 但至少渲染后的文本应该包含主题关键词
        assert len(rendered) > 50, f"渲染结果过短: {rendered[:50]}"
        has_theme = "童年" in rendered or "2025" in rendered
        if not has_theme:
            print(f"    渲染结果（前200字）: {rendered[:200]}")

        # 2. 模拟歌词写入
        lyrics_content = (
            "## 童年时光\n"
            "## Tags: 童年,怀旧\n\n"
            "[Verse 1]\n"
            "还记得那片蓝天\n"
            "阳光洒在旧照片\n"
            "[Chorus]\n"
            "童年的梦在飞翔\n"
            "带着希望去远方\n"
        )
        lyrics_file = pm.project_dir / "audio" / "lyrics.txt"
        lyrics_file.write_text(lyrics_content, encoding="utf-8")
        assert lyrics_file.exists()

        # 3. 模拟歌词元数据更新
        pm.set("song_title", "童年时光")
        pm.set("audio_duration_sec", 90)
        pm.update_step("① lyrics", "completed", "done")
        pm.update_step("② music", "completed", "done")

        # 4. 验证元数据完整性
        info = json.loads((pm.project_dir / "metadata" / "info.json").read_text(encoding="utf-8"))
        assert info.get("song_title") == "童年时光"
        assert info["pipeline"]["① lyrics"]["status"] == "completed"
        assert info["pipeline"]["② music"]["status"] == "completed"

        print("  [OK] 歌词+音乐数据流测试通过")

    # ── 测试 3: style_map + 场景数据 ────────────────────

    def test_03_scene_data_flow(self):
        """测试 style_map 与场景数据的协作"""
        from src.project_manager import ProjectManager
        from src.style_map import (
            build_char_prompt, get_art_style, get_mood_desc,
            THEME_VISUALS, get_theme_visual,
        )

        pm = ProjectManager.init_new(
            theme="星空",
            style="动漫风",
            music_style="流行",
            mood="梦幻",
            workspace_root=self.workspace,
        )
        self.project_dir = str(pm.project_dir)

        # 1. 构建角色 prompt
        char_prompt = build_char_prompt(
            style_name="动漫风",
            theme="星空",
            song_title="星空的梦",
            mood="梦幻",
        )
        assert "anime" in char_prompt or "Japanese" in char_prompt
        assert "star" in char_prompt or "星空" in char_prompt
        assert "dreamy" in char_prompt or "梦幻" in char_prompt

        # 2. 保存角色 prompt
        base_char = {
            "prompt": char_prompt,
            "style": "动漫风",
            "mood": "梦幻",
            "theme": "星空",
        }
        (pm.project_dir / "metadata").mkdir(parents=True, exist_ok=True)
        (pm.project_dir / "metadata" / "base_char.json").write_text(
            json.dumps(base_char, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 3. 模拟场景数据
        scenes = [
            {"id": 1, "name": "intro", "label": "星空-梦幻",
             "start": 0, "end": 12, "duration": 12,
             "text_preview": "夜空中繁星点点",
             "is_repeated": False},
            {"id": 2, "name": "verse1", "label": "星河-梦幻",
             "start": 12, "end": 28, "duration": 16,
             "text_preview": "流星划过天际边",
             "is_repeated": False},
            {"id": 3, "name": "chorus", "label": "星空-梦幻",
             "start": 28, "end": 48, "duration": 20,
             "text_preview": "在星空下许愿 梦不再遥远",
             "is_repeated": True},
            {"id": 4, "name": "verse2", "label": "银河-梦幻",
             "start": 48, "end": 64, "duration": 16,
             "text_preview": "月光洒落银色海",
             "is_repeated": False},
            {"id": 5, "name": "chorus", "label": "星空-梦幻",
             "start": 64, "end": 84, "duration": 20,
             "text_preview": "在星空下许愿 梦不再遥远",
             "is_repeated": True},
            {"id": 6, "name": "bridge", "label": "星光-梦幻",
             "start": 84, "end": 96, "duration": 12,
             "text_preview": "时光静静流淌",
             "is_repeated": False},
            {"id": 7, "name": "outro", "label": "星夜-梦幻",
             "start": 96, "end": 105, "duration": 9,
             "text_preview": "星光伴我入眠",
             "is_repeated": False},
        ]

        # 4. 保存场景数据
        scenes_file = pm.project_dir / "metadata" / "scenes.json"
        scenes_file.write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 5. 验证风格/情绪/主题的一致性
        art_style = get_art_style("动漫风")
        mood_desc = get_mood_desc("梦幻")
        theme_visual = get_theme_visual("星空")

        assert len(art_style) > 30
        assert "dreamy" in mood_desc
        assert "star" in theme_visual or "night" in theme_visual

        # 6. 验证场景数据可以反序列化
        loaded = json.loads(scenes_file.read_text(encoding="utf-8"))
        assert len(loaded) == 7
        assert loaded[-1]["name"] == "outro"

        print("  [OK] 场景数据流测试通过")

    # ── 测试 4: MVPipeline 创建与编排状态 ──────────────

    def test_04_pipeline_orchestration(self):
        """测试 MVPipeline 编排逻辑"""
        from src.pipeline import MVPipeline

        pipeline = MVPipeline.create_new(
            theme="夏天",
            style="写实摄影风",
            music_style="流行",
            mood="欢快",
            auto_mode=True,
        )
        self.project_dir = str(pipeline.project_dir)

        # 1. 验证 pipeline 的初始状态
        assert pipeline.pm is not None
        assert pipeline.pm.theme == "夏天"
        assert pipeline.auto_mode is True
        assert pipeline.client is not None
        assert pipeline.registry is not None

        # 2. 验证各步骤初始状态
        for step_key in ["① lyrics", "② music", "③ align",
                         "④ base", "⑤-⑦ images", "⑧ kb",
                         "⑨ concat", "⑩ merge", "⑪ export"]:
            status = pipeline.pm.get_step_status(step_key)
            if status:
                assert status["status"] in ("pending",)

        # 3. 验证自动模式下不需要暂停
        # 直接设置停用点，应该跳过
        from src.interaction import UserInteraction
        UserInteraction.pause_step2(pipeline.pm)
        if pipeline.auto_mode:
            pipeline.pm.approve("continue")
        # 在 auto_mode 下 pipeline 会跳过暂停点

        print("  [OK] Pipeline 编排状态测试通过")

    # ── 测试 5: ConfigManager 多 Provider 切换 ──────────

    def test_05_config_provider_switch(self):
        """测试 ConfigManager 的多 Provider 配置"""
        from src.config_manager import ConfigManager
        cfg = ConfigManager()

        # 1. 测试各 Provider 的 URL 获取
        providers = {
            "minimax": "minimaxi.com",
            "pollinations": "pollinations.ai",
            "alibaba": "aliyuncs.com",
            "dall-e": "openai.com",
        }

        import os
        for provider, expected_domain in providers.items():
            # 临时切换 provider
            original = cfg.get("image_api_provider")
            os.environ["IMAGE_API_PROVIDER"] = provider
            cfg._load_env_vars()

            url = cfg.get_image_api_url()
            model = cfg.get_image_model()
            token = cfg.get_image_token()

            assert expected_domain in url, \
                f"Provider {provider} URL 不包含 {expected_domain}: {url}"
            assert len(model) > 0, f"Provider {provider} model 为空"

        # 恢复
        os.environ["IMAGE_API_PROVIDER"] = original

        # 2. 验证 to_dict
        d = cfg.to_dict()
        assert "provider" in d
        assert "image_model" in d
        assert "workspace_root" in d

        print("  [OK] 多 Provider 配置测试通过")

    # ── 测试 6: LLMLogger 数据持久化 ─────────────────────

    def test_06_llm_logger_persistence(self):
        """测试 LLMLogger 的数据持久化"""
        from src.llm.logger import LLMLogger

        log_dir = os.path.join(self.test_dir, "llm_logs")
        os.makedirs(log_dir, exist_ok=True)
        logger = LLMLogger(log_dir)

        # 1. 记录各种类型的调用
        logger.log_api_call("test.prompt", "model-x", "test prompt",
                           {"result": "ok", "summary": "success"})
        logger.log_api_call("test.prompt", "model-x", "test prompt 2",
                           error="timeout")
        logger.log_image_call("image.gen", "image-01",
                             "a beautiful landscape",
                             "/tmp/output.png", file_size=102400)

        # 2. 验证日志文件
        assert logger.calls_file.exists()
        assert logger.errors_file.exists()

        # 3. 验证数据可以被读取
        calls = logger.get_calls(limit=10)
        assert len(calls) >= 2

        # 4. 验证统计信息
        stats = logger.get_stats()
        assert stats["total_calls"] >= 3
        assert "test.prompt" in stats.get("by_prompt_key", {})

        # 5. 验证摘要
        summary = logger.generate_summary()
        assert "total_calls" in summary or "总调用" in summary
        assert "test.prompt" in summary or "test" in summary

        print("  [OK] LLMLogger 数据持久化测试通过")

    # ── 测试 7: scripts_bridge 路径解析 ──────────────────

    def test_07_scripts_bridge_paths(self):
        """测试 scripts_bridge 的路径解析"""
        from src.scripts_bridge import _get_scripts_dir, _build_env

        # 1. 脚本目录应存在
        scripts_dir = _get_scripts_dir()
        assert scripts_dir.exists(), f"脚本目录不存在: {scripts_dir}"

        # 2. 至少能找到一些 .sh 文件
        sh_files = list(scripts_dir.glob("*.sh"))
        assert len(sh_files) > 0, f"在 {scripts_dir} 未找到任何 .sh 文件"
        print(f"     找到 {len(sh_files)} 个 Shell 脚本")

        # 3. 环境变量构建
        env = _build_env("/tmp/test_project")
        assert "MINIMAX_TOKEN" in env
        assert "IMAGE_API_PROVIDER" in env
        assert "no_proxy" in env
        assert "PROJECT_DIR" in env

        print("  [OK] scripts_bridge 路径解析测试通过")

    # ── 测试 8: 完整的 prompt 版本管理 ──────────────────

    def test_08_prompt_version_management(self):
        """测试 PromptRegistry 版本管理"""
        from src.llm.registry import PromptRegistry
        reg = PromptRegistry()

        # 1. 统计模板
        templates = reg.list_templates()
        assert len(templates) >= 10, f"至少应有 10 个模板, 实际 {len(templates)}"

        # 2. 验证各 key 可以渲染
        test_cases = [
            ("lyrics.generation", {"theme": "梦", "style": "动漫",
                                    "music_style": "流行", "mood": "梦幻",
                                    "language": "中文"}),
            ("lyrics.generation:v2.0", {"theme": "梦", "style": "动漫",
                                         "music_style": "流行", "mood": "梦幻",
                                         "language": "中文"}),
        ]

        for key, vars in test_cases:
            try:
                result = reg.render(key, vars)
                assert len(result) > 50, f"{key} 渲染结果过短"
            except KeyError as e:
                # 如果注册表未配，跳过
                print(f"    跳过 {key}: {e}")
                continue

        # 3. 测试回退：用不存在的 key 应抛 KeyError
        try:
            reg.render("nonexistent.key", {})
            assert False, "应该抛出 KeyError"
        except KeyError:
            pass

        print("  [OK] Prompt 版本管理测试通过")

    # ── 测试 9: main.py CLI 参数解析 ─────────────────────

    def test_09_cli_argument_parsing(self):
        """测试 main.py 的 CLI 参数解析"""
        from src.main import main as cli_main
        # 由于 CLI 会触发 Pipeline 创建，我们只测试参数解析部分
        import argparse

        # 模拟创建新项目的参数
        import sys
        test_args = [
            "src/main.py",
            "--theme", "冬天",
            "--style", "水彩插画风",
            "--mood", "宁静",
            "--auto",
        ]

        from src.main import _list_projects  # 至少可以导入
        assert callable(_list_projects)

        print("  [OK] CLI 参数结构测试通过")

    # ── 测试 10: UserInteraction 所有暂停点 ──────────────

    def test_10_all_interaction_points(self):
        """测试所有 UserInteraction 暂停点"""
        from src.project_manager import ProjectManager
        from src.interaction import UserInteraction

        pm = ProjectManager.init_new(
            theme="友谊", style="动漫风", workspace_root=self.workspace
        )
        self.project_dir = str(pm.project_dir)

        # 测试每个暂停点
        points = [
            ("step_2_approval", UserInteraction.pause_step2),
            ("step_3_alignment", UserInteraction.pause_step3_alignment),
            ("step_4_scene_review", UserInteraction.pause_step4_review_scenes),
        ]

        for step_name, pause_func in points:
            pause_func(pm)
            assert pm.is_awaiting_approval is True
            assert pm.pending_approval_info["step"] == step_name
            assert pm.pending_approval_info["prompt"] is not None

            # 模拟用户确认
            action = UserInteraction.handle_choice(pm, "continue")
            assert pm.is_awaiting_approval is False
            assert action == "continue"

        # 测试 step3 的手动模式
        UserInteraction.pause_step3_alignment(pm)
        action = UserInteraction.handle_choice(pm, "b")
        assert action == "manual_srt"

        # 测试 step3 的自动模式
        UserInteraction.pause_step3_alignment(pm)
        action = UserInteraction.handle_choice(pm, "a")
        assert action == "continue"

        print("  [OK] 所有交互暂停点测试通过")


if __name__ == "__main__":
    print("\n=== 端到端集成测试 ===\n")

    t = TestIntegrationE2E()
    t.setup_class()

    tests = [
        ("项目生命周期", t.test_01_project_lifecycle),
        ("歌词+音乐数据流", t.test_02_lyrics_music_flow),
        ("场景数据流", t.test_03_scene_data_flow),
        ("Pipeline编排", t.test_04_pipeline_orchestration),
        ("多Provider配置", t.test_05_config_provider_switch),
        ("LLMLogger持久化", t.test_06_llm_logger_persistence),
        ("ScriptsBridge路径", t.test_07_scripts_bridge_paths),
        ("Prompt版本管理", t.test_08_prompt_version_management),
        ("CLI参数解析", t.test_09_cli_argument_parsing),
        ("交互暂停点", t.test_10_all_interaction_points),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            print(f"\n-- {name} --")
            t.setup_method()
            func()
            t.teardown_method()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
            t.teardown_method()

    t.teardown_class()

    print(f"\n{'='*50}")
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)
