import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from graph_service.config import get_settings
from graph_service.routers import ingest, retrieve
from graph_service.zep_graphiti import initialize_graphiti

logger = logging.getLogger(__name__)

# /healthcheck stays open so platform health probes (Railway) keep working
# without a credential. Everything else requires the bearer token.
AUTH_EXEMPT_PATHS = {'/healthcheck'}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if not settings.graphiti_token:
        logger.warning(
            'GRAPHITI_TOKEN is not set - the API is running UNAUTHENTICATED. '
            'Set GRAPHITI_TOKEN in the service environment to require '
            'an "Authorization: Bearer <token>" header on every route except /healthcheck.'
        )
    await initialize_graphiti(settings)
    yield
    # Shutdown
    # No need to close Graphiti here, as it's handled per-request


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def bearer_auth(request: Request, call_next):
    token = get_settings().graphiti_token
    if token and request.url.path not in AUTH_EXEMPT_PATHS:
        supplied = request.headers.get('Authorization', '')
        expected = f'Bearer {token}'
        if not secrets.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8')):
            return JSONResponse(
                content={'detail': 'Not authenticated'},
                status_code=401,
                headers={'WWW-Authenticate': 'Bearer'},
            )
    return await call_next(request)


app.include_router(retrieve.router)
app.include_router(ingest.router)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
