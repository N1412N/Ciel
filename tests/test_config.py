import os
import unittest
from pathlib import Path
import sys

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from config import AppConfig, ServerConfig, OllamaConfig, PathConfig, VoiceConfig, LimitsConfig


class ConfigTests(unittest.TestCase):
    def test_default_config_values(self):
        cfg = AppConfig()
        self.assertEqual(cfg.server.host, "127.0.0.1")
        self.assertEqual(cfg.server.port, 5000)
        self.assertEqual(cfg.server.version, ServerConfig().version)
        self.assertTrue(cfg.ollama.api_url.startswith("http"))
        self.assertIn("qwen", cfg.ollama.default_model)
        self.assertEqual(cfg.limits.command_timeout_seconds, 30)
        self.assertEqual(cfg.limits.permission_timeout_seconds, 120)

    def test_validation_passes_on_defaults(self):
        cfg = AppConfig()
        errors = cfg.validate()
        self.assertEqual(errors, [])

    def test_validation_catches_invalid_port(self):
        cfg = AppConfig(server=ServerConfig(port=99999))
        errors = cfg.validate()
        self.assertTrue(any("port" in e.lower() for e in errors))

    def test_validation_catches_invalid_ollama_url(self):
        cfg = AppConfig(ollama=OllamaConfig(api_url="ftp://invalid-url"))
        errors = cfg.validate()
        self.assertTrue(any("ollama" in e.lower() for e in errors))

    def test_path_properties(self):
        cfg = AppConfig()
        self.assertTrue(str(cfg.paths.conversations_file).endswith("conversations.json"))
        self.assertTrue(str(cfg.paths.memory_file).endswith("memory.json"))


if __name__ == "__main__":
    unittest.main()
