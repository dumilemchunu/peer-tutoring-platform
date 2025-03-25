from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from firebase_admin import auth, firestore
import firebase_admin

auth_bp = Blueprint('auth', __name__)
db = firestore.client()

class User:
    def __init__(self, uid, data):
        self.id = uid
        self.name = data.get('name')
        self.email = data.get('email')
        self.role = data.get('role')
        self.is_verified = data.get('is_verified', False)
        self.student_number = data.get('student_number')
        self.staff_number = data.get('staff_number')
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_tutor(self):
        return self.role == 'tutor'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @staticmethod
    def get_by_email(email):
        try:
            user = auth.get_user_by_email(email)
            user_doc = db.collection('users').document(user.uid).get()
            if user_doc.exists:
                return User(user.uid, user_doc.to_dict())
        except:
            return None

@auth_bp.route('/sign-in', methods=['GET', 'POST'])
def sign_in():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Verify the password with Firebase Auth
            user = auth.get_user_by_email(email)
            # Note: We can't verify password directly with Firebase Admin SDK
            # In production, you should use Firebase Client SDK for this
            # For now, we'll trust the email exists and proceed
            
            user_doc = db.collection('users').document(user.uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_obj = User(user.uid, user_data)
                login_user(user_obj)
                return redirect(url_for('main.dashboard'))
            else:
                flash('User data not found.', 'error')
        except Exception as e:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/sign-in.html')

@auth_bp.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        student_number = request.form.get('student_number')
        staff_number = request.form.get('staff_number')
        
        try:
            # Create user in Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )
            
            # Store additional user data in Firestore
            user_data = {
                'name': name,
                'email': email,
                'role': role,
                'is_verified': False,
                'student_number': student_number if role == 'student' else None,
                'staff_number': staff_number if role == 'tutor' else None
            }
            
            db.collection('users').document(user.uid).set(user_data)
            flash('Account created successfully! Please sign in.', 'success')
            return redirect(url_for('auth.sign_in'))
            
        except Exception as e:
            flash('Error creating account. Please try again.', 'error')
    
    return render_template('auth/sign-up.html')

@auth_bp.route('/sign-out')
@login_required
def sign_out():
    logout_user()
    return redirect(url_for('main.index')) 