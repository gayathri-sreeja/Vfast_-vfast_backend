import uvicorn
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from Config.database import init_db, check_db_connection
from Services.admin_auth import router as admin_auth_router
from Services.booking_pg import router as booking_router
from Services.user_auth import router as user_auth_router
from Services.operator import router as operator_router
from Config.environment import APP_CONFIG

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=APP_CONFIG['name'],
    description="Visitor and Facility Allocation System Tool",
    version=APP_CONFIG['version'],
    docs_url="/docs",
    redoc_url="/redoc"
)

# Trust proxy headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.bits-pilani.ac.in"]
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:4000",
        "http://localhost:5000",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4000",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:5500",
        "https://vfast.bits-pilani.ac.in",
        "http://vfast.bits-pilani.ac.in",
        "*" if APP_CONFIG['debug'] else "https://vfast-admin.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🚀 VFAST Backend Starting...")
    logger.info("=" * 50)
    logger.info(f"Environment: {APP_CONFIG['environment']}")
    logger.info(f"Debug Mode: {APP_CONFIG['debug']}")
    
    # Check database connection
    if check_db_connection():
        init_db()
        logger.info("✅ Database connected and initialized")
    else:
        logger.error("❌ Database connection failed!")
        logger.error("⚠️ Some features may not work correctly")
    
    logger.info("✅ Backend startup complete")
    logger.info("=" * 50)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 VFAST Backend shutting down...")

# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    from Config.database import check_db_connection
    db_ok = check_db_connection()
    
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "service": "VFAST Backend"
    }

# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """Root endpoint"""
    return {
        "name": APP_CONFIG['name'],
        "version": APP_CONFIG['version'],
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

# Include routers
logger.info("📌 Including API routers...")
app.include_router(admin_auth_router, prefix="/api/v1")
logger.info("✅ Admin auth router included")
app.include_router(booking_router, prefix="/api/v1")
logger.info("✅ Booking router included")
app.include_router(user_auth_router, prefix="/api/v1")
logger.info("✅ User auth router included")
app.include_router(operator_router, prefix="/api/v1/admin")
logger.info("✅ Operator router included")

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"❌ Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": str(exc),
            "path": str(request.url)
        }
    )

if __name__ == '__main__':
    logger.info("📊 Starting Uvicorn server...")
    uvicorn.run(
        app=app,
        host='0.0.0.0',
        port=8000,
        log_level='info',
        reload=True,
        access_log=True
    )