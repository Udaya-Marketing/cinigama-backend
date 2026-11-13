from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.photos import router as photos_router
from app.api.v1.search import router as search_router
from app.api.v1.delivery import router as delivery_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(events_router)
api_router.include_router(photos_router)
api_router.include_router(search_router)
api_router.include_router(delivery_router)

