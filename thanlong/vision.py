"""Template matching in the device's original pixel coordinates."""

from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image


def match_template(image: Image.Image, template: Image.Image, region=None) -> dict:
    """Return the strongest normalized correlation and its absolute bounding box.

    A solid-color crop has no distinctive detail and makes OpenCV's normalized
    correlation degenerate. Reject it instead of reporting an arbitrary match.
    """
    if not isinstance(image, Image.Image) or not isinstance(template, Image.Image):
        raise ValueError("Screen and template must be Pillow images.")
    origin_x, origin_y = 0, 0
    if region is not None:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("Region must contain x, y, width, height.")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in region):
            raise ValueError("Region values must be integers.")
        origin_x, origin_y, width, height = region
        if origin_x < 0 or origin_y < 0 or width < 1 or height < 1 or origin_x + width > image.width or origin_y + height > image.height:
            raise ValueError("Search region lies outside the screenshot.")
        image = image.crop((origin_x, origin_y, origin_x + width, origin_y + height))
    if template.width < 2 or template.height < 2:
        raise ValueError("Template must be at least 2 by 2 pixels and contain visual detail.")
    if template.width > image.width or template.height > image.height:
        raise ValueError("Template is larger than its search region.")
    needle = np.asarray(template.convert("RGB"), dtype=np.uint8)
    if float(np.max(np.std(needle.astype(np.float32), axis=(0, 1)))) < 1.0:
        raise ValueError("Template has too little visual detail. Crop a distinctive icon or button with text.")
    haystack = np.asarray(image.convert("RGB"), dtype=np.uint8)
    correlation = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(correlation)
    if not math.isfinite(score):
        raise ValueError("Template matching produced an invalid score.")
    return {"score": min(1.0, max(-1.0, float(score))), "x": origin_x + location[0], "y": origin_y + location[1], "width": template.width, "height": template.height}
