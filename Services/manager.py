"""
Manager Service - Booking Approval & Rejection
Handles manager-specific booking approval workflows for VFAST.
Manager sees PENDING bookings and can approve/reject them.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import logging

from Config.database import get_db
from Config.models import (
    BookingRequest, BookingHistory, RoomType, User
)
from Services.admin_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/manager",
    tags=["Manager"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class RejectBookingRequest(BaseModel):
    reason: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_manager_access(current_user: dict) -> int:
    """Verify user has manager/admin scope and return admin_id."""
    if current_user.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required"
        )
    # Check if user has manager role
    role = current_user.get("role", "").lower()
    if role not in ["manager", "admin", "super_admin", "dean", "fic"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required for this action"
        )
    return current_user.get("admin_id")


def _verify_dean_access(current_user: dict) -> int:
    """Verify user has dean role and return admin_id."""
    if current_user.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dean access required"
        )
    role = current_user.get("role", "").lower()
    if role not in ["dean", "admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dean role required for this action"
        )
    return current_user.get("admin_id")


def _requires_dean_approval(booking: BookingRequest) -> bool:
    """Check if a booking requires dean approval.
    
    Returns True if booking_type is FACULTY_PROFESSIONAL AND:
    - room_count > 2, OR
    - nationality is non-Indian
    """
    if booking.booking_type != 'FACULTY_PROFESSIONAL':
        return False
    
    room_count = booking.room_count or 1
    nationality = (booking.nationality or 'Indian').lower()
    is_non_indian = nationality != 'indian'
    
    return room_count > 2 or is_non_indian


STATUS_BADGE = {
    'PENDING': 'warning',
    'PENDING_DEAN': 'info',
    'DEAN_APPROVED': 'primary',
    'MANAGER_APPROVED': 'success',
    'REJECTED': 'danger',
}


# ═══════════════════════════════════════════════════════════════════════════════
# MANAGER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/bookings", summary="List Pending Bookings for Manager Approval")
async def list_manager_bookings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List PENDING bookings for manager approval.
    Manager sees only PENDING bookings that need approval/rejection.
    """
    admin_id = _verify_manager_access(current_user)
    
    try:
        # Manager sees only PENDING bookings for approval
        bookings = (
            db.query(BookingRequest)
            .filter(BookingRequest.status == 'PENDING')
            .order_by(BookingRequest.submitted_at.desc())
            .all()
        )
        
        result = []
        for b in bookings:
            room_type = db.query(RoomType).filter(RoomType.id == b.room_type_id).first()
            user = db.query(User).filter(User.id == b.user_id).first()
            
            result.append({
                "id": b.id,
                "name": b.guest_name,
                "email": b.guest_email,
                "phone": b.guest_phone,
                "department": b.department,
                "check_in": str(b.check_in_date),
                "check_out": str(b.check_out_date),
                "pax": b.number_of_guests,
                "room_type": room_type.name if room_type else "Unknown",
                "booking_type": b.booking_type,
                "status": b.status,
                "purpose": b.purpose_of_visit,
                "submitted_at": b.submitted_at.strftime("%Y-%m-%d %H:%M") if b.submitted_at else None,
                "user_name": user.name if user else None,
                "user_email": user.email if user else None
            })
        
        return {
            "status": "success",
            "total": len(result),
            "bookings": result
        }
    
    except Exception as e:
        logger.error(f"Error fetching manager bookings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/approve", summary="Manager Approve Booking")
async def approve_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    request: Request = None
):
    """
    Approve a booking (Manager action).
    
    - For normal bookings: PENDING → MANAGER_APPROVED
    - For dean-required bookings: DEAN_APPROVED → MANAGER_APPROVED
    - Adds booking_history entry
    - Booking will then be visible to Operator for room allocation
    """
    admin_id = _verify_manager_access(current_user)
    
    try:
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Check if dean approval is required
        requires_dean = _requires_dean_approval(booking)
        
        logger.info(f"🔍 Manager Approve Check - Booking #{booking_id}: type={booking.booking_type}, room_count={booking.room_count}, status={booking.status}, requires_dean={requires_dean}")
        
        if requires_dean:
            # For dean-required bookings, manager can only approve DEAN_APPROVED status
            if booking.status != 'DEAN_APPROVED':
                raise HTTPException(
                    status_code=400, 
                    detail="This booking requires Dean approval first (Faculty Professional with >2 rooms)"
                )
        else:
            # Normal flow: approve PENDING bookings
            if booking.status != 'PENDING':
                raise HTTPException(
                    status_code=400, 
                    detail=f"Only PENDING bookings can be approved. Current status: {booking.status}"
                )
        
        old_status = booking.status
        
        # Update booking status
        booking.status = 'MANAGER_APPROVED'
        booking.manager_approved_at = datetime.utcnow()
        booking.manager_approved_by = admin_id
        booking.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='MANAGER_APPROVED',
            changed_by=admin_id,
            notes="Approved by manager",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"✅ Booking #{booking_id} approved by manager {admin_id}")
        
        return {
            "status": "success",
            "message": "Booking approved successfully. It will now be visible to operator for room allocation.",
            "data": {
                "booking_id": booking_id,
                "new_status": "MANAGER_APPROVED"
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving booking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/reject", summary="Manager Reject Booking")
async def reject_booking(
    booking_id: int,
    body: RejectBookingRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Reject a booking with a reason.
    
    - Manager can reject PENDING bookings
    - Operator can reject MANAGER_APPROVED bookings (via this endpoint too)
    - Updates booking status to REJECTED
    - Adds booking_history entry
    """
    # Allow both manager and operator roles
    if current_user.get("scope") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    admin_id = current_user.get("admin_id")
    role = current_user.get("role", "").lower()
    is_manager_role = role in ['manager', 'dean', 'fic', 'admin', 'super_admin']
    
    try:
        if not body.reason or not body.reason.strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required")
        
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        if booking.status == 'REJECTED':
            raise HTTPException(status_code=400, detail="Booking is already rejected")
        
        # Role-based status validation
        if is_manager_role:
            # Managers can reject PENDING or MANAGER_APPROVED
            if booking.status not in ['PENDING', 'MANAGER_APPROVED', 'FIC_APPROVED', 'DEAN_APPROVED']:
                raise HTTPException(status_code=400, detail="Cannot reject a booking in this status")
        else:
            # Operators can only reject MANAGER_APPROVED
            if booking.status not in ['MANAGER_APPROVED', 'FIC_APPROVED', 'DEAN_APPROVED']:
                raise HTTPException(status_code=400, detail="Operator can only reject bookings approved by manager")
        
        old_status = booking.status
        
        # Update booking status
        booking.status = 'REJECTED'
        booking.manager_rejected_reason = body.reason.strip()
        booking.updated_at = datetime.utcnow()
        
        # Add history entry
        rejected_by = "manager" if is_manager_role else "operator"
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='REJECTED',
            changed_by=admin_id,
            notes=f"Rejected by {rejected_by}: {body.reason.strip()}",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"❌ Booking #{booking_id} rejected by {rejected_by} {admin_id}: {body.reason}")
        
        return {
            "status": "success",
            "message": f"Booking #{booking_id} has been rejected",
            "data": {
                "booking_id": booking_id,
                "new_status": "REJECTED",
                "reason": body.reason.strip()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error rejecting booking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", summary="Manager Dashboard Stats")
async def get_manager_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get statistics for manager dashboard."""
    admin_id = _verify_manager_access(current_user)
    
    try:
        pending_count = db.query(BookingRequest).filter(BookingRequest.status == 'PENDING').count()
        approved_count = db.query(BookingRequest).filter(BookingRequest.status == 'MANAGER_APPROVED').count()
        rejected_count = db.query(BookingRequest).filter(BookingRequest.status == 'REJECTED').count()
        
        return {
            "status": "success",
            "data": {
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "total": pending_count + approved_count + rejected_count
            }
        }
    except Exception as e:
        logger.error(f"Error fetching manager stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# DEAN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dean/bookings", summary="List Bookings Requiring Dean Approval")
async def list_dean_bookings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List bookings requiring dean approval.
    Shows PENDING_DEAN bookings (Faculty Professional with room_count > 2).
    """
    admin_id = _verify_dean_access(current_user)
    
    try:
        # Dean sees PENDING_DEAN bookings
        bookings = (
            db.query(BookingRequest)
            .filter(BookingRequest.status == 'PENDING_DEAN')
            .order_by(BookingRequest.submitted_at.desc())
            .all()
        )
        
        result = []
        for b in bookings:
            room_type = db.query(RoomType).filter(RoomType.id == b.room_type_id).first()
            user = db.query(User).filter(User.id == b.user_id).first()
            
            result.append({
                "id": b.id,
                "guest_name": f"{b.first_name} {b.last_name}".strip(),
                "email": b.email,
                "phone_number": b.phone_number,
                "check_in": str(b.check_in) if b.check_in else None,
                "check_out": str(b.check_out) if b.check_out else None,
                "pax": b.pax,
                "room_count": b.room_count or 1,
                "room_type": room_type.name if room_type else "Unknown",
                "booking_type": b.booking_type,
                "status": b.status,
                "purpose_of_visit": b.purpose_of_visit,
                "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None,
                "user_name": user.name if user else None,
                "user_email": user.email if user else None
            })
        
        return {
            "status": "success",
            "data": {
                "bookings": result,
                "total": len(result)
            }
        }
    
    except Exception as e:
        logger.error(f"Error fetching dean bookings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dean/bookings/{booking_id}/approve", summary="Dean Approve Booking")
async def dean_approve_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Dean approves a PENDING_DEAN booking.
    
    - Updates booking status to DEAN_APPROVED
    - Booking will then be visible to Manager for approval
    """
    admin_id = _verify_dean_access(current_user)
    
    try:
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        if booking.status != 'PENDING_DEAN':
            raise HTTPException(
                status_code=400, 
                detail=f"Only PENDING_DEAN bookings can be approved by Dean. Current status: {booking.status}"
            )
        
        old_status = booking.status
        
        # Update booking status
        booking.status = 'DEAN_APPROVED'
        booking.dean_approved_at = datetime.utcnow()
        booking.dean_approved_by = admin_id
        booking.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='DEAN_APPROVED',
            changed_by=admin_id,
            notes="Approved by Dean",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"✅ Booking #{booking_id} approved by Dean {admin_id}")
        
        return {
            "status": "success",
            "message": "Booking approved by Dean. It now requires Manager approval.",
            "data": {
                "booking_id": booking_id,
                "new_status": "DEAN_APPROVED"
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in dean approval: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dean/bookings/{booking_id}/reject", summary="Dean Reject Booking")
async def dean_reject_booking(
    booking_id: int,
    body: RejectBookingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Dean rejects a PENDING_DEAN booking.
    """
    admin_id = _verify_dean_access(current_user)
    
    try:
        if not body.reason or not body.reason.strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required")
        
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        if booking.status != 'PENDING_DEAN':
            raise HTTPException(
                status_code=400, 
                detail=f"Only PENDING_DEAN bookings can be rejected by Dean. Current status: {booking.status}"
            )
        
        old_status = booking.status
        
        # Update booking status
        booking.status = 'REJECTED'
        booking.dean_rejected_reason = body.reason.strip()
        booking.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='REJECTED',
            changed_by=admin_id,
            notes=f"Rejected by Dean: {body.reason.strip()}",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        db.commit()
        
        logger.info(f"❌ Booking #{booking_id} rejected by Dean {admin_id}: {body.reason}")
        
        return {
            "status": "success",
            "message": f"Booking #{booking_id} has been rejected by Dean",
            "data": {
                "booking_id": booking_id,
                "new_status": "REJECTED",
                "reason": body.reason.strip()
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in dean rejection: {e}")
        raise HTTPException(status_code=500, detail=str(e))
