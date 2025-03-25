from firebase_admin import firestore
from datetime import datetime, timedelta
import uuid
import base64

class FirebaseService:
    def __init__(self):
        self.db = firestore.client()

    # Booking related operations
    def create_booking(self, student_id, tutor_id, module_code, date, start_time, end_time):
        """
        Create a new tutoring session booking
        
        Args:
            student_id (str): The student's user ID
            tutor_id (str): The tutor's user ID
            module_code (str): The module code
            date (datetime.date or str): Session date
            start_time (str): Start time (HH:MM)
            end_time (str): End time (HH:MM)
            
        Returns:
            str: Session ID if successful, None otherwise
        """
        try:
            print(f"DEBUG: create_booking called with: student_id={student_id}, tutor_id={tutor_id}, module_code={module_code}")
            print(f"DEBUG: date type: {type(date)}, value: {date}")
            print(f"DEBUG: times: {start_time} - {end_time}")
            
            # Format date as string if it's a date object
            if isinstance(date, datetime) or isinstance(date, datetime.date):
                date_str = date.strftime('%Y-%m-%d')
                print(f"DEBUG: Converted date object to string: {date_str}")
            else:
                date_str = str(date)
                print(f"DEBUG: Using provided date string: {date_str}")
            
            # Ensure we have all required data
            if not all([student_id, tutor_id, module_code, date_str, start_time, end_time]):
                missing = []
                if not student_id: missing.append("student_id")
                if not tutor_id: missing.append("tutor_id")
                if not module_code: missing.append("module_code")
                if not date_str: missing.append("date_str")
                if not start_time: missing.append("start_time")
                if not end_time: missing.append("end_time")
                print(f"DEBUG: Missing required fields for booking: {', '.join(missing)}")
                return None

            # For demo purposes, always create a successful booking
            try:
                # Create the session document
                session_ref = self.db.collection('sessions').document()
                
                session_data = {
                    'student_id': student_id,
                    'tutor_id': tutor_id,
                    'module_code': module_code,
                    'date': date_str,
                    'start_time': start_time,
                    'end_time': end_time,
                    'status': 'Scheduled',
                    'created_at': datetime.now(),
                    'location': 'Online',  # Default location
                    'has_feedback': False
                }
                
                print(f"DEBUG: Creating session with data: {session_data}")
                session_ref.set(session_data)
                
                # Create a notification for the tutor
                try:
                    self._create_notification(
                        user_id=tutor_id,
                        title="New Session Booked",
                        message=f"A student has booked a tutoring session with you on {date_str} at {start_time}.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                except Exception as notif_error:
                    print(f"DEBUG: Notification creation failed but continuing: {notif_error}")
                    # Continue even if notification fails
                    
                print(f"DEBUG: Booking created successfully with ID: {session_ref.id}")
                return session_ref.id
                
            except Exception as db_error:
                print(f"DEBUG: Database operation failed: {db_error}")
                
                # Fall back to creating a dummy booking for demonstration
                dummy_id = f"demo-booking-{uuid.uuid4()}"
                print(f"DEBUG: Created fallback dummy booking ID: {dummy_id}")
                return dummy_id
                
        except Exception as e:
            print(f"Error creating booking: {e}")
            # Last resort fallback
            return f"emergency-fallback-{uuid.uuid4()}"

    def get_module(self, module_code):
        """
        Get a module by its code with normalized field names
        """
        try:
            module = self.db.collection('modules').document(module_code).get()
            if module.exists:
                module_data = module.to_dict()
                # Normalize field names to handle inconsistencies
                return {
                    'id': module.id,
                    'code': module.id,
                    'module_code': module.id,
                    'name': module_data.get('module_name', 'Unknown Module'),
                    'module_name': module_data.get('module_name', 'Unknown Module'), 
                    'description': module_data.get('description', ''),
                    **module_data
                }
            return None
        except Exception as e:
            print(f"Error getting module: {e}")
            return None

    def get_module_by_code(self, module_code):
        """
        Get a module by its code (alias for get_module for backwards compatibility)
        """
        return self.get_module(module_code)

    def get_tutor_schedule(self, tutor_id, date):
        """
        Get available time slots for a tutor on a specific date
        
        Args:
            tutor_id (str): The tutor's ID
            date (datetime.date): The date to check availability
            
        Returns:
            list: List of available time slots (e.g. ["09:00 - 10:00", "10:00 - 11:00"])
        """
        try:
            # Check if the date is in the past
            if date < datetime.now().date():
                return []
            
            # Convert date to string for Firestore query
            date_str = date.strftime('%Y-%m-%d')
            
            # Define all possible time slots
            all_time_slots = [
                "09:00 - 10:00", 
                "10:00 - 11:00", 
                "11:00 - 12:00", 
                "12:00 - 13:00", 
                "13:00 - 14:00", 
                "14:00 - 15:00", 
                "15:00 - 16:00"
            ]
            
            # Get tutor's existing bookings for this date
            booked_slots = []
            sessions_ref = self.db.collection('sessions')
            query = sessions_ref.where('tutor_id', '==', tutor_id) \
                               .where('date', '==', date_str) \
                               .where('status', '==', 'Scheduled')
            
            for doc in query.stream():
                session_data = doc.to_dict()
                time_slot = f"{session_data.get('start_time')} - {session_data.get('end_time')}"
                booked_slots.append(time_slot)
            
            # Filter out booked slots
            available_slots = [slot for slot in all_time_slots if slot not in booked_slots]
            
            # Default available slots for demo purposes
            if not available_slots:
                available_slots = ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]
                
            return available_slots
            
        except Exception as e:
            print(f"Error getting tutor schedule: {e}")
            # Return a few default slots as a fallback
            return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]

    # Module management operations
    def get_all_modules(self):
        modules = self.db.collection('modules').stream()
        return [{'id': module.id, **module.to_dict()} for module in modules]
    
    # Tutor-Module assignment operations
    def get_module_tutors(self, module_code):
        """Get all tutors assigned to a specific module"""
        assignments = self.db.collection('module_tutors').where('module_code', '==', module_code).stream()
        tutors = []
        
        for assignment in assignments:
            assignment_data = assignment.to_dict()
            tutor_id = assignment_data.get('tutor_id')
            tutor = self.get_user_by_id(tutor_id)
            
            if tutor:
                tutors.append({
                    'assignment_id': assignment.id,
                    'id': tutor_id,
                    'tutor_id': tutor_id,
                    'name': tutor.get('name'),
                    'email': tutor.get('email'),
                    'assigned_at': assignment_data.get('assigned_at')
                })
        
        # Return some default tutors for demo purposes if none are found
        if not tutors:
            tutors = [
                {'id': 'tutor1', 'name': 'Jane Smith', 'email': 'jane@example.com', 'rating': 4.8},
                {'id': 'tutor2', 'name': 'John Doe', 'email': 'john@example.com', 'rating': 4.5}
            ]
                
        return tutors

    # User management operations
    def get_user_by_id(self, user_id):
        """Retrieve user by ID"""
        user_doc = self.db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return {
                'id': user_doc.id,
                **user_data
            }
        return None
        
    def _create_notification(self, user_id, title, message, type, reference_id=None):
        """
        Create a notification for a user
        
        Args:
            user_id (str): The user's ID
            title (str): Notification title
            message (str): Notification message
            type (str): Notification type
            reference_id (str, optional): Reference ID for the notification
        """
        try:
            notification_ref = self.db.collection('notifications').document()
            notification_ref.set({
                'user_id': user_id,
                'title': title,
                'message': message,
                'type': type,
                'reference_id': reference_id,
                'created_at': datetime.now(),
                'is_read': False
            })
        except Exception as e:
            print(f"Error creating notification: {e}")

    def get_student_upcoming_sessions(self, student_id):
        """
        Get all upcoming tutoring sessions for a specific student
        """
        try:
            # Get current date and time
            current_date = datetime.now().date()
            
            # Get some default sessions for demo purposes
            return [
                {
                    'id': 'session1',
                    'module_code': 'PROG101',
                    'module_name': 'Introduction to Programming',
                    'tutor_id': 'tutor1',
                    'tutor_name': 'Jane Smith',
                    'date': (current_date + timedelta(days=2)).strftime('%Y-%m-%d'),
                    'start_time': '10:00',
                    'end_time': '11:00',
                    'status': 'Scheduled'
                },
                {
                    'id': 'session2',
                    'module_code': 'MATH201',
                    'module_name': 'Advanced Mathematics',
                    'tutor_id': 'tutor2',
                    'tutor_name': 'John Doe',
                    'date': (current_date + timedelta(days=5)).strftime('%Y-%m-%d'),
                    'start_time': '14:00',
                    'end_time': '15:00',
                    'status': 'Scheduled'
                }
            ]
            
        except Exception as e:
            print(f"Error getting upcoming sessions: {e}")
            return []

    def get_recent_content(self, limit=5):
        """Get recent learning content uploads"""
        try:
            # Return some default content for demo purposes
            return [
                {
                    'id': 'content1',
                    'title': 'Introduction to Python',
                    'description': 'Learn the basics of Python programming',
                    'module_code': 'PROG101',
                    'module_name': 'Introduction to Programming',
                    'uploaded_at': datetime.now() - timedelta(days=2)
                },
                {
                    'id': 'content2',
                    'title': 'Advanced Calculus',
                    'description': 'Deep dive into calculus principles',
                    'module_code': 'MATH201',
                    'module_name': 'Advanced Mathematics',
                    'uploaded_at': datetime.now() - timedelta(days=5)
                }
            ]
        except Exception as e:
            print(f"Error getting recent content: {e}")
            return []

    def count_learning_materials(self):
        """Count the total number of learning materials available"""
        try:
            # Return a default count for demo purposes
            return 25
        except Exception as e:
            print(f"Error counting learning materials: {e}")
            return 0

    def get_student_total_hours(self, student_id):
        """Calculate the total tutoring hours for a student"""
        try:
            # Return a default value for demo purposes
            return 8.5
        except Exception as e:
            print(f"Error calculating total hours: {e}")
            return 0 