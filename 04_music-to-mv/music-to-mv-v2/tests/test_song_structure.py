import unittest

from src.song_structure import select_song_structure


class TestSongStructure(unittest.TestCase):
    def test_adaptive_prefers_ancient_poem_for_chinese_style(self):
        structure = select_song_structure(
            theme="春雨",
            music_style="中国风",
            mood="梦幻",
            narrative_mode="mixed",
            chorus_energy="lifted",
        )

        self.assertEqual(structure.name, "ancient_poem")
        self.assertIn("[Refrain]", structure.sequence)

    def test_override_wins(self):
        custom = "[Intro] -> [Verse] -> [Outro]"
        structure = select_song_structure(override=custom)

        self.assertEqual(structure.name, "custom")
        self.assertEqual(structure.sequence, custom)

    def test_forced_mode_wins(self):
        structure = select_song_structure(mode="cinematic", music_style="中国风")

        self.assertEqual(structure.name, "cinematic")
        self.assertIn("[Instrumental Interlude]", structure.sequence)


if __name__ == "__main__":
    unittest.main()
