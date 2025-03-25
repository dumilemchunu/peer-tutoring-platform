from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from firebase_admin import auth, firestore
from functools import wraps
from datetime import datetime, timezone

admin_bp = Blueprint('admin', __name__)
firebase_service = FirebaseService()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get system statistics
    stats = firebase_service.get_system_statistics()
    
    # Get recent tutor applications
    recent_applications = firebase_service.get_tutor_applications()[:5] if firebase_service.get_tutor_applications() else []
    
    # Get all modules
    modules = firebase_service.get_all_modules()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_applications=recent_applications,
                         modules=modules)

@admin_bp.route('/modules')
@login_required
@admin_required
def modules():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get all modules
    modules_list = firebase_service.get_all_modules()
    
    # Add tutor count to each module
    for module in modules_list:
        module_code = module.get('module_code') or module.get('id')
        tutors = firebase_service.get_module_tutors(module_code)
        module['tutor_count'] = len(tutors) if tutors else 0
    
    return render_template('admin/modules.html', modules=modules_list)

@admin_bp.route('/add-module', methods=['GET', 'POST'])
@login_required
@admin_required
def add_module():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        module_code = request.form.get('module_code')
        module_name = request.form.get('module_name')
        description = request.form.get('description')
        
        try:
            firebase_service.add_module(
                module_code=module_code,
                module_name=module_name,
                description=description
            )
            flash('Module added successfully', 'success')
        except Exception as e:
            flash(f'Error adding module: {str(e)}', 'error')
        
        return redirect(url_for('admin.modules'))
    
    return render_template('admin/add_module.html')

@admin_bp.route('/tutor-applications')
@login_required
@admin_required
def tutor_applications():
    applications = firebase_service.get_tutor_applications()
    return render_template('admin/tutor_applications.html', applications=applications)

@admin_bp.route('/approve-tutor/<application_id>', methods=['POST'])
@login_required
@admin_required
def approve_tutor(application_id):
    """
    Approve a tutor application
    """
    if firebase_service.approve_tutor_application(application_id):
        flash('Tutor application approved successfully.', 'success')
    else:
        flash('Failed to approve tutor application. Please try again.', 'danger')
    return redirect(url_for('admin.tutor_applications'))

@admin_bp.route('/reject-tutor/<application_id>', methods=['POST'])
@login_required
@admin_required
def reject_tutor(application_id):
    """
    Reject a tutor application
    """
    reason = request.form.get('reason', '')
    if firebase_service.reject_tutor_application(application_id, reason):
        flash('Tutor application rejected successfully.', 'success')
    else:
        flash('Failed to reject tutor application. Please try again.', 'danger')
    return redirect(url_for('admin.tutor_applications'))

# User Management Routes
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Display all users in the system"""
    try:
        print("Fetching users for admin dashboard...")
        users_data = firebase_service.get_all_users()
        print(f"Retrieved {len(users_data)} users from Firebase")
        
        if not users_data:
            flash('No users found.', 'warning')
            return render_template('admin/users.html', users=[])
            
        return render_template('admin/users.html', users=users_data)
        
    except Exception as e:
        print(f"Error in users route: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash('Error loading users. Please try again.', 'error')
        return render_template('admin/users.html', users=[])

@admin_bp.route('/users/<user_id>')
@login_required
@admin_required
def view_user(user_id):
    """View user details"""
    try:
        user = firebase_service.get_user_by_id(user_id)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('admin.users'))
        return render_template('admin/view_user.html', user=user)
    except Exception as e:
        print(f"Error viewing user: {str(e)}")
        flash('Error loading user details.', 'error')
        return redirect(url_for('admin.users'))

@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user details"""
    try:
        if request.method == 'GET':
            user = firebase_service.get_user_by_id(user_id)
            if not user:
                flash('User not found.', 'error')
                return redirect(url_for('admin.users'))
            return render_template('admin/edit_user.html', user=user)
        # Handle POST request here when implementing edit functionality
        return redirect(url_for('admin.users'))
    except Exception as e:
        print(f"Error editing user: {str(e)}")
        flash('Error loading user details.', 'error')
        return redirect(url_for('admin.users'))

@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))
    
    try:
        # Delete user
        success = firebase_service.delete_user(user_id)
        
        if success:
            flash('User deleted successfully.', 'success')
        else:
            flash('Error deleting user.', 'error')
            
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/create-user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        is_verified = 'is_verified' in request.form
        
        # Handle student/staff number based on role
        student_number = None
        staff_number = None
        
        if role == 'student':
            student_number = request.form.get('student_number')
        elif role == 'tutor':
            staff_number = request.form.get('staff_number')
        
        try:
            # Create user in Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )
            
            # Prepare user data for Firestore
            user_data = {
                'name': name,
                'email': email,
                'role': role,
                'is_verified': is_verified,
                'student_number': student_number,
                'staff_number': staff_number,
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            # Store user in Firestore
            db = firestore.client()
            db.collection('users').document(user.uid).set(user_data)
            
            flash('User created successfully.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            flash(f'Error creating user: {str(e)}', 'error')
    
    return render_template('admin/create_user.html')

# Module-Tutor Assignment Routes
@admin_bp.route('/modules/<module_code>/tutors')
@login_required
@admin_required
def module_tutors(module_code):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get module details
    db = firestore.client()
    module_ref = db.collection('modules').document(module_code)
    module = module_ref.get()
    
    if not module.exists:
        flash('Module not found.', 'error')
        return redirect(url_for('admin.modules'))
    
    module_data = module.to_dict()
    module_data['module_code'] = module_code  # Ensure module_code is in the data
    
    # Get tutors assigned to this module
    assigned_tutors = firebase_service.get_module_tutors(module_code)
    
    # Get available tutors who can be assigned to this module
    available_tutors = firebase_service.get_available_tutors(exclude_module_code=module_code)
    
    return render_template('admin/module_tutors.html', 
                         module=module_data,
                         module_code=module_code,
                         assigned_tutors=assigned_tutors,
                         available_tutors=available_tutors)

@admin_bp.route('/modules/<module_code>/assign-tutor', methods=['POST'])
@login_required
@admin_required
def assign_tutor(module_code):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    tutor_id = request.form.get('tutor_id')
    if not tutor_id:
        flash('No tutor selected.', 'error')
        return redirect(url_for('admin.module_tutors', module_code=module_code))
    
    try:
        firebase_service.assign_tutor_to_module(tutor_id, module_code)
        flash('Tutor assigned to module successfully.', 'success')
    except ValueError as e:
        flash(f'Error assigning tutor: {str(e)}', 'error')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
    
    return redirect(url_for('admin.module_tutors', module_code=module_code))

@admin_bp.route('/modules/tutors/<assignment_id>/remove', methods=['POST'])
@login_required
@admin_required
def remove_tutor_assignment(assignment_id):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get module code for redirect
    db = firestore.client()
    assignment_ref = db.collection('module_tutors').document(assignment_id)
    assignment = assignment_ref.get()
    
    if not assignment.exists:
        flash('Assignment not found.', 'error')
        return redirect(url_for('admin.modules'))
    
    module_code = assignment.to_dict().get('module_code')
    
    try:
        firebase_service.unassign_tutor_from_module(assignment_id)
        flash('Tutor removed from module successfully.', 'success')
    except Exception as e:
        flash(f'Error removing tutor: {str(e)}', 'error')
    
    return redirect(url_for('admin.module_tutors', module_code=module_code))

@admin_bp.route('/tutors/<tutor_id>/modules')
@login_required
@admin_required
def tutor_modules(tutor_id):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get tutor details
    tutor = firebase_service.get_user_by_id(tutor_id)
    if not tutor:
        flash('Tutor not found.', 'error')
        return redirect(url_for('admin.users'))
    
    # Get modules assigned to this tutor
    assigned_modules = firebase_service.get_tutor_modules(tutor_id)
    
    # Get all modules for assignment
    all_modules = firebase_service.get_all_modules()
    
    # Filter out already assigned modules
    assigned_module_codes = [m['module_code'] for m in assigned_modules]
    available_modules = [m for m in all_modules if m['id'] not in assigned_module_codes]
    
    return render_template('admin/tutor_modules.html',
                         tutor=tutor,
                         assigned_modules=assigned_modules,
                         available_modules=available_modules)

@admin_bp.route('/modules/<module_code>/edit', methods=['POST'])
@login_required
@admin_required
def edit_module(module_code):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    module_name = request.form.get('module_name')
    description = request.form.get('description')
    
    try:
        firebase_service.update_module(module_code, module_name, description)
        flash('Module updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating module: {str(e)}', 'error')
    
    return redirect(url_for('admin.modules'))

@admin_bp.route('/modules/<module_code>/delete', methods=['POST'])
@login_required
@admin_required
def delete_module(module_code):
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        firebase_service.delete_module(module_code)
        flash('Module deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting module: {str(e)}', 'error')
    
    return redirect(url_for('admin.modules'))

# Add this new route to view documents
@admin_bp.route('/documents/<doc_id>')
@login_required
@admin_required
def view_document(doc_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Get the document from Firestore
    document = firebase_service.get_document_content(doc_id)
    
    if not document:
        flash('Document not found.', 'error')
        return redirect(url_for('admin.tutor_applications'))
    
    # Create response with PDF content
    from flask import Response
    import base64
    
    try:
        # Decode the base64 content
        pdf_content = base64.b64decode(document.get('file_content', ''))
        
        # Create a response with the PDF content
        response = Response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={document.get("file_name", "document.pdf")}'
        
        return response
    except Exception as e:
        flash(f'Error displaying document: {str(e)}', 'error')
        return redirect(url_for('admin.tutor_applications')) 