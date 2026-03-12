from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from contextlib import asynccontextmanager
import logging

from .core.config import settings
from .core.database import connect_to_mongo, close_mongo_connection
from .services.file_service import file_service
from .services.metadata_service import metadata_service
from .services.kafka_service import kafka_producer_service
from .services.bias_report_service import bias_report_service
from .api import datasets, users, bias_reports, ai_models
from .services.transformation_report_service import transformation_report_service
from .api import transformation_reports
from .services.ai_model_service import ai_model_service
from .services.xai_report_service import xai_report_service
from .api import xai_reports
from .services.etd_hub_service import etd_hub_service
from .api import etd_hub, etd_hub_import
from .services.graphdb_service import graphdb_service
from .api import graphdb
from .api import user_files
from .services.user_file_service import user_file_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    # Startup
    logger.info("Starting up Data Warehouse API...")
    
    try:
        # Initialize database connection
        await connect_to_mongo()
        
        # Initialize services
        await file_service.initialize()
        await metadata_service.initialize()
        await bias_report_service.initialize()
        await transformation_report_service.initialize()
        await ai_model_service.initialize()
        await xai_report_service.initialize()
        await etd_hub_service.initialize()
        await graphdb_service.initialize()
        await user_file_service.initialize()
        
        # Initialize Kafka (non-fatal)
        try:
            await kafka_producer_service.start()
            logger.info("Kafka producer initialized")
        except Exception as kafka_error:
            logger.warning(f"Kafka init failed: {kafka_error}")
        
        logger.info("All services initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Data Warehouse API...")
    try:
        await kafka_producer_service.stop()
    except Exception as e:
        logger.error(f"Error stopping Kafka producer: {e}")
    await close_mongo_connection()


# Create FastAPI application (inner app: all routes; mounted at / and /autodw by root_app below)
inner_app = FastAPI(
    title="Data Warehouse API",
    description="""
    A comprehensive Data Warehouse API for storing and managing both structured and unstructured data.
    
    Features:
    - File upload to MinIO with organized user separation and versioning
    - Automatic metadata extraction and storage in MongoDB
    - Support for various file types (CSV, Excel, images, videos, audio, AI models)
    - User-based access control and dataset management
    - Advanced search and filtering capabilities
    - ETD-Hub: Reddit-like forum for ethical AI discussions with themes, questions, answers, and voting
    - GraphDB: SPARQL endpoint management for semantic knowledge graphs and triple stores
    
    File Organization Structure:
    - datasets/{user_id}/{dataset_id}/{version}/{filename}
    
    Example: datasets/user1/drowsiness/v1/heart_rate.csv
    
    ETD-Hub Features:
    - Themes: Case studies and ethical AI topics
    - Questions: Forum discussions on AI ethics
    - Answers: Expert responses with voting system
    - Experts: User profiles with expertise areas
    - Documents: File uploads for discussions (future feature)
    
    GraphDB Features:
    - SPARQL endpoint configuration and management
    - Support for SELECT and UPDATE queries
    - Connection testing and health monitoring
    - Repository management for semantic knowledge graphs
    """,
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,  # we serve openapi.json via custom route so we can inject "servers" for proxy
)
# Root app: serve the same API at / (direct :8000) and at /autodw (behind proxy at https://alfie.iti.gr/autodw).
# When the proxy forwards e.g. https://alfie.iti.gr/autodw/health to backend:8000/autodw/health,
# the mount strips the prefix and the sub-app receives /health. Lifespan runs on root so startup/shutdown run once.
root_app = FastAPI(
    title="Data Warehouse API (root)",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,  # no openapi on root so /openapi.json is served by mounted inner_app (avoids empty spec when proxy strips prefix)
)
root_app.mount("/autodw", inner_app)
root_app.mount("/", inner_app)
# Custom docs: use X-Forwarded-Prefix only when request came through a proxy (other X-Forwarded-* set), else /openapi.json for direct :8000 access
def _openapi_url_for_request(request: Request) -> str:
    prefix = request.headers.get("X-Forwarded-Prefix", "").strip().rstrip("/")
    from_proxy = any(request.headers.get(h) for h in ("X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host"))
    if prefix and from_proxy:
        return f"{prefix}/openapi.json"
    return "/openapi.json"


def _openapi_schema_with_servers(request: Request) -> dict:
    """Return OpenAPI schema; when behind proxy, add servers so Swagger UI calls /autodw/... not /..."""
    schema = inner_app.openapi()
    prefix = request.headers.get("X-Forwarded-Prefix", "").strip().rstrip("/")
    from_proxy = any(request.headers.get(h) for h in ("X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host"))
    if prefix and from_proxy:
        proto = request.headers.get("X-Forwarded-Proto", "https")
        host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", ""))
        base = f"{proto}://{host}{prefix}"
        schema["servers"] = [{"url": base}]
    return schema


@inner_app.get("/openapi.json", include_in_schema=False)
async def custom_openapi_json(request: Request):
    """Serve OpenAPI schema with correct servers when behind proxy (so Try it out uses /autodw/...)."""
    from fastapi.responses import JSONResponse
    return JSONResponse(content=_openapi_schema_with_servers(request))


@inner_app.get("/docs", include_in_schema=False)
async def swagger_ui_html(request: Request):
    openapi_url = _openapi_url_for_request(request)
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title=inner_app.title + " - Swagger UI",
    )


@inner_app.get("/redoc", include_in_schema=False)
async def redoc_html(request: Request):
    from fastapi.openapi.docs import get_redoc_html
    openapi_url = _openapi_url_for_request(request)
    return get_redoc_html(
        openapi_url=openapi_url,
        title=inner_app.title + " - ReDoc",
    )

# Add CORS middleware to inner app
inner_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers on inner app
inner_app.include_router(datasets.router)
inner_app.include_router(users.router)
inner_app.include_router(bias_reports.router)
inner_app.include_router(transformation_reports.router)
inner_app.include_router(ai_models.router)
inner_app.include_router(xai_reports.router)
inner_app.include_router(etd_hub.router)
inner_app.include_router(etd_hub_import.router)
inner_app.include_router(graphdb.router)
inner_app.include_router(user_files.router)


@inner_app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Welcome to Data Warehouse API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@inner_app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # You could add more comprehensive health checks here
        # like checking database connectivity, MinIO availability, etc.
        return {
            "status": "healthy",
            "services": {
                "api": "running",
                "database": "connected",
                "file_storage": "connected"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


# Export for uvicorn: root app so both / and /autodw work
app = root_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
