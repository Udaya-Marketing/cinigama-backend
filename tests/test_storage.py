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

