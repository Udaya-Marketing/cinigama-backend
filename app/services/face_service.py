import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import cv2
    _cv2_available = True
    _cv2_error = None
except Exception as _e:
    cv2 = None
    _cv2_available = False
    _cv2_error = str(_e)
import numpy as np
from PIL import Image, ImageOps

from app.config import settings
from app.core.exceptions import FaceDetectionError, InvalidImageError
from app.core.logging import app_logger


@dataclass
class DetectedFace:
    bounding_box: Dict[str, int]  # {"x": int, "y": int, "w": int, "h": int}
    confidence: float
    landmarks: Dict[str, List[float]]  # right_eye, left_eye, nose, mouth_right, mouth_left
    embedding: List[float]  # 128-dimensional L2-normalized float vector


class FaceRecognitionEngine:
    """Production OpenCV YuNet + SFace Face Detection and Recognition Engine.
    Operates CPU-only without external GPU or paid cloud API dependencies.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(
        self,
        yunet_path: Optional[Path] = None,
        sface_path: Optional[Path] = None,
        score_threshold: Optional[float] = None,
        nms_threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ):
        if not _cv2_available:
            raise RuntimeError(f"OpenCV (cv2) is not available: {_cv2_error}")
        self.yunet_path = Path(yunet_path or settings.yunet_path)
        self.sface_path = Path(sface_path or settings.sface_path)
        self.score_threshold = score_threshold or settings.YUNET_SCORE_THRESHOLD
        self.nms_threshold = nms_threshold or settings.YUNET_NMS_THRESHOLD
        self.top_k = top_k or settings.YUNET_TOP_K

        if not self.yunet_path.exists():
            raise RuntimeError(f"YuNet model not found at {self.yunet_path}. Run scripts/download_models.py.")
        if not self.sface_path.exists():
            raise RuntimeError(f"SFace model not found at {self.sface_path}. Run scripts/download_models.py.")

        app_logger.info(f"Initializing FaceRecognitionEngine with YuNet: {self.yunet_path.name}, SFace: {self.sface_path.name}")
        self._init_models()

    def _init_models(self) -> None:
        # Default detector initialized with nominal 320x320 size, updated per image
        self.detector = cv2.FaceDetectorYN.create(
            str(self.yunet_path),
            "",
            (320, 320),
            score_threshold=float(self.score_threshold),
            nms_threshold=float(self.nms_threshold),
            top_k=int(self.top_k),
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(self.sface_path),
            "",
        )

    @classmethod
    def get_instance(cls) -> "FaceRecognitionEngine":
        """Singleton accessor to prevent reloading 38MB model weights per request."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def load_image_with_orientation(image_source: Path | bytes) -> np.ndarray:
        """Load image bytes or file path, correctly applying EXIF orientation,
        and return a BGR numpy array compatible with OpenCV.
        """
        import io
        if isinstance(image_source, (str, Path)):
            with open(image_source, "rb") as f:
                raw_bytes = f.read()
        else:
            raw_bytes = image_source

        try:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            transposed = ImageOps.exif_transpose(pil_img)
            if transposed is not None:
                pil_img = transposed

            # Convert to RGB if needed
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            # Convert RGB PIL to BGR OpenCV
            rgb_arr = np.array(pil_img)
            bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
            return bgr_arr
        except Exception as exc:
            raise InvalidImageError(f"Failed to decode image: {exc}")

    def detect_and_extract_faces(
        self,
        image_source: Path | bytes,
        max_dimension: int = 1920,
    ) -> List[DetectedFace]:
        """Process an image, detect all faces with YuNet, align them,
        and extract 128-dimensional L2-normalized embeddings with SFace.
        """
        bgr_image = self.load_image_with_orientation(image_source)
        orig_h, orig_w = bgr_image.shape[:2]

        # Calculate inference resize factor to maintain high detection speed
        # while preserving sufficient resolution for distant event attendee faces
        scale = 1.0
        if max(orig_h, orig_w) > max_dimension:
            scale = max_dimension / float(max(orig_h, orig_w))
            infer_w = int(round(orig_w * scale))
            infer_h = int(round(orig_h * scale))
            infer_image = cv2.resize(bgr_image, (infer_w, infer_h), interpolation=cv2.INTER_AREA)
        else:
            infer_image = bgr_image
            infer_w, infer_h = orig_w, orig_h

        # Set input size dynamically for YuNet
        with self._lock:
            self.detector.setInputSize((infer_w, infer_h))
            _, faces = self.detector.detect(infer_image)

        if faces is None or len(faces) == 0:
            return []

        results: List[DetectedFace] = []

        for face in faces:
            # Face format: [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rc, y_rc, x_lc, y_lc, score]
            score = float(face[14])
            if score < self.score_threshold:
                continue

            # Scale coordinates back to original image space
            inv_scale = 1.0 / scale
            x = int(round(face[0] * inv_scale))
            y = int(round(face[1] * inv_scale))
            w = int(round(face[2] * inv_scale))
            h = int(round(face[3] * inv_scale))

            # Constrain bounding box to original image bounds
            x = max(0, min(x, orig_w - 1))
            y = max(0, min(y, orig_h - 1))
            w = max(1, min(w, orig_w - x))
            h = max(1, min(h, orig_h - y))

            if min(w, h) < settings.MIN_FACE_SIZE_PX:
                continue

            # Scale landmarks to original space
            landmarks = {
                "right_eye": [float(face[4] * inv_scale), float(face[5] * inv_scale)],
                "left_eye": [float(face[6] * inv_scale), float(face[7] * inv_scale)],
                "nose_tip": [float(face[8] * inv_scale), float(face[9] * inv_scale)],
                "mouth_right": [float(face[10] * inv_scale), float(face[11] * inv_scale)],
                "mouth_left": [float(face[12] * inv_scale), float(face[13] * inv_scale)],
            }

            # Prepare face record in scale of the image passed to SFace alignCrop
            # We align on the scaled inference image for speed and numerical stability
            scaled_face_record = face.copy()

            with self._lock:
                aligned_face = self.recognizer.alignCrop(infer_image, scaled_face_record)
                feature = self.recognizer.feature(aligned_face)

            # L2 Normalization: ensure unit vector for exact cosine similarity
            norm = np.linalg.norm(feature[0])
            if norm > 0:
                normalized_embedding = (feature[0] / norm).tolist()
            else:
                normalized_embedding = feature[0].tolist()

            results.append(
                DetectedFace(
                    bounding_box={"x": x, "y": y, "w": w, "h": h},
                    confidence=score,
                    landmarks=landmarks,
                    embedding=normalized_embedding,
                )
            )

        return results

    def process_selfie(
        self,
        image_bytes: bytes,
    ) -> DetectedFace:
        """Process attendee selfie for face matching.
        Strict verification:
        - Must contain EXACTLY ONE detectable face.
        - Face must be clear, properly sized, and pass confidence thresholds.
        """
        faces = self.detect_and_extract_faces(image_bytes, max_dimension=1280)

        if len(faces) == 0:
            raise FaceDetectionError(
                "No face detected in the selfie. Please ensure good lighting and face the camera directly."
            )

        if len(faces) > settings.MAX_SELFIE_FACES_ALLOWED:
            raise FaceDetectionError(
                f"Multiple faces ({len(faces)}) detected in the selfie. "
                "Please upload a photo of only yourself for identity verification."
            )

        face = faces[0]

        if face.confidence < self.score_threshold:
            raise FaceDetectionError(
                f"Selfie face confidence ({face.confidence:.2f}) is below the required threshold ({self.score_threshold:.2f}). "
                "Please provide a clearer photo."
            )

        if min(face.bounding_box["w"], face.bounding_box["h"]) < settings.MIN_FACE_SIZE_PX:
            raise FaceDetectionError(
                f"The detected face in the selfie is too small ({min(face.bounding_box['w'], face.bounding_box['h'])}px < {settings.MIN_FACE_SIZE_PX}px). Please take a closer portrait."
            )

        return face

    @staticmethod
    def compute_cosine_similarity(vec1: List[float] | np.ndarray, vec2: List[float] | np.ndarray) -> float:
        """Compute cosine similarity between two 128-d vectors."""
        a = np.array(vec1, dtype=np.float32)
        b = np.array(vec2, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


face_engine = FaceRecognitionEngine.get_instance

