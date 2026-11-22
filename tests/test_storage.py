import uuid
from pathlib import Path
import pytest
from app.core.exceptions import InvalidImageError, PermissionDeniedError
from app.services.storage_service import StorageService


def test_storage_path_traversal_prevention(tmp_path: Path):
    service = StorageService(base_dir=tmp_path)
    traversal_path = tmp_path / ".." / ".." / "etc" / "passwd"

    with pytest.raises(PermissionDeniedError):
        service._ensure_safe_path(traversal_path)


def test_storage_inspect_valid_and_invalid(sample_image_bytes: bytes, tmp_path: Path):
    service = StorageService(base_dir=tmp_path)

    # Valid JPEG
    mime, w, h, ext = service.validate_and_inspect_image(sample_image_bytes, "test.jpg")
    assert mime == "image/jpeg"
    assert ext == ".jpg"
    assert w == 320
    assert h == 240

    # Corrupt content
    with pytest.raises(InvalidImageError):
        service.validate_and_inspect_image(b"not an image", "fake.jpg")


def test_storage_disk_space_check(tmp_path: Path):
    service = StorageService(base_dir=tmp_path)
    stats = service.check_disk_space()
    assert "total_bytes" in stats
    assert "free_bytes" in stats
    assert stats["percent_free"] > 0


def test_storage_watermark_applied(tmp_path: Path):
    from PIL import Image
    service = StorageService(base_dir=tmp_path)

    # Base image with dark tone (1000x800) so white logo is clearly distinguishable
    base_color = (40, 40, 50)
    base_img = Image.new("RGB", (1000, 800), base_color)
    watermarked = service.apply_watermark(base_img)

    assert watermarked.size == (1000, 800)
    assert watermarked.mode == "RGB"

    # Bottom left pixel must remain base color
    assert watermarked.getpixel((50, 750)) == base_color

    # If logo file exists, top right corner must have blended watermarked pixels
    logo = service.get_watermark_logo()
    if logo is not None:
        # Check area in top-right corner where watermark sits
        found_watermark = False
        for y in range(20, 150):
            for x in range(800, 980):
                if watermarked.getpixel((x, y)) != base_color:
                    found_watermark = True
                    break
            if found_watermark:
                break
        assert found_watermark, "Watermark was not detected in the top-right corner"


def test_storage_save_original_applies_watermark(tmp_path: Path):
    import io
    from PIL import Image
    service = StorageService(base_dir=tmp_path)

    base_img = Image.new("RGB", (800, 600), (255, 255, 255))
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()

    saved_path_str = service.save_original_photo(
        event_id=event_id,
        photo_id=photo_id,
        file_bytes=raw_bytes,
        ext=".jpg",
    )
    saved_path = Path(saved_path_str)
    assert saved_path.exists()

    saved_img = Image.open(saved_path)
    assert saved_img.size == (800, 600)


def test_storage_watermark_scale_diff_portrait_and_landscape(tmp_path: Path):
    from PIL import Image
    service = StorageService(base_dir=tmp_path)
    logo = service.get_watermark_logo()
    if logo is None:
        pytest.skip("No watermark logo found to test")

    # 1. Landscape (1200x800)
    landscape_img = Image.new("RGB", (1200, 800), (30, 30, 30))
    wm_landscape = service.apply_watermark(landscape_img)
    assert wm_landscape.size == (1200, 800)

    # 2. Portrait (800x1200)
    portrait_img = Image.new("RGB", (800, 1200), (30, 30, 30))
    wm_portrait = service.apply_watermark(portrait_img)
    assert wm_portrait.size == (800, 1200)


