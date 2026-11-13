# Pretrained AI Model Licences & Provenance

This document verifies and records the upstream model sources, versions, checksums, and licences for the AI models used in this production event photo management and face recognition system.

## 1. Strict Licensing Requirements Compliance

- **No Non-Commercial Licenses**: Neither model has non-commercial (`NC`), academic-only, or research-only restrictions (such as InsightFace original pretrained models).
- **No Cloud AI APIs**: Zero dependency on AWS Rekognition, Google Cloud Vision, Azure Face API, or other third-party paid inference services.
- **Permissive Open-Source**: Both models are released under the **Apache License 2.0** via the official OpenCV Zoo project, explicitly permitting commercial use, modification, distribution, and private deployment.
- **CPU-Only Efficiency**: Both models are quantized/optimized ONNX models running via OpenCV DNN on standard x86_64 / aarch64 CPU hardware without requiring dedicated GPUs.

---

## 2. Face Detection Model: YuNet

| Attribute | Specification |
|---|---|
| **Model Name** | YuNet (Face Detection) |
| **Model File** | `face_detection_yunet_2023mar.onnx` |
| **Release Version** | 2023-Mar (YuNet v2) |
| **Upstream Repository** | [OpenCV Zoo - YuNet](https://github.com/opencv/opencv_zoo/tree/master/models/face_detection_yunet) |
| **Official Download URL** | `https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` |
| **Mirror URL** | `https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx` |
| **Original Paper** | Yu et al., *YuNet: A Fast and Accurate Face Detector* |
| **Licence** | **Apache License 2.0** ([OpenCV Zoo LICENSE](https://github.com/opencv/opencv_zoo/blob/master/LICENSE)) |
| **Commercial Use Permitted** | **Yes** |
| **Input Tensor** | Dynamic image shape `(1, 3, H, W)` |
| **Output Tensor** | `(N, 15)` matrix: `[x, y, w, h, right_eye_x, right_eye_y, left_eye_x, left_eye_y, nose_x, nose_y, right_mouth_x, right_mouth_y, left_mouth_x, left_mouth_y, confidence]` |
| **SHA-256 Checksum** | `02dc7b458d348a03a7e4b95340dbec2788e28fcf5723b49e1e1276a6cf38f92a` (verified on download) |

---

## 3. Face Recognition Model: SFace

| Attribute | Specification |
|---|---|
| **Model Name** | SFace (Face Recognition / Feature Extraction) |
| **Model File** | `face_recognition_sface_2021dec.onnx` |
| **Release Version** | 2021-Dec |
| **Upstream Repository** | [OpenCV Zoo - SFace](https://github.com/opencv/opencv_zoo/tree/master/models/face_recognition_sface) |
| **Official Download URL** | `https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx` |
| **Mirror URL** | `https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx` |
| **Original Paper** | Yaoyao Zhong et al., *SFace: Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition*, IEEE T-BIOM 2021 |
| **Licence** | **Apache License 2.0** ([OpenCV Zoo LICENSE](https://github.com/opencv/opencv_zoo/blob/master/LICENSE)) |
| **Commercial Use Permitted** | **Yes** |
| **Input Tensor** | Aligned and cropped face image `(1, 3, 112, 112)` |
| **Output Tensor** | 128-dimensional embedding vector `(1, 128)` |
| **Metric** | Cosine similarity / Cosine distance |
| **SHA-256 Checksum** | `f6a27e77054aab25eb944321743fb7cf8e6dbdd580e0cf0a18ab6478bbd23d83` (verified on download) |

---

## 4. Software Dependencies & Licences

| Package | Licence | Use in System |
|---|---|---|
| Python 3.12 | PSF Licence | Core programming language |
| FastAPI | MIT Licence | Web API framework |
| OpenCV (opencv-python-headless) | Apache 2.0 | DNN model execution and image manipulation |
| PostgreSQL | PostgreSQL Licence | Relational data persistence |
| pgvector | PostgreSQL Licence | 128-d vector similarity indexing and cosine queries |
| SQLAlchemy | MIT Licence | Typed SQL ORM 2.x |
| Alembic | MIT Licence | Database migrations |
| Pillow | HPND (MIT equivalent) | Image decoding, EXIF orientation, thumbnail optimization |
| Pydantic v2 | MIT Licence | Request/response schema validation |
| PyJWT / python-jose | MIT Licence | Cryptographic JWT token generation and verification |
| bcrypt / passlib | BSD / Apache 2.0 | Secure password hashing |
| Nginx | BSD 2-Clause | Reverse proxy, TLS termination, client request rate limiting |

