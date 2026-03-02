import jwt
from datetime import datetime, timedelta
import logging
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer()

# Load from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_super_secret_key_here_change_in_production_12345")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Validate secret key length
if len(JWT_SECRET_KEY) < 32:
    logger.warning(f"⚠️ JWT_SECRET_KEY is only {len(JWT_SECRET_KEY)} bytes. Minimum recommended: 32 bytes")


def create_access_token(data: dict, expires_delta: timedelta = None, scope: str = "admin"):
    """
    Create JWT access token
    
    Args:
        data: Dictionary with user data
        expires_delta: Custom expiration time
        scope: Token scope (admin, verify_otp, etc)
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    to_encode["scope"] = scope
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })
    
    try:
        encoded_jwt = jwt.encode(
            to_encode,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        
        logger.info(f"✅ Access token created with scope: {scope}")
        return encoded_jwt
        
    except Exception as e:
        logger.error(f"❌ Error creating token: {str(e)}")
        raise


async def get_current_user(credentials = Depends(security)):
    """
    Validate JWT token and extract user information
    
    Args:
        credentials: HTTP Bearer credentials from request
    
    Returns:
        Dictionary with user data (admin_id, email, scope, role, etc)
    
    Raises:
        HTTPException: If token is invalid, expired, or missing required fields
    """
    token = credentials.credentials
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        
        # Extract required fields
        admin_id = payload.get("admin_id")
        email = payload.get("email")
        scope = payload.get("scope")
        
        if admin_id is None:
            logger.error("❌ admin_id not found in token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing admin_id"
            )
        
        if email is None:
            logger.error("❌ email not found in token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing email"
            )
        
        # Log successful validation
        logger.info(f"✅ Token valid for admin_id={admin_id}, email={email}, scope={scope}")
        
        # Return user data
        return {
            "admin_id": admin_id,
            "email": email,
            "scope": scope,
            "role": payload.get("role"),
            "username": payload.get("username"),
            "login_type": payload.get("login_type"),
            "hierarchy_level": payload.get("hierarchy_level"),
            "permissions": payload.get("permissions")
        }
        
    except jwt.ExpiredSignatureError:
        logger.error("❌ Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    
    except jwt.InvalidSignatureError:
        logger.error("❌ Token signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature"
        )
    
    except jwt.DecodeError as e:
        logger.error(f"❌ Token decode error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )
    
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    except Exception as e:
        logger.error(f"❌ Unexpected error verifying token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )


def verify_token(token: str):
    """
    Verify JWT token (without HTTP context)
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload
    
    Raises:
        jwt.InvalidTokenError if token is invalid
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.error("❌ Token expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token: {str(e)}")
        raise