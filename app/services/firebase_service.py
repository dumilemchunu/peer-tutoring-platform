from firebase_admin import firestore
from datetime import datetime

class FirebaseService:
    def __init__(self):
        self.db = firestore.client()

    # Booking related operations
    def create_booking(self, student_id, tutor_id, module_code, date, time_slot):
        booking_ref = self.db.collection('bookings').document()
        booking_data = {
            'student_id': student_id,
            'tutor_id': tutor_id,
            'module_code': module_code,
            'date': date,
            'time_slot': time_slot,
            'status': 'pending',
            'created_at': datetime.now()
        }
        booking_ref.set(booking_data)
        return booking_ref.id

    def get_tutor_bookings(self, tutor_id):
        bookings = self.db.collection('bookings').where('tutor_id', '==', tutor_id).stream()
        return [{'id': booking.id, **booking.to_dict()} for booking in bookings]

    def get_student_bookings(self, student_id):
        bookings = self.db.collection('bookings').where('student_id', '==', student_id).stream()
        return [{'id': booking.id, **booking.to_dict()} for booking in bookings]

    # Feedback related operations
    def submit_feedback(self, student_id, tutor_id, booking_id, rating, comment):
        feedback_ref = self.db.collection('feedback').document()
        feedback_data = {
            'student_id': student_id,
            'tutor_id': tutor_id,
            'booking_id': booking_id,
            'rating': rating,
            'comment': comment,
            'created_at': datetime.now()
        }
        feedback_ref.set(feedback_data)
        return feedback_ref.id

    def get_tutor_feedback(self, tutor_id):
        feedback = self.db.collection('feedback').where('tutor_id', '==', tutor_id).stream()
        return [{'id': feedback.id, **feedback.to_dict()} for feedback in feedback]

    # Content management operations
    def upload_content(self, content_data, module_code, title, description, tutor_id):
        content_ref = self.db.collection('content').document()
        content_data = {
            'title': title,
            'description': description,
            'module_code': module_code,
            'tutor_id': tutor_id,
            'content': content_data,  # Store content directly in Firestore
            'uploaded_at': datetime.now()
        }
        content_ref.set(content_data)
        return content_ref.id

    def get_module_content(self, module_code):
        content = self.db.collection('content').where('module_code', '==', module_code).stream()
        return [{'id': content.id, **content.to_dict()} for content in content]

    # Module management operations
    def add_module(self, module_code, module_name, description):
        module_ref = self.db.collection('modules').document(module_code)
        module_data = {
            'module_code': module_code,
            'module_name': module_name,
            'description': description,
            'created_at': datetime.now()
        }
        module_ref.set(module_data)
        return module_code

    def get_all_modules(self):
        modules = self.db.collection('modules').stream()
        return [{'id': module.id, **module.to_dict()} for module in modules]

    # Tutor availability operations
    def set_tutor_availability(self, tutor_id, availabilities):
        availability_ref = self.db.collection('availabilities').document(tutor_id)
        availability_data = {
            'tutor_id': tutor_id,
            'schedules': availabilities,
            'updated_at': datetime.now()
        }
        availability_ref.set(availability_data)
        return tutor_id

    def get_tutor_availability(self, tutor_id):
        availability = self.db.collection('availabilities').document(tutor_id).get()
        return availability.to_dict() if availability.exists else None 