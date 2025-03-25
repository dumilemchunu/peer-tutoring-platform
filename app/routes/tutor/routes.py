from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from app import db

tutor_bp = Blueprint('tutor', __name__)
firebase_service = FirebaseService()

@tutor_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get tutor's bookings and feedback
    bookings = firebase_service.get_tutor_bookings(current_user.id)
    feedback = firebase_service.get_tutor_feedback(current_user.id)
    
    return render_template('tutor/Tutor-Dashboard.html', 
                         bookings=bookings,
                         feedback=feedback)

@tutor_bp.route('/set-availability', methods=['GET', 'POST'])
@login_required
def set_availability():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        availabilities = request.form.getlist('availabilities[]')
        firebase_service.set_tutor_availability(current_user.id, availabilities)
        flash('Availability updated successfully', 'success')
        return redirect(url_for('tutor.dashboard'))
    
    # Get current availability
    availability = firebase_service.get_tutor_availability(current_user.id)
    return render_template('tutor/set_availability.html', 
                         current_availability=availability)

@tutor_bp.route('/upload-content', methods=['GET', 'POST'])
@login_required
def upload_content():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        module_code = request.form.get('module_code')
        content = request.form.get('content')  # Get content as text
        
        try:
            firebase_service.upload_content(
                content_data=content,
                module_code=module_code,
                title=title,
                description=description,
                tutor_id=current_user.id
            )
            flash('Content uploaded successfully', 'success')
        except Exception as e:
            flash(f'Error uploading content: {str(e)}', 'error')
        
        return redirect(url_for('tutor.dashboard'))
    
    # Get available modules for the dropdown
    modules = firebase_service.get_all_modules()
    return render_template('tutor/upload_content.html', 
                         modules=modules) 