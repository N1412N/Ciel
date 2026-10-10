import json
import os
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from app import app
from task_manager import task_manager, TaskStatus


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_list_tasks_empty_or_valid(self):
        resp = self.client.get("/api/tasks")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("tasks", data)
        self.assertIsInstance(data["tasks"], list)

    def test_submit_unsupported_task_type_returns_400(self):
        resp = self.client.post("/api/tasks", json={"type": "unknown_super_task"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "error")

    def test_get_nonexistent_task_returns_404(self):
        resp = self.client.get("/api/tasks/nonexistent_id_123")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_nonexistent_task_returns_400(self):
        resp = self.client.post("/api/tasks/nonexistent_id_123/cancel")
        self.assertEqual(resp.status_code, 400)

    def test_task_events_stream_and_lifecycle(self):
        # Manually create a task in task_manager
        task = task_manager.submit("custom_test", lambda: "success_result")
        
        # Check task can be retrieved via API
        resp = self.client.get(f"/api/tasks/{task.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["task"]["id"], task.id)

        # Check events SSE stream endpoint
        stream_resp = self.client.get(f"/api/tasks/{task.id}/events")
        self.assertEqual(stream_resp.status_code, 200)
        self.assertTrue("text/event-stream" in stream_resp.headers.get("Content-Type", ""))


if __name__ == "__main__":
    unittest.main()
