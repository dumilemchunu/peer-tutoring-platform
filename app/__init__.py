from flask import Flask
from flask_login import LoginManager
from config import Config
import firebase_admin
from firebase_admin import credentials, firestore
import os
import traceback
from dotenv import load_dotenv

# Load environment variables from .env file in development
load_dotenv()

# Initialize Firebase Admin with robust error handling
firebase_app = None
db = None

try:
    # Check if Firebase is already initialized
    if not firebase_admin._apps:
        print("Initializing Firebase Admin SDK...")
        
        # Create credentials dictionary from environment variables
        cred_dict = {
            "type": "service_account",
            "project_id": os.environ.get('FIREBASE_PROJECT_ID'),
            "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": os.environ.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
            "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.environ.get('FIREBASE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_X509_CERT_URL')
        }
        
        # Verify required credentials are present
        required_fields = ['project_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if not cred_dict.get(field)]
        
        if missing_fields:
            raise ValueError(f"Missing required Firebase credentials: {', '.join(missing_fields)}")
            
        print("Initializing Firebase with credentials from environment variables...")
        cred = credentials.Certificate(cred_dict)
        firebase_app = firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully")
    else:
        firebase_app = firebase_admin.get_app()
        print("Using existing Firebase app")
        
    # Initialize Firestore client
    db = firestore.client()
    print("Firestore client initialized successfully")
except Exception as e:
    print(f"CRITICAL ERROR initializing Firebase: {str(e)}")
    print(f"Detailed error: {traceback.format_exc()}")
    raise  # Re-raise the exception since Firebase is required

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.sign_in'

@login_manager.user_loader
def load_user(user_id):
    from app.auth import User
    try:
        if db:
            user_doc = db.collection('users').document(user_id).get()
            if user_doc.exists:
                return User(user_id, user_doc.to_dict())
    except Exception as e:
        print(f"Error loading user {user_id}: {str(e)}")
    return None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Override config with environment variables
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', app.config['SECRET_KEY'])
    
    # Configure upload folder
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    login_manager.init_app(app)
    
    from .auth import auth_bp
    from .main import main_bp
    from .routes.admin.routes import admin_bp
    from .routes.student.routes import student_bp
    from .routes.tutor.routes import tutor_bp
    from .routes.student.booking import booking_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(tutor_bp, url_prefix='/tutor')
    app.register_blueprint(booking_bp, url_prefix='/student/booking')
    
    return app
