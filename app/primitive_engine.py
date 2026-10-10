"""
primitive_engine.py -- High-Performance Geometric Primitive Art Engine
Inspired by Michael Fogleman's Primitive Pictures (fogleman/primitive).

Reproduces any image using geometric primitives (triangles, rectangles,
ellipses, circles, rotated rectangles, or combo) through iterative hill-climbing
optimization. Outputs crisp resolution-independent SVG vector graphics and PNG.
"""

import json
import math
import os
import random
import time
from typing import Callable, Dict, List, Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image


class ShapeType:
    TRIANGLE = "triangle"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    CIRCLE = "circle"
    ROTATED_RECT = "rotated_rect"
    COMBO = "combo"


class PrimitiveShape:
    """Represents a single geometric primitive with geometry, color, and alpha."""
    def __init__(self, kind: str, params: dict, color: Tuple[int, int, int], alpha: float):
        self.kind = kind
        self.params = params  # Geometry parameters
        self.color = color    # (R, G, B)
        self.alpha = alpha    # 0.0 - 1.0

    def to_svg(self, scale_x: float = 1.0, scale_y: float = 1.0) -> str:
        """Serialize shape into standard SVG XML markup."""
        r, g, b = self.color
        color_str = f"rgb({r},{g},{b})"
        alpha_str = f"{self.alpha:.2f}"

        if self.kind == ShapeType.TRIANGLE:
            pts = self.params["points"]
            scaled = " ".join(f"{p[0] * scale_x:.1f},{p[1] * scale_y:.1f}" for p in pts)
            return f'<polygon points="{scaled}" fill="{color_str}" fill-opacity="{alpha_str}" />'

        elif self.kind == ShapeType.RECTANGLE:
            x = self.params["x"] * scale_x
            y = self.params["y"] * scale_y
            w = self.params["w"] * scale_x
            h = self.params["h"] * scale_y
            return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{color_str}" fill-opacity="{alpha_str}" />'

        elif self.kind == ShapeType.CIRCLE:
            cx = self.params["cx"] * scale_x
            cy = self.params["cy"] * scale_y
            rad = self.params["r"] * ((scale_x + scale_y) / 2.0)
            return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" fill="{color_str}" fill-opacity="{alpha_str}" />'

        elif self.kind == ShapeType.ELLIPSE:
            cx = self.params["cx"] * scale_x
            cy = self.params["cy"] * scale_y
            rx = self.params["rx"] * scale_x
            ry = self.params["ry"] * scale_y
            angle = self.params.get("angle", 0.0)
            transform = f' transform="rotate({angle:.1f} {cx:.1f} {cy:.1f})"' if angle else ""
            return f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}"{transform} fill="{color_str}" fill-opacity="{alpha_str}" />'

        elif self.kind == ShapeType.ROTATED_RECT:
            pts = self.params["points"]
            scaled = " ".join(f"{p[0] * scale_x:.1f},{p[1] * scale_y:.1f}" for p in pts)
            return f'<polygon points="{scaled}" fill="{color_str}" fill-opacity="{alpha_str}" />'

        return ""


class PrimitiveArtModel:
    """Optimization model that iteratively reproduces an image with geometric shapes."""

    def __init__(
        self,
        target_image: np.ndarray,
        mode: str = ShapeType.TRIANGLE,
        working_size: int = 128,
        alpha: float = 0.55,
        num_candidates: int = 25,
        num_mutations: int = 20,
    ):
        # target_image is RGB uint8
        self.orig_h, self.orig_w = target_image.shape[:2]
        self.mode = mode.lower()
        self.alpha = max(0.1, min(1.0, alpha))
        self.num_candidates = num_candidates
        self.num_mutations = num_mutations

        # Compute scaling factors to working size
        aspect = self.orig_w / float(self.orig_h)
        if aspect >= 1.0:
            self.work_w = working_size
            self.work_h = max(16, int(round(working_size / aspect)))
        else:
            self.work_h = working_size
            self.work_w = max(16, int(round(working_size * aspect)))

        # Downscale target to working resolution for fast vector computations
        self.target = cv2.resize(target_image, (self.work_w, self.work_h), interpolation=cv2.INTER_AREA)

        # Average background color
        mean_col = np.mean(self.target, axis=(0, 1)).astype(np.uint8)
        self.bg_color = (int(mean_col[0]), int(mean_col[1]), int(mean_col[2]))

        # Current working canvas
        self.canvas = np.full_like(self.target, self.bg_color)
        self.current_mse = self._calc_mse(self.canvas)
        self.shapes: List[PrimitiveShape] = []

    def _calc_mse(self, img: np.ndarray) -> float:
        """Mean squared error between canvas and target image."""
        diff = img.astype(np.float32) - self.target.astype(np.float32)
        return float(np.mean(diff * diff))

    def _random_shape(self, kind: str) -> dict:
        """Generate a random shape parameter dict within working bounds."""
        w, h = self.work_w, self.work_h

        if kind == ShapeType.TRIANGLE:
            pts = np.array([
                [random.randint(0, w - 1), random.randint(0, h - 1)],
                [random.randint(0, w - 1), random.randint(0, h - 1)],
                [random.randint(0, w - 1), random.randint(0, h - 1)],
            ], dtype=np.int32)
            return {"kind": ShapeType.TRIANGLE, "points": pts}

        elif kind == ShapeType.RECTANGLE:
            x1, x2 = sorted([random.randint(0, w - 1), random.randint(0, w - 1)])
            y1, y2 = sorted([random.randint(0, h - 1), random.randint(0, h - 1)])
            return {"kind": ShapeType.RECTANGLE, "x": x1, "y": y1, "w": max(2, x2 - x1), "h": max(2, y2 - y1)}

        elif kind == ShapeType.CIRCLE:
            cx = random.randint(0, w - 1)
            cy = random.randint(0, h - 1)
            r = random.randint(3, max(4, min(w, h) // 2))
            return {"kind": ShapeType.CIRCLE, "cx": cx, "cy": cy, "r": r}

        elif kind == ShapeType.ELLIPSE:
            cx = random.randint(0, w - 1)
            cy = random.randint(0, h - 1)
            rx = random.randint(3, max(4, w // 2))
            ry = random.randint(3, max(4, h // 2))
            angle = random.uniform(0, 360)
            return {"kind": ShapeType.ELLIPSE, "cx": cx, "cy": cy, "rx": rx, "ry": ry, "angle": angle}

        elif kind == ShapeType.ROTATED_RECT:
            cx = random.randint(0, w - 1)
            cy = random.randint(0, h - 1)
            rw = random.randint(4, max(5, w // 2))
            rh = random.randint(4, max(5, h // 2))
            angle = random.uniform(0, 180)
            rect = ((float(cx), float(cy)), (float(rw), float(rh)), float(angle))
            box = cv2.boxPoints(rect).astype(np.int32)
            return {"kind": ShapeType.ROTATED_RECT, "points": box, "cx": cx, "cy": cy, "rw": rw, "rh": rh, "angle": angle}

        return self._random_shape(ShapeType.TRIANGLE)

    def _mutate_shape(self, shape_dict: dict) -> dict:
        """Mutate a shape slightly (hill-climbing step)."""
        kind = shape_dict["kind"]
        w, h = self.work_w, self.work_h
        mut = shape_dict.copy()

        if kind == ShapeType.TRIANGLE:
            pts = mut["points"].copy()
            idx = random.randint(0, 2)
            delta = random.randint(-12, 12)
            axis = random.randint(0, 1)
            pts[idx, axis] = max(0, min(w - 1 if axis == 0 else h - 1, pts[idx, axis] + delta))
            mut["points"] = pts
            return mut

        elif kind == ShapeType.RECTANGLE:
            prop = random.choice(["x", "y", "w", "h"])
            limit = w if prop in ("x", "w") else h
            mut[prop] = max(0, min(limit - 1, mut[prop] + random.randint(-8, 8)))
            if prop in ("w", "h"):
                mut[prop] = max(2, mut[prop])
            return mut

        elif kind == ShapeType.CIRCLE:
            prop = random.choice(["cx", "cy", "r"])
            if prop == "cx":
                mut["cx"] = max(0, min(w - 1, mut["cx"] + random.randint(-8, 8)))
            elif prop == "cy":
                mut["cy"] = max(0, min(h - 1, mut["cy"] + random.randint(-8, 8)))
            else:
                mut["r"] = max(2, min(max(w, h), mut["r"] + random.randint(-6, 6)))
            return mut

        elif kind == ShapeType.ELLIPSE:
            prop = random.choice(["cx", "cy", "rx", "ry", "angle"])
            if prop == "cx":
                mut["cx"] = max(0, min(w - 1, mut["cx"] + random.randint(-8, 8)))
            elif prop == "cy":
                mut["cy"] = max(0, min(h - 1, mut["cy"] + random.randint(-8, 8)))
            elif prop == "rx":
                mut["rx"] = max(2, min(w, mut["rx"] + random.randint(-6, 6)))
            elif prop == "ry":
                mut["ry"] = max(2, min(h, mut["ry"] + random.randint(-6, 6)))
            else:
                mut["angle"] = (mut["angle"] + random.uniform(-25, 25)) % 360
            return mut

        elif kind == ShapeType.ROTATED_RECT:
            cx = max(0, min(w - 1, mut["cx"] + random.randint(-8, 8)))
            cy = max(0, min(h - 1, mut["cy"] + random.randint(-8, 8)))
            rw = max(4, min(w, mut["rw"] + random.randint(-6, 6)))
            rh = max(4, min(h, mut["rh"] + random.randint(-6, 6)))
            angle = (mut["angle"] + random.uniform(-20, 20)) % 180
            rect = ((float(cx), float(cy)), (float(rw), float(rh)), float(angle))
            box = cv2.boxPoints(rect).astype(np.int32)
            mut.update({"points": box, "cx": cx, "cy": cy, "rw": rw, "rh": rh, "angle": angle})
            return mut

        return mut

    def _render_mask(self, shape_dict: dict) -> Optional[np.ndarray]:
        """Rasterize a shape to a 2D boolean mask."""
        mask = np.zeros((self.work_h, self.work_w), dtype=np.uint8)
        kind = shape_dict["kind"]

        if kind in (ShapeType.TRIANGLE, ShapeType.ROTATED_RECT):
            cv2.fillPoly(mask, [shape_dict["points"]], 255)
        elif kind == ShapeType.RECTANGLE:
            x, y, w, h = shape_dict["x"], shape_dict["y"], shape_dict["w"], shape_dict["h"]
            cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
        elif kind == ShapeType.CIRCLE:
            cv2.circle(mask, (shape_dict["cx"], shape_dict["cy"]), shape_dict["r"], 255, -1)
        elif kind == ShapeType.ELLIPSE:
            cv2.ellipse(
                mask,
                (shape_dict["cx"], shape_dict["cy"]),
                (shape_dict["rx"], shape_dict["ry"]),
                shape_dict.get("angle", 0.0),
                0,
                360,
                255,
                -1,
            )

        if not np.any(mask > 0):
            return None
        return mask

    def _evaluate_shape(self, shape_dict: dict) -> Tuple[float, Optional[Tuple[int, int, int]], Optional[np.ndarray]]:
        """Compute optimal color, blended canvas, and MSE score for a candidate shape."""
        mask = self._render_mask(shape_dict)
        if mask is None:
            return float("inf"), None, None

        idx = mask > 0
        # Optimal color is the mean of target pixels covered by the shape
        target_pixels = self.target[idx]
        mean_color = np.mean(target_pixels, axis=0).astype(np.uint8)
        color_tuple = (int(mean_color[0]), int(mean_color[1]), int(mean_color[2]))

        # Alpha composite shape onto current canvas
        blended = self.canvas.copy()
        solid_color = np.full_like(self.canvas, color_tuple)
        
        # Fast alpha blend on covered region
        a = self.alpha
        blended[idx] = (a * solid_color[idx].astype(np.float32) + (1.0 - a) * self.canvas[idx].astype(np.float32)).astype(np.uint8)

        mse = self._calc_mse(blended)
        return mse, color_tuple, blended

    def step(self) -> Optional[PrimitiveShape]:
        """Add one optimal shape to the canvas using candidate sampling and hill climbing."""
        # Determine shape kind for this step
        if self.mode == ShapeType.COMBO:
            kinds = [ShapeType.TRIANGLE, ShapeType.RECTANGLE, ShapeType.ELLIPSE, ShapeType.CIRCLE]
            active_kind = random.choice(kinds)
        else:
            active_kind = self.mode

        best_mse = self.current_mse
        best_shape_dict = None
        best_color = None
        best_blended = None

        # 1. Sample random candidate shapes
        min_sample_mse = float("inf")
        fallback_cand = None
        fallback_col = None
        fallback_blended = None

        for _ in range(self.num_candidates):
            cand = self._random_shape(active_kind)
            mse, col, blended = self._evaluate_shape(cand)
            if mse < min_sample_mse:
                min_sample_mse = mse
                fallback_cand = cand
                fallback_col = col
                fallback_blended = blended
            if mse < best_mse:
                best_mse = mse
                best_shape_dict = cand
                best_color = col
                best_blended = blended

        if best_shape_dict is None:
            if fallback_cand is None:
                return None
            best_shape_dict = fallback_cand
            best_color = fallback_col
            best_blended = fallback_blended
            best_mse = min_sample_mse

        # 2. Hill climbing: mutate the best candidate to refine vertices
        curr_shape = best_shape_dict
        for _ in range(self.num_mutations):
            mutated = self._mutate_shape(curr_shape)
            mse, col, blended = self._evaluate_shape(mutated)
            if mse < best_mse:
                best_mse = mse
                curr_shape = mutated
                best_color = col
                best_blended = blended

        # 3. Lock in the winning shape
        self.canvas = best_blended
        self.current_mse = best_mse

        shape_obj = PrimitiveShape(
            kind=curr_shape["kind"],
            params=curr_shape,
            color=best_color,
            alpha=self.alpha,
        )
        self.shapes.append(shape_obj)
        return shape_obj

    def export_svg(self) -> str:
        """Export the generated artwork as resolution-independent vector SVG."""
        scale_x = self.orig_w / float(self.work_w)
        scale_y = self.orig_h / float(self.work_h)

        bg_r, bg_g, bg_b = self.bg_color
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.orig_w} {self.orig_h}" width="{self.orig_w}" height="{self.orig_h}">',
            f'  <rect width="{self.orig_w}" height="{self.orig_h}" fill="rgb({bg_r},{bg_g},{bg_b})" />',
        ]
        for shape in self.shapes:
            svg_tag = shape.to_svg(scale_x, scale_y)
            if svg_tag:
                lines.append(f"  {svg_tag}")
        lines.append("</svg>")
        return "\n".join(lines)

    def export_png(self, output_width: Optional[int] = None) -> np.ndarray:
        """Render high-resolution raster image from vector shapes."""
        out_w = output_width or self.orig_w
        aspect = self.orig_h / float(self.orig_w)
        out_h = int(round(out_w * aspect))

        scale_x = out_w / float(self.work_w)
        scale_y = out_h / float(self.work_h)

        canvas = np.full((out_h, out_w, 3), self.bg_color, dtype=np.uint8)
        a = self.alpha

        for s in self.shapes:
            mask = np.zeros((out_h, out_w), dtype=np.uint8)
            kind = s.kind

            if kind in (ShapeType.TRIANGLE, ShapeType.ROTATED_RECT):
                pts = (s.params["points"] * np.array([scale_x, scale_y])).astype(np.int32)
                cv2.fillPoly(mask, [pts], 255)
            elif kind == ShapeType.RECTANGLE:
                x = int(round(s.params["x"] * scale_x))
                y = int(round(s.params["y"] * scale_y))
                w = int(round(s.params["w"] * scale_x))
                h = int(round(s.params["h"] * scale_y))
                cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
            elif kind == ShapeType.CIRCLE:
                cx = int(round(s.params["cx"] * scale_x))
                cy = int(round(s.params["cy"] * scale_y))
                rad = int(round(s.params["r"] * ((scale_x + scale_y) / 2.0)))
                cv2.circle(mask, (cx, cy), rad, 255, -1)
            elif kind == ShapeType.ELLIPSE:
                cx = int(round(s.params["cx"] * scale_x))
                cy = int(round(s.params["cy"] * scale_y))
                rx = max(1, int(round(s.params["rx"] * scale_x)))
                ry = max(1, int(round(s.params["ry"] * scale_y)))
                cv2.ellipse(mask, (cx, cy), (rx, ry), s.params.get("angle", 0.0), 0, 360, 255, -1)

            idx = mask > 0
            if np.any(idx):
                col_solid = np.full_like(canvas, s.color)
                canvas[idx] = (a * col_solid[idx].astype(np.float32) + (1.0 - a) * canvas[idx].astype(np.float32)).astype(np.uint8)

        return canvas


def run_primitive_reproduction(
    image_path: str,
    num_shapes: int = 60,
    mode: str = "triangle",
    output_dir: Optional[str] = None,
    alpha: float = 0.55,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
) -> Dict[str, Union[str, int, float]]:
    """
    Main entry point to convert an image into geometric primitive art.
    Outputs both SVG and PNG to output_dir (or image directory).
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")

    # Read image with PIL to guarantee RGB format
    with Image.open(image_path) as pil_img:
        pil_rgb = pil_img.convert("RGB")
        img_np = np.array(pil_rgb)

    model = PrimitiveArtModel(
        target_image=img_np,
        mode=mode,
        working_size=128,
        alpha=alpha,
        num_candidates=30,
        num_mutations=25,
    )

    t0 = time.time()
    for step_num in range(1, num_shapes + 1):
        model.step()
        if progress_callback:
            progress_callback(step_num, num_shapes, model.current_mse)

    duration = time.time() - t0

    # Output paths
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    out_dir = output_dir or os.path.dirname(os.path.abspath(image_path))
    os.makedirs(out_dir, exist_ok=True)

    timestamp = int(time.time())
    svg_filename = f"{base_name}_primitive_{mode}_{num_shapes}_{timestamp}.svg"
    png_filename = f"{base_name}_primitive_{mode}_{num_shapes}_{timestamp}.png"

    svg_path = os.path.join(out_dir, svg_filename)
    png_path = os.path.join(out_dir, png_filename)

    # 1. Save SVG
    svg_content = model.export_svg()
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    # 2. Save PNG
    hi_res_png = model.export_png()
    Image.fromarray(hi_res_png).save(png_path)

    return {
        "status": "ok",
        "num_shapes": len(model.shapes),
        "mode": mode,
        "duration_seconds": round(duration, 2),
        "final_mse": round(model.current_mse, 2),
        "svg_path": svg_path,
        "png_path": png_path,
        "svg_filename": svg_filename,
        "png_filename": png_filename,
    }
