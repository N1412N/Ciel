import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import agent_tools
from agent_tools import (
    extract_drawing_subject,
    is_explicit_ai_image_request,
    extract_ai_image_prompt,
    handle_direct_command,
    detect_fallback_intent,
    tool_draw_in_paint,
)


class PaintDrawingTests(unittest.TestCase):
    def test_extract_drawing_subject(self):
        cases = [
            ("draw a cat", "cat"),
            ("sketch a robot", "robot"),
            ("paint a house", "house"),
            ("draw a car in Paint", "car"),
            ("open Paint and draw a castle", "castle"),
            ("draw a blue robot with wings", "blue robot with wings"),
            ("draw a village beside a mountain", "village beside a mountain"),
            ("please draw me a cute kitten on Paint canvas", "cute kitten"),
            ("create a drawing of a futuristic spaceship", "futuristic spaceship"),
            ("make a drawing of sunset over ocean", "sunset over ocean"),
        ]
        for query, expected_sub in cases:
            extracted = extract_drawing_subject(query)
            self.assertEqual(extracted, expected_sub, f"Failed extracting from: '{query}'")

    def test_explicit_ai_image_detection(self):
        ai_cases = [
            "generate an image of a cat",
            "create an AI image of a house",
            "make digital artwork of a robot",
            "use AI to create a picture of a tree",
            "generate a Stable Diffusion image of a cyberpunk dragon",
        ]
        for query in ai_cases:
            self.assertTrue(is_explicit_ai_image_request(query), f"Should be AI image request: '{query}'")

        paint_cases = [
            "draw a cat",
            "sketch a robot",
            "paint a house",
            "draw a car in Paint",
            "open Paint and draw a castle",
        ]
        for query in paint_cases:
            self.assertFalse(is_explicit_ai_image_request(query), f"Should NOT be AI image request: '{query}'")

    @patch("agent_tools.tool_draw_in_paint")
    @patch("agent_tools.tool_generate_image")
    def test_direct_command_routes_to_paint(self, mock_gen_img, mock_draw_paint):
        mock_draw_paint.return_value = "[Report] Drawing completed"
        mock_gen_img.return_value = "[Notice] Generating"

        handled, _ = handle_direct_command("draw a cat")
        self.assertTrue(handled)
        mock_draw_paint.assert_called_once_with("cat")
        mock_gen_img.assert_not_called()

        mock_draw_paint.reset_mock()
        mock_gen_img.reset_mock()

        handled, _ = handle_direct_command("sketch a robot")
        self.assertTrue(handled)
        mock_draw_paint.assert_called_once_with("robot")
        mock_gen_img.assert_not_called()

        mock_draw_paint.reset_mock()
        mock_gen_img.reset_mock()

        handled, _ = handle_direct_command("draw a blue robot with wings")
        self.assertTrue(handled)
        mock_draw_paint.assert_called_once_with("blue robot with wings")
        mock_gen_img.assert_not_called()

    @patch("agent_tools.tool_draw_in_paint")
    @patch("agent_tools.tool_generate_image")
    def test_direct_command_routes_ai_requests_to_generate_image(self, mock_gen_img, mock_draw_paint):
        mock_gen_img.return_value = "[Notice] Generating image"
        mock_draw_paint.return_value = "[Report] Drawing"

        handled, _ = handle_direct_command("generate an image of a cat")
        self.assertTrue(handled)
        mock_gen_img.assert_called_once()
        self.assertIn("cat", mock_gen_img.call_args[0][0])
        mock_draw_paint.assert_not_called()

        mock_gen_img.reset_mock()
        mock_draw_paint.reset_mock()

        handled, _ = handle_direct_command("create an AI image of a robot")
        self.assertTrue(handled)
        mock_gen_img.assert_called_once()
        self.assertIn("robot", mock_gen_img.call_args[0][0])
        mock_draw_paint.assert_not_called()

    def test_fallback_intent_routing(self):
        calls = detect_fallback_intent("", "draw a cat")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "draw_in_paint")
        self.assertEqual(calls[0]["args"]["subject"], "cat")

        ai_calls = detect_fallback_intent("", "generate an image of a cybernetic dragon")
        self.assertEqual(len(ai_calls), 1)
        self.assertEqual(ai_calls[0]["tool"], "generate_image")
        self.assertIn("cybernetic dragon", ai_calls[0]["args"]["prompt"])

    @patch("agent_tools.tool_open_application", return_value="[Report] Opened")
    @patch("agent_tools.tool_focus_window", return_value="[Report] Focused")
    @patch("time.sleep", return_value=None)
    def test_mouse_button_always_released_on_error(self, mock_sleep, mock_focus, mock_open):
        import pyautogui
        orig_moveTo = pyautogui.moveTo
        orig_mouseUp = pyautogui.mouseUp

        mouse_up_called = []

        def failing_moveTo(*args, **kwargs):
            raise RuntimeError("Simulation error during stroke")

        def tracked_mouseUp(*args, **kwargs):
            mouse_up_called.append(kwargs.get("button", "left"))

        pyautogui.moveTo = failing_moveTo
        pyautogui.mouseUp = tracked_mouseUp

        try:
            res = tool_draw_in_paint("house")
            self.assertIn("interrupted", res.lower())
            self.assertTrue(len(mouse_up_called) >= 1)
        finally:
            pyautogui.moveTo = orig_moveTo
            pyautogui.mouseUp = orig_mouseUp


if __name__ == "__main__":
    unittest.main()
