import numpy as np
import pytest
from app.core.exceptions import FaceDetectionError
from app.services.face_service import FaceRecognitionEngine
from scripts.generate_test_data import create_synthetic_face_image


def test_face_engine_initialization():
    engine = FaceRecognitionEngine.get_instance()
    assert engine.detector is not None
    assert engine.recognizer is not None


def test_cosine_similarity_properties():
    engine = FaceRecognitionEngine.get_instance()
    v1 = np.random.randn(128).astype(np.float32)
    v1 = v1 / np.linalg.norm(v1)

    # Identical vector similarity must be 1.0
    sim_self = engine.compute_cosine_similarity(v1, v1)
    assert abs(sim_self - 1.0) < 1e-4

    # Opposite vector similarity must be -1.0
    sim_neg = engine.compute_cosine_similarity(v1, -v1)
    assert abs(sim_neg - (-1.0)) < 1e-4

    # Orthogonal vectors should have 0 similarity
    v2 = np.zeros(128, dtype=np.float32)
    v2[0] = 1.0
    v3 = np.zeros(128, dtype=np.float32)
    v3[1] = 1.0
    sim_ortho = engine.compute_cosine_similarity(v2, v3)
    assert abs(sim_ortho - 0.0) < 1e-4


def test_selfie_no_face_rejected():
    engine = FaceRecognitionEngine.get_instance()
    # Pure blank image contains 0 faces
    blank_img = create_synthetic_face_image(width=400, height=400, face_count=0)

    with pytest.raises(FaceDetectionError) as exc_info:
        engine.process_selfie(blank_img)
    assert "No face detected" in str(exc_info.value)

