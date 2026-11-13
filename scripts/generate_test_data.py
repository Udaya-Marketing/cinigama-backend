"""
Generate synthetic images and test datasets for testing and benchmarking.
Creates test photos with simple face structures and variations.
"""

import io
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np


def create_synthetic_face_image(
    width: int = 640,
    height: int = 480,
    face_count: int = 1,
    bg_color: tuple = (230, 230, 230),
) -> bytes:
    """Create a synthetic RGB image with specified dimensions and drawn human head/face features."""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    spacing = width // (face_count + 1)
    for i in range(face_count):
        center_x = spacing * (i + 1)
        center_y = height // 2

        face_w = min(120, spacing // 2)
        face_h = int(face_w * 1.3)

        x0, y0 = center_x - face_w // 2, center_y - face_h // 2
        x1, y1 = center_x + face_w // 2, center_y + face_h // 2

        # Draw skin-colored oval for head
        skin_tone = (235, 195, 160)
        draw.ellipse([x0, y0, x1, y1], fill=skin_tone, outline=(180, 140, 110), width=2)

        # Eyes
        eye_y = y0 + int(face_h * 0.4)
        eye_w, eye_h = 8, 6
        draw.ellipse([center_x - 25, eye_y - eye_h, center_x - 15, eye_y + eye_h], fill=(50, 40, 40))
        draw.ellipse([center_x + 15, eye_y - eye_h, center_x + 25, eye_y + eye_h], fill=(50, 40, 40))

        # Nose
        nose_y = y0 + int(face_h * 0.6)
        draw.line([center_x, eye_y + 5, center_x, nose_y], fill=(160, 110, 80), width=2)

        # Mouth
        mouth_y = y0 + int(face_h * 0.78)
        draw.line([center_x - 18, mouth_y, center_x + 18, mouth_y], fill=(180, 70, 70), width=3)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


if __name__ == "__main__":
    out_dir = Path("test_fixtures")
    out_dir.mkdir(exist_ok=True)
    img_data = create_synthetic_face_image(width=800, height=600, face_count=2)
    with open(out_dir / "sample_faces.jpg", "wb") as f:
        f.write(img_data)
    print("Saved sample test fixture to test_fixtures/sample_faces.jpg")

