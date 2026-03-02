from sqlalchemy.orm import Session
from sqlalchemy import select
from Config.models import AdminUser, AdminRole, OTPToken, LoginHistory
# ✅ CORRECT
from Config.jwt import create_access_token, verify_token
from Config.environment import OTP_CONFIG
from Helpers.password_helper import hash_password, verify_password
from Helpers.email_helper import send_otp_email
from datetime import datetime, timedelta
import random
import logging
from google.auth.transport import requests
from google.oauth2 import id_token
import os

logger = logging.getLogger(__name__)

# ============ HELPER 1: PASSWORD LOGIN ============

async def admin_password_login(db: Session, username: str, password: str, ip_address: str = None):
    """
    Step 1: Admin login with username/password
    Generates OTP and sends email
    Returns temporary JWT with 'verify_otp' scope
    """
    try:
        logger.info(f"🔐 Password login attempt: {username}")
        
        # Query admin
        stmt = select(AdminUser).where(AdminUser.username == username)
        admin = db.execute(stmt).scalars().first()
        
        if not admin:
            logger.warning(f"❌ Login failed: Invalid username {username}")
            return None, "Invalid username or password"
        
        # Check active status
        if not admin.is_active:
            logger.warning(f"❌ Login failed: Admin inactive {admin.email}")
            return None, "Your account is disabled. Contact administrator."
        
        # Verify password
        if not admin.password_hash or not verify_password(password, admin.password_hash):
            logger.warning(f"❌ Login failed: Wrong password for {admin.email}")
            return None, "Invalid username or password"
        
        # Get role
        role = db.query(AdminRole).filter(AdminRole.id == admin.admin_role_id).first()
        
        # Create final JWT token directly (no OTP required)
        final_jwt = create_access_token(
            data={
                'admin_id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'username': admin.username,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions or [],
                'login_type': 'PASSWORD'
            },
            expires_delta=timedelta(hours=24),
            scope='admin'
        )
        
        # Record login
        login_record = LoginHistory(
            admin_id=admin.id,
            login_type='PASSWORD',
            ip_address=ip_address,
            success=True
        )
        db.add(login_record)
        
        # Update last_login
        admin.last_login = datetime.utcnow()
        admin.login_count += 1
        
        db.commit()
        logger.info(f"✅ Direct login successful for {admin.email} - Total logins: {admin.login_count}")
        
        return {
            'status': 'success',
            'message': 'Login successful',
            'access_token': final_jwt,
            'token_type': 'bearer',
            'expires_in': 86400,
            'admin': {
                'id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'username': admin.username,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions
            }
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Password login error: {str(e)}")
        return None, f"Login failed: {str(e)}"


# ============ HELPER 2: GOOGLE OAUTH LOGIN ============

async def admin_google_login(db: Session, token: str, ip_address: str = None):
    """
    Step 1: Admin login with Google OAuth token
    Generates OTP and sends email
    Returns temporary JWT with 'verify_otp' scope
    """
    try:
        logger.info("🔐 Google OAuth login attempt")
        
        # Verify Google token
        try:
            GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        except ValueError as e:
            logger.warning(f"❌ Invalid Google token: {str(e)}")
            return None, "Invalid Google token"
        
        google_email = idinfo.get('email')
        google_id = idinfo.get('sub')
        google_name = idinfo.get('name')
        
        if not google_email:
            logger.warning("❌ No email in Google token")
            return None, "Could not extract email from Google token"
        
        # Query admin
        stmt = select(AdminUser).where(
            (AdminUser.google_id == google_id) | (AdminUser.email == google_email)
        )
        admin = db.execute(stmt).scalars().first()
        
        if not admin:
            logger.warning(f"❌ Google account not linked: {google_email}")
            return None, "Google account not linked to admin. Contact administrator."
        
        # Check active status
        if not admin.is_active:
            logger.warning(f"❌ Admin inactive: {admin.email}")
            return None, "Your account is disabled"
        
        # Update Google ID if first time
        if not admin.google_id:
            admin.google_id = google_id
            admin.google_email = google_email
            logger.info(f"📝 Updated Google ID for {admin.email}")
        
        # Get role
        role = db.query(AdminRole).filter(AdminRole.id == admin.admin_role_id).first()
        
        # Create final JWT token directly (no OTP required)
        final_jwt = create_access_token(
            data={
                'admin_id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'username': admin.username,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions or [],
                'login_type': 'GOOGLE_OAUTH'
            },
            expires_delta=timedelta(hours=24),
            scope='admin'
        )
        
        # Record login
        login_record = LoginHistory(
            admin_id=admin.id,
            login_type='GOOGLE_OAUTH',
            ip_address=ip_address,
            success=True
        )
        db.add(login_record)
        
        # Update last_login
        admin.last_login = datetime.utcnow()
        admin.login_count += 1
        
        db.commit()
        logger.info(f"✅ Google OAuth login successful for {admin.email} - Total logins: {admin.login_count}")
        
        return {
            'status': 'success',
            'message': 'Login successful',
            'access_token': final_jwt,
            'token_type': 'bearer',
            'expires_in': 86400,
            'admin': {
                'id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'username': admin.username,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions
            }
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Google login error: {str(e)}")
        return None, f"Google authentication failed"


# ============ HELPER 3: OTP VERIFICATION ============

async def verify_admin_otp(db: Session, admin_id: int, otp_code: str, login_type: str, ip_address: str = None):
    """
    Step 2: Verify OTP and return final JWT with full admin scope
    Records login in login_history
    Updates admin last_login timestamp
    """
    try:
        logger.info(f"🔐 OTP verification attempt for admin {admin_id}")
        
        # Get admin
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            logger.warning(f"❌ Admin not found: {admin_id}")
            return None, "Admin not found"
        
        # Find valid OTP
        stmt = select(OTPToken).where(
            (OTPToken.admin_id == admin_id) &
            (OTPToken.otp_code == otp_code) &
            (OTPToken.is_used == False)
        )
        otp_token = db.execute(stmt).scalars().first()
        
        if not otp_token:
            logger.warning(f"❌ OTP invalid for admin: {admin.email}")
            return None, "Invalid OTP"
        
        # Check expiration
        if otp_token.expires_at < datetime.utcnow():
            logger.warning(f"❌ OTP expired for: {admin.email}")
            return None, "OTP expired. Request new OTP."
        
        # Check attempts
        if otp_token.attempts >= otp_token.max_attempts:
            logger.warning(f"❌ Max OTP attempts exceeded for: {admin.email}")
            return None, "Too many attempts. Request new OTP."
        
        # Mark OTP as used
        otp_token.attempts += 1
        otp_token.is_used = True
        
        # Get role
        role = db.query(AdminRole).filter(AdminRole.id == admin.admin_role_id).first()
        
        # ✅ FIXED: create_token → create_access_token
        # Create final JWT
        final_jwt = create_access_token(
            data={
                'admin_id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'username': admin.username,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions or [],
                'login_type': login_type
            },
            expires_delta=timedelta(hours=24),
            scope='admin'
        )
        
        # Record login
        login_record = LoginHistory(
            admin_id=admin.id,
            login_type=login_type,
            ip_address=ip_address,
            success=True
        )
        db.add(login_record)
        
        # Update last_login
        admin.last_login = datetime.utcnow()
        admin.login_count += 1
        
        db.commit()
        logger.info(f"✅ Successful login: {admin.email} ({login_type}) - Total logins: {admin.login_count}")
        
        return {
            'status': 'success',
            'message': 'Login Successful!',
            'access_token': final_jwt,
            'token_type': 'bearer',
            'expires_in': 86400,
            'admin': {
                'id': admin.id,
                'email': admin.email,
                'name': admin.name,
                'role': role.role_name,
                'hierarchy_level': role.hierarchy_level,
                'permissions': role.permissions,
                
            }
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ OTP verification error: {str(e)}")
        return None, f"OTP verification failed: {str(e)}"


# ============ HELPER 4: RESEND OTP ============

async def resend_admin_otp(db: Session, admin_id: int):
    """
    Request new OTP if previous expired
    """
    try:
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        
        if not admin:
            return None, "Admin not found"
        
        # Delete old unused OTP tokens
        db.query(OTPToken).filter(
            (OTPToken.admin_id == admin_id) &
            (OTPToken.is_used == False)
        ).delete()
        
        # Generate new OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(OTP_CONFIG['code_length'])])
        
        new_otp = OTPToken(
            admin_id=admin.id,
            otp_code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=OTP_CONFIG['expiry_minutes'])
        )
        db.add(new_otp)
        db.commit()
        
        # Send OTP
        await send_otp_email(admin.email, otp_code, admin.name)
        
        logger.info(f"📧 New OTP generated and sent to {admin.email}")
        
        return {'status': 'success', 'message': 'New OTP sent to your email'}, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Resend OTP error: {str(e)}")
        return None, str(e)


# ============ HELPER 5: FORGOT PASSWORD - REQUEST OTP ============

async def forgot_password_request(db: Session, email: str):
    """
    Request password reset OTP
    Generates OTP and sends to admin's email
    Returns temporary JWT for password reset flow
    """
    try:
        logger.info(f"🔐 Forgot password request for: {email}")
        
        # Find admin by email
        stmt = select(AdminUser).where(AdminUser.email == email)
        admin = db.execute(stmt).scalars().first()
        
        if not admin:
            # Security: Don't reveal if email exists
            logger.warning(f"❌ Email not found: {email}")
            # Return success anyway to prevent email enumeration
            return {
                'status': 'success',
                'message': 'If the email exists, a password reset code has been sent'
            }, None
        
        # Check if account is active
        if not admin.is_active:
            logger.warning(f"❌ Account inactive: {email}")
            return None, "Your account is disabled. Contact administrator."
        
        # Delete old unused OTP tokens for this admin
        db.query(OTPToken).filter(
            (OTPToken.admin_id == admin.id) &
            (OTPToken.is_used == False)
        ).delete()
        
        # Generate OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(OTP_CONFIG['code_length'])])
        logger.info(f"📧 Generated password reset OTP for {admin.email}")
        
        # Save OTP to database
        otp_token = OTPToken(
            admin_id=admin.id,
            otp_code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=OTP_CONFIG['expiry_minutes'])
        )
        db.add(otp_token)
        
        # Send OTP email
        email_sent = await send_otp_email(admin.email, otp_code, admin.name, subject="Password Reset OTP")
        
        if not email_sent:
            logger.warning(f"⚠️ OTP email could not be sent to {admin.email}")
        
        # Create temporary JWT for password reset flow
        reset_token = create_access_token(
            data={
                'admin_id': admin.id,
                'email': admin.email,
                'purpose': 'password_reset'
            },
            expires_delta=timedelta(minutes=OTP_CONFIG['expiry_minutes']),
            scope='reset_password'
        )
        
        db.commit()
        logger.info(f"✅ Password reset OTP sent to {admin.email}")
        
        return {
            'status': 'success',
            'message': 'Password reset code sent to your email',
            'reset_token': reset_token,
            'token_type': 'bearer',
            'email_mask': admin.email[:3] + '*' * (len(admin.email) - 6) + admin.email[-3:]
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Forgot password error: {str(e)}")
        return None, f"Password reset request failed: {str(e)}"


# ============ HELPER 6: VERIFY FORGOT PASSWORD OTP & RESET PASSWORD ============

async def reset_password_with_otp(db: Session, admin_id: int, otp_code: str, new_password: str):
    """
    Verify OTP and reset password
    Requires temporary reset_password token
    """
    try:
        logger.info(f"🔐 Password reset attempt for admin {admin_id}")
        
        # Get admin
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            logger.warning(f"❌ Admin not found: {admin_id}")
            return None, "Admin not found"
        
        # Find valid OTP
        stmt = select(OTPToken).where(
            (OTPToken.admin_id == admin_id) &
            (OTPToken.otp_code == otp_code) &
            (OTPToken.is_used == False)
        )
        otp_token = db.execute(stmt).scalars().first()
        
        if not otp_token:
            logger.warning(f"❌ Invalid OTP for password reset: {admin.email}")
            return None, "Invalid OTP code"
        
        # Check expiration
        if otp_token.expires_at < datetime.utcnow():
            logger.warning(f"❌ OTP expired for: {admin.email}")
            return None, "OTP expired. Request new password reset."
        
        # Check attempts
        if otp_token.attempts >= otp_token.max_attempts:
            logger.warning(f"❌ Max OTP attempts exceeded for: {admin.email}")
            return None, "Too many attempts. Request new password reset."
        
        # Mark OTP as used
        otp_token.attempts += 1
        otp_token.is_used = True
        
        # Hash new password
        admin.password_hash = hash_password(new_password)
        admin.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"✅ Password reset successful for: {admin.email}")
        
        return {
            'status': 'success',
            'message': 'Password reset successfully. You can now login with your new password.'
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Password reset error: {str(e)}")
        return None, f"Password reset failed: {str(e)}"


# ============ HELPER 7: CHANGE PASSWORD (For Logged-in Users) ============

async def change_password_request(db: Session, admin_id: int):
    """
    Request OTP to change password (for logged-in admins)
    Sends OTP to admin's email
    """
    try:
        logger.info(f"🔐 Change password OTP request for admin {admin_id}")
        
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            return None, "Admin not found"
        
        # Delete old unused OTP tokens
        db.query(OTPToken).filter(
            (OTPToken.admin_id == admin.id) &
            (OTPToken.is_used == False)
        ).delete()
        
        # Generate OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(OTP_CONFIG['code_length'])])
        logger.info(f"📧 Generated change password OTP for {admin.email}")
        
        # Save OTP to database
        otp_token = OTPToken(
            admin_id=admin.id,
            otp_code=otp_code,
            expires_at=datetime.utcnow() + timedelta(minutes=OTP_CONFIG['expiry_minutes'])
        )
        db.add(otp_token)
        
        # Send OTP email
        email_sent = await send_otp_email(admin.email, otp_code, admin.name, subject="Change Password OTP")
        
        if not email_sent:
            logger.warning(f"⚠️ OTP email could not be sent to {admin.email}")
        
        db.commit()
        logger.info(f"✅ Change password OTP sent to {admin.email}")
        
        return {
            'status': 'success',
            'message': 'OTP sent to your email for password change verification',
            'email_mask': admin.email[:3] + '*' * (len(admin.email) - 6) + admin.email[-3:]
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Change password OTP error: {str(e)}")
        return None, str(e)


# ============ HELPER 8: VERIFY OTP & CHANGE PASSWORD ============

async def change_password_with_otp(db: Session, admin_id: int, current_password: str, otp_code: str, new_password: str):
    """
    Verify current password and OTP, then change to new password
    """
    try:
        logger.info(f"🔐 Change password verification for admin {admin_id}")
        
        # Get admin
        admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            return None, "Admin not found"
        
        # Verify current password
        if not admin.password_hash or not verify_password(current_password, admin.password_hash):
            logger.warning(f"❌ Current password incorrect for: {admin.email}")
            return None, "Current password is incorrect"
        
        # Find valid OTP
        stmt = select(OTPToken).where(
            (OTPToken.admin_id == admin_id) &
            (OTPToken.otp_code == otp_code) &
            (OTPToken.is_used == False)
        )
        otp_token = db.execute(stmt).scalars().first()
        
        if not otp_token:
            logger.warning(f"❌ Invalid OTP for password change: {admin.email}")
            return None, "Invalid OTP code"
        
        # Check expiration
        if otp_token.expires_at < datetime.utcnow():
            logger.warning(f"❌ OTP expired for: {admin.email}")
            return None, "OTP expired. Request new OTP."
        
        # Check attempts
        if otp_token.attempts >= otp_token.max_attempts:
            logger.warning(f"❌ Max OTP attempts exceeded for: {admin.email}")
            return None, "Too many attempts. Request new OTP."
        
        # Mark OTP as used
        otp_token.attempts += 1
        otp_token.is_used = True
        
        # Hash new password
        admin.password_hash = hash_password(new_password)
        admin.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"✅ Password changed successfully for: {admin.email}")
        
        return {
            'status': 'success',
            'message': 'Password changed successfully'
        }, None
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Change password error: {str(e)}")
        return None, f"Password change failed: {str(e)}"