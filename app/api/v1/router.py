from fastapi import APIRouter

from app.api.v1 import agent, auth, health, user

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(agent.router)
