from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService
from app import db

student_bp = Blueprint('student', __name__)
firebase_service = FirebaseService()

@student_bp.route('/home')
@login_required
def home():
    if not current_user.is_student:
        flash('Access denied. You must be a student to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get student's bookings and available modules
    bookings = firebase_service.get_student_bookings(current_user.id)
    modules = firebase_service.get_all_modules()
    
    return render_template('student/student_home.html',
                         bookings=bookings,
                         modules=modules)

@student_bp.route('/book-tutor', methods=['GET', 'POST'])
@login_required
def book_tutor():
    if not current_user.is_student:
        flash('Access denied. You must be a student to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        tutor_id = request.form.get('tutor_id')
        module_code = request.form.get('module_code')
        date = request.form.get('date')
        time_slot = request.form.get('time_slot')
        
        try:
            firebase_service.create_booking(
                student_id=current_user.id,
                tutor_id=tutor_id,
                module_code=module_code,
                date=date,
                time_slot=time_slot
            )
            flash('Booking request submitted successfully', 'success')
        except Exception as e:
            flash(f'Error creating booking: {str(e)}', 'error')
        
        return redirect(url_for('student.home'))
    
    # Get available modules and tutors
    modules = firebase_service.get_all_modules()
    return render_template('student/Book_tutor.html',
                         modules=modules)

@student_bp.route('/submit-feedback', methods=['GET', 'POST'])
@login_required
def submit_feedback():
    if not current_user.is_student:
        flash('Access denied. You must be a student to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        booking_id = request.form.get('booking_id')
        tutor_id = request.form.get('tutor_id')
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        
        try:
            firebase_service.submit_feedback(
                student_id=current_user.id,
                tutor_id=tutor_id,
                booking_id=booking_id,
                rating=rating,
                comment=comment
            )
            flash('Feedback submitted successfully', 'success')
        except Exception as e:
            flash(f'Error submitting feedback: {str(e)}', 'error')
        
        return redirect(url_for('student.home'))
    
    # Get student's completed bookings for feedback
    bookings = firebase_service.get_student_bookings(current_user.id)
    completed_bookings = [b for b in bookings if b.get('status') == 'completed']
    
    return render_template('student/submit_feedback.html',
                         completed_bookings=completed_bookings) 