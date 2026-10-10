import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from model_router import ModelRouter, RouteDecision
from app import app
from config import config


class ModelRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()
        self.client = app.test_client()

    def test_classify_trivial_command(self):
        model, reason, label = self.router.classify_task("hello")
        self.assertEqual(model, "qwen2.5-coder:1.5b")
        self.assertIn("1.5B", label)

        model, reason, label = self.router.classify_task("15 * 4")
        self.assertEqual(model, "qwen2.5-coder:1.5b")

    def test_classify_coding_and_general_task(self):
        model, reason, label = self.router.classify_task("Build a FastAPI backend service")
        self.assertEqual(model, config.ollama.default_model)
        self.assertIn("Primary", label)

    def test_classify_deep_reasoning_request(self):
        model, reason, label = self.router.classify_task("think deeply and provide a mathematical proof")
        self.assertEqual(model, "qwen3:latest")
        self.assertIn("Qwen 3", label)

    def test_ollama_offline_handling(self):
        offline_router = ModelRouter(api_url="http://127.0.0.1:59999")
        self.assertFalse(offline_router.is_ollama_online())
        decision = offline_router.route_task("hello")
        self.assertFalse(decision.available)
        self.assertIn("offline", decision.reason.lower())

    def test_model_fallback_when_preferred_missing(self):
        router = ModelRouter()
        # Mock online with only default_model installed
        with patch.object(router, "is_ollama_online", return_value=True):
            with patch.object(router, "get_installed_models", return_value={config.ollama.default_model.lower()}):
                # Request reasoning model which is missing
                decision = router.route_task("think deeply and prove theorem")
                self.assertEqual(decision.model, config.ollama.default_model)
                self.assertTrue(decision.fallback_used)
                self.assertTrue(decision.available)

    def test_api_models_route_endpoint(self):
        resp = self.client.post("/api/models/route", json={"prompt": "hi"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("decision", data)
        self.assertIn("model", data["decision"])
        self.assertIn("reason", data["decision"])


if __name__ == "__main__":
    unittest.main()
