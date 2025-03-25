from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from firebase_admin import auth, firestore
import firebase_admin
import os
from werkzeug.utils import secure_filename
from app.services.firebase_service import FirebaseService
import traceback

auth_bp = Blueprint('auth', __name__)
firebase_service = FirebaseService()

# Initialize Firestore with error handling
try:
    db = firestore.client()
except Exception as e:
    print(f"Error initializing Firestore in auth.py: {str(e)}")
    db = None

class User:
    def __init__(self, uid, data):
        self.id = uid
        self.name = data.get('name', 'Unknown User')
        self.email = data.get('email', 'user@example.com')
        self.role = data.get('role', 'student')
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
            if not db:
                print("WARNING: Firestore not available in get_by_email")
                return None
                
            user = auth.get_user_by_email(email)
            user_doc = db.collection('users').document(user.uid).get()
            if user_doc.exists:
                return User(user.uid, user_doc.to_dict())
        except Exception as e:
            print(f"Error in get_by_email: {str(e)}")
            return None

@auth_bp.route('/sign-in', methods=['GET', 'POST'])
def sign_in():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    # Check if Firebase is initialized
    if hasattr(current_app, 'config') and not current_app.config.get('FIREBASE_INITIALIZED', True):
        flash('System is currently in maintenance mode. Please try again later.', 'warning')
        return render_template('auth/sign-in.html')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Demo/development mode login (if Firebase is not available)
            if hasattr(current_app, 'config') and not current_app.config.get('FIREBASE_INITIALIZED', True):
                # Hardcoded demo accounts for testing
                if email == 'student@example.com' and password == 'password':
                    user_data = {'name': 'Demo Student', 'email': email, 'role': 'student', 'is_verified': True}
                    user_obj = User('demo-student-id', user_data)
                    login_user(user_obj)
                    return redirect(url_for('student.home'))
                elif email == 'tutor@example.com' and password == 'password':
                    user_data = {'name': 'Demo Tutor', 'email': email, 'role': 'tutor', 'is_verified': True}
                    user_obj = User('demo-tutor-id', user_data)
                    login_user(user_obj)
                    return redirect(url_for('tutor.dashboard'))
                else:
                    flash('Invalid email or password in demo mode.', 'error')
                    return render_template('auth/sign-in.html')
            
            # Normal Firebase authentication
            user = auth.get_user_by_email(email)
            
            if not db:
                flash('Database service is temporarily unavailable.', 'error')
                return render_template('auth/sign-in.html')
                
            user_doc = db.collection('users').document(user.uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                
                # Check tutor approval status
                if user_data.get('role') == 'tutor' and not user_data.get('is_verified'):
                    flash('Your tutor account is pending approval by an administrator. You will be notified once approved.', 'warning')
                    return render_template('auth/sign-in.html')
                
                user_obj = User(user.uid, user_data)
                login_user(user_obj)
                
                # Redirect to appropriate dashboard
                if user_obj.is_student:
                    return redirect(url_for('student.home'))
                elif user_obj.is_tutor:
                    return redirect(url_for('tutor.dashboard'))
                elif user_obj.is_admin:
                    return redirect(url_for('admin.dashboard'))
                else:
                    return redirect(url_for('main.dashboard'))
            else:
                flash('User data not found.', 'error')
        except Exception as e:
            print(f"Error during sign-in: {str(e)}")
            print(traceback.format_exc())
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
        
        try:
            # Create user in Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )
            
            # Prepare base user data
            user_data = {
                'name': name,
                'email': email,
                'role': role,
                'created_at': firestore.SERVER_TIMESTAMP,
                'is_verified': False
            }
            
            # Add role-specific fields
            if role == 'student':
                student_number = request.form.get('student_number')
                user_data['student_number'] = student_number
                user_data['is_verified'] = True  # Students are verified automatically
            
            elif role == 'tutor':
                staff_number = request.form.get('staff_number')
                qualifications = request.form.get('qualifications')
                subjects = request.form.get('subjects')
                availability = request.form.get('availability')
                
                user_data['staff_number'] = staff_number
                user_data['qualifications'] = qualifications
                user_data['subjects'] = subjects
                user_data['availability'] = availability
                user_data['tutor_status'] = 'pending'  # Add status field for admin approval
                
                # Handle file uploads for academic record and CV
                academic_record_id = None
                cv_id = None
                
                if 'academic_record' in request.files:
                    academic_record = request.files['academic_record']
                    if academic_record.filename:
                        # Secure the filename and save to temp location
                        academic_filename = secure_filename(academic_record.filename)
                        academic_path = os.path.join(current_app.config['UPLOAD_FOLDER'], academic_filename)
                        academic_record.save(academic_path)
                        
                        # Get file size
                        file_size = os.path.getsize(academic_path)
                        
                        # Encode file to base64
                        file_content = firebase_service.encode_file_to_base64(academic_path)
                        
                        # Store document reference with encoded content
                        academic_record_id = firebase_service.store_document_reference(
                            user_id=user.uid,
                            doc_type='academic_record',
                            file_content=file_content,
                            file_name=academic_filename,
                            file_size=file_size
                        )
                        
                        # Remove the temp file
                        if os.path.exists(academic_path):
                            os.remove(academic_path)
                
                if 'cv' in request.files:
                    cv = request.files['cv']
                    if cv.filename:
                        # Secure the filename and save to temp location
                        cv_filename = secure_filename(cv.filename)
                        cv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], cv_filename)
                        cv.save(cv_path)
                        
                        # Get file size
                        file_size = os.path.getsize(cv_path)
                        
                        # Encode file to base64
                        file_content = firebase_service.encode_file_to_base64(cv_path)
                        
                        # Store document reference with encoded content
                        cv_id = firebase_service.store_document_reference(
                            user_id=user.uid,
                            doc_type='cv',
                            file_content=file_content,
                            file_name=cv_filename,
                            file_size=file_size
                        )
                        
                        # Remove the temp file
                        if os.path.exists(cv_path):
                            os.remove(cv_path)
                
                # Create a tutor application record
                application_data = {
                    'user_id': user.uid,
                    'name': name,
                    'email': email,
                    'staff_number': staff_number,
                    'qualifications': qualifications,
                    'subjects': subjects,
                    'availability': availability,
                    'academic_record_id': academic_record_id,
                    'cv_id': cv_id,
                    'status': 'pending',
                    'created_at': firestore.SERVER_TIMESTAMP
                }
                
                # Store the tutor application
                db.collection('tutor_applications').document(user.uid).set(application_data)
            
            # Store user data in Firestore
            db.collection('users').document(user.uid).set(user_data)
            
            # Redirect based on role
            if role == 'student':
                # Log the student in automatically
                user_obj = User(user.uid, user_data)
                login_user(user_obj)
                flash('Account created successfully! Welcome to the Student Dashboard.', 'success')
                return redirect(url_for('student.home'))
            else:
                # For tutors, redirect to sign-in with a message about pending approval
                flash('Your tutor application has been submitted and is pending approval by an administrator. You will be notified once your account is approved.', 'info')
                return redirect(url_for('auth.sign_in'))
            
        except Exception as e:
            flash(f'Error creating account: {str(e)}', 'error')
    
    return render_template('auth/sign_up.html')

@auth_bp.route('/sign-out')
@login_required
def sign_out():
    logout_user()
    return redirect(url_for('main.index')) 