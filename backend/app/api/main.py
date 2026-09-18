from fastapi import APIRouter

from app.api.routes import (
    agent,
    agent_ws,
    knowledge_base,
    login,
    private,
    providers,
    settings as settings_routes,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(agent.router)
api_router.include_router(knowledge_base.router)
api_router.include_router(agent_ws.router)
api_router.include_router(providers.router)
api_router.include_router(settings_routes.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
