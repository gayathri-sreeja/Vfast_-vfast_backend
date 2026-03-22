"""
Operator Service - Room Allocation & Booking Management
Handles operator-specific booking workflows for VFAST.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import logging

from Config.database import get_db
from Config.models import (
    BookingRequest, BookingHistory, RoomAllocation,
    Room, RoomType, User, AdminUser, AdminActionsLog
)
from Services.admin_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/operator",
    tags=["Operator"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class AllocateRoomRequest(BaseModel):
    room_id: int


class RejectBookingRequest(BaseModel):
    reason: str


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_operator_access(current_user: dict) -> int:
    """Verify user has operator/admin scope and return admin_id."""
    if current_user.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin/Operator access required"
        )
    return current_user.get("admin_id")


def _verify_operator_only(current_user: dict) -> int:
    """Verify user has OPERATOR role specifically (not manager/dean/fic). Returns admin_id."""
    if current_user.get("scope") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required"
        )
    role = current_user.get("role", "").lower()
    if role not in ["operator", "admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only operator login can perform this action"
        )
    return current_user.get("admin_id")


def _log_admin_action(
    db: Session,
    admin_id: int,
    action_type: str,
    entity_type: str,
    entity_id: int,
    details: dict = None,
    request: Request = None
):
    """Log admin action for audit trail."""
    try:
        log_entry = AdminActionsLog(
            admin_id=admin_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
    except Exception as e:
        logger.warning(f"Failed to log admin action: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# OPERATOR ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/bookings", summary="List Operator-Relevant Bookings")
async def list_operator_bookings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List bookings relevant to the admin role:
    - Dean: sees PENDING_DEAN + DEAN_APPROVED + all other statuses
    - Manager/FIC: sees PENDING + DEAN_APPROVED + all other statuses
    - Operator: sees MANAGER_APPROVED+ (excludes PENDING, PENDING_DEAN, DEAN_APPROVED)
    - All: can see REJECTED for reference
    """
    admin_id = _verify_operator_access(current_user)
    role = current_user.get("role", "").lower()
    
    try:
        # Build allowed statuses based on role
        is_dean_role = role in ['dean', 'admin', 'super_admin']
        is_manager_role = role in ['manager', 'dean', 'fic', 'admin', 'super_admin']
        
        allowed_statuses = [
            'MANAGER_APPROVED', 'FIC_APPROVED',  # Awaiting operator approval
            'OPERATOR_APPROVED',  # Approved by operator, ready for room allocation
            'OPERATOR_ALLOCATED', 'CHECKED_IN',  # Already allocated
            'REJECTED'  # For reference
        ]
        
        # Dean can see PENDING_DEAN
        if is_dean_role:
            allowed_statuses.append('PENDING_DEAN')
        
        # Managers can see PENDING and DEAN_APPROVED bookings
        if is_manager_role:
            allowed_statuses.append('PENDING')
            allowed_statuses.append('DEAN_APPROVED')
        
        bookings = (
            db.query(BookingRequest)
            .filter(BookingRequest.status.in_(allowed_statuses))
            .order_by(BookingRequest.submitted_at.desc())
            .all()
        )
        
        result = []
        for b in bookings:
            room_type = db.query(RoomType).filter(RoomType.id == b.room_type_id).first()
            
            # Get allocated room if any
            allocation = db.query(RoomAllocation).filter(
                RoomAllocation.booking_request_id == b.id,
                RoomAllocation.deallocated_at == None
            ).first()
            
            allocated_room = None
            if allocation:
                room = db.query(Room).filter(Room.id == allocation.room_id).first()
                if room:
                    allocated_room = {
                        "room_id": room.id,
                        "room_number": room.room_number,
                        "floor": room.floor,
                        "building": room.building
                    }
            
            # Determine display name
            if b.booking_type == 'FACULTY_PROFESSIONAL':
                guest_name = b.first_name  # Event Name
                guest_detail = b.last_name  # Department
            else:
                guest_name = f"{b.first_name} {b.last_name}".strip()
                guest_detail = None
            
            result.append({
                "id": b.id,
                "guest_name": guest_name,
                "guest_detail": guest_detail,
                "email": b.email,
                "phone_number": b.phone_number,
                "check_in": str(b.check_in) if b.check_in else None,
                "check_out": str(b.check_out) if b.check_out else None,
                "pax": b.pax,
                "room_count": b.room_count or 1,
                "nationality": b.nationality or "Indian",
                "room_type_id": b.room_type_id,
                "room_type": room_type.name if room_type else "Unknown",
                "booking_type": b.booking_type,
                "status": b.status,
                "purpose_of_visit": b.purpose_of_visit,
                "special_requirements": b.special_requirements,
                "submitted_at": b.submitted_at.isoformat() if b.submitted_at else None,
                "allocated_room": allocated_room,
                "manager_rejected_reason": b.manager_rejected_reason,
                "dean_rejected_reason": b.dean_rejected_reason,
                "requires_dean_approval": (
                    b.booking_type == 'FACULTY_PROFESSIONAL' and 
                    ((b.room_count or 1) > 2 or (b.nationality or 'Indian').lower() != 'indian')
                )
            })
        
        return {
            "status": "success",
            "data": {
                "bookings": result,
                "total": len(result)
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing operator bookings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/{booking_id}", summary="Get Booking Details")
async def get_booking_details(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get detailed booking information including history and allocations."""
    _verify_operator_access(current_user)
    
    try:
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        room_type = db.query(RoomType).filter(RoomType.id == booking.room_type_id).first()
        user = db.query(User).filter(User.id == booking.user_id).first()
        
        # Get allocations
        allocations = db.query(RoomAllocation).filter(
            RoomAllocation.booking_request_id == booking_id
        ).all()
        
        allocation_data = []
        for alloc in allocations:
            room = db.query(Room).filter(Room.id == alloc.room_id).first()
            allocation_data.append({
                "id": alloc.id,
                "room_number": room.room_number if room else "Unknown",
                "room_id": alloc.room_id,
                "allocated_at": alloc.allocated_at.isoformat() if alloc.allocated_at else None,
                "deallocated_at": alloc.deallocated_at.isoformat() if alloc.deallocated_at else None
            })
        
        # Get history
        history = db.query(BookingHistory).filter(
            BookingHistory.booking_request_id == booking_id
        ).order_by(BookingHistory.changed_at.desc()).all()
        
        history_data = [{
            "id": h.id,
            "status_from": h.status_from,
            "status_to": h.status_to,
            "notes": h.notes,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None
        } for h in history]
        
        return {
            "status": "success",
            "data": {
                "booking": {
                    "id": booking.id,
                    "first_name": booking.first_name,
                    "last_name": booking.last_name,
                    "email": booking.email,
                    "phone_number": booking.phone_number,
                    "check_in": str(booking.check_in),
                    "check_out": str(booking.check_out),
                    "pax": booking.pax,
                    "room_type": room_type.name if room_type else "Unknown",
                    "room_type_id": booking.room_type_id,
                    "booking_type": booking.booking_type,
                    "status": booking.status,
                    "purpose_of_visit": booking.purpose_of_visit,
                    "special_requirements": booking.special_requirements,
                    "submitted_at": booking.submitted_at.isoformat() if booking.submitted_at else None
                },
                "user": {
                    "id": user.id if user else None,
                    "name": user.name if user else "Unknown",
                    "email": user.email if user else None
                },
                "allocations": allocation_data,
                "history": history_data
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms/available", summary="Get Available Rooms")
async def get_available_rooms(
    room_type_id: int,
    check_in: str,
    check_out: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get available and occupied rooms for a given room type and date range.
    Uses vfast.get_available_rooms() PostgreSQL function.
    """
    _verify_operator_access(current_user)
    
    try:
        # Parse dates
        ci = datetime.strptime(check_in, "%Y-%m-%d").date()
        co = datetime.strptime(check_out, "%Y-%m-%d").date()
        
        # Try to use the PostgreSQL function
        available_rooms = []
        occupied_rooms = []
        
        try:
            # Call vfast.get_available_rooms(room_type_id, check_in, check_out)
            result = db.execute(
                text("SELECT * FROM vfast.get_available_rooms(:rt_id, :ci, :co)"),
                {"rt_id": room_type_id, "ci": ci, "co": co}
            )
            available_rows = result.fetchall()
            
            for row in available_rows:
                available_rooms.append({
                    "room_id": row[0],
                    "room_number": row[1],
                    "floor": row[2] if len(row) > 2 else None,
                    "building": row[3] if len(row) > 3 else None,
                    "capacity": row[4] if len(row) > 4 else None
                })
        except Exception as func_err:
            logger.warning(f"get_available_rooms function failed, using fallback: {func_err}")
            # Fallback: query rooms directly
            rooms = db.query(Room).filter(
                Room.room_type_id == room_type_id,
                Room.status == 'AVAILABLE'
            ).all()
            
            # Get room IDs that are occupied during this period
            occupied_query = db.execute(
                text("""
                    SELECT DISTINCT ra.room_id
                    FROM vfast.room_allocations ra
                    JOIN vfast.booking_requests br ON ra.booking_request_id = br.id
                    WHERE ra.deallocated_at IS NULL
                      AND br.status NOT IN ('REJECTED', 'CHECKED_OUT', 'CANCELLED')
                      AND br.check_in < :co
                      AND br.check_out > :ci
                """),
                {"ci": ci, "co": co}
            )
            occupied_ids = {row[0] for row in occupied_query.fetchall()}
            
            for room in rooms:
                room_data = {
                    "room_id": room.id,
                    "room_number": room.room_number,
                    "floor": room.floor,
                    "building": room.building,
                    "capacity": room.capacity
                }
                if room.id in occupied_ids:
                    occupied_rooms.append(room_data)
                else:
                    available_rooms.append(room_data)
        
        # Get occupied rooms with booking details
        occupied_result = db.execute(
            text("""
                SELECT r.id, r.room_number, r.floor, r.building, r.capacity,
                       br.id as booking_id, br.first_name, br.last_name,
                       br.check_in, br.check_out
                FROM vfast.rooms r
                JOIN vfast.room_allocations ra ON r.id = ra.room_id
                JOIN vfast.booking_requests br ON ra.booking_request_id = br.id
                WHERE r.room_type_id = :rt_id
                  AND ra.deallocated_at IS NULL
                  AND br.status NOT IN ('REJECTED', 'CHECKED_OUT', 'CANCELLED')
                  AND br.check_in < :co
                  AND br.check_out > :ci
                ORDER BY r.room_number
            """),
            {"rt_id": room_type_id, "ci": ci, "co": co}
        )
        
        for row in occupied_result.fetchall():
            guest_name = f"{row[6]} {row[7]}".strip() if row[7] else row[6]
            occupied_rooms.append({
                "room_id": row[0],
                "room_number": row[1],
                "floor": row[2],
                "building": row[3],
                "capacity": row[4],
                "booking_id": row[5],
                "guest_name": guest_name,
                "check_in": str(row[8]),
                "check_out": str(row[9])
            })
        
        return {
            "status": "success",
            "data": {
                "available_rooms": available_rooms,
                "occupied_rooms": occupied_rooms,
                "room_type_id": room_type_id,
                "check_in": check_in,
                "check_out": check_out
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available rooms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/allocate", summary="Allocate Room to Booking")
async def allocate_room(
    booking_id: int,
    body: AllocateRoomRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Allocate a room to a booking.
    
    - Creates room_allocation record
    - Updates booking status to OPERATOR_ALLOCATED
    - Adds booking_history entry
    - Logs action in admin_actions_log
    """
    admin_id = _verify_operator_access(current_user)
    
    try:
        # Get booking
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Verify booking is in allocatable status
        allocatable_statuses = ['MANAGER_APPROVED', 'DEAN_APPROVED', 'FIC_APPROVED']
        if booking.status not in allocatable_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Booking status is {booking.status}, cannot allocate room"
            )
        
        # Get room
        room = db.query(Room).filter(Room.id == body.room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Verify room is not already allocated for this period
        existing_allocation = db.execute(
            text("""
                SELECT ra.id FROM vfast.room_allocations ra
                JOIN vfast.booking_requests br ON ra.booking_request_id = br.id
                WHERE ra.room_id = :room_id
                  AND ra.deallocated_at IS NULL
                  AND br.status NOT IN ('REJECTED', 'CHECKED_OUT', 'CANCELLED')
                  AND br.check_in < :co
                  AND br.check_out > :ci
            """),
            {"room_id": body.room_id, "ci": booking.check_in, "co": booking.check_out}
        ).fetchone()
        
        if existing_allocation:
            raise HTTPException(
                status_code=409,
                detail="Room is already allocated for this period"
            )
        
        # ── Transaction: Allocate room ──
        old_status = booking.status
        
        # 1. Create room allocation
        allocation = RoomAllocation(
            booking_request_id=booking_id,
            room_id=body.room_id,
            allocated_by=admin_id,
            allocated_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(allocation)
        
        # 2. Update booking status
        booking.status = 'OPERATOR_ALLOCATED'
        booking.operator_allocated_at = datetime.utcnow()
        booking.operator_allocated_by = admin_id
        booking.updated_at = datetime.utcnow()
        
        # 3. Add history entry
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='OPERATOR_ALLOCATED',
            changed_by=admin_id,
            notes=f"Room {room.room_number} allocated by operator",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        # 4. Log admin action (disabled for now)
        # _log_admin_action(
        #     db=db,
        #     admin_id=admin_id,
        #     action_type='ALLOCATE',
        #     entity_type='BOOKING',
        #     entity_id=booking_id,
        #     details={
        #         "room_id": body.room_id,
        #         "room_number": room.room_number,
        #         "previous_status": old_status
        #     },
        #     request=request
        # )
        
        db.commit()
        
        logger.info(f"✅ Room {room.room_number} allocated to booking #{booking_id} by admin {admin_id}")
        
        return {
            "status": "success",
            "message": f"Room {room.room_number} allocated successfully",
            "data": {
                "booking_id": booking_id,
                "room_id": body.room_id,
                "room_number": room.room_number,
                "new_status": "OPERATOR_ALLOCATED"
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error allocating room: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/approve", summary="Operator Approve Booking")
async def approve_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    request: Request = None
):
    """
    Operator approves a MANAGER_APPROVED booking.
    
    - Updates booking status to OPERATOR_APPROVED
    - Adds booking_history entry
    - Booking is now ready for room allocation or check-in
    - Only operators can perform this action (not managers)
    """
    admin_id = _verify_operator_only(current_user)
    
    try:
        booking = db.query(BookingRequest).filter(BookingRequest.id == booking_id).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Operator can only approve bookings that manager has already approved
        if booking.status not in ['MANAGER_APPROVED', 'FIC_APPROVED', 'DEAN_APPROVED']:
            raise HTTPException(
                status_code=400, 
                detail=f"Only manager-approved bookings can be approved by operator. Current status: {booking.status}"
            )
        
        old_status = booking.status
        
        # Update booking status
        booking.status = 'OPERATOR_APPROVED'
        booking.updated_at = datetime.utcnow()
        
        # Add history entry
        history = BookingHistory(
            booking_request_id=booking_id,
            status_from=old_status,
            status_to='OPERATOR_APPROVED',
            changed_by=admin_id,
            notes="Approved by operator - ready for room allocation",
            changed_at=datetime.utcnow()
        )
        db.add(history)
        
        # Log admin action (disabled for now)
        # _log_admin_action(
        #     db=db,
        #     admin_id=admin_id,
        #     action_type='APPROVE',
        #     entity_type='BOOKING',
        #     entity_id=booking_id,
        #     details={"previous_status": old_status},
        #     request=request
        # )
        
        db.commit()
        
        logger.info(f"✅ Booking #{booking_id} approved by operator {admin_id}")
        
        return {
            "status": "success",
            "message": "Booking approved by operator. Ready for room allocation.",
            "data": {
                "booking_id": booking_id,
                "new_status": "OPERATOR_APPROVED"
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving booking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/reject", summary="Reject Booking")
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
    - Operator can only reject MANAGER_APPROVED bookings
    - Updates booking status to REJECTED
    - Adds booking_history entry
    """
    admin_id = _verify_operator_access(current_user)
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
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot reject a booking in this status"
                )
        else:
            # Operators can only reject MANAGER_APPROVED
            if booking.status not in ['MANAGER_APPROVED', 'FIC_APPROVED', 'DEAN_APPROVED']:
                raise HTTPException(
                    status_code=400, 
                    detail="Operator can only reject bookings that have been approved by manager"
                )
        
        # ── Transaction: Reject booking ──
        old_status = booking.status
        
        # 1. Update booking status
        booking.status = 'REJECTED'
        booking.manager_rejected_reason = body.reason.strip()
        booking.updated_at = datetime.utcnow()
        
        # 2. Add history entry
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
        
        # 3. Log admin action (disabled for now)
        # _log_admin_action(
        #     db=db,
        #     admin_id=admin_id,
        #     action_type='REJECT',
        #     entity_type='BOOKING',
        #     entity_id=booking_id,
        #     details={
        #         "reason": body.reason.strip(),
        #         "previous_status": old_status
        #     },
        #     request=request
        # )
        
        db.commit()
        
        logger.info(f"❌ Booking #{booking_id} rejected by admin {admin_id}: {body.reason}")
        
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


@router.get("/stats", summary="Get Operator Dashboard Stats")
async def get_operator_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get statistics for operator dashboard."""
    _verify_operator_access(current_user)
    
    try:
        # Bookings awaiting allocation
        awaiting = db.query(BookingRequest).filter(
            BookingRequest.status.in_(['MANAGER_APPROVED', 'DEAN_APPROVED', 'FIC_APPROVED'])
        ).count()
        
        # Allocated bookings
        allocated = db.query(BookingRequest).filter(
            BookingRequest.status == 'OPERATOR_ALLOCATED'
        ).count()
        
        # Checked in
        checked_in = db.query(BookingRequest).filter(
            BookingRequest.status == 'CHECKED_IN'
        ).count()
        
        # Available rooms (total)
        total_rooms = db.query(Room).filter(Room.status == 'AVAILABLE').count()
        
        # Occupied rooms (with active allocations)
        today = date.today()
        occupied_rooms = db.execute(
            text("""
                SELECT COUNT(DISTINCT ra.room_id)
                FROM vfast.room_allocations ra
                JOIN vfast.booking_requests br ON ra.booking_request_id = br.id
                WHERE ra.deallocated_at IS NULL
                  AND br.status IN ('OPERATOR_ALLOCATED', 'CHECKED_IN')
                  AND br.check_in <= :today
                  AND br.check_out > :today
            """),
            {"today": today}
        ).scalar() or 0
        
        return {
            "status": "success",
            "data": {
                "bookings": {
                    "awaiting_allocation": awaiting,
                    "allocated": allocated,
                    "checked_in": checked_in
                },
                "rooms": {
                    "total": total_rooms,
                    "occupied": occupied_rooms,
                    "available": total_rooms - occupied_rooms
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting operator stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
