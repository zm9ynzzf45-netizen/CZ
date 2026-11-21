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

    def test_english_language_switches_voice_and_prompt(self):
        params = cz.build_video_params({
            "lang": "en", "voice": "de-DE-KatjaNeural-Female",
            "plan": {"title": "T", "script": "Text", "clips": ["c1"]},
        })
        self.assertEqual(params.video_language, "en-US")
        self.assertEqual(params.voice_name, "en-US-JennyNeural-Female")
        prompt = cz.build_plan_prompt({"niche": "x", "lang": "en"})
        self.assertIn("englischer Sprechertext", prompt)
        self.assertIn("deutscher Sprechertext", cz.build_plan_prompt({"niche": "x"}))

    def test_trend_details_reach_plan_prompt(self):
        prompt = cz.build_plan_prompt({"niche": "x", "trend": {
            "name": "N", "desc": "D", "hook": "H1", "format": "F1", "prompt": "P1"}})
        for part in ("Trend-Hook: H1", "Trend-Aufbau: F1", "Trend-Beispielprompt: P1"):
            self.assertIn(part, prompt)

    def test_parse_trends_sorts_clamps_and_limits(self):
        items = [{"name": f"T{i}", "score": i} for i in range(15)] + [{"name": ""}, {"name": "X", "score": "x"}]
        trends = cz.parse_trends("vorweg " + json.dumps({"items": items}))
        self.assertEqual(len(trends), 10)
        self.assertIn(trends[0]["name"], {"T10", "T11", "T12", "T13", "T14"})
        self.assertEqual(trends[0]["score"], 10)
        with self.assertRaises(ValueError):
            cz.parse_trends(json.dumps({"items": []}))

    def test_generate_trends_saves_with_source(self):
        import tempfile
        reply = json.dumps({"items": [{"name": "A", "score": 7, "desc": "d"}]})
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cz.utils, "storage_dir", return_value=tmp), \
                mock.patch("app.services.llm._generate_response", return_value=reply):
            data = cz.generate_trends("Katzen", "TikTok")
            self.assertEqual(data["source"], "KI-Einschätzung")
            self.assertEqual(cz.get_trends()["items"][0]["name"], "A")


class CzUpdateTest(unittest.TestCase):
    def _git(self, cwd, *args):
        import subprocess
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=cwd, check=True, capture_output=True)

    def test_update_pulls_new_commits_and_refuses_local_changes(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            remote, work, clone = (os.path.join(tmp, n) for n in ("remote.git", "work", "clone"))
            self._git(tmp, "init", "--bare", "-b", "main", remote)
            self._git(tmp, "clone", remote, work)
            open(os.path.join(work, "a.txt"), "w").write("1")
            self._git(work, "add", "a.txt"); self._git(work, "commit", "-m", "first")
            self._git(work, "push", "origin", "main")
            self._git(tmp, "clone", remote, clone)
            with mock.patch.object(cz, "_repo_dir", return_value=clone), \
                    mock.patch.object(cz, "_uv_binary", return_value="true"):
                self.assertFalse(cz.run_update()["updated"])
                open(os.path.join(work, "a.txt"), "w").write("2")
                self._git(work, "commit", "-am", "second change"); self._git(work, "push")
                result = cz.run_update()
                self.assertTrue(result["updated"])
                self.assertIn("second change", result["changes"])
                self.assertEqual(open(os.path.join(clone, "a.txt")).read(), "2")
                open(os.path.join(clone, "a.txt"), "w").write("local edit")
                with self.assertRaises(RuntimeError):
                    cz.run_update()

    def test_restart_is_noop_outside_the_app(self):
        with mock.patch.dict("os.environ", {"CZ_APP_PATH": ""}):
            self.assertFalse(cz.restart_app())


if __name__ == "__main__":
    unittest.main()
