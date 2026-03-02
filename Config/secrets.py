"""
VFAST Application Settings
Loads configuration from .env file
"""

from pydantic_settings import BaseSettings
from pydantic import Field
import os
from dotenv import load_dotenv
import logging

# Load .env file
load_dotenv()

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """
    Application Configuration Settings
    Loads from .env file in root directory
    """
    
    # ============ DATABASE CONFIGURATION ============
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/vfast",
        description="PostgreSQL connection string"
    )
    
    # ============ JWT CONFIGURATION ============
    jwt_secret_key: str = Field(
        default="test-secret-key-change-in-production-12345",
        description="Secret key for JWT token signing"
    )
    
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT algorithm"
    )
    
    access_token_expire_minutes: int = Field(
        default=1440,
        description="JWT token expiration time in minutes"
    )
    
    # ============ GOOGLE OAUTH CONFIGURATION ============
    google_client_id: str = Field(
        default="",
        description="Google OAuth 2.0 Client ID"
    )
    
    google_client_secret: str = Field(
        default="",
        description="Google OAuth 2.0 Client Secret"
    )
    
    # ============ EMAIL CONFIGURATION ============
    gmail_user: str = Field(
        default="dummy@gmail.com",
        description="Gmail address for sending emails"
    )
    
    gmail_password: str = Field(
        default="dummy-password",
        description="Gmail app-specific password"
    )
    
    # ============ APPLICATION CONFIGURATION ============
    environment: str = Field(
        default="development",
        description="Application environment (development/production)"
    )
    
    api_port: int = Field(
        default=8000,
        description="API server port"
    )
    
    api_host: str = Field(
        default="localhost",
        description="API server host"
    )
    
    debug: bool = Field(
        default=True,
        description="Debug mode flag"
    )
    
    class Config:
        """Pydantic Configuration"""
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # ✅ CRITICAL: Ignore extra environment variables
        env_file_encoding = "utf-8"


# Create global settings instance
try:
    settings = Settings()
    logger.info("✅ Settings loaded from .env file")
    
    # Log loaded environment
    logger.info(f"   Environment: {settings.environment}")
    logger.info(f"   Debug Mode: {settings.debug}")
    logger.info(f"   API: {settings.api_host}:{settings.api_port}")
    
except Exception as e:
    logger.error(f"❌ Failed to load settings: {str(e)}")
    raise


# Export settings for use in other modules
__all__ = ['settings', 'Settings']