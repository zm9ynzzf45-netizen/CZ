import json
import unittest
from unittest import mock

from app.config import config
from app.services import cz


class CzStudioTest(unittest.TestCase):
    def test_clip_plan_rounds_up(self):
        self.assertEqual(cz.clip_plan(30, 10), [10, 10, 10])
        self.assertEqual(cz.clip_plan(15, 10), [10, 10])
        self.assertEqual(cz.clip_plan(5, 5), [5])

    def test_prompt_contains_briefing(self):
        prompt = cz.build_plan_prompt({
            "niche": "Katzen", "length": 30, "clip": 10, "idea": "Katze rettet Stadt",
            "trend": {"name": "Fake-Doku", "desc": "Tierfilm"},
        })
        self.assertIn("Nische: Katzen", prompt)
        self.assertIn("Fake-Doku", prompt)
        self.assertIn("3 Clips à 10 s", prompt)

    def test_parse_plan_pads_and_trims_clips(self):
        text = "Hier: " + json.dumps({"title": "T", "script": "S", "clips": ["a", "b"]})
        self.assertEqual(cz.parse_plan(text, 3)["clips"], ["a", "b", "b"])
        self.assertEqual(cz.parse_plan(text, 1)["clips"], ["a"])
        with self.assertRaises(ValueError):
            cz.parse_plan("kein json", 2)

    def test_build_plan_uses_llm(self):
        reply = json.dumps({"title": "T", "script": "S", "clips": ["p1"]})
        with mock.patch("app.services.llm._generate_response", return_value=reply):
            plan = cz.build_plan({"niche": "Gym", "length": 5, "clip": 5})
        self.assertEqual(plan["clips"], ["p1"])
        with self.assertRaises(ValueError):
            cz.build_plan({"niche": ""})

    def test_video_params_use_higgsfield_and_plan(self):
        params = cz.build_video_params({
            "clip": 10, "voice": "de-DE-ConradNeural-Male", "subs": False,
            "plan": {"title": "Titel", "script": "Text", "clips": ["c1", "c2"]},
        })
        self.assertEqual(params.video_source, "higgsfield")
        self.assertEqual(params.video_terms, ["c1", "c2"])
        self.assertEqual(params.video_script, "Text")
        self.assertEqual(params.video_clip_duration, 10)
        self.assertEqual(params.voice_name, "de-DE-ConradNeural-Male")
        self.assertFalse(params.subtitle_enabled)
        with self.assertRaises(ValueError):
            cz.build_video_params({"plan": {"script": "", "clips": []}})

    def test_settings_validate_and_save(self):
        saved = dict(config.app)
        try:
            with mock.patch.object(config, "save_config"):
                status = cz.save_settings({
                    "llm_provider": "anthropic", "llm_api_key": "k",
                    "higgsfield_api_key": "id:secret",
                })
                self.assertTrue(status["llm_ready"])
                self.assertTrue(status["higgsfield_ready"])
                with self.assertRaises(ValueError):
                    cz.save_settings({"higgsfield_api_key": "no-colon"})
                with self.assertRaises(ValueError):
                    cz.save_settings({"llm_provider": "unknown"})
        finally:
            config.app.clear()
            config.app.update(saved)

    def test_projects_and_trends_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cz.utils, "storage_dir", return_value=tmp):
            self.assertTrue(cz.get_trends()["examples"])
            cz.save_trends([{"name": "A", "desc": "d"}, {"name": ""}], "heute")
            self.assertEqual([t["name"] for t in cz.get_trends()["items"]], ["A"])
            project = cz.save_project({"name": "P", "inputs": {"niche": "x"}})
            cz.save_project({"id": project["id"], "task_id": "t1"})
            listed = cz.list_projects()
            self.assertEqual(listed[0]["task_id"], "t1")
            self.assertEqual(listed[0]["name"], "P")
            cz.delete_project(project["id"])
            self.assertEqual(cz.list_projects(), [])
            with self.assertRaises(ValueError):
                cz.save_project({"id": "../.."})


if __name__ == "__main__":
    unittest.main()
