from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, send_file, jsonify, abort, session
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from app import db
import os
from datetime import datetime, timedelta
import io
import pytz
from werkzeug.utils import secure_filename
import uuid
import traceback

student_bp = Blueprint('student', __name__, url_prefix='/student')
firebase_service = FirebaseService()

@student_bp.before_request
def check_student():
    """Check if the user is a student before processing requests"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    
    if current_user.role != 'student':
        flash('You do not have permission to access the student area.', 'danger')
        return redirect(url_for('main.index'))

# Global error handler for uncaught exceptions in the student blueprint
@student_bp.errorhandler(Exception)
def handle_unexpected_error(e):
    current_app.logger.error(f"Unexpected error in student routes: {str(e)}")
    current_app.logger.error(traceback.format_exc())
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred. Please try again later.',
            'details': str(e) if current_app.debug else None
        }), 500
    
    # Return a user-friendly error page
    flash('An unexpected error occurred. Our team has been notified.', 'danger')
    return redirect(url_for('student.home'))

@student_bp.route('/')
@login_required
def home():
    """Student dashboard homepage"""
    # Get today's date
    today_date = datetime.now()
    
    # Get student bookings
    bookings = firebase_service.get_student_bookings(current_user.id)
    
    # Get upcoming sessions
    upcoming_sessions = firebase_service.get_student_upcoming_sessions(current_user.id)
    
    # Get recent content
    recent_content = firebase_service.get_recent_content(limit=5)
    
    # Get available modules
    modules = firebase_service.get_all_modules()
    
    # Get statistics
    stats = {
        'upcoming_sessions': len(upcoming_sessions),
        'total_modules': len(modules),
        'learning_materials': firebase_service.count_learning_materials(),
        'total_hours': firebase_service.get_student_total_hours(current_user.id)
    }
    
    return render_template('student/dashboard.html', 
                          current_user=current_user,
                          today_date=today_date,
                          upcoming_sessions=upcoming_sessions,
                          recent_content=recent_content,
                          modules=modules,
                          bookings=bookings,
                          debug_mode=True,
                          stats=stats)

@student_bp.route('/book-wizard', methods=['GET', 'POST'])
@login_required
def book_wizard():
    """Multi-step booking wizard for scheduling tutor sessions"""
    try:
        current_app.logger.info("Starting book_wizard route handler")
        
        # Get current step from session
        current_step = session.get('booking_step', 1)
        current_app.logger.info(f"Current booking step: {current_step}")
        
        # Get saved booking data from session
        booking_data = session.get('booking_data', {})
        
        # Initialize variables
        modules = []
        selected_module = None
        module_tutors = []
        available_dates = []
        available_slots = []
        error_occurred = False
        error_message = None
        
        # Handle form submission for each step
        if request.method == 'POST':
            current_app.logger.info(f"Processing POST request for step {current_step}")
            
            # Step 1: Module selection
            if current_step == 1:
                module_code = request.form.get('module_code')
                current_app.logger.info(f"Selected module: {module_code}")
                
                if not module_code:
                    flash('Please select a module.', 'danger')
                    return redirect(url_for('student.book_wizard'))
                
                # Save selected module and move to next step
                booking_data['module_code'] = module_code
                session['booking_data'] = booking_data
                session['booking_step'] = 2
                return redirect(url_for('student.book_wizard'))
            
            # Step 2: Tutor selection
            elif current_step == 2:
                tutor_id = request.form.get('tutor_id')
                current_app.logger.info(f"Selected tutor: {tutor_id}")
                
                if not tutor_id:
                    flash('Please select a tutor.', 'danger')
                    return redirect(url_for('student.book_wizard'))
                
                # Save selected tutor and move to next step
                booking_data['tutor_id'] = tutor_id
                session['booking_data'] = booking_data
                session['booking_step'] = 3
                return redirect(url_for('student.book_wizard'))
            
            # Step 3: Date selection
            elif current_step == 3:
                session_date = request.form.get('session_date')
                current_app.logger.info(f"Selected date: {session_date}")
                
                if not session_date:
                    flash('Please select a date.', 'danger')
                    return redirect(url_for('student.book_wizard'))
                
                # Save selected date and move to next step
                booking_data['session_date'] = session_date
                session['booking_data'] = booking_data
                session['booking_step'] = 4
                return redirect(url_for('student.book_wizard'))
            
            # Step 4: Time slot selection
            elif current_step == 4:
                time_slot = request.form.get('time_slot')
                current_app.logger.info(f"Selected time slot: {time_slot}")
                
                if not time_slot:
                    flash('Please select a time slot.', 'danger')
                    return redirect(url_for('student.book_wizard'))
                
                # Parse the time slot
                try:
                    start_time, end_time = time_slot.split(' - ')
                except ValueError:
                    flash('Invalid time slot format.', 'danger')
                    return redirect(url_for('student.book_wizard'))
                
                # Save selected time and move to confirmation step
                booking_data['start_time'] = start_time
                booking_data['end_time'] = end_time
                session['booking_data'] = booking_data
                session['booking_step'] = 5
                return redirect(url_for('student.book_wizard'))
            
            # Step 5: Confirmation and booking creation
            elif current_step == 5:
                current_app.logger.info("Processing booking confirmation")
                
                # Get all booking data
                module_code = booking_data.get('module_code')
                tutor_id = booking_data.get('tutor_id')
                session_date = booking_data.get('session_date')
                start_time = booking_data.get('start_time')
                end_time = booking_data.get('end_time')
                
                # Validate all required fields
                if not all([module_code, tutor_id, session_date, start_time, end_time]):
                    flash('Missing booking information. Please start again.', 'danger')
                    # Reset booking wizard
                    session.pop('booking_step', None)
                    session.pop('booking_data', None)
                    return redirect(url_for('student.book_wizard'))
                
                # Create the booking
                try:
                    current_app.logger.info("Attempting to create booking")
                    
                    # Create reservation first
                    reservation_id = firebase_service.create_reservation(
                        student_id=current_user.id,
                        tutor_id=tutor_id,
                        module_code=module_code,
                        date=session_date,
                        start_time=start_time,
                        end_time=end_time
                    )
                    
                    if not reservation_id:
                        flash('Unable to reserve this session. The time slot may no longer be available.', 'danger')
                        return redirect(url_for('student.book_wizard'))
                    
                    # Confirm the reservation to create final booking
                    booking_id = firebase_service.confirm_reservation(reservation_id)
                    
                    if booking_id:
                        # Clear booking wizard data
                        session.pop('booking_step', None)
                        session.pop('booking_data', None)
                        
                        if booking_id.startswith(('demo-', 'fallback-', 'emergency-')):
                            flash('Your session has been booked (demo mode).', 'info')
                        else:
                            flash('Your tutoring session has been booked successfully!', 'success')
                        return redirect(url_for('student.home'))
                    else:
                        flash('Unable to confirm the booking. Please try again.', 'danger')
                        return redirect(url_for('student.book_wizard'))
                        
                except Exception as booking_error:
                    current_app.logger.error(f"Error creating booking: {str(booking_error)}")
                    current_app.logger.error(traceback.format_exc())
                    flash('An error occurred while booking your session. Please try again.', 'danger')
                    return redirect(url_for('student.book_wizard'))
        
        # Handle each step for GET requests
        try:
            # Step 1: Module selection
            if current_step == 1:
                current_app.logger.info("Loading modules for step 1")
                
                # Get all modules
                try:
                    modules = firebase_service.get_all_modules() or []
                    
                    # Normalize module data
                    for module in modules:
                        if 'code' not in module and 'module_code' in module:
                            module['code'] = module['module_code']
                        elif 'module_code' not in module and 'code' in module:
                            module['module_code'] = module['code']
                        
                        if 'name' not in module and 'module_name' in module:
                            module['name'] = module['module_name']
                        elif 'module_name' not in module and 'name' in module:
                            module['module_name'] = module['name']
                except Exception as e:
                    current_app.logger.error(f"Error retrieving modules: {str(e)}")
                    current_app.logger.error(traceback.format_exc())
                    error_occurred = True
                    error_message = "Failed to retrieve modules. Please try again."
            
            # Step 2: Tutor selection
            elif current_step == 2:
                module_code = booking_data.get('module_code')
                current_app.logger.info(f"Loading tutors for module {module_code}")
                
                if not module_code:
                    flash('Missing module selection. Please start again.', 'danger')
                    session.pop('booking_step', None)
                    session.pop('booking_data', None)
                    return redirect(url_for('student.book_wizard'))
                
                try:
                    # Get selected module details
                    selected_module = firebase_service.get_module(module_code)
                    if not selected_module:
                        selected_module = {
                            'id': module_code,
                            'code': module_code,
                            'module_code': module_code,
                            'name': f"Module {module_code}",
                            'module_name': f"Module {module_code}"
                        }
                    
                    # Get tutors for this module
                    module_tutors = firebase_service.get_module_tutors(module_code) or []
                    
                    if not module_tutors:
                        error_occurred = True
                        error_message = "No tutors found for this module. Please select a different module."
                        session['booking_step'] = 1
                        return redirect(url_for('student.book_wizard'))
                except Exception as e:
                    current_app.logger.error(f"Error loading tutors: {str(e)}")
                    current_app.logger.error(traceback.format_exc())
                    error_occurred = True
                    error_message = "Error retrieving tutors. Please try again."
                    session['booking_step'] = 1
                    return redirect(url_for('student.book_wizard'))
            
            # Step 3: Date selection
            elif current_step == 3:
                tutor_id = booking_data.get('tutor_id')
                module_code = booking_data.get('module_code')
                current_app.logger.info(f"Loading available dates for tutor {tutor_id}")
                
                if not tutor_id or not module_code:
                    flash('Missing required information. Please start again.', 'danger')
                    session.pop('booking_step', None)
                    session.pop('booking_data', None)
                    return redirect(url_for('student.book_wizard'))
                
                try:
                    # Get tutor details
                    tutor = firebase_service.get_user_by_id(tutor_id)
                    if not tutor:
                        flash('Selected tutor not found. Please start again.', 'danger')
                        session.pop('booking_step', None)
                        session.pop('booking_data', None)
                        return redirect(url_for('student.book_wizard'))
                    
                    # Generate dates for next 14 days
                    today = datetime.now().date()
                    available_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 15)]
                    
                    # Get selected module details for display
                    selected_module = firebase_service.get_module(module_code)
                    if not selected_module:
                        selected_module = {
                            'id': module_code,
                            'code': module_code,
                            'name': f"Module {module_code}"
                        }
                    
                    # Store tutor name for display
                    booking_data['tutor_name'] = tutor.get('name', 'Unknown Tutor')
                    booking_data['module_name'] = selected_module.get('name', selected_module.get('module_name', f"Module {module_code}"))
                    session['booking_data'] = booking_data
                    
                except Exception as e:
                    current_app.logger.error(f"Error loading dates: {str(e)}")
                    current_app.logger.error(traceback.format_exc())
                    error_occurred = True
                    error_message = "Error retrieving available dates. Please try again."
                    return redirect(url_for('student.book_wizard'))
            
            # Step 4: Time slot selection
            elif current_step == 4:
                tutor_id = booking_data.get('tutor_id')
                session_date = booking_data.get('session_date')
                current_app.logger.info(f"Loading time slots for tutor {tutor_id} on date {session_date}")
                
                if not tutor_id or not session_date:
                    flash('Missing required information. Please start again.', 'danger')
                    session.pop('booking_step', None)
                    session.pop('booking_data', None)
                    return redirect(url_for('student.book_wizard'))
                
                try:
                    # Parse the date
                    date_obj = datetime.strptime(session_date, '%Y-%m-%d').date()
                    
                    # Get available time slots
                    available_slots = firebase_service.get_tutor_schedule(tutor_id, date_obj)
                    
                    if not available_slots:
                        flash('No available time slots for this date. Please select another date.', 'info')
                        session['booking_step'] = 3
                        return redirect(url_for('student.book_wizard'))
                        
                except Exception as e:
                    current_app.logger.error(f"Error loading time slots: {str(e)}")
                    current_app.logger.error(traceback.format_exc())
                    error_occurred = True
                    error_message = "Error retrieving available time slots. Please try again."
                    return redirect(url_for('student.book_wizard'))
            
            # Step 5: Confirmation
            elif current_step == 5:
                # All data is already in booking_data, just need to prepare for display
                current_app.logger.info("Preparing confirmation page")
                
                # Ensure all required data is present
                required_fields = ['module_code', 'module_name', 'tutor_id', 'tutor_name', 
                                 'session_date', 'start_time', 'end_time']
                                 
                for field in required_fields:
                    if field not in booking_data:
                        flash('Missing booking information. Please start again.', 'danger')
                        session.pop('booking_step', None)
                        session.pop('booking_data', None)
                        return redirect(url_for('student.book_wizard'))
            
            # Invalid step - reset wizard
            else:
                session['booking_step'] = 1
                session['booking_data'] = {}
                return redirect(url_for('student.book_wizard'))
                
        except Exception as step_error:
            current_app.logger.error(f"Error processing step {current_step}: {str(step_error)}")
            current_app.logger.error(traceback.format_exc())
            flash('An error occurred. Please try again.', 'danger')
            session.pop('booking_step', None)
            session.pop('booking_data', None)
            return redirect(url_for('student.book_wizard'))
        
        # Render the appropriate template based on current step
        return render_template('student/book_wizard.html',
                             current_user=current_user,
                             current_step=current_step,
                             booking_data=booking_data,
                             modules=modules,
                             selected_module=selected_module,
                             module_tutors=module_tutors,
                             available_dates=available_dates,
                             available_slots=available_slots,
                             error_occurred=error_occurred,
                             error_message=error_message)
                             
    except Exception as e:
        current_app.logger.error(f"Unhandled error in book_wizard view: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        flash('An unexpected error occurred. Please try again later.', 'danger')
        # Reset booking wizard
        session.pop('booking_step', None)
        session.pop('booking_data', None)
        return redirect(url_for('student.home'))

# Reset wizard
@student_bp.route('/reset-booking')
@login_required
def reset_booking():
    """Reset the booking wizard"""
    session.pop('booking_step', None)
    session.pop('booking_data', None)
    flash('Booking wizard has been reset.', 'info')
    return redirect(url_for('student.book_wizard'))

@student_bp.route('/view-modules')
@login_required
def view_modules():
    """View modules page"""
    # Get module_id from query parameters (if any)
    module_id = request.args.get('module_id')
    
    # Get all modules
    modules = firebase_service.get_all_modules()
    
    # Get specific module details if module_id is provided
    selected_module = None
    module_tutors = []
    module_content = []
    
    if module_id:
        selected_module = firebase_service.get_module(module_id)
        if selected_module:
            module_tutors = firebase_service.get_module_tutors(module_id)
            module_content = firebase_service.get_module_content(module_id)
    
    return render_template('student/view_modules.html',
                          modules=modules,
                          selected_module=selected_module,
                          module_tutors=module_tutors,
                          module_content=module_content)

@student_bp.route('/view-content')
@login_required
def view_content():
    """View learning content"""
    # Get filter parameters
    module_filter = request.args.get('module', '')
    content_type_filter = request.args.get('content_type', '')
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # Get modules for filter dropdown
    modules = firebase_service.get_all_modules()
    
    # Get filtered content
    content_items, total_items = firebase_service.get_filtered_content(
        module_code=module_filter,
        content_type=content_type_filter,
        search_query=search_query,
        page=page,
        per_page=per_page
    )
    
    # Calculate pagination
    total_pages = (total_items + per_page - 1) // per_page
    
    return render_template('student/view_content.html',
                          modules=modules,
                          content_items=content_items,
                          current_page=page,
                          total_pages=total_pages)

@student_bp.route('/download-content/<content_id>')
@login_required
def download_content(content_id):
    """Download learning content"""
    # Get content details
    content = firebase_service.get_content(content_id)
    if not content:
        flash('Content not found.', 'danger')
        return redirect(url_for('student.view_content'))
    
    # Log download for analytics
    firebase_service.log_content_download(current_user.id, content_id)
    
    # Redirect to download URL
    return redirect(content.get('download_url', url_for('student.view_content')))

@student_bp.route('/view-session/<session_id>')
@login_required
def view_session(session_id):
    """View session details"""
    # Get session details
    session_data = firebase_service.get_session(session_id)
    if not session_data:
        flash('Session not found.', 'danger')
        return redirect(url_for('student.home'))
    
    # Check if the session belongs to the current user
    if session_data.get('student_id') != current_user.id:
        flash('You do not have permission to view this session.', 'danger')
        return redirect(url_for('student.home'))
    
    return render_template('student/view_session.html',
                          session=session_data)

@student_bp.route('/cancel-session/<session_id>', methods=['POST'])
@login_required
def cancel_session(session_id):
    """Cancel a booked session"""
    # Get session details
    session_data = firebase_service.get_session(session_id)
    if not session_data:
        flash('Session not found.', 'danger')
        return redirect(url_for('student.home'))
    
    # Check if the session belongs to the current user
    if session_data.get('student_id') != current_user.id:
        flash('You do not have permission to cancel this session.', 'danger')
        return redirect(url_for('student.home'))
    
    # Check if the session can be cancelled (e.g., not too close to start time)
    session_date = session_data.get('date')
    session_start_time = session_data.get('start_time')
    
    if session_date and session_start_time:
        # Convert to datetime object
        try:
            date_obj = datetime.strptime(session_date, '%Y-%m-%d').date()
            time_obj = datetime.strptime(session_start_time, '%H:%M').time()
            session_datetime = datetime.combine(date_obj, time_obj)
            
            # Check if session is within 24 hours
            if datetime.now() + timedelta(hours=24) > session_datetime:
                flash('Sessions can only be cancelled more than 24 hours in advance.', 'danger')
                return redirect(url_for('student.view_session', session_id=session_id))
        except ValueError:
            pass  # Continue with cancellation if date parsing fails
    
    # Cancel the session
    if firebase_service.cancel_session(session_id):
        flash('Session cancelled successfully.', 'success')
    else:
        flash('Failed to cancel the session. Please try again.', 'danger')
    
    return redirect(url_for('student.home'))

@student_bp.route('/submit-feedback', methods=['GET'])
@login_required
def submit_feedback():
    """View to submit feedback for completed sessions"""
    # Get session_id from query parameters (if any)
    session_id = request.args.get('session_id')
    
    # If session_id is provided, show the feedback form for that session
    session_to_review = None
    if session_id:
        session_to_review = firebase_service.get_session(session_id)
        
        # Check if the session belongs to the current user
        if not session_to_review or session_to_review.get('student_id') != current_user.id:
            flash('Invalid session selected.', 'danger')
            return redirect(url_for('student.submit_feedback'))
        
        # Check if feedback has already been submitted
        if session_to_review.get('has_feedback'):
            flash('You have already submitted feedback for this session.', 'info')
            return redirect(url_for('student.submit_feedback'))
    
    # Get past sessions for this student that don't have feedback yet
    past_sessions = firebase_service.get_student_past_sessions(current_user.id)
    
    return render_template('student/submit_feedback.html',
                          session_to_review=session_to_review,
                          past_sessions=past_sessions)

@student_bp.route('/submit-session-feedback/<session_id>', methods=['POST'])
@login_required
def submit_session_feedback(session_id):
    """Process feedback submission"""
    # Get session details
    session_data = firebase_service.get_session(session_id)
    if not session_data:
        flash('Session not found.', 'danger')
        return redirect(url_for('student.submit_feedback'))
    
    # Check if the session belongs to the current user
    if session_data.get('student_id') != current_user.id:
        flash('You do not have permission to submit feedback for this session.', 'danger')
        return redirect(url_for('student.submit_feedback'))
    
    # Check if feedback has already been submitted
    if session_data.get('has_feedback'):
        flash('You have already submitted feedback for this session.', 'info')
        return redirect(url_for('student.submit_feedback'))
    
    # Get form data
    rating = request.form.get('rating')
    feedback_text = request.form.get('feedback')
    was_helpful = request.form.get('was_helpful')
    improvement = request.form.get('improvement', '')
    
    # Validate required fields
    if not all([rating, feedback_text, was_helpful]):
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('student.submit_feedback', session_id=session_id))
    
    # Submit feedback
    if firebase_service.submit_feedback(
        session_id=session_id,
        student_id=current_user.id,
        tutor_id=session_data.get('tutor_id'),
        rating=int(rating),
        feedback=feedback_text,
        was_helpful=was_helpful,
        improvement=improvement
    ):
        flash('Feedback submitted successfully. Thank you!', 'success')
    else:
        flash('Failed to submit feedback. Please try again.', 'danger')
    
    return redirect(url_for('student.submit_feedback'))

@student_bp.route('/get-tutor-schedule')
@login_required
def get_tutor_schedule():
    """API endpoint to get available time slots for a tutor on a specific date"""
    tutor_id = request.args.get('tutor_id')
    date_str = request.args.get('date')
    
    if not tutor_id or not date_str:
        current_app.logger.error(f"Missing parameters: tutor_id={tutor_id}, date={date_str}")
        return jsonify({'error': 'Missing required parameters', 'success': False}), 400
    
    try:
        # Parse the date from string
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_app.logger.info(f"Parsed date: {date_obj} for tutor: {tutor_id}")
        
        # Get the tutor's schedule
        available_slots = firebase_service.get_tutor_schedule(tutor_id, date_obj)
        current_app.logger.info(f"Retrieved {len(available_slots)} slots for tutor {tutor_id}")
        
        return jsonify({
            'success': True,
            'schedule': available_slots
        })
    except ValueError as ve:
        current_app.logger.error(f"Invalid date format: {date_str}, error: {str(ve)}")
        return jsonify({'error': 'Invalid date format', 'success': False}), 400
    except Exception as e:
        current_app.logger.error(f"Error fetching tutor schedule: {str(e)}")
        return jsonify({'error': 'Failed to retrieve schedule', 'success': False}), 500

@student_bp.route('/quickbook', methods=['GET', 'POST'])
@login_required
def quickbook_redirect():
    """Redirect to quick-book route"""
    return redirect(url_for('student.quick_book'))
    
@student_bp.route('/quick-book', methods=['GET', 'POST'])
@login_required
def quick_book():
    """Quick booking page"""
    try:
        # Initialize variables
        modules = []
        selected_module = None
        module_tutors = []
        firebase_service = FirebaseService()
        today_date = datetime.today().strftime('%Y-%m-%d')
        
        # Check if we're coming from a specific module
        module_code = request.args.get('module_code')
        if module_code:
            print(f"Module code from query params: {module_code}")
        
        # For POST method (form submission)
        if request.method == 'POST':
            # Get form data
            module_code = request.form.get('module_code')
            tutor_id = request.form.get('tutor_id')
            session_date = request.form.get('session_date')
            time_slot = request.form.get('time_slot')
            notes = request.form.get('notes', '')
            
            # Validate required fields
            if not all([module_code, tutor_id, session_date, time_slot]):
                missing_fields = []
                if not module_code: missing_fields.append("Module")
                if not tutor_id: missing_fields.append("Tutor")
                if not session_date: missing_fields.append("Date")
                if not time_slot: missing_fields.append("Time Slot")
                
                flash(f"Missing required fields: {', '.join(missing_fields)}", "danger")
                return redirect(url_for('student.quick_book'))
            
            # Create booking
            try:
                booking_result = firebase_service.create_booking(
                    student_id=current_user.id,
                    tutor_id=tutor_id,
                    module_code=module_code,
                    session_date=session_date,
                    time_slot=time_slot,
                    notes=notes
                )
                
                if booking_result.get('success'):
                    flash("Session booking request submitted! You'll be notified when the tutor confirms.", "success")
                    return redirect(url_for('student.home'))
                else:
                    flash(f"Failed to book session: {booking_result.get('error', 'Unknown error')}", "danger")
            except Exception as e:
                print(f"Error creating booking: {str(e)}")
                flash("An error occurred while booking your session. Please try again.", "danger")
        
        # For GET method (displaying form)
        try:
            # Get all modules
            modules = firebase_service.get_all_modules()
            
            # If module_code is provided, get the selected module details
            if module_code:
                for module in modules:
                    if module.get('code') == module_code:
                        selected_module = module
                        break
                
                # If we have a selected module, get tutors for that module
                if selected_module:
                    module_tutors = firebase_service.get_module_tutors(module_code) or []
        except Exception as e:
            print(f"Error loading modules or tutors: {str(e)}")
            flash("Error loading modules. Using demo data instead.", "warning")
            
            # Use demo data if real data can't be loaded
            modules = [
                {"code": "DAST401", "name": "Data Structures"},
                {"code": "PBDE401", "name": "Platform Based Development"},
                {"code": "RESK401", "name": "Research Skills"}
            ]
            
            if module_code:
                selected_module = next((m for m in modules if m.get('code') == module_code), None)
                module_tutors = [
                    {"tutor_id": "tutor1", "name": "Dr. Smith"},
                    {"tutor_id": "tutor2", "name": "Prof. Johnson"}
                ]
        
        return render_template(
            'student/quick_book.html',
            modules=modules,
            selected_module=selected_module,
            module_tutors=module_tutors,
            today_date=today_date
        )
    except Exception as e:
        print(f"Unhandled error in quick_book route: {str(e)}")
        flash("An unexpected error occurred. Please try again later.", "danger")
        return redirect(url_for('student.home'))

@student_bp.route('/book', methods=['GET', 'POST'])
@login_required
def book_redirect():
    """Simple redirect to quick-book"""
    return redirect(url_for('student.quick_book'))

@student_bp.route('/api/tutors-by-module/<module_code>')
@login_required
def api_tutors_by_module(module_code):
    """API endpoint to get tutors for a specific module"""
    try:
        # Get tutors for this module
        tutors = firebase_service.get_module_tutors(module_code) or []
        
        # Return as JSON
        return jsonify({
            'success': True,
            'tutors': tutors
        })
    except Exception as e:
        current_app.logger.error(f"Error getting tutors for module {module_code}: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@student_bp.route('/quick-book-redirect')
@login_required
def quick_book_redirect():
    """Redirect to the new booking.quick route"""
    from flask import current_app
    current_app.logger.info("Redirecting from /student/quick-book-redirect to /student/booking/quick")
    return redirect(url_for('booking.quick'))

@student_bp.route('/view-bookings')
@login_required
def view_bookings():
    """View all bookings for the current student"""
    try:
        # Get all student bookings
        bookings = firebase_service.get_student_bookings(current_user.id)
        
        # If no bookings found, possibly provide demo data in development
        if not bookings:
            print(f"No bookings found for student {current_user.id}")
            # If in development, we might want to show demo bookings
            # This is handled by the get_student_bookings method

        # Separate bookings by status for easier template rendering
        pending_bookings = [b for b in bookings if b.get('status') == 'pending']
        confirmed_bookings = [b for b in bookings if b.get('status') == 'confirmed']
        completed_bookings = [b for b in bookings if b.get('status') == 'completed']
        cancelled_bookings = [b for b in bookings if b.get('status') == 'cancelled']
        
        return render_template('student/view_bookings.html',
                              bookings=bookings,
                              pending_bookings=pending_bookings,
                              confirmed_bookings=confirmed_bookings,
                              completed_bookings=completed_bookings,
                              cancelled_bookings=cancelled_bookings,
                              debug_mode=True)
    
    except Exception as e:
        print(f"Error in view_bookings: {str(e)}")
        flash("An error occurred while retrieving your bookings.", "danger")
        return redirect(url_for('student.home'))

@student_bp.route('/cancel-booking/<booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Cancel a booking"""
    try:
        # Check if the booking exists and belongs to the student
        booking = firebase_service.get_session(booking_id)
        if not booking:
            flash("Booking not found.", "danger")
            return redirect(url_for('student.view_bookings'))
        
        if booking.get('student_id') != current_user.id:
            flash("You don't have permission to cancel this booking.", "danger")
            return redirect(url_for('student.view_bookings'))
        
        # Only confirmed or pending bookings can be cancelled
        if booking.get('status') not in ['confirmed', 'pending']:
            flash("This booking cannot be cancelled.", "danger")
            return redirect(url_for('student.view_bookings'))
        
        # Cancel the booking
        success = firebase_service.update_session_status(booking_id, 'cancelled')
        if success:
            flash("Booking cancelled successfully.", "success")
        else:
            flash("Failed to cancel booking.", "danger")
        
        return redirect(url_for('student.view_bookings'))
    
    except Exception as e:
        print(f"Error in cancel_booking: {str(e)}")
        flash("An error occurred while cancelling your booking.", "danger")
        return redirect(url_for('student.view_bookings')) 