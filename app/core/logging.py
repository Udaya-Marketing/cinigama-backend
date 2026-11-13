import logging
import sys
from typing import Any, Dict


class BiometricSanitizingFilter(logging.Filter):
    """Filter that intercepts and ensures biometric embeddings, raw vectors,
    or binary image data are never written to disk or logs.
    """
    FORBIDDEN_KEYS = {"embedding", "embeddings", "vector", "face_vector", "raw_image", "image_bytes", "selfie_bytes"}

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = self.sanitize_dict(record.msg)
        elif isinstance(record.args, dict):
            record.args = self.sanitize_dict(record.args)
        return True

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for k, v in data.items():
            if any(forbidden in k.lower() for forbidden in self.FORBIDDEN_KEYS):
                sanitized[k] = "[REDACTED_BIOMETRIC_DATA]"
            elif isinstance(v, dict):
                sanitized[k] = self.sanitize_dict(v)
            else:
                sanitized[k] = v
        return sanitized


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("event_photos")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(BiometricSanitizingFilter())
        logger.addHandler(handler)

    return logger


app_logger = setup_logging()

