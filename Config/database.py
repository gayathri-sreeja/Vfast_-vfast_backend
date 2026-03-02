import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# PostgreSQL Connection String
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/vfast"
)

print(f"📊 Connecting to: {DATABASE_URL.split('@')[1]}")

# Create Engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    echo=False,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"connect_timeout": 10}
)

# Set search path to vfast schema on connection
@event.listens_for(engine, "connect")
def set_search_path(dbapi_conn, connection_record):
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET search_path TO vfast, public")
        cursor.close()
        logger.info("✅ PostgreSQL vfast schema connected")
    except Exception as e:
        logger.error(f"❌ Schema connection error: {str(e)}")

# Session Factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db() -> Session:
    """Dependency injection for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    try:
        from Config.models import Base
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database init error: {str(e)}")

def check_db_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            db_version = result.fetchone()[0]
            logger.info(f"✅ Database connected: {db_version.split(',')[0]}")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        return False