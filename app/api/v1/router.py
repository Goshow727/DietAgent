from fastapi import APIRouter

from app.api.v1 import agent, auth, banner, insight, nls, user, vision
from app.api.v1.food import burn_router, food_router, intake_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(insight.router)
api_router.include_router(agent.router)
api_router.include_router(nls.router)
api_router.include_router(food_router)
api_router.include_router(intake_router)
api_router.include_router(burn_router)
api_router.include_router(banner.router)
api_router.include_router(vision.router)
