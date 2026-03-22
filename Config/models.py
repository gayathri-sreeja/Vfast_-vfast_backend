# ✅ CORRECT
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, 
    TEXT, Date, DECIMAL, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional, List

Base = declarative_base()

# ============ ADMIN MODELS ============

class AdminRole(Base):
    """Admin Roles"""
    __tablename__ = "admin_roles"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    role_name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(TEXT)
    permissions = Column(JSONB, default=[])
    hierarchy_level = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    admin_users = relationship("AdminUser", back_populates="role")


class AdminUser(Base):
    """Admin Users"""
    __tablename__ = "admin_users"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone_number = Column(String(20))
    
    # Authentication
    username = Column(String(255), unique=True, index=True)
    password_hash = Column(String(255))
    
    # Google OAuth
    google_id = Column(String(500), unique=True, index=True)
    google_email = Column(String(255))
    
    # Role
    admin_role_id = Column(Integer, ForeignKey("vfast.admin_roles.id"), nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    
    # Relationships
    role = relationship("AdminRole", back_populates="admin_users")
    otp_tokens = relationship("OTPToken", back_populates="admin", cascade="all, delete-orphan")
    login_history = relationship("LoginHistory", back_populates="admin", cascade="all, delete-orphan")

class OTPToken(Base):
    """OTP Tokens for 2FA"""
    __tablename__ = "otp_tokens"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("vfast.admin_users.id"), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    is_used = Column(Boolean, default=False)
    
    # Relationships
    admin = relationship("AdminUser", back_populates="otp_tokens")


class LoginHistory(Base):
    """Admin Login Audit Trail"""
    __tablename__ = "login_history"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("vfast.admin_users.id"), nullable=False, index=True)
    login_type = Column(String(50), nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(TEXT)
    success = Column(Boolean, default=True)
    error_message = Column(TEXT)
    login_timestamp = Column(DateTime, default=datetime.utcnow)
    logout_timestamp = Column(DateTime)
    
    # Relationships
    admin = relationship("AdminUser", back_populates="login_history")


# ============ USER MODELS ============

class User(Base):
    """Users (Student/Alumni/Faculty)"""
    __tablename__ = "users"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone_number = Column(String(20))
    user_type = Column(String(50), nullable=False)  # STUDENT, ALUMNI, FACULTY
    
    password_hash = Column(String(255))
    google_id = Column(String(500), unique=True, index=True)
    
    is_active = Column(Boolean, default=True)
    
    institution_id = Column(String(50))
    department = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    bookings = relationship("BookingRequest", back_populates="user")
# ============ ROOM MODELS ============

class RoomType(Base):
    """Room Types"""
    __tablename__ = "room_types"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(TEXT)
    capacity = Column(Integer, nullable=False)
    amenities = Column(JSONB, default=[])
    base_price = Column(DECIMAL(10, 2))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    rooms = relationship("Room", back_populates="room_type")


class Room(Base):
    """Rooms"""
    __tablename__ = "rooms"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    room_number = Column(String(50), unique=True, nullable=False, index=True)
    room_type_id = Column(Integer, ForeignKey("vfast.room_types.id"), nullable=False)
    floor = Column(Integer)
    building = Column(String(100))
    status = Column(String(50), default='AVAILABLE', index=True)
    capacity = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    room_type = relationship("RoomType", back_populates="rooms")
    # ✅ FIXED: Changed "Allocation" to "RoomAllocation"
    allocations = relationship(
        "RoomAllocation",
        foreign_keys="[RoomAllocation.room_id]",
        back_populates="room"
    )
# ============ BOOKING MODELS ============

class BookingRequest(Base):
    """Booking Requests"""
    __tablename__ = "booking_requests"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("vfast.users.id"), nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255))
    email = Column(String(255), nullable=False)
    phone_number = Column(String(20))
    gender = Column(String(20))
    nationality = Column(String(100), default='Indian')
    
    check_in = Column(Date, nullable=False, index=True)
    check_out = Column(Date, nullable=False, index=True)
    pax = Column(Integer, nullable=False)
    room_count = Column(Integer, default=1)
    room_type_id = Column(Integer, ForeignKey("vfast.room_types.id"))
    
    booking_type = Column(String(50), nullable=False, index=True)
    is_international = Column(Boolean, default=False)
    is_bulk = Column(Boolean, default=False)
    
    status = Column(String(50), default='PENDING', index=True)
    
    submitted_at = Column(DateTime, default=datetime.utcnow)
    
    manager_approved_at = Column(DateTime)
    manager_approved_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    manager_notes = Column(TEXT)
    manager_rejected_reason = Column(TEXT)
    
    fic_approved_at = Column(DateTime)
    fic_approved_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    fic_notes = Column(TEXT)
    fic_rejected_reason = Column(TEXT)
    
    dean_approved_at = Column(DateTime)
    dean_approved_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    dean_notes = Column(TEXT)
    dean_rejected_reason = Column(TEXT)
    
    operator_allocated_at = Column(DateTime)
    operator_allocated_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    
    physically_arrived = Column(Boolean, default=False)
    physically_arrived_at = Column(DateTime)
    
    checked_in_at = Column(DateTime)
    checked_in_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    
    checked_out_at = Column(DateTime)
    checked_out_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    
    purpose_of_visit = Column(TEXT)
    special_requirements = Column(TEXT)
    gst_number = Column(String(50))
    relation_to_campus = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="bookings")
    allocations = relationship("RoomAllocation", back_populates="booking")
    history = relationship("BookingHistory", back_populates="booking")


class RoomAllocation(Base):
    """Room Allocation & Reallocation"""
    __tablename__ = "room_allocations"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    booking_request_id = Column(Integer, ForeignKey("vfast.booking_requests.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("vfast.rooms.id"), nullable=False)
    
    allocated_at = Column(DateTime, default=datetime.utcnow)
    allocated_by = Column(Integer, ForeignKey("vfast.admin_users.id"), nullable=False)
    
    reallocated_from_room_id = Column(Integer, ForeignKey("vfast.rooms.id"))
    reallocated_at = Column(DateTime)
    reallocated_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    reallocation_reason = Column(TEXT)
    reallocation_count = Column(Integer, default=0)
    
    deallocated_at = Column(DateTime)
    deallocated_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    booking = relationship("BookingRequest", back_populates="allocations")
    
    # ✅ FIX: Specify which foreign key for each relationship
    room = relationship(
        "Room",
        foreign_keys=[room_id],
        back_populates="allocations"
    )
    
    reallocated_from_room = relationship(
        "Room",
        foreign_keys=[reallocated_from_room_id]
    )
    
    allocated_by_admin = relationship(
        "AdminUser",
        foreign_keys=[allocated_by]
    )
    
    reallocated_by_admin = relationship(
        "AdminUser",
        foreign_keys=[reallocated_by]
    )
    
    deallocated_by_admin = relationship(
        "AdminUser",
        foreign_keys=[deallocated_by]
    )
class BookingHistory(Base):
    """Booking Status History"""
    __tablename__ = "booking_history"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    booking_request_id = Column(Integer, ForeignKey("vfast.booking_requests.id"), nullable=False)
    status_from = Column(String(50))
    status_to = Column(String(50))
    changed_by = Column(Integer, ForeignKey("vfast.admin_users.id"))
    notes = Column(TEXT)
    changed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    booking = relationship("BookingRequest", back_populates="history")


class AdminActionsLog(Base):
    """Admin Actions Audit Log"""
    __tablename__ = "admin_actions_log"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("vfast.admin_users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)  # ALLOCATE, REJECT, CHECKIN, CHECKOUT
    entity_type = Column(String(50), nullable=False)  # BOOKING, ROOM
    entity_id = Column(Integer, nullable=False)
    details = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(TEXT)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    admin = relationship("AdminUser")


class ApprovalMatrix(Base):
    """Booking Approval Workflow"""
    __tablename__ = "approval_matrix"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    booking_type = Column(String(50), nullable=False, unique=True)
    approval_sequence = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemSettings(Base):
    """System Settings"""
    __tablename__ = "system_settings"
    __table_args__ = {'schema': 'vfast'}
    
    id = Column(Integer, primary_key=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(TEXT)
    description = Column(TEXT)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============ PYDANTIC SCHEMAS ============

class AdminPasswordLoginRequest(BaseModel):
    username: str
    password: str

class AdminGoogleLoginRequest(BaseModel):
    token: str

class VerifyOtpRequest(BaseModel):
    otp: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    otp: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    otp: str
    new_password: str

class AdminUserResponse(BaseModel):
    id: int
    email: str
    name: str
    role_name: str
    hierarchy_level: int
    permissions: List
    is_active: bool
    
    class Config:
        from_attributes = True

class BookingRequestSchema(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: str
    phone_number: str
    check_in: str
    check_out: str
    pax: int
    room_type: str
    booking_type: str
    purpose_of_visit: Optional[str] = None
    special_requirements: Optional[str] = None
    is_international: bool = False
    is_bulk: bool = False

class RoomAvailabilitySchema(BaseModel):
    room_type: str
    available_count: int
    total_count: int

class ApprovalRequestSchema(BaseModel):
    booking_id: int
    action: str  # APPROVE, REJECT
    notes: Optional[str] = None

class AllocationRequestSchema(BaseModel):
    booking_id: int
    room_id: int
    reason: Optional[str] = None