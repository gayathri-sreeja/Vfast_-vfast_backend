"""
User Authentication Endpoints
Handles frontend user Google sign-in, creating/updating records in vfast.users
and issuing scoped JWTs for booking API calls.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import logging

from Config.database import get_db
from Config.models import User
from Config.jwt import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth/user",
    tags=["User Auth"]
)


class GoogleSignInRequest(BaseModel):
    google_id: str
    email: str
    name: str
    phone_number: Optional[str] = ""
    institution_id: Optional[str] = ""
    department: Optional[str] = ""


@router.post("/google-signin", summary="Frontend user Google sign-in")
async def user_google_signin(
    body: GoogleSignInRequest,
    db: Session = Depends(get_db)
):
    """
    Called by the frontend immediately after Google OAuth.
    1. Finds existing user by email or google_id, OR creates a new STUDENT record.
    2. Returns a scoped JWT (scope=user) valid for 24 h.
    """
    # Find existing user
    user = db.query(User).filter(
        or_(User.email == body.email, User.google_id == body.google_id)
    ).first()

    if user:
        # Sync latest profile data from Google
        if body.name:
            user.name = body.name
        if body.phone_number:
            user.phone_number = body.phone_number
        if not user.google_id and body.google_id:
            user.google_id = body.google_id
        if not user.institution_id and body.institution_id:
            user.institution_id = body.institution_id
        if not user.department and body.department:
            user.department = body.department
        user.last_login = datetime.utcnow()
        logger.info(f"🔄 Existing user signed in: {user.email}")
    else:
        # Create a new user record
        user = User(
            email          = body.email,
            name           = body.name,
            phone_number   = body.phone_number or None,
            google_id      = body.google_id,
            user_type      = "STUDENT",
            institution_id = body.institution_id or None,
            department     = body.department or None,
            is_active      = True,
            last_login     = datetime.utcnow(),
        )
        db.add(user)
        logger.info(f"✅ New user created: {body.email}")

    db.commit()
    db.refresh(user)

    # Issue a user-scoped JWT
    token = create_access_token(
        data={
            "sub":   str(user.id),
            "email": user.email,
            "scope": "user",
        },
        expires_delta=timedelta(hours=24),
        scope="user",
    )

    return {
        "status": "success",
        "data": {
            "access_token": token,
            "user": {
                "id":        user.id,
                "email":     user.email,
                "name":      user.name,
                "user_type": user.user_type,
            }
        }
    }


# ──────────────────────────────────────────────
# BITS Email Login
# ──────────────────────────────────────────────

class BitsLoginRequest(BaseModel):
    email: str
    user_type: str  # 'STUDENT' or 'FACULTY'


@router.post("/bits-login", summary="Login with BITS Pilani email")
async def bits_login(
    body: BitsLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login with BITS Pilani email address.
    - Creates user if not exists
    - Returns JWT token
    - user_type determined by frontend based on email pattern
    """
    email = body.email.strip().lower()
    user_type = body.user_type.upper()
    
    # Validate domain
    if not email.endswith('@pilani.bits-pilani.ac.in'):
        raise HTTPException(status_code=400, detail="Only BITS Pilani emails are allowed")
    
    # Validate user_type
    if user_type not in ['STUDENT', 'FACULTY']:
        raise HTTPException(status_code=400, detail="Invalid user type")
    
    # Extract name from email
    local_part = email.split('@')[0]
    # Convert email part to name (e.g., "h20241234" -> "H20241234", "meera.iyer" -> "Meera Iyer")
    if '.' in local_part:
        name = ' '.join(word.capitalize() for word in local_part.split('.'))
    else:
        name = local_part.upper() if user_type == 'STUDENT' else local_part.capitalize()
    
    # Find or create user
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        user = User(
            email      = email,
            name       = name,
            user_type  = user_type,
            is_active  = True,
            last_login = datetime.utcnow(),
        )
        db.add(user)
        logger.info(f"✅ New {user_type} user created: {email}")
    else:
        user.last_login = datetime.utcnow()
        # Update user_type if changed (shouldn't happen normally)
        if user.user_type != user_type:
            user.user_type = user_type
    
    db.commit()
    db.refresh(user)
    
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "scope": "user"},
        expires_delta=timedelta(hours=24),
        scope="user",
    )
    
    logger.info(f"🔑 BITS login: {email} ({user_type})")
    
    return {
        "status": "success",
        "data": {
            "access_token": token,
            "user": {
                "id":        user.id,
                "email":     user.email,
                "name":      user.name,
                "user_type": user.user_type,
            }
        }
    }


# ──────────────────────────────────────────────
# DEV Login — local testing only
# ──────────────────────────────────────────────

@router.post("/dev-login-student", summary="[DEV ONLY] Login as Rahul Sharma (Student)")
async def dev_login_student(db: Session = Depends(get_db)):
    """
    Creates (or retrieves) the test student user 'Rahul Sharma' in the database
    and returns a valid JWT. Remove this endpoint before production deployment.
    """
    DEV_EMAIL = "rahul.student@bits-pilani.ac.in"
    DEV_NAME = "Rahul Sharma"

    user = db.query(User).filter(User.email == DEV_EMAIL).first()

    if not user:
        user = User(
            email      = DEV_EMAIL,
            name       = DEV_NAME,
            user_type  = "STUDENT",
            is_active  = True,
            last_login = datetime.utcnow(),
        )
        db.add(user)
        logger.warning(f"🛠️  DEV student user '{DEV_NAME}' created")
    else:
        user.last_login = datetime.utcnow()

    db.commit()
    db.refresh(user)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "scope": "user"},
        expires_delta=timedelta(hours=24),
        scope="user",
    )

    logger.warning("⚠️  DEV STUDENT LOGIN used — disable before production!")

    return {
        "status": "success",
        "data": {
            "access_token": token,
            "user": {
                "id":        user.id,
                "email":     user.email,
                "name":      user.name,
                "user_type": user.user_type,
            }
        }
    }


@router.post("/dev-login-faculty", summary="[DEV ONLY] Login as Dr. Meera Iyer (Faculty)")
async def dev_login_faculty(db: Session = Depends(get_db)):
    """
    Creates (or retrieves) the test faculty user 'Dr. Meera Iyer' in the database
    and returns a valid JWT. Remove this endpoint before production deployment.
    """
    DEV_EMAIL = "meera.faculty@bits-pilani.ac.in"
    DEV_NAME = "Dr. Meera Iyer"

    user = db.query(User).filter(User.email == DEV_EMAIL).first()

    if not user:
        user = User(
            email      = DEV_EMAIL,
            name       = DEV_NAME,
            user_type  = "FACULTY",
            is_active  = True,
            last_login = datetime.utcnow(),
        )
        db.add(user)
        logger.warning(f"🛠️  DEV faculty user '{DEV_NAME}' created")
    else:
        user.last_login = datetime.utcnow()

    db.commit()
    db.refresh(user)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "scope": "user"},
        expires_delta=timedelta(hours=24),
        scope="user",
    )

    logger.warning("⚠️  DEV FACULTY LOGIN used — disable before production!")

    return {
        "status": "success",
        "data": {
            "access_token": token,
            "user": {
                "id":        user.id,
                "email":     user.email,
                "name":      user.name,
                "user_type": user.user_type,
            }
        }
    }


# Keep legacy endpoint for backwards compatibility
@router.post("/dev-login", summary="[DEV ONLY] Login as user1 (legacy)")
async def dev_login(db: Session = Depends(get_db)):
    """Legacy dev login - redirects to student login."""
    return await dev_login_student(db)
