from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "ERROR",
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.extra = extra or {}


class AuthenticationError(AppError):
    def __init__(self, detail: str = "Invalid credentials or authentication token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code="AUTHENTICATION_FAILED",
        )


class PermissionDeniedError(AppError):
    def __init__(self, detail: str = "Permission denied for this resource"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code="PERMISSION_DENIED",
        )


class NotFoundError(AppError):
    def __init__(self, detail: str = "Requested resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            code="RESOURCE_NOT_FOUND",
        )


class ConflictError(AppError):
    def __init__(self, detail: str = "Resource conflict occurred"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            code="RESOURCE_CONFLICT",
        )


class InvalidImageError(AppError):
    def __init__(self, detail: str = "Uploaded file is not a valid or supported image"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code="INVALID_IMAGE",
        )


class FaceDetectionError(AppError):
    def __init__(self, detail: str = "Face detection or recognition failure"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            code="FACE_DETECTION_ERROR",
        )


class ConsentRequiredError(AppError):
    def __init__(self, detail: str = "Attendee biometric consent is required before performing face search"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code="CONSENT_REQUIRED",
        )


class RateLimitExceededError(AppError):
    def __init__(self, detail: str = "Search request rate limit exceeded. Please wait before retrying."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            code="RATE_LIMIT_EXCEEDED",
        )

