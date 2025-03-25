from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from app import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta

tutor_bp = Blueprint('tutor', __name__)
firebase_service = FirebaseService()

@tutor_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get modules assigned to this tutor
    try:
        # Try to get assigned modules from firebase_service
        assigned_modules = firebase_service.get_tutor_modules(current_user.id)
    except Exception as e:
        print(f"ERROR: Unable to get assigned modules: {str(e)}")
        assigned_modules = []
    
    # Get all tutor's bookings
    all_bookings = firebase_service.get_tutor_bookings(current_user.id)
    
    # If there are no bookings at all, don't bother with module filtering
    if not all_bookings:
        print(f"DEBUG: No bookings found for dashboard")
        bookings = []
    else:
        # Extract module codes from assigned modules - normalize to lowercase for case-insensitive matching
        assigned_module_codes = []
        if assigned_modules:
            assigned_module_codes = [module['module_code'].lower() for module in assigned_modules]
            print(f"DEBUG: Tutor is assigned to modules: {assigned_module_codes}")
        
        # If we have assigned modules, filter bookings; otherwise show all
        if assigned_module_codes:
            # Case-insensitive filtering by converting all module codes to lowercase
            bookings = [
                booking for booking in all_bookings 
                if booking.get('module_code') and booking.get('module_code').lower() in assigned_module_codes
            ]
            print(f"DEBUG: Dashboard filtered to {len(bookings)} bookings for assigned modules")
            
            # If filtering resulted in no bookings, show all bookings instead
            if not bookings:
                print(f"DEBUG: Dashboard filtering removed all bookings, showing all instead")
                bookings = all_bookings
        else:
            # If no assigned modules found or error occurred, show all bookings
            print(f"DEBUG: No assigned modules found for dashboard, showing all bookings")
            bookings = all_bookings
    
    # Get tutor's availability
    availability = [
        {
            'day': 'Monday',
            'start_time': '09:00',
            'end_time': '11:00'
        },
        {
            'day': 'Wednesday',
            'start_time': '14:00',
            'end_time': '16:00'
        },
        {
            'day': 'Friday',
            'start_time': '10:00',
            'end_time': '12:00'
        }
    ]
    
    # Get content uploaded by this tutor
    content = [
        {
            'id': '1',
            'title': 'Introduction to Programming',
            'description': 'A beginner\'s guide to programming concepts.',
            'module_name': 'Computer Science 101',
            'uploaded_at': datetime.now() - timedelta(days=5)
        },
        {
            'id': '2',
            'title': 'Database Design Principles',
            'description': 'Learn the fundamentals of database design.',
            'module_name': 'Database Systems',
            'uploaded_at': datetime.now() - timedelta(days=10)
        },
        {
            'id': '3',
            'title': 'Web Development Basics',
            'description': 'Introduction to HTML, CSS, and JavaScript.',
            'module_name': 'Web Technologies',
            'uploaded_at': datetime.now() - timedelta(days=15)
        }
    ]
    
    # Get feedback from students
    feedback = [
        {
            'id': '1',
            'student_name': 'John Smith',
            'rating': 4,
            'comment': 'Very helpful session, explained concepts clearly.'
        },
        {
            'id': '2',
            'student_name': 'Emily Johnson',
            'rating': 5,
            'comment': 'Excellent tutor, helped me understand difficult topics.'
        },
        {
            'id': '3',
            'student_name': 'Michael Brown',
            'rating': 4,
            'comment': 'Good session, but could have been more interactive.'
        }
    ]
    
    return render_template('tutor/Tutor-Dashboard.html', 
                          bookings=bookings, 
                          availability=availability, 
                          content=content, 
                          feedback=feedback,
                          assigned_modules=assigned_modules,
                          debug_mode=True)

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
    
    # Get all tutor's bookings
    print(f"DEBUG: Getting bookings for tutor {current_user.id}")
    all_bookings = firebase_service.get_tutor_bookings(current_user.id)
    print(f"DEBUG: Retrieved {len(all_bookings)} bookings for tutor {current_user.id}")
    
    # If there are no bookings at all, don't bother with module filtering
    if not all_bookings:
        print(f"DEBUG: No bookings found, will add demo data later")
        bookings = []
    else:
        # Get modules assigned to this tutor
        assigned_modules = []
        try:
            # Try to get assigned modules from firebase_service
            assigned_modules = firebase_service.get_tutor_modules(current_user.id)
        except Exception as e:
            print(f"ERROR: Unable to get assigned modules: {str(e)}")
            assigned_modules = []
            
        # Extract module codes from assigned modules - normalize to lowercase for case-insensitive matching
        assigned_module_codes = []
        if assigned_modules:
            assigned_module_codes = [module['module_code'].lower() for module in assigned_modules]
            print(f"DEBUG: Tutor is assigned to modules: {assigned_module_codes}")
        
        # If we have assigned modules, filter bookings; otherwise show all
        if assigned_module_codes:
            # Case-insensitive filtering by converting all module codes to lowercase
            bookings = [
                booking for booking in all_bookings 
                if booking.get('module_code') and booking.get('module_code').lower() in assigned_module_codes
            ]
            print(f"DEBUG: Filtered to {len(bookings)} bookings for assigned modules")
            
            # If filtering resulted in no bookings, show all bookings instead
            if not bookings:
                print(f"DEBUG: Filtering removed all bookings, showing all instead")
                bookings = all_bookings
        else:
            # If no assigned modules found or error occurred, show all bookings
            print(f"DEBUG: No assigned modules found, showing all bookings")
            bookings = all_bookings
    
    # Add some demo bookings if none exist (fallback protection)
    if not bookings:
        print(f"DEBUG: No bookings found, adding demo data as fallback")
        today = datetime.now()
        bookings = [
            {
                'id': f'emergency_demo_1',
                'student_name': 'Emergency Demo Student',
                'module_name': 'Demo Module',
                'date': (today + timedelta(days=1)).strftime('%Y-%m-%d'),
                'time_slot': '10:00 - 11:00',
                'status': 'pending',
            }
        ]
    
    return render_template('tutor/manage_bookings.html', bookings=bookings, debug_mode=True)

@tutor_bp.route('/debug-bookings')
@login_required
def debug_bookings():
    """Debug route to display booking details for troubleshooting"""
    if not current_user.is_tutor:
        flash('Access denied. You must be a tutor to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get raw bookings data
    all_bookings = firebase_service.get_tutor_bookings(current_user.id)
    
    # Get a sample session from Firestore directly
    debug_info = {
        'tutor_id': current_user.id,
        'bookings_count': len(all_bookings),
        'bookings': all_bookings,
        'has_module_codes': any(booking.get('module_code') for booking in all_bookings),
        'module_codes': [booking.get('module_code') for booking in all_bookings if booking.get('module_code')]
    }
    
    # Get raw query of sessions to check
    try:
        sessions_ref = firebase_service.db.collection('sessions')
        all_sessions = list(sessions_ref.limit(10).stream())
        debug_info['all_sessions_count'] = len(all_sessions)
        if all_sessions:
            # Get first session as example
            first_session = all_sessions[0].to_dict()
            first_session['id'] = all_sessions[0].id
            debug_info['sample_session'] = first_session
    except Exception as e:
        debug_info['query_error'] = str(e)
    
    return render_template('tutor/debug_bookings.html', debug_info=debug_info)

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