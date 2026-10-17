from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.cards import router as cards_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.collection import router as collection_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.internal.ingestion import router as ingestion_router
from app.api.v1.market import router as market_router
from app.api.v1.sets import router as sets_router
from app.api.v1.valuations import router as valuations_router

api_router = APIRouter()
api_router.include_router(cards_router)
api_router.include_router(catalog_router)
api_router.include_router(valuations_router)
api_router.include_router(collection_router)
api_router.include_router(dashboard_router)
api_router.include_router(ingestion_router)
api_router.include_router(ai_router)
api_router.include_router(market_router)
api_router.include_router(sets_router)
