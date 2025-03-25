from flask import Flask
from flask_login import LoginManager
from config import Config
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin
cred = credentials.Certificate('service-account.json')
firebase_admin.initialize_app(cred)

# Initialize Firestore
db = firestore.client()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.sign_in'

@login_manager.user_loader
def load_user(user_id):
    from app.auth import User
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        return User(user_id, user_doc.to_dict())
    return None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    login_manager.init_app(app)
    
    from .auth import auth_bp
    from .main import main_bp
    from .routes.admin.routes import admin_bp
    from .routes.student.routes import student_bp
    from .routes.tutor.routes import tutor_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(tutor_bp, url_prefix='/tutor')
    
    return app
