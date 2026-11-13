from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import AppError
from app.core.logging import app_logger
from app.services.face_service import FaceRecognitionEngine
from app.services.storage_service import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage and models are available
    app_logger.info("Initializing application startup checks...")
    try:
        storage_service.events_dir.mkdir(parents=True, exist_ok=True)
        storage_service.temp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if settings.yunet_path.exists() and settings.sface_path.exists():
        app_logger.info("Pre-warming Face Recognition Engine models...")
        try:
            FaceRecognitionEngine.get_instance()
            app_logger.info("Face Recognition models ready.")
        except Exception as e:
            app_logger.warning(f"Could not initialize face engine at startup: {e}")
    else:
        app_logger.warning(
            f"Face models missing in {settings.MODELS_DIR}. Run scripts/download_models.py."
        )

    yield

    app_logger.info("Application shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production AI-Powered Event Photo Management & Face Recognition System.\n\n"
        "Features:\n"
        "- OpenCV YuNet (Face Detection) + OpenCV SFace (128-d Feature Embeddings)\n"
        "- Exact vector similarity matching via PostgreSQL and pgvector\n"
        "- Strict event-level data isolation and privacy controls\n"
        "- DPDP Act 2023 compliant consent recording and search sessions\n"
        "- Autonomous background worker for batch photo ingestion\n"
        "- Fully open-source, commercial-ready (Apache 2.0 weights), running CPU-only"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handlers
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.detail,
                "details": exc.extra,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters or payload",
                "details": exc.errors(),
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    app_logger.exception(f"Unhandled server exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred",
                "details": None,
            },
        },
    )


@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    disk = storage_service.check_disk_space()
    models_ready = settings.yunet_path.exists() and settings.sface_path.exists()
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "models_ready": models_ready,
        "disk_storage": disk,
    }


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)

