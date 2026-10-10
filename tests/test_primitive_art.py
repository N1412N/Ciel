"""
test_primitive_art.py -- Comprehensive Tests for Primitive Pictures Geometric Art Engine
"""

import json
import os
import sys
import unittest
from pathlib import Path
import numpy as np

# Add app to path
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from primitive_engine import (
    PrimitiveArtModel,
    ShapeType,
    run_primitive_reproduction,
)
from agent_tools import (
    tool_generate_primitive_art,
    TOOLS,
    ToolRiskLevel,
    parse_and_execute_tool_call,
)


class TestPrimitiveArtEngine(unittest.TestCase):
    """Test suite for Primitive Art mathematical model and rendering."""

    @classmethod
    def setUpClass(cls):
        # Create a synthetic 100x100 test image (red box on blue background)
        cls.test_img = np.zeros((100, 100, 3), dtype=np.uint8)
        cls.test_img[:, :] = [30, 50, 180]  # Blue
        cls.test_img[30:70, 30:70] = [200, 40, 40]  # Red center square
        
        # Save sample image to disk
        from config import config
        cls.sample_path = str(config.paths.chats_dir / "sample_target.png")
        from PIL import Image
        Image.fromarray(cls.test_img).save(cls.sample_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.sample_path):
            os.remove(cls.sample_path)

    def test_model_reduces_error_triangles(self):
        """Iterative shape addition must decrease MSE error."""
        model = PrimitiveArtModel(
            target_image=self.test_img,
            mode=ShapeType.TRIANGLE,
            working_size=64,
            alpha=0.6,
            num_candidates=15,
            num_mutations=10,
        )
        initial_mse = model.current_mse
        self.assertGreater(initial_mse, 0)

        for _ in range(8):
            model.step()

        self.assertLess(
            model.current_mse,
            initial_mse,
            "Canvas MSE error must decrease as shapes are added."
        )
        self.assertEqual(len(model.shapes), 8)

    def test_all_shape_modes(self):
        """Model must successfully step and render for each supported shape mode."""
        modes = [
            ShapeType.TRIANGLE,
            ShapeType.RECTANGLE,
            ShapeType.CIRCLE,
            ShapeType.ELLIPSE,
            ShapeType.COMBO,
        ]
        for mode in modes:
            model = PrimitiveArtModel(
                target_image=self.test_img,
                mode=mode,
                working_size=64,
                num_candidates=10,
                num_mutations=5,
            )
            shape = model.step()
            self.assertIsNotNone(shape, f"Failed to generate shape for mode: {mode}")
            self.assertEqual(len(model.shapes), 1)

    def test_svg_export_format(self):
        """Exported SVG must be valid XML with root svg tags and dimensions."""
        model = PrimitiveArtModel(
            target_image=self.test_img,
            mode=ShapeType.TRIANGLE,
            working_size=64,
            num_candidates=10,
            num_mutations=5,
        )
        model.step()
        model.step()

        svg_str = model.export_svg()
        self.assertTrue(svg_str.startswith("<svg"))
        self.assertTrue(svg_str.endswith("</svg>"))
        self.assertIn('viewBox="0 0 100 100"', svg_str)
        self.assertIn("<polygon", svg_str)
        self.assertIn("fill-opacity", svg_str)

    def test_png_rasterization(self):
        """Exported PNG canvas must match original dimensions and dtype."""
        model = PrimitiveArtModel(
            target_image=self.test_img,
            mode=ShapeType.RECTANGLE,
            working_size=64,
            num_candidates=10,
            num_mutations=5,
        )
        model.step()
        png_arr = model.export_png()
        self.assertEqual(png_arr.shape, (100, 100, 3))
        self.assertEqual(png_arr.dtype, np.uint8)

    def test_run_primitive_reproduction(self):
        """End-to-end run_primitive_reproduction saves SVG and PNG to disk."""
        from config import config
        out_dir = str(config.paths.chats_dir / "primitive_run_test")
        res = run_primitive_reproduction(
            image_path=self.sample_path,
            num_shapes=10,
            mode="combo",
            output_dir=out_dir,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["num_shapes"], 10)
        self.assertTrue(os.path.exists(res["svg_path"]))
        self.assertTrue(os.path.exists(res["png_path"]))
        self.assertGreater(os.path.getsize(res["svg_path"]), 0)
        self.assertGreater(os.path.getsize(res["png_path"]), 0)


class TestPrimitiveToolAndApi(unittest.TestCase):
    """Test suite for agent tool and Flask API endpoints."""

    @classmethod
    def setUpClass(cls):
        from app import app
        cls.client = app.test_client()

        # Create dummy image
        cls.dummy_img = np.full((64, 64, 3), 120, dtype=np.uint8)
        cls.dummy_img[20:44, 20:44] = [240, 200, 40]
        from config import config
        cls.img_path = str(config.paths.chats_dir / "dummy_for_tool.png")
        from PIL import Image
        Image.fromarray(cls.dummy_img).save(cls.img_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.img_path):
            os.remove(cls.img_path)

    def test_tool_catalog_metadata(self):
        """generate_primitive_art must be registered with correct risk level and schema."""
        self.assertIn("generate_primitive_art", TOOLS)
        spec = TOOLS["generate_primitive_art"]
        self.assertEqual(spec["risk_level"], ToolRiskLevel.REVERSIBLE_WRITE)
        self.assertFalse(spec["requires_permission"])
        self.assertIn("image_path", spec["allowed_arguments"])
        self.assertIn("num_shapes", spec["allowed_arguments"])
        self.assertIn("mode", spec["allowed_arguments"])

    def test_tool_execution(self):
        """Tool executes successfully and reports paths."""
        res = tool_generate_primitive_art(self.img_path, num_shapes=8, mode="triangle")
        self.assertIn("[Report: Geometric Primitive Art Created]", res)
        self.assertIn("SVG Vector Output", res)
        self.assertIn("PNG Raster Output", res)

    def test_tool_rejects_missing_image(self):
        """Tool returns friendly error when image is missing."""
        res = tool_generate_primitive_art("non_existent_file_xyz_123.jpg")
        self.assertIn("[ERROR] Source image not found", res)

    def test_api_primitive_generate_endpoint(self):
        """POST /api/primitive/generate returns valid SVG and paths."""
        payload = {
            "image_path": self.img_path,
            "num_shapes": 8,
            "mode": "triangle",
        }
        resp = self.client.post("/api/primitive/generate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("svg_path", data)
        self.assertIn("png_path", data)
        self.assertIn("svg_content", data)
        self.assertTrue(data["svg_content"].startswith("<svg"))

    def test_api_primitive_generate_async_task(self):
        """POST /api/primitive/generate with async_task=True queues background job."""
        payload = {
            "image_path": self.img_path,
            "num_shapes": 10,
            "mode": "circle",
            "async_task": True,
        }
        resp = self.client.post("/api/primitive/generate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "queued")
        self.assertIn("task_id", data)


if __name__ == "__main__":
    unittest.main()
