from flask import Flask
from flask_login import LoginManager
from config import Config
import firebase_admin
from firebase_admin import credentials, firestore
import os
import traceback

# Initialize Firebase Admin with robust error handling
firebase_app = None
db = None

try:
    # Check if Firebase is already initialized
    if not firebase_admin._apps:
        # Check if running on Render (production)
        if os.environ.get('RENDER'):
            # Use JSON string from environment variable on Render
            firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
            if firebase_creds_json:
                import json
                cred_dict = json.loads(firebase_creds_json)
                cred = credentials.Certificate(cred_dict)
            else:
                # Fallback to service account file if no env var
                cred = credentials.Certificate('service-account.json')
        else:
            # Development mode - use service account file
            cred = credentials.Certificate('service-account.json')
        
        firebase_app = firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully")
    else:
        firebase_app = firebase_admin.get_app()
        print("Using existing Firebase app")
        
    # Initialize Firestore
    db = firestore.client()
    print("Firestore client initialized successfully")
except Exception as e:
    print(f"ERROR initializing Firebase: {str(e)}")
    print(f"Detailed error: {traceback.format_exc()}")
    # Continue with app initialization but set flags for services to handle gracefully

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
        # Fallback if database is not available or doc doesn't exist
        return User(user_id, {'name': 'Demo User', 'email': 'demo@example.com', 'role': 'student'})
    except Exception as e:
        print(f"Error loading user {user_id}: {str(e)}")
        # Return a fallback user for demo/dev purposes
        return User(user_id, {'name': 'Demo User', 'email': 'demo@example.com', 'role': 'student'})
    return None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Override config with environment variables
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', app.config['SECRET_KEY'])
    app.config['DEMO_MODE'] = os.environ.get('DEMO_MODE', 'False').lower() == 'true'
    
    # Configure upload folder
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Set Firebase status in app config for error handling
    app.config['FIREBASE_INITIALIZED'] = firebase_app is not None
    app.config['FIRESTORE_INITIALIZED'] = db is not None
    
    login_manager.init_app(app)
    
    # Configure error handling
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal Server Error: {error}")
        # You would render a template here - for now just return text
        return "We apologize for the inconvenience. The system encountered an error. Please try again later or contact support.", 500
    
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
