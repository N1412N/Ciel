import os
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import agent_tools
from agent_tools import TOOLS, ToolRiskLevel, parse_and_execute_tool_call


class ToolSafetyTests(unittest.TestCase):
    def test_all_tools_have_metadata(self):
        valid_risk_levels = {
            ToolRiskLevel.READ_ONLY,
            ToolRiskLevel.REVERSIBLE_WRITE,
            ToolRiskLevel.DESTRUCTIVE,
            ToolRiskLevel.SYSTEM_CONTROL,
            ToolRiskLevel.COMPUTER_AUTOMATION,
            ToolRiskLevel.NETWORK_ACCESS,
        }
        for name, meta in TOOLS.items():
            self.assertIn("fn", meta, f"Tool '{name}' missing fn")
            self.assertIn("risk_level", meta, f"Tool '{name}' missing risk_level")
            self.assertIn(meta["risk_level"], valid_risk_levels, f"Tool '{name}' invalid risk_level")
            self.assertIn("requires_permission", meta, f"Tool '{name}' missing requires_permission")
            self.assertIn("timeout_seconds", meta, f"Tool '{name}' missing timeout_seconds")
            self.assertIn("allowed_arguments", meta, f"Tool '{name}' missing allowed_arguments")

    def test_unexpected_argument_rejected(self):
        call_str = '```tool\n{"tool": "read_file", "args": {"path": "test.txt", "injected_param": "malicious"}}\n```'
        results = list(parse_and_execute_tool_call(call_str))
        self.assertTrue(results)
        self.assertIn("Unexpected arguments for tool 'read_file'", results[0][0])

    def test_invalid_argument_type_rejected(self):
        call_str = '```tool\n{"tool": "read_file", "args": {"path": 12345}}\n```'
        results = list(parse_and_execute_tool_call(call_str))
        self.assertTrue(results)
        self.assertIn("Invalid argument type for 'path'", results[0][0])

    def test_open_application_rejects_ssrf_urls(self):
        res = agent_tools.tool_open_application("http://127.0.0.1:11434/api/tags")
        self.assertIn("Security rejection", res)

    def test_automation_tools_require_permission(self):
        original = agent_tools.request_permission
        agent_tools.request_permission = lambda *_: False
        try:
            self.assertIn("DENIED", agent_tools.tool_computer_mouse(action="click", x=100, y=100))
            self.assertIn("DENIED", agent_tools.tool_computer_keyboard(action="type", text="secret"))
            self.assertIn("DENIED", agent_tools.tool_open_application("notepad"))
        finally:
            agent_tools.request_permission = original


if __name__ == "__main__":
    unittest.main()
