from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.photos import global_router as global_photos_router, router as photos_router
from app.api.v1.search import router as search_router
from app.api.v1.delivery import router as delivery_router
from app.api.v1.restricted_faces import router as restricted_faces_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(events_router)
api_router.include_router(photos_router)
api_router.include_router(global_photos_router)
api_router.include_router(search_router)
api_router.include_router(delivery_router)
api_router.include_router(restricted_faces_router)

