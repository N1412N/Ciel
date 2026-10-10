import os
import sys
import time
import unittest
from pathlib import Path

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from task_manager import TaskManager, TaskStatus


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.tm = TaskManager(max_workers=2, max_history=10)

    def test_task_success(self):
        def simple_add(a, b):
            return a + b

        task = self.tm.submit("calc", simple_add, 2, 3)
        # Wait up to 2 seconds for completion
        for _ in range(40):
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                break
            time.sleep(0.05)

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.result, 5)
        self.assertEqual(task.progress, 100)
        self.assertIsNone(task.error)
        self.assertIsNotNone(task.started_at)
        self.assertIsNotNone(task.completed_at)

    def test_task_failure_captures_exception(self):
        def faulty_job():
            raise ValueError("Intentional job failure")

        task = self.tm.submit("broken", faulty_job)
        for _ in range(40):
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                break
            time.sleep(0.05)

        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn("Intentional job failure", str(task.error))

    def test_task_cancellation_running(self):
        def long_job(task_ctx):
            for i in range(20):
                if task_ctx.cancel_event.is_set():
                    return "stopped early"
                time.sleep(0.05)
            return "finished"

        task = self.tm.submit("long", long_job)
        time.sleep(0.08)  # Let it start
        cancelled = self.tm.cancel_task(task.id)
        self.assertTrue(cancelled)

        for _ in range(40):
            if task.status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED):
                break
            time.sleep(0.05)

        self.assertEqual(task.status, TaskStatus.CANCELLED)

    def test_progress_tracking_and_events(self):
        def staged_job(task_ctx):
            task_ctx.update_progress(25, "Quarter done")
            time.sleep(0.05)
            task_ctx.update_progress(75, "Almost done")
            return "all done"

        task = self.tm.submit("staged", staged_job)
        for _ in range(40):
            if task.status == TaskStatus.COMPLETED:
                break
            time.sleep(0.05)

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        d = task.to_dict()
        self.assertEqual(d["progress"], 100)
        self.assertIn("duration_seconds", d)
        self.assertFalse(task.events_queue.empty())


if __name__ == "__main__":
    unittest.main()
