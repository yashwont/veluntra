from fastapi import APIRouter

from app.api.v1 import auth, health, notes, tasks, users, workspaces

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(workspaces.router)
api_router.include_router(tasks.router)
api_router.include_router(notes.router)
