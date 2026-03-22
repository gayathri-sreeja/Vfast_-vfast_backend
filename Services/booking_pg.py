"""
PostgreSQL-backed Booking Endpoints
Handles reservation submissions from the VFAST frontend, storing all
data in the vfast.booking_requests (and related) PostgreSQL tables.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
import logging
import jwt
import os

from Config.database import get_db
from Config.models import (
    BookingRequest, User, RoomType, Room, BookingHistory
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/booking",
    tags=["Booking (PostgreSQL)"]
)

# Optional bearer — we never hard-reject missing tokens here;
# that is handled per-endpoint.
_bearer = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "your_super_secret_key_here_change_in_production_12345")
JWT_ALG    = os.getenv("JWT_ALGORITHM", "HS256")


# ──────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────

class SubmitBookingRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    email: str
    phone_number: Optional[str] = ""
    gender: Optional[str] = ""
    nationality: Optional[str] = "Indian"
    check_in: str           # "YYYY-MM-DD"
    check_out: str          # "YYYY-MM-DD"
    pax: int
    room_count: Optional[int] = 1
    room_type_id: int
    booking_type: Optional[str] = "STUDENT"
    is_international: Optional[bool] = False
    is_bulk: Optional[bool] = False
    purpose_of_visit: Optional[str] = ""
    special_requirements: Optional[str] = ""
    gst_number: Optional[str] = ""
    relation_to_campus: Optional[str] = ""


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _decode_token(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[dict]:
    """Return decoded payload or None (never raises)."""
    if not credentials:
        return None
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception:
        return None


def _get_or_create_user(db: Session, email: str, name: str = "", phone: str = "") -> User:
    """Return existing user by email, or create a minimal record."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        first  = name.split()[0] if name else email.split("@")[0]
        user   = User(
            email=email,
            name=name or first,
            phone_number=phone or None,
            user_type="STUDENT",
            is_active=True,
        )
        db.add(user)
        db.flush()          # get id without full commit
        logger.info(f"Created new user for email={email} id={user.id}")
    return user


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid date format '{s}'. Expected YYYY-MM-DD."
        )


def _rooms_occupied_in_range(db: Session, room_type_id: int,
                              check_in: date, check_out: date) -> int:
    """Count bookings that overlap with the requested range (not REJECTED/CHECKED_OUT)."""
    active_statuses = ('PENDING', 'APPROVED', 'CHECKED_IN')
    return db.query(func.count(BookingRequest.id)).filter(
        BookingRequest.room_type_id == room_type_id,
        BookingRequest.status.in_(active_statuses),
        BookingRequest.check_in  < check_out,
        BookingRequest.check_out > check_in,
    ).scalar() or 0


# ──────────────────────────────────────────────
# GET /booking/room-types
# ──────────────────────────────────────────────

@router.get("/room-types", summary="List all active room types")
async def get_room_types(db: Session = Depends(get_db)):
    """
    Returns active room types from vfast.room_types.
    Used by the frontend booking form dropdown.
    """
    room_types = (
        db.query(RoomType)
        .filter(RoomType.is_active == True)
        .order_by(RoomType.id)
        .all()
    )

    data = [
        {
            "id":          rt.id,
            "name":        rt.name,
            "description": rt.description,
            "capacity":    rt.capacity,
            "base_price":  float(rt.base_price) if rt.base_price else 0.0,
            "amenities":   rt.amenities or [],
        }
        for rt in room_types
    ]

    return {"status": "success", "data": {"room_types": data}}


# ──────────────────────────────────────────────
# GET /booking/availability
# ──────────────────────────────────────────────

@router.get("/availability", summary="Check room availability for date range")
async def check_availability(
    check_in: str,
    check_out: str,
    room_type_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Returns availability per room type for the given date range.
    Availability = total rooms of that type − active overlapping bookings.
    """
    ci = _parse_date(check_in)
    co = _parse_date(check_out)

    if co <= ci:
        raise HTTPException(400, "check_out must be after check_in")

    today = date.today()
    if ci < today:
        raise HTTPException(400, "check_in cannot be in the past")

    # Query room types
    q = db.query(RoomType).filter(RoomType.is_active == True)
    if room_type_id:
        q = q.filter(RoomType.id == room_type_id)
    room_types = q.all()

    availability = []
    for rt in room_types:
        total_rooms = db.query(func.count(Room.id)).filter(
            Room.room_type_id == rt.id,
            Room.status == 'AVAILABLE'
        ).scalar() or 0

        occupied = _rooms_occupied_in_range(db, rt.id, ci, co)
        available = max(0, total_rooms - occupied)

        availability.append({
            "room_type_id":   rt.id,
            "room_type_name": rt.name,
            "total_rooms":    total_rooms,
            "occupied_rooms": occupied,
            "available_rooms":available,
        })

    return {"status": "success", "data": {"availability": availability}}


# ──────────────────────────────────────────────
# POST /booking/submit-booking
# ──────────────────────────────────────────────

@router.post("/submit-booking", summary="Submit a reservation request")
async def submit_booking(
    body: SubmitBookingRequest,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)
):
    """
    Saves the reservation to vfast.booking_requests in PostgreSQL.

    User resolution order:
      1. Decode Bearer JWT (scope=user) → look up by user_id
      2. Fallback: find/create user by email supplied in the form
    """
    # ── Resolve user ───────────────────────────────────────────
    user: Optional[User] = None
    payload = _decode_token(credentials)

    if payload and payload.get("scope") == "user":
        uid = payload.get("sub")
        if uid:
            user = db.query(User).filter(User.id == int(uid)).first()

    if not user:
        # look up / create by email
        user = _get_or_create_user(
            db,
            email=body.email,
            name=f"{body.first_name} {body.last_name}".strip(),
            phone=body.phone_number,
        )

    # ── Validate room type ─────────────────────────────────────
    room_type = db.query(RoomType).filter(
        RoomType.id == body.room_type_id,
        RoomType.is_active == True
    ).first()
    if not room_type:
        raise HTTPException(400, f"Room type id={body.room_type_id} not found or inactive")

    # ── Validate dates ─────────────────────────────────────────
    ci = _parse_date(body.check_in)
    co = _parse_date(body.check_out)

    if co <= ci:
        raise HTTPException(400, "check_out must be after check_in")
    if ci < date.today():
        raise HTTPException(400, "check_in cannot be in the past")
    if (co - ci).days > 30:
        raise HTTPException(400, "Maximum stay duration is 30 days")
    if body.pax < 1 or body.pax > 500:
        raise HTTPException(400, "Invalid number of persons")

    # ── Availability guard ─────────────────────────────────────
    occupied = _rooms_occupied_in_range(db, body.room_type_id, ci, co)
    total    = db.query(func.count(Room.id)).filter(
        Room.room_type_id == body.room_type_id
    ).scalar() or 0

    if total > 0 and occupied >= total:
        raise HTTPException(409, "No rooms available for selected dates")

    # ── Determine initial status ────────────────────────────────
    # Faculty Professional with room_count > 2 OR non-Indian nationality requires Dean approval first
    room_count = body.room_count or 1
    booking_type = body.booking_type or "STUDENT"
    nationality = body.nationality or "Indian"
    is_non_indian = nationality.lower() != "indian"
    requires_dean = (
        booking_type == 'FACULTY_PROFESSIONAL' and 
        (room_count > 2 or is_non_indian)
    )
    initial_status = "PENDING_DEAN" if requires_dean else "PENDING"

    # ── Create booking record ──────────────────────────────────
    booking = BookingRequest(
        user_id              = user.id,
        first_name           = body.first_name,
        last_name            = body.last_name or "",
        email                = body.email,
        phone_number         = body.phone_number or "",
        check_in             = ci,
        check_out            = co,
        pax                  = body.pax,
        room_type_id         = body.room_type_id,
        booking_type         = booking_type,
        is_international     = body.is_international or is_non_indian,
        is_bulk              = body.is_bulk,
        purpose_of_visit     = body.purpose_of_visit or "",
        special_requirements = body.special_requirements or "",
        gst_number           = body.gst_number or "",
        relation_to_campus   = body.relation_to_campus or "",
        gender               = body.gender or "",
        nationality          = nationality,
        room_count           = room_count,
        status               = initial_status,
        submitted_at         = datetime.utcnow(),
        created_at           = datetime.utcnow(),
        updated_at           = datetime.utcnow(),
    )
    db.add(booking)
    db.flush()   # get id

    # ── Write history entry ────────────────────────────────────
    history_note = "Booking submitted - Requires Dean approval" if requires_dean else "Booking submitted by guest"
    history = BookingHistory(
        booking_request_id = booking.id,
        status_from        = None,
        status_to          = initial_status,
        notes              = history_note,
        changed_at         = datetime.utcnow(),
    )
    db.add(history)

    db.commit()
    db.refresh(booking)

    status_message = "Reservation submitted. Requires Dean approval first." if requires_dean else "Reservation submitted successfully"
    logger.info(f"✅ Booking #{booking.id} created for user {user.email} (status: {initial_status})")

    return {
        "status": "success",
        "message": status_message,
        "data": {
            "booking_id":  booking.id,
            "status":      booking.status,
            "check_in":    str(booking.check_in),
            "check_out":   str(booking.check_out),
            "room_type":   room_type.name,
            "pax":         booking.pax,
            "submitted_at":booking.submitted_at.strftime("%Y-%m-%d %H:%M"),
        }
    }


# ──────────────────────────────────────────────
# GET /booking/my-bookings
# ──────────────────────────────────────────────

@router.get("/my-bookings", summary="Get bookings for the authenticated user")
async def my_bookings(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)
):
    """
    Returns bookings for the authenticated user (JWT scope=user).
    Also supports lookup by email via ?email=... query param.
    """
    payload = _decode_token(credentials)
    if not payload or payload.get("scope") != "user":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid user token required"
        )

    uid = payload.get("sub")
    bookings = (
        db.query(BookingRequest)
        .filter(BookingRequest.user_id == int(uid))
        .order_by(BookingRequest.submitted_at.desc())
        .all()
    )

    def _rt_name(rt_id):
        if not rt_id:
            return None
        rt = db.query(RoomType).filter(RoomType.id == rt_id).first()
        return rt.name if rt else None

    data = [
        {
            "booking_id":       b.id,
            "status":           b.status,
            "booking_type":     b.booking_type,
            "first_name":       b.first_name,
            "last_name":        b.last_name,
            "check_in":         str(b.check_in),
            "check_out":        str(b.check_out),
            "room_type":        _rt_name(b.room_type_id),
            "pax":              b.pax,
            "purpose_of_visit": b.purpose_of_visit,
            "rejection_reason": b.manager_rejected_reason,
            "submitted_at":     b.submitted_at.strftime("%Y-%m-%d %H:%M") if b.submitted_at else None,
        }
        for b in bookings
    ]

    return {"status": "success", "data": {"bookings": data}}
