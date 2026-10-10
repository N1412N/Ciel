"""
test_desktop_operator.py -- Tests for Desktop Operator Tools and Ollama Compatibility Bridge
Inspired by ciel-jarvis-taskbar.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Add app to path
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import config
from agent_tools import (
    tool_get_screen_size,
    tool_discover_applications,
    tool_search_user_files,
    tool_list_pinned_items,
    tool_add_pinned_item,
    tool_launch_pinned_item,
    discover_start_menu_applications,
    TOOLS,
    ToolRiskLevel,
    parse_and_execute_tool_call,
)


class TestDesktopOperatorTools(unittest.TestCase):
    """Test suite for desktop operator tools inspired by ciel-jarvis-taskbar."""

    def test_get_screen_size(self):
        """Screen size query should return valid dimensions."""
        res_str = tool_get_screen_size()
        data = json.loads(res_str)
        self.assertIn("width", data)
        self.assertIn("height", data)
        self.assertGreater(data["width"], 0)
        self.assertGreater(data["height"], 0)

    def test_discover_applications(self):
        """Discover applications should catalog installed Start Menu apps."""
        apps = discover_start_menu_applications()
        self.assertIsInstance(apps, list)
        
        # Test tool_discover_applications output format
        res = tool_discover_applications()
        self.assertIsInstance(res, str)
        self.assertTrue("[Installed Applications Catalog" in res or "No Start menu applications" in res)

        # Test query filtering
        filtered_res = tool_discover_applications(query="nonexistent_xyz_app_123")
        self.assertIn("No installed applications matching", filtered_res)

    def test_search_user_files(self):
        """Search user files should search safely and reject queries under 2 chars."""
        # Query under 2 chars rejected
        short_res = tool_search_user_files("a")
        self.assertIn("[ERROR] Search query must be at least 2 characters", short_res)

        # Safe search across libraries
        res = tool_search_user_files("desktop", max_results=5)
        self.assertIsInstance(res, str)
        self.assertTrue(
            "[User File Search Results for" in res
            or "No filename matches found" in res
        )

    def test_pinned_items_lifecycle(self):
        """Test listing, adding, and updating pinned items."""
        # 1. List pins
        list_res = tool_list_pinned_items()
        self.assertIn("[Pinned Quick-Access Items", list_res)

        # 2. Add a new pin
        add_res = tool_add_pinned_item(
            label="Test Calculator",
            target="calc.exe",
            kind="application"
        )
        self.assertIn("[SUCCESS]", add_res)

        # 3. Verify it is now listed
        updated_list = tool_list_pinned_items()
        self.assertIn("Test Calculator", updated_list)

        # 4. Update the pin
        update_res = tool_add_pinned_item(
            label="Test Calculator",
            target="calc.exe",
            kind="application"
        )
        self.assertIn("Updated existing pinned item", update_res)

        # 5. Launch unknown pin
        err_res = tool_launch_pinned_item("completely_unknown_pin_xyz")
        self.assertIn("[ERROR] No pinned item matching", err_res)

    def test_tools_catalog_and_risk_tiers(self):
        """Verify that all 6 new operator tools are registered with proper risk tiers and schemas."""
        expected_tools = {
            "discover_applications": ToolRiskLevel.READ_ONLY,
            "search_user_files": ToolRiskLevel.READ_ONLY,
            "get_screen_size": ToolRiskLevel.READ_ONLY,
            "list_pinned_items": ToolRiskLevel.READ_ONLY,
            "add_pinned_item": ToolRiskLevel.REVERSIBLE_WRITE,
            "launch_pinned_item": ToolRiskLevel.SYSTEM_CONTROL,
        }

        for tool_name, expected_risk in expected_tools.items():
            self.assertIn(tool_name, TOOLS, f"Tool '{tool_name}' must be registered in TOOLS catalog.")
            spec = TOOLS[tool_name]
            self.assertEqual(spec["risk_level"], expected_risk, f"Tool '{tool_name}' has incorrect risk level.")
            self.assertTrue(callable(spec["fn"]), f"Tool '{tool_name}' fn must be callable.")
            self.assertIn("allowed_arguments", spec, f"Tool '{tool_name}' must declare allowed_arguments.")

    def test_tool_argument_validation(self):
        """Ensure parse_and_execute_tool_call validates types and extra parameters for new tools."""
        # Valid search call
        call_valid = '```tool\n{"tool": "search_user_files", "args": {"query": "notes", "max_results": 10}}\n```'
        results = list(parse_and_execute_tool_call(call_valid))
        self.assertTrue(results)
        self.assertTrue(results[0][1], "Tool should be marked as called")

        # Type mismatch for search query (int instead of str)
        call_invalid_type = '```tool\n{"tool": "search_user_files", "args": {"query": 12345}}\n```'
        results = list(parse_and_execute_tool_call(call_invalid_type))
        self.assertTrue(results)
        self.assertIn("Invalid argument type for 'query'", results[0][0])

        # Unexpected extra argument
        call_extra = '```tool\n{"tool": "get_screen_size", "args": {"extra_arg": "injected"}}\n```'
        results = list(parse_and_execute_tool_call(call_extra))
        self.assertTrue(results)
        self.assertIn("Unexpected arguments for tool 'get_screen_size'", results[0][0])


class TestOllamaCompatibilityBridge(unittest.TestCase):
    """Test suite for /api/tags and Ollama compatibility endpoint."""

    @classmethod
    def setUpClass(cls):
        from app import app
        cls.client = app.test_client()

    def test_api_tags_discovery(self):
        """Ollama clients (e.g. ciel-jarvis-taskbar) must receive valid JSON models list from /api/tags."""
        resp = self.client.get("/api/tags")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("models", data)
        model_names = [m.get("name") for m in data["models"]]
        self.assertIn("ciel-auto", model_names)
        self.assertIn("qwen2.5-coder:7b", model_names)
        self.assertIn("qwen3:latest", model_names)
        self.assertIn("qwen2.5-coder:1.5b", model_names)


if __name__ == "__main__":
    unittest.main()
