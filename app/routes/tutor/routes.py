from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from app import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime

tutor_bp = Blueprint('tutor', __name__)
firebase_service = FirebaseService()

@tutor_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get modules assigned to this tutor first
    assigned_modules = firebase_service.get_tutor_modules(current_user.id)
    
    # Get tutor's bookings, availability, content, and feedback
    bookings = firebase_service.get_tutor_bookings(current_user.id)
    availability = firebase_service.get_tutor_availability(current_user.id)
    content = firebase_service.get_tutor_content(current_user.id)
    feedback = firebase_service.get_tutor_feedback(current_user.id)
    
    return render_template('tutor/Tutor-Dashboard.html', 
                          bookings=bookings,
                          availability=availability.get('schedules', []),
                          content=content,
                          feedback=feedback,
                          assigned_modules=assigned_modules)

@tutor_bp.route('/manage-bookings', methods=['GET', 'POST'])
@login_required
def manage_bookings():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        booking_id = request.form.get('booking_id')
        action = request.form.get('action')
        
        if booking_id and action in ['confirm', 'reject', 'cancel']:
            firebase_service.update_booking_status(booking_id, action)
            flash(f'Booking {action}ed successfully', 'success')
        
        return redirect(url_for('tutor.dashboard'))
    
    # Get tutor's bookings
    bookings = firebase_service.get_tutor_bookings(current_user.id)
    return render_template('tutor/manage_bookings.html', bookings=bookings)

@tutor_bp.route('/set-availability', methods=['GET', 'POST'])
@login_required
def set_availability():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        # Process form data for availability
        days = request.form.getlist('day[]')
        start_times = request.form.getlist('start_time[]')
        end_times = request.form.getlist('end_time[]')
        
        # Create availability schedule
        availabilities = []
        for i in range(len(days)):
            if i < len(start_times) and i < len(end_times):
                availabilities.append({
                    'day': days[i],
                    'start_time': start_times[i],
                    'end_time': end_times[i]
                })
        
        firebase_service.set_tutor_availability(current_user.id, availabilities)
        flash('Availability schedule updated successfully', 'success')
        return redirect(url_for('tutor.dashboard'))
    
    # Get current availability
    availability = firebase_service.get_tutor_availability(current_user.id)
    return render_template('tutor/set_availability.html', 
                          availability=availability.get('schedules', []))

@tutor_bp.route('/upload-content', methods=['GET', 'POST'])
@login_required
def upload_content():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get modules assigned to this tutor
    assigned_modules = firebase_service.get_tutor_modules(current_user.id)
    
    # If tutor has no assigned modules, show message and redirect
    if not assigned_modules:
        flash('You are not assigned to any modules yet. Please contact an administrator to get assigned to modules.', 'warning')
        return redirect(url_for('tutor.dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        module_code = request.form.get('module_code')
        
        # Verify that the tutor is assigned to this module
        module_codes = [module['module_code'] for module in assigned_modules]
        if module_code not in module_codes:
            flash('You are not authorized to upload content for this module.', 'error')
            return redirect(url_for('tutor.upload_content'))
        
        # Check if file is uploaded
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                # Save file to disk
                filename = secure_filename(file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Get file type from extension
                file_type = os.path.splitext(filename)[1][1:].lower()
                
                try:
                    # Upload file reference to Firestore
                    firebase_service.upload_content(
                        content_data=file_path,  # Store the file path
                        module_code=module_code,
                        title=title,
                        description=description,
                        tutor_id=current_user.id,
                        file_type=file_type
                    )
                    flash('Content uploaded successfully', 'success')
                except Exception as e:
                    flash(f'Error uploading content: {str(e)}', 'error')
            else:
                flash('No file selected', 'error')
        else:
            # Handle text content
            content_text = request.form.get('content_text')
            if content_text:
                try:
                    firebase_service.upload_content(
                        content_data=content_text,
                        module_code=module_code,
                        title=title,
                        description=description,
                        tutor_id=current_user.id,
                        file_type='text'
                    )
                    flash('Content uploaded successfully', 'success')
                except Exception as e:
                    flash(f'Error uploading content: {str(e)}', 'error')
            else:
                flash('No content provided', 'error')
        
        return redirect(url_for('tutor.dashboard'))
    
    # Check if a specific module was requested (from quick upload buttons)
    selected_module = request.args.get('module', '')
    
    # Only pass assigned modules to the template
    return render_template('tutor/upload_content.html', modules=assigned_modules, selected_module=selected_module)

@tutor_bp.route('/delete-content/<content_id>', methods=['POST'])
@login_required
def delete_content(content_id):
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to perform this action.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        firebase_service.delete_content(content_id)
        flash('Content deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting content: {str(e)}', 'error')
    
    return redirect(url_for('tutor.dashboard'))

@tutor_bp.route('/view-feedback')
@login_required
def view_feedback():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get tutor's feedback
    feedback = firebase_service.get_tutor_feedback(current_user.id)
    return render_template('tutor/view_feedback.html', feedback=feedback)

@tutor_bp.route('/my-modules')
@login_required
def my_modules():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get modules assigned to this tutor
    assigned_modules = firebase_service.get_tutor_modules(current_user.id)
    
    # Get all students assigned to each module for quick reference
    module_students = {}
    for module in assigned_modules:
        module_code = module['module_code']
        # Get bookings for this module and tutor to find unique students
        bookings = firebase_service.get_tutor_bookings(current_user.id)
        students = []
        student_ids = set()
        
        for booking in bookings:
            if booking.get('module_code') == module_code and booking.get('student_id') not in student_ids:
                student_ids.add(booking.get('student_id'))
                students.append({
                    'id': booking.get('student_id'),
                    'name': booking.get('student_name')
                })
        
        module_students[module_code] = students
    
    return render_template('tutor/my_modules.html', 
                          assigned_modules=assigned_modules,
                          module_students=module_students) 