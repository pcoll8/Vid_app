"""Routers package initialization"""
from .jobs import router as jobs_router
from .clips import router as clips_router
from .settings import router as settings_router
from .websocket import router as websocket_router
from .schedules import router as schedules_router

__all__ = ["jobs_router", "clips_router", "settings_router", "websocket_router", "schedules_router"]
