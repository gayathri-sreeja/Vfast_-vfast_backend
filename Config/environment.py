import os
from dotenv import load_dotenv

load_dotenv()

# Current environment
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# Email Configuration
GMAIL_CONFIG = {
    'sender_email': os.getenv('GMAIL_USER'),
    'sender_password': os.getenv('GMAIL_PASSWORD'),
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587
}

# JWT Configuration
JWT_CONFIG = {
    'secret_key': os.getenv('JWT_SECRET_KEY'),
    'algorithm': os.getenv('JWT_ALGORITHM', 'HS256'),
    'access_token_expire_minutes': int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 1440))
}

# Google OAuth Configuration
GOOGLE_CONFIG = {
    'client_id': os.getenv('GOOGLE_CLIENT_ID'),
    'client_secret': os.getenv('GOOGLE_CLIENT_SECRET')
}

# Database Configuration
DB_CONFIG = {
    'url': os.getenv('DATABASE_URL'),
    'schema': 'vfast'
}

# Application Configuration
APP_CONFIG = {
    'name': 'VFAST',
    'version': '1.0.0',
    'environment': ENVIRONMENT,
    'debug': ENVIRONMENT == 'development'
}

# OTP Configuration
OTP_CONFIG = {
    'expiry_minutes': 10,
    'max_attempts': 5,
    'code_length': 6
}

# Booking Configuration
BOOKING_CONFIG = {
    'max_stay_days': 7,
    'max_pax_per_room': 4,
    'booking_advance_days': 90,
    'min_rooms_per_request': 1
}