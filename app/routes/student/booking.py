from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, jsonify, session
from flask_login import login_required, current_user
from app.services.firebase_service import FirebaseService
from datetime import datetime, timedelta
import traceback

# Create a booking blueprint without a prefix (prefix is applied in app/__init__.py)
booking_bp = Blueprint('booking', __name__)
firebase_service = FirebaseService()

@booking_bp.route('/test')
def test_route():
    """Simple test route to verify the blueprint is working"""
    return "Booking blueprint test route is working"

@booking_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Main booking page - redirects to quick book"""
    return redirect(url_for('booking.quick'))

@booking_bp.route('/quick', methods=['GET', 'POST'])
@login_required
def quick():
    """Simple one-page booking form"""
    try:
        # Initialize variables
        modules = []
        selected_module = None
        error_occurred = False
        error_message = None
        
        # Get module_code from query parameters (if any)
        module_code = request.args.get('module_code')
        
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
            error_message = "Failed to retrieve modules. Using demo data."
            modules = firebase_service._get_demo_modules()
        
        # Get selected module details if module_code is provided
        if module_code:
            selected_module = next((m for m in modules if m.get('code') == module_code or m.get('module_code') == module_code), None)
            if not selected_module:
                selected_module = firebase_service.get_module(module_code)
        
        # Handle form submission
        if request.method == 'POST':
            current_app.logger.info("Processing POST request for quick booking")
            
            # Get form data
            form_data = request.form.to_dict()
            current_app.logger.info(f"Received form data: {form_data}")
            
            module_code = form_data.get('module_code')
            tutor_id = form_data.get('tutor_id')
            session_date = form_data.get('session_date')
            time_slot = form_data.get('time_slot')
            notes = form_data.get('notes', '')
            
            # Validate required fields
            if not all([module_code, tutor_id, session_date, time_slot]):
                missing = []
                if not module_code: missing.append("module")
                if not tutor_id: missing.append("tutor") 
                if not session_date: missing.append("date")
                if not time_slot: missing.append("time slot")
                
                error_msg = f'Please select a {" and ".join(missing)}.'
                current_app.logger.warning(f"Missing required fields: {error_msg}")
                flash(error_msg, 'danger')
                return redirect(url_for('booking.quick'))
            
            # Parse the time slot
            try:
                start_time, end_time = time_slot.split(' - ')
                current_app.logger.info(f"Parsed time slot: start={start_time}, end={end_time}")
            except ValueError as e:
                current_app.logger.error(f"Invalid time slot format: {time_slot}, error: {str(e)}")
                flash('Invalid time slot format.', 'danger')
                return redirect(url_for('booking.quick'))
            
            # Create a reservation and confirm it immediately
            try:
                current_app.logger.info("Attempting direct booking")
                
                # Create reservation first
                reservation_id = firebase_service.create_reservation(
                    student_id=current_user.id,
                    tutor_id=tutor_id,
                    module_code=module_code,
                    date=session_date,
                    start_time=start_time,
                    end_time=end_time,
                    notes=notes
                )
                
                if not reservation_id:
                    flash('Unable to book this session. The time slot may no longer be available.', 'danger')
                    return redirect(url_for('booking.quick'))
                
                # Confirm the reservation to create final booking
                booking_id = firebase_service.confirm_reservation(reservation_id)
                
                if booking_id:
                    if booking_id.startswith(('demo-', 'fallback-', 'emergency-')):
                        flash('Your session has been booked (demo mode).', 'info')
                    else:
                        flash('Your tutoring session has been booked successfully!', 'success')
                    return redirect(url_for('student.home'))
                else:
                    flash('Unable to confirm the booking. Please try again.', 'danger')
                    return redirect(url_for('booking.quick'))
                    
            except Exception as booking_error:
                current_app.logger.error(f"Error creating booking: {str(booking_error)}")
                current_app.logger.error(traceback.format_exc())
                flash('An error occurred while booking your session. Please try again.', 'danger')
                return redirect(url_for('booking.quick'))
        
        # Get today's date for the date picker
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('student/quick_book.html',
                             current_user=current_user,
                             modules=modules,
                             selected_module=selected_module,
                             today_date=today_date,
                             error_occurred=error_occurred,
                             error_message=error_message)
    
    except Exception as e:
        current_app.logger.error(f"Unhandled error in booking.quick view: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        flash('An unexpected error occurred. Please try again later.', 'danger')
        return redirect(url_for('student.home'))

@booking_bp.route('/api/tutors-by-module/<module_code>')
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

@booking_bp.route('/api/time-slots')
@login_required
def get_time_slots():
    """API endpoint to get available time slots for a tutor on a specific date"""
    try:
        tutor_id = request.args.get('tutor_id')
        date = request.args.get('date')
        
        if not tutor_id or not date:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
            
        # Get available slots from Firebase
        schedule = firebase_service.get_tutor_availability(tutor_id, date) or []
        
        # If no slots available in real data, return demo slots
        if not schedule or len(schedule) == 0:
            current_app.logger.info(f"No real slots available, using demo data for tutor {tutor_id} on {date}")
            # Generate demo time slots
            demo_slots = [
                "09:00 - 10:00",
                "10:00 - 11:00",
                "11:00 - 12:00",
                "13:00 - 14:00",
                "14:00 - 15:00",
                "15:00 - 16:00"
            ]
            schedule = demo_slots
        
        return jsonify({
            'success': True,
            'schedule': schedule
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting time slots: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@booking_bp.route('/wizard', methods=['GET', 'POST'])
@login_required
def wizard():
    """Multi-step booking wizard"""
    # Redirect to the step-by-step wizard
    return redirect(url_for('student.book_wizard')) 