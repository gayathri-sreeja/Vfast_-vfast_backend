import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from Config.environment import GMAIL_CONFIG, APP_CONFIG

logger = logging.getLogger(__name__)

async def send_otp_email(email: str, otp_code: str, name: str, subject: str = None) -> bool:
    """
    Send OTP via email
    In development mode, just log the OTP
    """
    
    if subject is None:
        subject = '🔐 VFAST Admin Portal - OTP Verification'
    
    # ============ DEVELOPMENT MODE: LOG OTP INSTEAD OF SENDING ============
    if APP_CONFIG['environment'] == 'development':
        logger.warning("=" * 60)
        logger.warning("📧 EMAIL SIMULATION (Development Mode)")
        logger.warning("=" * 60)
        logger.warning(f"TO: {email}")
        logger.warning(f"NAME: {name}")
        logger.warning(f"SUBJECT: {subject}")
        logger.warning(f"OTP: {otp_code}")
        logger.warning(f"VALID FOR: 10 minutes")
        logger.warning("=" * 60)
        logger.warning("⚠️ In production, this would send a real email")
        logger.warning("=" * 60)
        return True
    
    # ============ PRODUCTION MODE: SEND REAL EMAIL ============
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_CONFIG['sender_email']
        msg['To'] = email
        msg['Subject'] = subject
        
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px;">
                    <h2 style="color: #333; text-align: center;">🏨 VFAST Admin Portal</h2>
                    <hr style="border: none; border-top: 1px solid #ddd;">
                    
                    <p>Hi <strong>{name}</strong>,</p>
                    
                    <p>Your one-time password (OTP) for VFAST Admin login is:</p>
                    
                    <div style="
                        background-color: #f0f0f0; 
                        padding: 20px; 
                        border-radius: 8px; 
                        text-align: center; 
                        margin: 20px 0;
                    ">
                        <h1 style="
                            color: #007bff; 
                            letter-spacing: 5px; 
                            font-family: monospace; 
                            margin: 0;
                        ">{otp_code}</h1>
                    </div>
                    
                    <p style="color: #666;">
                        ⏰ <strong>Note:</strong> This OTP will expire in <strong>10 minutes</strong>. 
                        Do not share it with anyone.
                    </p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd;">
                    
                    <p style="color: #999; font-size: 12px;">
                        If you did not request this OTP, please ignore this email or contact your administrator immediately.
                    </p>
                    
                    <p style="color: #999; font-size: 12px; margin-bottom: 0;">
                        <strong>Best regards,</strong><br>
                        VFAST Team<br>
                        Birla Institute of Technology and Science (BITS) Pilani
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        server = smtplib.SMTP(GMAIL_CONFIG['smtp_server'], GMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(GMAIL_CONFIG['sender_email'], GMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        
        logger.info(f"✅ OTP email sent to: {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending OTP email: {str(e)}")
        logger.error("⚠️ Falling back to console logging")
        # Log to console instead
        logger.warning(f"📧 OTP for {email}: {otp_code}")
        return False


async def send_approval_notification(email: str, name: str, booking_id: int, status: str, reason: str = None) -> bool:
    """Send approval/rejection notification"""
    
    if APP_CONFIG['environment'] == 'development':
        logger.warning(f"📧 NOTIFICATION: {name} - Booking {booking_id} {status}")
        return True
    
    # ... rest of production email code ...
    return True