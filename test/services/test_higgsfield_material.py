import unittest
from unittest import mock

from app.config import config
from app.models.schema import VideoAspect
from app.services import material


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class HiggsfieldMaterialTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(config.app)
        config.app["higgsfield_api_keys"] = "kid:secret"
        for key in ("higgsfield_model", "higgsfield_durations",
                    "higgsfield_send_aspect_ratio", "higgsfield_extra_params",
                    "higgsfield_negative_prompt"):
            config.app.pop(key, None)

    def tearDown(self):
        config.app.clear()
        config.app.update(self._saved)

    def test_duration_snaps_to_allowed_values(self):
        self.assertEqual(material._higgsfield_pick_duration(3), 5)
        self.assertEqual(material._higgsfield_pick_duration(6), 10)
        self.assertEqual(material._higgsfield_pick_duration(30), 10)
        config.app["higgsfield_durations"] = [6, 10]
        self.assertEqual(material._higgsfield_pick_duration(5), 6)

    def test_payload_omits_aspect_ratio_by_default(self):
        payload = material.build_higgsfield_payload("p", 5, VideoAspect.portrait)
        self.assertEqual(payload, {"prompt": "p", "duration": 5})
        config.app["higgsfield_send_aspect_ratio"] = True
        config.app["higgsfield_extra_params"] = {"cfg_scale": 0.4}
        payload = material.build_higgsfield_payload("p", 5, VideoAspect.portrait)
        self.assertEqual(payload["aspect_ratio"], "9:16")
        self.assertEqual(payload["cfg_scale"], 0.4)

    @mock.patch.object(material.time, "sleep", lambda *_: None)
    def test_submit_poll_and_return_video(self):
        submit = _Resp(200, {
            "status": "queued", "request_id": "r1",
            "status_url": "https://api.higgsfield.ai/requests/r1/status",
        })
        polls = [
            _Resp(200, {"status": "in_progress"}),
            _Resp(200, {"status": "completed", "video": {"url": "https://cdn/x.mp4"}}),
        ]
        with mock.patch.object(material.requests, "post", return_value=submit) as post, \
                mock.patch.object(material.requests, "get", side_effect=polls):
            items = material.generate_videos_higgsfield("a cat", 3)
        url = post.call_args.args[0]
        self.assertEqual(
            url, "https://api.higgsfield.ai/kling-video/v2.5-turbo/pro/text-to-video"
        )
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Key kid:secret")
        self.assertIn("Idempotency-Key", headers)
        self.assertEqual(post.call_args.kwargs["json"]["duration"], 5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://cdn/x.mp4")
        self.assertEqual(items[0].provider, "higgsfield")
        self.assertEqual(items[0].source_info["asset_id"], "r1")

    def test_clear_rejection_returns_empty(self):
        with mock.patch.object(
            material.requests, "post",
            return_value=_Resp(401, {"detail": "Invalid credentials"}),
        ):
            self.assertEqual(material.generate_videos_higgsfield("a", 5), [])

    @mock.patch.object(material.time, "sleep", lambda *_: None)
    def test_nsfw_is_skipped(self):
        submit = _Resp(200, {"request_id": "r2", "status_url": "https://s"})
        with mock.patch.object(material.requests, "post", return_value=submit), \
                mock.patch.object(material.requests, "get",
                                  return_value=_Resp(200, {"status": "nsfw"})):
            self.assertEqual(material.generate_videos_higgsfield("a", 5), [])

    def test_server_error_on_submit_stops_everything(self):
        with mock.patch.object(material.requests, "post", return_value=_Resp(502, {})):
            with self.assertRaises(material.HiggsfieldUnconfirmedTaskError):
                material.generate_videos_higgsfield("a", 5)

    def test_unknown_poll_state_keeps_request_id(self):
        submit = _Resp(200, {"request_id": "r3", "status_url": "https://s"})
        with mock.patch.object(material.requests, "post", return_value=submit), \
                mock.patch.object(material.requests, "get",
                                  return_value=_Resp(404, {"detail": "nope"})):
            with self.assertRaises(material.HiggsfieldUnconfirmedTaskError) as ctx:
                material.generate_videos_higgsfield("a", 5)
        self.assertEqual(ctx.exception.prediction_id, "r3")
        self.assertIsInstance(ctx.exception, material.WaveSpeedUnconfirmedTaskError)



class HiggsfieldCliTest(unittest.TestCase):
    def test_cli_requires_charge_confirmation(self):
        import cli

        with self.assertRaises(SystemExit):
            cli.parse_args(["--video-subject", "t", "--video-source", "higgsfield"])
        args = cli.parse_args([
            "--video-subject", "t", "--video-source", "higgsfield",
            "--confirm-higgsfield-charge",
        ])
        self.assertEqual(cli.build_video_params(args).video_source, "higgsfield")


if __name__ == "__main__":
    unittest.main()
