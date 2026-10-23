"""
Unit tests for idempotency of logging/audio engine and TONE3000 callback handling.
"""

import unittest
from unittest.mock import patch, MagicMock
import logging
from fastapi.testclient import TestClient

import setup_logging
from engine.audio import AudioEngine
import t3k_fastapi as t3k
import server


class TestLoggingIdempotency(unittest.TestCase):
    def test_setup_logging_idempotent(self):
        root = logging.getLogger()

        # Call setup_logging multiple times
        setup_logging.setup_logging()
        count1 = len(root.handlers)
        setup_logging.setup_logging()
        count2 = len(root.handlers)

        self.assertEqual(count1, count2, "Handlers should not duplicate on multiple setup_logging calls")


class TestAudioEngineIdempotency(unittest.TestCase):
    def test_audio_engine_start_idempotent(self):
        class FakeStream:
            def __init__(self):
                self.active = True
                self.stopped = False
            def start(self):
                self.active = True
            def stop(self):
                self.stopped = True
                self.active = False
            def close(self):
                self.active = False

        engine = AudioEngine(sample_rate=48000, block_size=128)
        # Use the engine's own resolved pair: hard-coded PortAudio indices are
        # not stable across machines, so they cannot express "same settings".
        start_in, start_out = engine.input_device, engine.output_device

        with patch("engine.audio.sd.Stream", return_value=FakeStream()) as mock_stream_cls:
            # First start call
            ok, msg = engine.start(input_id=start_in, output_id=start_out, sample_rate=48000, block_size=128)
            self.assertTrue(ok)
            self.assertEqual(mock_stream_cls.call_count, 1)

            # Second start call with identical settings
            ok2, msg2 = engine.start(input_id=start_in, output_id=start_out, sample_rate=48000, block_size=128)
            self.assertTrue(ok2)
            self.assertEqual(mock_stream_cls.call_count, 1, "sd.Stream should not be recreated when settings match")

            # Third start call with changed settings should restart
            ok3, msg3 = engine.start(input_id=start_in, output_id=start_out, sample_rate=44100, block_size=128)
            self.assertTrue(ok3)
            self.assertEqual(mock_stream_cls.call_count, 2, "sd.Stream should restart when settings change")

            engine.stop()


class TestTone3000Flow(unittest.TestCase):
    def test_form_content_type_not_overridden(self):
        # Test that _http preserves application/x-www-form-urlencoded when form is passed
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"access_token": "abc", "expires_in": 3600}'
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            status, body, hdrs = t3k._http("POST", "https://example.com/oauth/token",
                                           headers={"Content-Type": "application/json"},
                                           form={"grant_type": "authorization_code", "code": "xyz"})
            # Verify request
            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.headers.get("Content-type"), "application/x-www-form-urlencoded")

    def test_t3k_error_contains_upstream_details(self):
        import urllib.error
        from io import BytesIO

        err_body = b'{"error": "invalid_grant", "error_description": "Code expired"}'
        err = urllib.error.HTTPError("https://example.com", 400, "Bad Request", {}, BytesIO(err_body))

        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(t3k.T3KError) as cm:
                t3k._http("POST", "https://example.com/test", form={"a": "b"})
            
            exc = cm.exception
            self.assertEqual(exc.status, 400)
            self.assertIn("Code expired", str(exc))
            self.assertIn("Code expired", exc.response_text)
            self.assertEqual(exc.details.get("error"), "invalid_grant")

    def test_callback_duplicate_prevention(self):
        # Setup pending state
        state_key = "test_state_123"
        code_val = "test_code_456"
        t3k._PENDING[state_key] = {
            "verifier": "test_verifier",
            "redirect_uri": "http://127.0.0.1:8000/api/t3k/callback",
            "prompt": "select_tone",
            "tone_id": None,
            "created": 9999999999.0,
        }

        with patch("t3k_fastapi.exchange_code", return_value={"access_token": "token123"}) as mock_exch:
            with patch("t3k_fastapi.get_user", return_value={"username": "tester"}):
                # Call 1
                query1 = {"code": code_val, "state": state_key, "tone_id": "777"}
                res1 = t3k.handle_callback(query1)
                self.assertEqual(res1["tone_id"], 777)
                self.assertEqual(mock_exch.call_count, 1)

                # Call 2 with identical code (duplicate callback invocation)
                query2 = {"code": code_val, "state": state_key, "tone_id": "777"}
                res2 = t3k.handle_callback(query2)
                self.assertEqual(res2["tone_id"], 777)
                self.assertEqual(mock_exch.call_count, 1, "exchange_code must not be called twice for single-use code")


class TestFastAPICallbackEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_callback_endpoint_invalid_state_no_name_error(self):
        # Invoking callback with non-existent state should return HTTP 400 cleanly without NameError
        resp = self.client.get("/api/t3k/callback?code=invalid_code&state=nonexistent_state")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("state ไม่ตรงหรือหมดอายุ", resp.text)

    def test_callback_endpoint_canceled_no_name_error(self):
        # Cancelled callback should return HTTP 200 cleanly without NameError
        resp = self.client.get("/api/t3k/callback?canceled=true&state=test_cancel_state")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ยกเลิกแล้ว", resp.text)

    def test_callback_endpoint_success_and_cache_no_name_error(self):
        state_key = "fastapi_test_state_ok"
        code_val = "fastapi_test_code_ok"
        t3k._PENDING[state_key] = {
            "verifier": "test_verifier_fastapi",
            "redirect_uri": "http://127.0.0.1:8000/api/t3k/callback",
            "prompt": "select_tone",
            "tone_id": None,
            "created": 9999999999.0,
        }

        mock_info = {"title": "Test Rig", "gear": "amp", "model": "TestModel"}
        with patch("t3k_fastapi.exchange_code", return_value={"access_token": "token_ok"}) as mock_exch:
            with patch("t3k_fastapi.get_user", return_value={"username": "testuser"}):
                with patch("server._install_t3k_tone", return_value=mock_info) as mock_install:
                    # First request: exchanges code and installs tone
                    url = f"/api/t3k/callback?code={code_val}&state={state_key}&tone_id=888"
                    resp1 = self.client.get(url)
                    self.assertEqual(resp1.status_code, 200)
                    self.assertIn("โหลดเสียงเรียบร้อย", resp1.text)
                    self.assertEqual(mock_exch.call_count, 1)
                    self.assertEqual(mock_install.call_count, 1)

                    # Second request (duplicate invocation): served from cache, no NameError, no re-exchange
                    resp2 = self.client.get(url)
                    self.assertEqual(resp2.status_code, 200)
                    self.assertIn("โหลดเสียงเรียบร้อย", resp2.text)
                    self.assertEqual(mock_exch.call_count, 1, "exchange_code must not be called twice on duplicate HTTP GET")
                    self.assertEqual(mock_install.call_count, 1, "install tone must not be called twice on duplicate HTTP GET")

    def test_callback_endpoint_upstream_error_warning_logged(self):
        state_key = "fastapi_test_state_err"
        code_val = "fastapi_test_code_err"
        t3k._PENDING[state_key] = {
            "verifier": "test_verifier_err",
            "redirect_uri": "http://127.0.0.1:8000/api/t3k/callback",
            "prompt": "select_tone",
            "tone_id": None,
            "created": 9999999999.0,
        }

        err = t3k.T3KError("TONE3000 ตอบกลับ HTTP 400", status=400, code="invalid_grant",
                             response_text='{"error": "invalid_grant", "error_description": "Code expired"}',
                             details={"error": "invalid_grant", "error_description": "Code expired"})
        with patch("t3k_fastapi.exchange_code", side_effect=err):
            with self.assertLogs("server", level="WARNING") as cm:
                url = f"/api/t3k/callback?code={code_val}&state={state_key}&tone_id=888"
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 400)
                self.assertIn("เชื่อมต่อไม่สำเร็จ", resp.text)
                # Verify that upstream error details were included in the server warning log
                log_output = "\n".join(cm.output)
                self.assertIn("upstream", log_output)
                self.assertIn("Code expired", log_output)


if __name__ == "__main__":
    unittest.main()
