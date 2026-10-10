import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from security import SecurityError, validate_http_url, workspace_path
import agent_tools
import app


class BackendSecurityTests(unittest.TestCase):
    def test_workspace_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            self.assertEqual(workspace_path(str(root / "src" / "main.py"), str(root)).name, "main.py")
            with self.assertRaises(SecurityError):
                workspace_path(str(root / ".." / "secret.txt"), str(root))

    def test_validate_http_url_rejects_local_targets(self):
        with self.assertRaises(SecurityError):
            validate_http_url("http://127.0.0.1:11434/api/tags")
        with self.assertRaises(SecurityError):
            validate_http_url("file:///etc/passwd")

    def test_command_and_clipboard_tools_require_permission(self):
        original = agent_tools.request_permission
        agent_tools.request_permission = lambda *_: False
        try:
            self.assertIn("DENIED", agent_tools.tool_run_command("Write-Host unsafe"))
            self.assertIn("DENIED", agent_tools.tool_set_clipboard("x'); Remove-Item *; '"))
        finally:
            agent_tools.request_permission = original

    def test_tool_parser_rejects_non_object_args(self):
        result = list(agent_tools.parse_and_execute_tool_call(
            '```tool\n{"tool":"get_clipboard","args":[]}\n```', ""
        ))
        self.assertTrue(result)
        self.assertIn("args must be an object", result[0][0])

    def test_agent_tools_filesystem_sandbox(self):
        agent_tools.set_allow_read_all(False)
        outside_path = str(Path(agent_tools.DEFAULT_WORKSPACE).parent / "outside_secret.txt")
        outside_dir = str(Path(agent_tools.DEFAULT_WORKSPACE).parent / "outside_dir")

        self.assertIn("[ERROR] Security rejection", agent_tools.tool_read_file(outside_path))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_create_file(outside_path, "payload"))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_write_file(outside_path, "payload"))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_list_directory(outside_dir))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_create_folder(outside_dir))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_delete_file(outside_path))
        self.assertIn("[ERROR] Security rejection", agent_tools.tool_search_files(outside_dir, "*.txt"))

    def test_persistence_atomic_and_backup_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_chats = os.path.join(tmp, "test_conversations.json")
            test_memory = os.path.join(tmp, "test_memory.json")

            orig_chats_file = app.CHATS_FILE
            orig_memory_file = app.MEMORY_FILE
            app.CHATS_FILE = test_chats
            app.MEMORY_FILE = test_memory

            try:
                # 1. Test Chat backup and recovery
                sample_chats = {"chat-1": {"id": "chat-1", "title": "Test Chat", "messages": []}}
                app.save_all_chats(sample_chats)
                self.assertTrue(os.path.exists(test_chats))

                # Save second time so .bak is populated
                sample_chats["chat-1"]["title"] = "Updated Chat"
                app.save_all_chats(sample_chats)
                self.assertTrue(os.path.exists(test_chats + ".bak"))

                # Corrupt primary file
                with open(test_chats, "w", encoding="utf-8") as f:
                    f.write("<<<corrupted-json-data>>>")

                # load_all_chats should recover from .bak rather than returning empty
                recovered_chats = app.load_all_chats()
                self.assertIn("chat-1", recovered_chats)

                # 2. Test Memory backup and recovery
                sample_memory = [{"id": "m1", "fact": "Master prefers Python", "created_at": "2026-09-27"}]
                app.save_memory(sample_memory)
                self.assertTrue(os.path.exists(test_memory))

                # Save second time to populate .bak
                sample_memory.append({"id": "m2", "fact": "Master builds AI", "created_at": "2026-09-27"})
                app.save_memory(sample_memory)
                self.assertTrue(os.path.exists(test_memory + ".bak"))

                # Corrupt primary file
                with open(test_memory, "w", encoding="utf-8") as f:
                    f.write("{invalid: json}")

                recovered_memory = app.load_memory()
                self.assertTrue(len(recovered_memory) >= 1)
                self.assertEqual(recovered_memory[0]["id"], "m1")

            finally:
                app.CHATS_FILE = orig_chats_file
                app.MEMORY_FILE = orig_memory_file


if __name__ == "__main__":
    unittest.main()
