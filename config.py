import os
from datetime import timedelta

class Config:
    """Application configuration"""
    # Secret key for session signing (load from environment or use default)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Demo mode setting - can be overridden with environment variable
    DEMO_MODE = os.environ.get('DEMO_MODE', 'False').lower() == 'true'
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt', 'zip', 'rar', 'jpg', 'jpeg', 'png'}
    
    # Debug mode - disable in production
    DEBUG = os.environ.get('FLASK_ENV', 'development') != 'production'
    
    # Firebase settings can be configured via environment variables
    # FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID')
    # FIREBASE_AUTH_DOMAIN = os.environ.get('FIREBASE_AUTH_DOMAIN')
    # FIREBASE_API_KEY = os.environ.get('FIREBASE_API_KEY')
