from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from Config.database import get_db
from Config.models import (
    AdminPasswordLoginRequest,
    AdminGoogleLoginRequest,
    VerifyOtpRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    AdminUserResponse,
    AdminUser,
    AdminRole,
    LoginHistory,
    BookingRequest,
    BookingHistory,
    User,
    RoomType
)
from pydantic import BaseModel
from typing import Optional, List, Dict
from Helpers.admin_auth import (
    admin_password_login,
    admin_google_login,
    verify_admin_otp,
    resend_admin_otp,
    forgot_password_request,
    reset_password_with_otp,
    change_password_request,
    change_password_with_otp
)
from Config.jwt import get_current_user
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin Authentication"]
)

# ============ ENDPOINT 1: PASSWORD LOGIN ============

@router.post("/login/password", summary="Admin Password Login")
async def password_login(
    request: AdminPasswordLoginRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Admin login with username and password
    
    Returns final JWT token directly (no OTP required)
    Token is valid for 24 hours
    """
    client_ip = req.client.host if req.client else None
    
    response_data, error = await admin_password_login(
        db,
        request.username,
        request.password,
        ip_address=client_ip
    )
    
    if error:
        raise HTTPException(status_code=401, detail=error)
    
    return response_data


# ============ ENDPOINT 2: GOOGLE OAUTH LOGIN ============

@router.post("/login/google", summary="Admin Google OAuth Login")
async def google_login(
    request: AdminGoogleLoginRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Admin login with Google OAuth token
    
    Returns final JWT token directly (no OTP required)
    Token valid for 24 hours
    """
    client_ip = req.client.host if req.client else None
    
    response_data, error = await admin_google_login(
        db,
        request.token,
        ip_address=client_ip
    )
    
    if error:
        raise HTTPException(status_code=401, detail=error)
    
    return response_data


# ============ ENDPOINT 3: VERIFY OTP ============

@router.post("/verify-otp", summary="Verify OTP & Get Final JWT")
async def verify_otp(
    otp_request: VerifyOtpRequest,
    req: Request,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify OTP and get final admin JWT token
    
    Requires temporary JWT from /login/password or /login/google
    
    Returns final JWT with full admin scope (valid 24 hours)
    """
    try:
        # ✅ Check scope inside the handler
        token_scope = current_user.get("scope")
        if token_scope != "verify_otp":
            logger.warning(f"❌ Invalid scope for OTP verification: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'verify_otp'"
            )
        
        client_ip = req.client.host if req.client else None
        admin_id = current_user.get('admin_id')
        login_type = current_user.get('login_type', 'UNKNOWN')
        
        logger.info(f"🔐 Verifying OTP for admin {admin_id}")
        
        # Verify OTP and return final token
        response_data, error = await verify_admin_otp(
            db,
            admin_id,
            otp_request.otp,
            login_type,
            ip_address=client_ip
        )
        
        if error:
            raise HTTPException(status_code=401, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ OTP verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )


# ============ ENDPOINT 4: RESEND OTP ============

@router.post("/resend-otp", summary="Request New OTP")
async def resend_otp(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Request new OTP if previous one expired
    
    Requires temporary JWT from /login/password or /login/google
    """
    try:
        # ✅ Check scope inside the handler
        token_scope = current_user.get("scope")
        if token_scope != "verify_otp":
            logger.warning(f"❌ Invalid scope for resend OTP: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'verify_otp'"
            )
        
        admin_id = current_user.get('admin_id')
        logger.info(f"📧 Resending OTP for admin {admin_id}")
        
        response_data, error = await resend_admin_otp(
            db,
            admin_id
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Resend OTP error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resend OTP failed"
        )


# ============ ENDPOINT 5: GET CURRENT ADMIN PROFILE ============

@router.get("/me", response_model=AdminUserResponse, summary="Get Current Admin Profile")
async def get_current_admin_profile(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Get current logged-in admin's profile information
    
    Requires final admin JWT token
    """
    try:
        # ✅ Check scope inside the handler
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            logger.warning(f"❌ Invalid scope for profile access: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        admin_id = current_user.get('admin_id')
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        
        if not admin:
            logger.warning(f"❌ Admin not found: {admin_id}")
            raise HTTPException(status_code=404, detail="Admin not found")
        
        logger.info(f"✅ Admin profile retrieved: {admin.email}")
        
        return {
            'id': admin.id,
            'email': admin.email,
            'name': admin.name,
            'role_name': current_user.get('role'),
            'hierarchy_level': current_user.get('hierarchy_level'),
            'permissions': current_user.get('permissions'),
            'is_active': admin.is_active
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving admin profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT 6: LOGOUT ============

@router.post("/logout", summary="Admin Logout")
async def logout(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Log out admin and record logout timestamp
    
    Requires admin JWT token
    """
    try:
        # ✅ Check scope inside the handler
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            logger.warning(f"❌ Invalid scope for logout: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        admin_id = current_user.get('admin_id')
        
        # Find most recent login
        recent_login = db.query(LoginHistory).filter(
            LoginHistory.admin_id == admin_id
        ).order_by(LoginHistory.login_timestamp.desc()).first()
        
        if recent_login:
            recent_login.logout_timestamp = datetime.utcnow()
            db.commit()
        
        logger.info(f"✅ Admin logged out: {current_user.get('email')}")
        
        return {'status': 'success', 'message': 'Logged out successfully'}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Logout error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT 7: GET ADMIN STATS ============

@router.get("/stats", summary="Get Admin Dashboard Stats")
async def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Get comprehensive dashboard statistics for admin.
    Returns booking counts by status, room availability, user totals,
    today's activity, recent bookings, and role-specific metrics.
    Requires admin JWT token.
    """
    try:
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )

        from Config.models import BookingRequest, Room, User, RoomAllocation
        from sqlalchemy import func, cast, Date

        admin_id = current_user.get('admin_id')
        role = current_user.get('role')
        today = datetime.utcnow().date()

        logger.info(f"📊 Retrieving dashboard stats for admin {admin_id} (role: {role})")

        # ── Booking counts by status ──────────────────────────────────
        booking_status_rows = (
            db.query(BookingRequest.status, func.count(BookingRequest.id))
            .group_by(BookingRequest.status)
            .all()
        )
        booking_by_status = {row[0]: row[1] for row in booking_status_rows}
        total_bookings    = sum(booking_by_status.values())
        pending_bookings  = booking_by_status.get('PENDING', 0)
        approved_bookings = booking_by_status.get('APPROVED', 0)
        rejected_bookings = booking_by_status.get('REJECTED', 0)
        checked_in        = booking_by_status.get('CHECKED_IN', 0)
        checked_out       = booking_by_status.get('CHECKED_OUT', 0)

        # ── Today's activity ──────────────────────────────────────────
        checkins_today = (
            db.query(func.count(BookingRequest.id))
            .filter(cast(BookingRequest.check_in, Date) == today)
            .scalar() or 0
        )
        checkouts_today = (
            db.query(func.count(BookingRequest.id))
            .filter(cast(BookingRequest.check_out, Date) == today)
            .scalar() or 0
        )

        # ── Room stats ────────────────────────────────────────────────
        total_rooms     = db.query(func.count(Room.id)).scalar() or 0
        available_rooms = (
            db.query(func.count(Room.id))
            .filter(Room.status == 'AVAILABLE')
            .scalar() or 0
        )
        occupied_rooms  = total_rooms - available_rooms

        # ── User stats ────────────────────────────────────────────────
        total_users = db.query(func.count(User.id)).scalar() or 0

        # ── Admin login history ───────────────────────────────────────
        total_logins = (
            db.query(func.count(LoginHistory.id))
            .filter(LoginHistory.admin_id == admin_id)
            .scalar() or 0
        )

        # ── Recent bookings (last 10) ─────────────────────────────────
        recent_rows = (
            db.query(BookingRequest)
            .order_by(BookingRequest.created_at.desc())
            .limit(10)
            .all()
        )
        recent_bookings = [
            {
                'id':            r.id,
                'name':          f"{r.first_name} {r.last_name or ''}".strip(),
                'email':         r.email,
                'check_in':      str(r.check_in),
                'check_out':     str(r.check_out),
                'status':        r.status,
                'pax':           r.pax,
                'submitted_at':  r.submitted_at.strftime('%Y-%m-%d %H:%M') if r.submitted_at else None,
            }
            for r in recent_rows
        ]

        # ── Role-specific stats ───────────────────────────────────────
        role_stats: Dict = {}
        if role == 'MANAGER':
            role_stats['total_approvals'] = (
                db.query(func.count(BookingRequest.id))
                .filter(BookingRequest.manager_approved_by == admin_id)
                .scalar() or 0
            )
        elif role == 'OPERATOR':
            role_stats['total_allocations'] = (
                db.query(func.count(BookingRequest.id))
                .filter(BookingRequest.operator_allocated_by == admin_id)
                .scalar() or 0
            )
        elif role in ('DEAN', 'FIC', 'IN_CHARGE'):
            role_stats['total_approvals'] = (
                db.query(func.count(BookingRequest.id))
                .filter(BookingRequest.dean_approved_by == admin_id)
                .scalar() or 0
            )

        logger.info(f"✅ Dashboard stats compiled for {current_user.get('email')}")

        return {
            'admin_id':         admin_id,
            'role':             role,
            'total_logins':     total_logins,
            'bookings': {
                'total':        total_bookings,
                'pending':      pending_bookings,
                'approved':     approved_bookings,
                'rejected':     rejected_bookings,
                'checked_in':   checked_in,
                'checked_out':  checked_out,
            },
            'today': {
                'checkins':     checkins_today,
                'checkouts':    checkouts_today,
            },
            'rooms': {
                'total':        total_rooms,
                'available':    available_rooms,
                'occupied':     occupied_rooms,
            },
            'users': {
                'total':        total_users,
            },
            'recent_bookings':  recent_bookings,
            **role_stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ ENDPOINT 8: FORGOT PASSWORD - REQUEST OTP ============

@router.post("/forgot-password", summary="Request Password Reset OTP")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset OTP
    
    Sends OTP to the admin's registered email
    Returns temporary reset token for password reset flow
    """
    try:
        logger.info(f"📧 Forgot password request for: {request.email}")
        
        response_data, error = await forgot_password_request(
            db,
            request.email
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Forgot password error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset request failed"
        )


# ============ ENDPOINT 9: RESET PASSWORD WITH OTP ============

@router.post("/reset-password", summary="Reset Password with OTP")
async def reset_password(
    reset_request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Reset password using OTP
    
    Requires temporary reset_password token from /forgot-password
    Verifies OTP and sets new password
    """
    try:
        # Check scope
        token_scope = current_user.get("scope")
        if token_scope != "reset_password":
            logger.warning(f"❌ Invalid scope for password reset: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'reset_password'"
            )
        
        admin_id = current_user.get('admin_id')
        logger.info(f"🔐 Password reset for admin {admin_id}")
        
        response_data, error = await reset_password_with_otp(
            db,
            admin_id,
            reset_request.otp,
            reset_request.new_password
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


# ============ ENDPOINT 10: CHANGE PASSWORD - REQUEST OTP ============

@router.post("/change-password/request-otp", summary="Request OTP for Password Change")
async def request_password_change_otp(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Request OTP to change password
    
    Requires admin JWT token (logged-in user)
    Sends OTP to admin's email for verification
    """
    try:
        # Check scope
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            logger.warning(f"❌ Invalid scope for change password request: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        admin_id = current_user.get('admin_id')
        logger.info(f"📧 Change password OTP request for admin {admin_id}")
        
        response_data, error = await change_password_request(
            db,
            admin_id
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Change password OTP request error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Change password OTP request failed"
        )


# ============ ENDPOINT 11: CHANGE PASSWORD WITH OTP ============

@router.post("/change-password", summary="Change Password with OTP")
async def change_password(
    change_request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Change password with OTP verification
    
    Requires admin JWT token (logged-in user)
    Verifies current password, OTP, then changes to new password
    """
    try:
        # Check scope
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            logger.warning(f"❌ Invalid scope for change password: {token_scope}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        admin_id = current_user.get('admin_id')
        logger.info(f"🔐 Change password for admin {admin_id}")
        
        response_data, error = await change_password_with_otp(
            db,
            admin_id,
            change_request.current_password,
            change_request.otp,
            change_request.new_password
        )
        
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Change password error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# RESERVATION MANAGEMENT ENDPOINTS (OPERATOR/ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

class RejectReservationRequest(BaseModel):
    reason: str


@router.get("/reservations", summary="List All Reservations")
async def list_reservations(
    status_filter: Optional[str] = None,
    booking_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    List all reservations for admin/operator review.
    
    Query Parameters:
    - status_filter: PENDING, APPROVED, REJECTED, CHECKED_IN, CHECKED_OUT
    - booking_type: STUDENT, FACULTY_PERSONAL, FACULTY_PROFESSIONAL
    
    Requires admin JWT token.
    """
    try:
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        query = db.query(BookingRequest).order_by(BookingRequest.submitted_at.desc())
        
        if status_filter:
            query = query.filter(BookingRequest.status == status_filter.upper())
        
        if booking_type:
            query = query.filter(BookingRequest.booking_type == booking_type.upper())
        
        reservations = query.all()
        
        result = []
        for r in reservations:
            # Get user info
            user = db.query(User).filter(User.id == r.user_id).first()
            # Get room type info
            room_type = db.query(RoomType).filter(RoomType.id == r.room_type_id).first() if r.room_type_id else None
            
            # Determine display name based on booking type
            if r.booking_type == 'FACULTY_PROFESSIONAL':
                display_name = r.first_name  # Event Name
                display_detail = r.last_name  # Department
            else:
                display_name = f"{r.first_name} {r.last_name}".strip()
                display_detail = None
            
            result.append({
                'id': r.id,
                'display_name': display_name,
                'display_detail': display_detail,
                'email': r.email,
                'phone_number': r.phone_number,
                'check_in': str(r.check_in) if r.check_in else None,
                'check_out': str(r.check_out) if r.check_out else None,
                'pax': r.pax,
                'room_type': room_type.name if room_type else 'Unknown',
                'booking_type': r.booking_type,
                'status': r.status,
                'purpose_of_visit': r.purpose_of_visit,
                'special_requirements': r.special_requirements,
                'submitted_at': r.submitted_at.isoformat() if r.submitted_at else None,
                'user_name': user.name if user else 'Unknown',
                'user_email': user.email if user else None,
                'manager_rejected_reason': r.manager_rejected_reason
            })
        
        return {
            'status': 'success',
            'data': {
                'reservations': result,
                'total': len(result)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error listing reservations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reservations/{reservation_id}", summary="Get Reservation Details")
async def get_reservation_details(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Get detailed information about a specific reservation.
    
    Requires admin JWT token.
    """
    try:
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        reservation = db.query(BookingRequest).filter(BookingRequest.id == reservation_id).first()
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        
        user = db.query(User).filter(User.id == reservation.user_id).first()
        room_type = db.query(RoomType).filter(RoomType.id == reservation.room_type_id).first() if reservation.room_type_id else None
        
        # Get history
        history = db.query(BookingHistory).filter(
            BookingHistory.booking_request_id == reservation_id
        ).order_by(BookingHistory.changed_at.desc()).all()
        
        history_list = [{
            'id': h.id,
            'status_from': h.status_from,
            'status_to': h.status_to,
            'notes': h.notes,
            'changed_at': h.changed_at.isoformat() if h.changed_at else None
        } for h in history]
        
        return {
            'status': 'success',
            'data': {
                'reservation': {
                    'id': reservation.id,
                    'first_name': reservation.first_name,
                    'last_name': reservation.last_name,
                    'email': reservation.email,
                    'phone_number': reservation.phone_number,
                    'check_in': str(reservation.check_in) if reservation.check_in else None,
                    'check_out': str(reservation.check_out) if reservation.check_out else None,
                    'pax': reservation.pax,
                    'room_type': room_type.name if room_type else 'Unknown',
                    'room_type_id': reservation.room_type_id,
                    'booking_type': reservation.booking_type,
                    'status': reservation.status,
                    'purpose_of_visit': reservation.purpose_of_visit,
                    'special_requirements': reservation.special_requirements,
                    'relation_to_campus': reservation.relation_to_campus,
                    'submitted_at': reservation.submitted_at.isoformat() if reservation.submitted_at else None,
                    'manager_rejected_reason': reservation.manager_rejected_reason
                },
                'user': {
                    'id': user.id if user else None,
                    'name': user.name if user else 'Unknown',
                    'email': user.email if user else None,
                    'user_type': user.user_type if user else None
                },
                'history': history_list
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting reservation details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservations/{reservation_id}/accept", summary="Accept Reservation")
async def accept_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Accept a pending reservation.
    
    Changes status from PENDING to APPROVED.
    Requires admin JWT token.
    """
    try:
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        admin_id = current_user.get('admin_id')
        
        reservation = db.query(BookingRequest).filter(BookingRequest.id == reservation_id).first()
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        
        if reservation.status != 'PENDING':
            raise HTTPException(status_code=400, detail=f"Reservation is already {reservation.status}")
        
        # Update reservation
        old_status = reservation.status
        reservation.status = 'APPROVED'
        reservation.manager_approved_at = datetime.utcnow()
        reservation.manager_approved_by = admin_id
        reservation.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=reservation_id,
            status_from=old_status,
            status_to='APPROVED',
            notes=f"Accepted by admin ID {admin_id}",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"✅ Reservation {reservation_id} accepted by admin {admin_id}")
        
        return {
            'status': 'success',
            'message': f'Reservation #{reservation_id} has been accepted',
            'data': {
                'reservation_id': reservation_id,
                'new_status': 'APPROVED'
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error accepting reservation: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reservations/{reservation_id}/reject", summary="Reject Reservation")
async def reject_reservation(
    reservation_id: int,
    body: RejectReservationRequest,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user)
):
    """
    Reject a pending reservation with a reason.
    
    Changes status from PENDING to REJECTED.
    Requires admin JWT token.
    
    Body:
    - reason: Rejection reason (required)
    """
    try:
        token_scope = current_user.get("scope")
        if token_scope != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid scope: {token_scope}. Expected 'admin'"
            )
        
        if not body.reason or not body.reason.strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required")
        
        admin_id = current_user.get('admin_id')
        
        reservation = db.query(BookingRequest).filter(BookingRequest.id == reservation_id).first()
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        
        if reservation.status != 'PENDING':
            raise HTTPException(status_code=400, detail=f"Reservation is already {reservation.status}")
        
        # Update reservation
        old_status = reservation.status
        reservation.status = 'REJECTED'
        reservation.manager_rejected_reason = body.reason.strip()
        reservation.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=reservation_id,
            status_from=old_status,
            status_to='REJECTED',
            notes=f"Rejected by admin ID {admin_id}: {body.reason.strip()}",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"❌ Reservation {reservation_id} rejected by admin {admin_id}: {body.reason}")
        
        return {
            'status': 'success',
            'message': f'Reservation #{reservation_id} has been rejected',
            'data': {
                'reservation_id': reservation_id,
                'new_status': 'REJECTED',
                'reason': body.reason.strip()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error rejecting reservation: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))