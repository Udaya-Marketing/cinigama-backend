import io
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.config import Config
from PIL import Image, ImageOps

from app.config import settings
from app.core.exceptions import InvalidImageError, PermissionDeniedError
from app.core.logging import app_logger


class StorageService:
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = Path(base_dir or settings.STORAGE_BASE_DIR).resolve()
        self.events_dir = (self._base_dir / "events").resolve()
        self.temp_dir = (self._base_dir / "temp").resolve()
        try:
            self.events_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._s3_client = None
        self._watermark_logo = None

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @base_dir.setter
    def base_dir(self, value: Path) -> None:
        self._base_dir = Path(value).resolve()
        self.events_dir = (self._base_dir / "events").resolve()
        self.temp_dir = (self._base_dir / "temp").resolve()

    @property
    def is_r2(self) -> bool:
        """Return True if Cloudflare R2 storage backend is enabled and configured."""
        return (
            settings.STORAGE_BACKEND.lower() == "r2"
            and bool(settings.R2_ACCESS_KEY_ID)
            and bool(settings.R2_SECRET_ACCESS_KEY)
            and bool(settings.R2_BUCKET_NAME)
        )

    def get_s3_client(self):
        """Lazy initializer for S3/R2 client."""
        if self._s3_client is None:
            endpoint = settings.R2_ENDPOINT_URL
            if not endpoint and settings.R2_ACCOUNT_ID:
                endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

            self._s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
        return self._s3_client

    def get_event_dirs(self, event_id: uuid.UUID) -> Tuple[Path, Path]:
        """Return (originals_dir, thumbnails_dir) for local storage, ensuring they exist."""
        event_path = (self.events_dir / str(event_id)).resolve()
        self._ensure_safe_path(event_path)
        originals = event_path / "originals"
        thumbnails = event_path / "thumbnails"
        originals.mkdir(parents=True, exist_ok=True)
        thumbnails.mkdir(parents=True, exist_ok=True)
        return originals, thumbnails

    def _ensure_safe_path(self, target_path: Path) -> None:
        """Prevent directory traversal attacks for local storage paths."""
        resolved_target = target_path.resolve()
        resolved_base = self.base_dir.resolve()
        if not resolved_target.is_relative_to(resolved_base):
            raise PermissionDeniedError("Invalid storage path or attempted path traversal")

    def validate_and_inspect_image(
        self,
        file_bytes: bytes,
        original_filename: str,
    ) -> Tuple[str, int, int, str]:
        """Validate file size, content header, MIME type, and dimensions.
        Returns: (mime_type, width, height, extension)
        """
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise InvalidImageError(
                f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE_MB}MB"
            )

        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.verify()
        except Exception:
            raise InvalidImageError("File is corrupted or not a valid image")

        try:
            image = Image.open(io.BytesIO(file_bytes))
            img_format = (image.format or "").upper()
            width, height = image.size
        except Exception:
            raise InvalidImageError("Could not inspect image dimensions")

        format_mime_map = {
            "JPEG": ("image/jpeg", ".jpg"),
            "JPG": ("image/jpeg", ".jpg"),
            "PNG": ("image/png", ".png"),
            "WEBP": ("image/webp", ".webp"),
        }

        if img_format not in format_mime_map:
            raise InvalidImageError(
                f"Unsupported image format: {img_format}. Allowed: JPEG, PNG, WebP"
            )

        mime_type, ext = format_mime_map[img_format]

        if width > settings.MAX_IMAGE_DIMENSION_PX or height > settings.MAX_IMAGE_DIMENSION_PX:
            raise InvalidImageError(
                f"Image dimensions ({width}x{height}) exceed maximum allowed {settings.MAX_IMAGE_DIMENSION_PX}px"
            )

        return mime_type, width, height, ext

    def get_watermark_logo(self) -> Optional[Image.Image]:
        """Load and cache the watermark logo if available."""
        if getattr(self, "_watermark_logo", None) is None:
            candidates = [
                Path(settings.WATERMARK_LOGO_PATH),
                self.base_dir / "logo" / "logo-white.webp",
                Path("storage/logo/logo-white.webp"),
                Path(__file__).resolve().parent.parent / "assets" / "logo-white.webp",
            ]
            logo_file = None
            for p in candidates:
                if p.is_file():
                    logo_file = p
                    break

            if not logo_file:
                app_logger.debug("Watermark logo file not found in candidate paths.")
                return None

            try:
                self._watermark_logo = Image.open(logo_file).convert("RGBA")
            except Exception as e:
                app_logger.warning(f"Could not load watermark logo from {logo_file}: {e}")
                return None

        return self._watermark_logo

    def apply_watermark(self, image: Image.Image) -> Image.Image:
        """Apply watermark logo to the top right corner with 50% fade."""
        if not getattr(settings, "WATERMARK_ENABLED", True):
            return image

        logo = self.get_watermark_logo()
        if logo is None:
            return image

        try:
            img = image.copy()
            img_w, img_h = img.size

            # Scale logo proportionally to photo width (default 15%)
            scale = getattr(settings, "WATERMARK_SCALE", 0.15)
            target_w = max(20, int(img_w * scale))
            if target_w >= img_w:
                return image

            aspect = logo.height / logo.width
            target_h = max(1, int(target_w * aspect))
            if target_h >= img_h:
                return image

            resized_logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Apply 50% fade (or configured opacity) to alpha channel
            opacity = getattr(settings, "WATERMARK_OPACITY", 0.50)
            r, g, b, a = resized_logo.split()
            a = a.point(lambda p: int(p * opacity))
            resized_logo.putalpha(a)

            # Calculate top-right position with margin
            margin_pct = getattr(settings, "WATERMARK_MARGIN_PERCENT", 0.02)
            margin_x = max(10, int(img_w * margin_pct))
            margin_y = max(10, int(img_h * margin_pct))

            x = max(0, img_w - target_w - margin_x)
            y = max(0, margin_y)

            orig_mode = img.mode
            if orig_mode != "RGBA":
                rgba_img = img.convert("RGBA")
                rgba_img.paste(resized_logo, (x, y), mask=resized_logo)
                return rgba_img.convert("RGB") if orig_mode == "RGB" else rgba_img
            else:
                img.paste(resized_logo, (x, y), mask=resized_logo)
                return img

        except Exception as e:
            app_logger.warning(f"Failed to apply watermark: {e}")
            return image

    def save_original_photo(
        self,
        event_id: uuid.UUID,
        photo_id: uuid.UUID,
        file_bytes: bytes,
        ext: str,
        mime_type: str = "image/jpeg",
    ) -> str:
        """Save original uploaded image with EXIF orientation correction.
        Uploads directly to Cloudflare R2 if enabled, otherwise saves locally.
        Returns the storage path or R2 object key.
        """
        img = Image.open(io.BytesIO(file_bytes))
        transposed_img = ImageOps.exif_transpose(img)
        if transposed_img is not None:
            img = transposed_img

        # Apply watermark logo in top-right corner with 50% fade
        img = self.apply_watermark(img)

        norm_buffer = io.BytesIO()
        ext_lower = ext.lower()
        if ext_lower in (".jpg", ".jpeg"):
            save_format = "JPEG"
        elif ext_lower == ".png":
            save_format = "PNG"
        elif ext_lower == ".webp":
            save_format = "WEBP"
        else:
            save_format = img.format or "JPEG"

        if save_format == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")

        if save_format == "JPEG":
            img.save(norm_buffer, format="JPEG", quality=95)
        else:
            img.save(norm_buffer, format=save_format)
        normalized_bytes = norm_buffer.getvalue()

        if self.is_r2:
            r2_key = f"events/{event_id}/originals/{photo_id}{ext}"
            s3 = self.get_s3_client()
            s3.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=r2_key,
                Body=normalized_bytes,
                ContentType=mime_type,
            )
            app_logger.info(f"Uploaded original photo to Cloudflare R2: {r2_key}")
            return r2_key
        else:
            originals_dir, _ = self.get_event_dirs(event_id)
            filename = f"{photo_id}{ext}"
            destination = originals_dir / filename
            self._ensure_safe_path(destination)
            with open(destination, "wb") as f:
                f.write(normalized_bytes)
            return str(destination)

    def generate_thumbnail(
        self,
        event_id: uuid.UUID,
        photo_id: uuid.UUID,
        original_source: Path | str | None = None,
        original_path: Path | str | None = None,
    ) -> str:
        """Generate an optimized WebP thumbnail stripping metadata.
        Uploads to Cloudflare R2 if enabled, otherwise saves locally.
        Returns thumbnail storage path or R2 object key.
        """
        source = original_source or original_path
        if source is None:
            raise ValueError("original_source or original_path must be provided")

        if isinstance(source, Path) and source.exists():
            img_bytes = source.read_bytes()
        elif isinstance(source, str) and Path(source).exists():
            img_bytes = Path(source).read_bytes()
        else:
            s3 = self.get_s3_client()
            r2_obj = s3.get_object(Bucket=settings.R2_BUCKET_NAME, Key=str(source))
            img_bytes = r2_obj["Body"].read()

        img = Image.open(io.BytesIO(img_bytes))
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed

        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")

        max_dim = settings.THUMBNAIL_MAX_DIMENSION_PX
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        thumb_buffer = io.BytesIO()
        img.save(thumb_buffer, "WEBP", quality=settings.THUMBNAIL_WEBP_QUALITY, optimize=True)
        thumb_bytes = thumb_buffer.getvalue()

        if self.is_r2:
            r2_key = f"events/{event_id}/thumbnails/{photo_id}.webp"
            s3 = self.get_s3_client()
            s3.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=r2_key,
                Body=thumb_bytes,
                ContentType="image/webp",
            )
            app_logger.info(f"Uploaded thumbnail to Cloudflare R2: {r2_key}")
            return r2_key
        else:
            _, thumbnails_dir = self.get_event_dirs(event_id)
            thumb_filename = f"{photo_id}.webp"
            destination = thumbnails_dir / thumb_filename
            self._ensure_safe_path(destination)
            with open(destination, "wb") as f:
                f.write(thumb_bytes)
            return str(destination)

    def download_to_temp_file(self, storage_path_or_key: str) -> Path:
        """Ensure an image is available on local disk for inference.
        If it's an R2 key, downloads to temporary scratchpad directory.
        """
        p = Path(storage_path_or_key)
        if p.exists():
            return p

        s3 = self.get_s3_client()
        temp_filename = f"temp_{uuid.uuid4().hex}_{p.name}"
        temp_dest = self.temp_dir / temp_filename
        s3.download_file(settings.R2_BUCKET_NAME, storage_path_or_key, str(temp_dest))
        return temp_dest

    def generate_presigned_url(
        self,
        key: str,
        expires_in: Optional[int] = None,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a short-lived Cloudflare R2 presigned URL for direct, secure client downloading."""
        if not self.is_r2:
            return None

        expiry = expires_in or settings.R2_PRESIGNED_EXPIRY_SECONDS
        s3 = self.get_s3_client()

        params = {
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
        }
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        url = s3.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiry,
        )
        return url

    def delete_photo_files(self, original_path: Optional[str], thumbnail_path: Optional[str]) -> None:
        """Safely delete original and thumbnail files from R2 or local disk."""
        if self.is_r2:
            s3 = self.get_s3_client()
            objects_to_delete = []
            for k in (original_path, thumbnail_path):
                if k and not k.startswith("/"):
                    objects_to_delete.append({"Key": k})

            if objects_to_delete:
                try:
                    s3.delete_objects(
                        Bucket=settings.R2_BUCKET_NAME,
                        Delete={"Objects": objects_to_delete},
                    )
                    app_logger.info(f"Deleted {len(objects_to_delete)} objects from Cloudflare R2")
                except Exception as e:
                    app_logger.warning(f"Failed to delete objects from R2: {e}")

        # Clean local files if any exist
        for path_str in (original_path, thumbnail_path):
            if path_str and (path_str.startswith("/") or "\\" in path_str):
                p = Path(path_str).resolve()
                try:
                    if p.is_relative_to(self.base_dir) and p.exists():
                        p.unlink()
                except Exception as e:
                    app_logger.warning(f"Failed to delete local photo file {p}: {e}")

    def delete_event_directory(self, event_id: uuid.UUID) -> None:
        """Recursively delete all stored files for an event from R2 and local disk."""
        if self.is_r2:
            s3 = self.get_s3_client()
            prefix = f"events/{event_id}/"
            try:
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
                    if "Contents" in page:
                        delete_items = [{"Key": obj["Key"]} for obj in page["Contents"]]
                        s3.delete_objects(Bucket=settings.R2_BUCKET_NAME, Delete={"Objects": delete_items})
                        app_logger.info(f"Purged {len(delete_items)} event objects from Cloudflare R2 for {event_id}")
            except Exception as e:
                app_logger.warning(f"Failed to delete event prefix from R2: {e}")

        # Local directory cleanup
        event_path = (self.events_dir / str(event_id)).resolve()
        try:
            if event_path.is_relative_to(self.events_dir) and event_path.exists():
                shutil.rmtree(event_path)
        except Exception as e:
            app_logger.warning(f"Failed to delete event directory {event_path}: {e}")

    def check_disk_space(self) -> dict:
        """Return storage status."""
        check_path = self.base_dir if self.base_dir.exists() else Path("/tmp")
        stat = shutil.disk_usage(check_path)
        info = {
            "backend": "cloudflare_r2" if self.is_r2 else "local",
            "bucket": settings.R2_BUCKET_NAME if self.is_r2 else None,
            "total_bytes": stat.total,
            "used_bytes": stat.used,
            "free_bytes": stat.free,
            "percent_free": round((stat.free / stat.total) * 100, 2),
            "local_total_bytes": stat.total,
            "local_used_bytes": stat.used,
            "local_free_bytes": stat.free,
            "local_percent_free": round((stat.free / stat.total) * 100, 2),
        }
        return info


storage_service = StorageService()
