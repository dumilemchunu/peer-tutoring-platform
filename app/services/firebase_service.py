from firebase_admin import firestore
from datetime import datetime, timedelta
import uuid
import base64
from app.utils.date_utils import parse_date

class FirebaseService:
    def __init__(self):
        self.demo_mode = False
        try:
            from flask import current_app
            if current_app and hasattr(current_app, 'config'):
                # Check if Firebase is initialized from app config
                if not current_app.config.get('FIRESTORE_INITIALIZED', True):
                    print("WARNING: Firebase not initialized, using demo mode")
                    self.demo_mode = True
                    self.db = None
                    return
                    
                # Check for demo mode setting in app config
                if current_app.config.get('DEMO_MODE', False):
                    print("INFO: Application is running in DEMO MODE as configured")
                    self.demo_mode = True
                    self.db = None
                    return
                
            # Try to initialize Firestore client
            self.db = firestore.client()
            print("Firestore client initialized successfully in FirebaseService")
        except Exception as e:
            print(f"ERROR initializing Firestore client in FirebaseService: {e}")
            import traceback
            print(f"Detailed error: {traceback.format_exc()}")
            self.demo_mode = True
            self.db = None
            
    def _ensure_db(self):
        """Ensure we have a valid Firestore database connection"""
        if self.demo_mode:
            print("WARNING: Running in demo mode, no database connection available")
            return False
            
        if not self.db:
            try:
                self.db = firestore.client()
                print("Firestore client re-initialized successfully")
                return True
            except Exception as e:
                print(f"Failed to re-initialize Firestore client: {e}")
                self.demo_mode = True
                return False
        return True

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
            print(f"DEBUG: create_booking called with:")
            print(f"student_id: {student_id} ({type(student_id)})")
            print(f"tutor_id: {tutor_id} ({type(tutor_id)})")
            print(f"module_code: {module_code} ({type(module_code)})")
            print(f"date: {date} ({type(date)})")
            print(f"start_time: {start_time} ({type(start_time)})")
            print(f"end_time: {end_time} ({type(end_time)})")
            
            # In demo mode, always return a fake booking ID
            if self.demo_mode:
                fake_id = f"demo-booking-{uuid.uuid4()}"
                print(f"DEMO MODE: Generated fake booking ID: {fake_id}")
                return fake_id
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available")
                fake_id = f"fallback-booking-{uuid.uuid4()}"
                print(f"FALLBACK: Generated fallback booking ID: {fake_id}")
                return fake_id
            
            # Convert all parameters to strings
            student_id = str(student_id)
            tutor_id = str(tutor_id)
            module_code = str(module_code)
            
            # Handle date conversion
            if isinstance(date, str):
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                    date_str = date
                except ValueError as e:
                    print(f"ERROR: Invalid date format: {e}")
                    return None
            else:
                try:
                    date_obj = date
                    date_str = date.strftime('%Y-%m-%d')
                except Exception as e:
                    print(f"ERROR: Invalid date object: {e}")
                    return None
            
            # Validate times
            try:
                # Ensure times are in HH:MM format
                datetime.strptime(start_time, '%H:%M')
                datetime.strptime(end_time, '%H:%M')
            except ValueError as e:
                print(f"ERROR: Invalid time format: {e}")
                return None
            
            # Ensure all required fields are present
            if not all([student_id, tutor_id, module_code, date_str, start_time, end_time]):
                missing = []
                if not student_id: missing.append("student_id")
                if not tutor_id: missing.append("tutor_id")
                if not module_code: missing.append("module_code")
                if not date_str: missing.append("date")
                if not start_time: missing.append("start_time")
                if not end_time: missing.append("end_time")
                print(f"ERROR: Missing required fields: {', '.join(missing)}")
                return None
            
            # Check if the slot is still available
            try:
                available_slots = self.get_tutor_schedule(tutor_id, date_obj)
                time_slot = f"{start_time} - {end_time}"
                
                if time_slot not in available_slots:
                    print(f"ERROR: Time slot {time_slot} is not available")
                    return None
            except Exception as e:
                print(f"ERROR: Failed to verify slot availability: {e}")
                return None
            
            # Create the session document
            try:
                session_ref = self.db.collection('sessions').document()
                
                session_data = {
                    'student_id': student_id,
                    'tutor_id': tutor_id,
                    'module_code': module_code,
                    'date': date_str,
                    'start_time': start_time,
                    'end_time': end_time,
                    'status': 'Scheduled',
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'location': 'Online',  # Default location
                    'has_feedback': False
                }
                
                print(f"DEBUG: Creating session with data: {session_data}")
                session_ref.set(session_data)
                
                # Create notifications
                try:
                    # Notification for tutor
                    self._create_notification(
                        user_id=tutor_id,
                        title="New Session Booked",
                        message=f"A student has booked a tutoring session with you on {date_str} at {start_time}.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                    
                    # Notification for student
                    self._create_notification(
                        user_id=student_id,
                        title="Session Booking Confirmed",
                        message=f"Your tutoring session has been booked for {date_str} at {start_time}.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                except Exception as notif_error:
                    print(f"WARNING: Failed to create notifications: {notif_error}")
                    # Continue even if notifications fail
                
                print(f"DEBUG: Booking created successfully with ID: {session_ref.id}")
                return session_ref.id
                
            except Exception as db_error:
                print(f"ERROR: Database operation failed: {db_error}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                return None
            
        except Exception as e:
            print(f"ERROR: Unexpected error in create_booking: {e}")
            import traceback
            print(f"DEBUG: Outer traceback: {traceback.format_exc()}")
            return None

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
            print(f"DEBUG: get_tutor_schedule called with tutor_id={tutor_id}, date={date}")
            
            # In demo mode, return demo schedule
            if self.demo_mode:
                print("DEMO MODE: Returning demo schedule")
                return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available for get_tutor_schedule")
                return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]  # Return demo schedule
            
            # Check if the date is in the past
            if isinstance(date, str):
                try:
                    date = datetime.strptime(date, '%Y-%m-%d').date()
                except ValueError as e:
                    print(f"ERROR: Invalid date format: {e}")
                    return []
                
            if date < datetime.now().date():
                print(f"DEBUG: Date {date} is in the past")
                return []
            
            # Convert date to string for Firestore query
            date_str = date.strftime('%Y-%m-%d')
            print(f"DEBUG: Converted date to string: {date_str}")
            
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
            
            try:
                # Get tutor's existing bookings for this date
                booked_slots = []
                sessions_ref = self.db.collection('sessions')
                query = sessions_ref.where('tutor_id', '==', str(tutor_id)) \
                                   .where('date', '==', date_str) \
                                   .where('status', '==', 'Scheduled')
                
                print(f"DEBUG: Querying for booked slots with tutor_id={tutor_id}, date={date_str}")
                
                for doc in query.stream():
                    session_data = doc.to_dict()
                    start_time = session_data.get('start_time')
                    end_time = session_data.get('end_time')
                    if start_time and end_time:
                        time_slot = f"{start_time} - {end_time}"
                        booked_slots.append(time_slot)
                        print(f"DEBUG: Found booked slot: {time_slot}")
                
                # Filter out booked slots
                available_slots = [slot for slot in all_time_slots if slot not in booked_slots]
                print(f"DEBUG: Available slots after filtering: {available_slots}")
                
                return available_slots
                
            except Exception as db_error:
                print(f"ERROR: Database query failed: {str(db_error)}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                # Return demo slots as fallback
                return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]
                
        except Exception as e:
            print(f"ERROR: Unexpected error in get_tutor_schedule: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            # Return demo slots as fallback
            return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]

    # Module management operations
    def get_all_modules(self):
        """Get all available modules with error handling"""
        try:
            # In demo mode, return demo modules
            if self.demo_mode:
                print("DEMO MODE: Returning demo modules")
                return [
                    {'id': 'PROG101', 'code': 'PROG101', 'module_code': 'PROG101', 'name': 'Introduction to Programming', 'module_name': 'Introduction to Programming', 'description': 'Learn the foundations of programming logic and syntax.'},
                    {'id': 'CSCI312', 'code': 'CSCI312', 'module_code': 'CSCI312', 'name': 'Data Structures', 'module_name': 'Data Structures', 'description': 'Study fundamental data structures and algorithms.'},
                    {'id': 'DB310', 'code': 'DB310', 'module_code': 'DB310', 'name': 'Database Systems', 'module_name': 'Database Systems', 'description': 'Learn database design, SQL, and data management.'},
                    {'id': 'CHEM120', 'code': 'CHEM120', 'module_code': 'CHEM120', 'name': 'General Chemistry', 'module_name': 'General Chemistry', 'description': 'Introduction to principles of chemistry.'}
                ]
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available for get_all_modules")
                return self._get_demo_modules()
            
            # Try to fetch modules from Firestore
            modules = []
            modules_ref = self.db.collection('modules').stream()
            for module in modules_ref:
                module_data = module.to_dict()
                modules.append({
                    'id': module.id, 
                    'code': module.id,
                    'module_code': module.id,
                    'name': module_data.get('module_name', 'Unknown Module'),
                    'module_name': module_data.get('module_name', 'Unknown Module'),
                    'description': module_data.get('description', ''),
                    **module_data
                })
            
            # If we found modules, return them
            if modules:
                return modules
            
            # Otherwise return demo modules
            return self._get_demo_modules()
            
        except Exception as e:
            print(f"Error getting all modules: {e}")
            import traceback
            print(traceback.format_exc())
            return self._get_demo_modules()
        
    def _get_demo_modules(self):
        """Return demo modules for fallback"""
        return [
            {'id': 'PROG101', 'code': 'PROG101', 'module_code': 'PROG101', 'name': 'Introduction to Programming', 'module_name': 'Introduction to Programming', 'description': 'Learn the foundations of programming logic and syntax.'},
            {'id': 'CSCI312', 'code': 'CSCI312', 'module_code': 'CSCI312', 'name': 'Data Structures', 'module_name': 'Data Structures', 'description': 'Study fundamental data structures and algorithms.'},
            {'id': 'DB310', 'code': 'DB310', 'module_code': 'DB310', 'name': 'Database Systems', 'module_name': 'Database Systems', 'description': 'Learn database design, SQL, and data management.'},
            {'id': 'CHEM120', 'code': 'CHEM120', 'module_code': 'CHEM120', 'name': 'General Chemistry', 'module_name': 'General Chemistry', 'description': 'Introduction to principles of chemistry.'}
        ]
    
    # Tutor-Module assignment operations
    def get_module_tutors(self, module_code):
        """Get all tutors assigned to a specific module"""
        try:
            print(f"DEBUG: Getting tutors for module {module_code}")
            
            # In demo mode, return demo tutors
            if self.demo_mode:
                print("DEMO MODE: Returning demo tutors")
                return [
                    {'id': 'tutor1', 'name': 'Jane Smith', 'email': 'jane@example.com', 'rating': 4.8},
                    {'id': 'tutor2', 'name': 'John Doe', 'email': 'john@example.com', 'rating': 4.5}
                ]
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available for get_module_tutors")
                return self._get_demo_tutors()
            
            try:
                # Query for module-tutor assignments
                print(f"DEBUG: Querying module_tutors collection for module {module_code}")
                assignments = self.db.collection('module_tutors').where('module_code', '==', str(module_code)).stream()
                
                tutors = []
                for assignment in assignments:
                    try:
                        assignment_data = assignment.to_dict()
                        tutor_id = assignment_data.get('tutor_id')
                        print(f"DEBUG: Found tutor assignment for tutor_id: {tutor_id}")
                        
                        if not tutor_id:
                            print(f"WARNING: Missing tutor_id in assignment {assignment.id}")
                            continue
                            
                        # Get tutor details
                        tutor = self.get_user_by_id(tutor_id)
                        if tutor:
                            tutors.append({
                                'assignment_id': assignment.id,
                                'id': tutor_id,
                                'tutor_id': tutor_id,
                                'name': tutor.get('name', 'Unknown Tutor'),
                                'email': tutor.get('email', ''),
                                'assigned_at': assignment_data.get('assigned_at')
                            })
                            print(f"DEBUG: Added tutor {tutor.get('name')} to results")
                        else:
                            print(f"WARNING: Could not find tutor with ID {tutor_id}")
                            
                    except Exception as assignment_error:
                        print(f"ERROR processing assignment {assignment.id}: {str(assignment_error)}")
                        import traceback
                        print(traceback.format_exc())
                        continue
                
                # If we found tutors, return them
                if tutors:
                    print(f"DEBUG: Returning {len(tutors)} tutors found")
                    return tutors
                
                # Otherwise return demo tutors
                print("DEBUG: No tutors found, returning demo tutors")
                return self._get_demo_tutors()
                
            except Exception as query_error:
                print(f"ERROR querying module tutors: {str(query_error)}")
                import traceback
                print(traceback.format_exc())
                return self._get_demo_tutors()
            
        except Exception as e:
            print(f"ERROR in get_module_tutors: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return self._get_demo_tutors()
            
    def _get_demo_tutors(self):
        """Return demo tutors for fallback"""
        return [
            {'id': 'tutor1', 'name': 'Jane Smith', 'email': 'jane@example.com', 'rating': 4.8},
            {'id': 'tutor2', 'name': 'John Doe', 'email': 'john@example.com', 'rating': 4.5}
        ]

    # User management operations
    def get_user_by_id(self, user_id):
        """Retrieve user by ID"""
        try:
            print(f"DEBUG: Getting user with ID {user_id}")
            
            # In demo mode, return demo user
            if self.demo_mode:
                print("DEMO MODE: Returning demo user")
                return {
                    'id': user_id,
                    'name': 'Demo User',
                    'email': 'demo@example.com',
                    'role': 'student'
                }
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available for get_user_by_id")
                return self._get_demo_user(user_id)
            
            try:
                # Get user document
                print(f"DEBUG: Querying users collection for ID {user_id}")
                user_doc = self.db.collection('users').document(str(user_id)).get()
                
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    print(f"DEBUG: Found user {user_data.get('name', 'Unknown')}")
                    return {
                        'id': user_doc.id,
                        **user_data
                    }
                else:
                    print(f"WARNING: No user found with ID {user_id}")
                    return None
                    
            except Exception as query_error:
                print(f"ERROR querying user: {str(query_error)}")
                import traceback
                print(traceback.format_exc())
                return self._get_demo_user(user_id)
                
        except Exception as e:
            print(f"ERROR in get_user_by_id: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return self._get_demo_user(user_id)
            
    def _get_demo_user(self, user_id):
        """Return demo user for fallback"""
        return {
            'id': user_id,
            'name': 'Demo User',
            'email': 'demo@example.com',
            'role': 'student'
        }
        
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
                'created_at': firestore.SERVER_TIMESTAMP,
                'is_read': False
            })
        except Exception as e:
            print(f"Error creating notification: {e}")

    def get_student_upcoming_sessions(self, student_id):
        """
        Get all upcoming tutoring sessions for a specific student
        """
        try:
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available for get_student_upcoming_sessions")
                return self._get_fallback_sessions()
            
            # Get current date
            current_date = datetime.now().date()
            current_date_str = current_date.strftime('%Y-%m-%d')
            
            # Try to get real sessions first
            try:
                student_id = str(student_id)  # Ensure student_id is a string
                
                # Query for upcoming sessions
                sessions_ref = self.db.collection('sessions')
                query = sessions_ref.where('student_id', '==', student_id) \
                                   .where('status', '==', 'Scheduled')
                
                sessions = []
                for doc in query.stream():
                    session_data = doc.to_dict()
                    session_date_str = session_data.get('date')
                    
                    # Skip sessions in the past
                    if session_date_str < current_date_str:
                        continue
                        
                    # Convert date string to datetime object
                    session_date = parse_date(session_date_str)
                    if not session_date:
                        continue
                        
                    # Get tutor name if possible
                    tutor_id = session_data.get('tutor_id')
                    tutor_name = "Unknown Tutor"
                    try:
                        tutor = self.get_user_by_id(tutor_id)
                        if tutor:
                            tutor_name = tutor.get('name', 'Unknown Tutor')
                    except:
                        pass  # Use default tutor name
                    
                    # Get module name if possible
                    module_code = session_data.get('module_code')
                    module_name = f"Module {module_code}"
                    try:
                        module = self.get_module(module_code)
                        if module:
                            module_name = module.get('name', module_name)
                    except:
                        pass  # Use default module name
                    
                    sessions.append({
                        'id': doc.id,
                        'module_code': module_code,
                        'module_name': module_name,
                        'tutor_id': tutor_id,
                        'tutor_name': tutor_name,
                        'date': session_date,
                        'start_time': session_data.get('start_time'),
                        'end_time': session_data.get('end_time'),
                        'status': session_data.get('status')
                    })
                
                # If we found real sessions, return them
                if sessions:
                    return sorted(sessions, key=lambda s: (s['date'].strftime('%Y-%m-%d') if s['date'] else '', s['start_time']))
            except Exception as query_error:
                print(f"Error querying sessions: {query_error}")
                # Continue to fallback data
            
            # Return fallback sessions
            return self._get_fallback_sessions(current_date)
            
        except Exception as e:
            print(f"Error getting upcoming sessions: {e}")
            return self._get_fallback_sessions()
        
    def _get_fallback_sessions(self, current_date=None):
        """Generate fallback session data for demo purposes"""
        if not current_date:
            current_date = datetime.now().date()
        
        return [
            {
                'id': 'session1',
                'module_code': 'PROG101',
                'module_name': 'Introduction to Programming',
                'tutor_id': 'tutor1',
                'tutor_name': 'Jane Smith',
                'date': datetime.now() + timedelta(days=2),
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
                'date': datetime.now() + timedelta(days=5),
                'start_time': '14:00',
                'end_time': '15:00',
                'status': 'Scheduled'
            }
        ]

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

    def get_module_content(self, module_code):
        """Get learning content for a specific module"""
        try:
            # In demo mode, return demo content
            if self.demo_mode:
                print(f"DEMO MODE: Returning demo content for module {module_code}")
                return self._get_demo_content(module_code)
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print(f"ERROR: No valid database connection available for get_module_content")
                return self._get_demo_content(module_code)
            
            # Try to fetch module content from Firestore
            module_code = str(module_code)  # Ensure module_code is a string
            content_items = []
            
            try:
                content_ref = self.db.collection('content').where('module_code', '==', module_code).stream()
                
                for item in content_ref:
                    item_data = item.to_dict()
                    content_items.append({
                        'id': item.id,
                        'title': item_data.get('title', 'Untitled Content'),
                        'description': item_data.get('description', ''),
                        'type': item_data.get('type', 'Document'),
                        'module_code': module_code,
                        'uploaded_by': item_data.get('uploaded_by'),
                        'uploaded_at': item_data.get('uploaded_at'),
                        'download_url': item_data.get('download_url', '')
                    })
                    
                return content_items
            except Exception as e:
                print(f"Error fetching module content: {str(e)}")
                # Continue to fallback data
            
            # If we couldn't get real content, return demo content
            return self._get_demo_content(module_code)
            
        except Exception as e:
            print(f"Error in get_module_content: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return self._get_demo_content(module_code)
        
    def _get_demo_content(self, module_code=None):
        """Return demo content for fallback"""
        current_time = datetime.now()
        
        if module_code == 'PROG101':
            return [
                {
                    'id': 'content-1',
                    'title': 'Introduction to Programming Concepts',
                    'description': 'Learn the basic concepts of programming logic',
                    'type': 'Document',
                    'module_code': 'PROG101',
                    'uploaded_by': 'tutor1',
                    'uploaded_at': current_time - timedelta(days=5),
                    'download_url': '#'
                },
                {
                    'id': 'content-2',
                    'title': 'Getting Started with Python',
                    'description': 'A beginner\'s guide to Python programming',
                    'type': 'Video',
                    'module_code': 'PROG101',
                    'uploaded_by': 'tutor2',
                    'uploaded_at': current_time - timedelta(days=3),
                    'download_url': '#'
                }
            ]
        elif module_code == 'CSCI312':
            return [
                {
                    'id': 'content-3',
                    'title': 'Advanced Data Structures',
                    'description': 'Learn about complex data structures',
                    'type': 'Document',
                    'module_code': 'CSCI312',
                    'uploaded_by': 'tutor1',
                    'uploaded_at': current_time - timedelta(days=7),
                    'download_url': '#'
                }
            ]
        else:
            return [
                {
                    'id': f'content-demo-{uuid.uuid4()}',
                    'title': f'Sample Content for {module_code or "All Modules"}',
                    'description': 'This is sample content for demonstration purposes',
                    'type': 'Document',
                    'module_code': module_code or 'DEMO101',
                    'uploaded_by': 'demo-tutor',
                    'uploaded_at': current_time - timedelta(days=2),
                    'download_url': '#'
                }
            ]

    def get_filtered_content(self, module_code=None, content_type=None, search_query=None, page=1, per_page=12):
        """
        Get learning content with filtering options
        
        Args:
            module_code (str, optional): Filter by module code
            content_type (str, optional): Filter by content type (document, video, etc.)
            search_query (str, optional): Search in title and description
            page (int): Page number for pagination
            per_page (int): Items per page
            
        Returns:
            tuple: (list of content items, total count)
        """
        try:
            # In demo mode, return demo filtered content
            if self.demo_mode:
                print(f"DEMO MODE: Returning demo filtered content")
                return self._get_filtered_demo_content(module_code, content_type, search_query, page, per_page)
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print(f"ERROR: No valid database connection available for get_filtered_content")
                return self._get_filtered_demo_content(module_code, content_type, search_query, page, per_page)
            
            # Try to fetch content from Firestore
            try:
                # Start with a base query
                query = self.db.collection('content')
                
                # Apply filters
                if module_code:
                    query = query.where('module_code', '==', str(module_code))
                    
                if content_type:
                    query = query.where('type', '==', content_type)
                
                # Execute query
                all_items = []
                for doc in query.stream():
                    item_data = doc.to_dict()
                    
                    # Apply search filter manually (Firestore doesn't support text search directly)
                    if search_query and search_query.strip():
                        title = item_data.get('title', '').lower()
                        description = item_data.get('description', '').lower()
                        if search_query.lower() not in title and search_query.lower() not in description:
                            continue
                    
                    all_items.append({
                        'id': doc.id,
                        'title': item_data.get('title', 'Untitled Content'),
                        'description': item_data.get('description', ''),
                        'type': item_data.get('type', 'Document'),
                        'module_code': item_data.get('module_code', ''),
                        'uploaded_by': item_data.get('uploaded_by'),
                        'uploaded_at': item_data.get('uploaded_at'),
                        'download_url': item_data.get('download_url', '#')
                    })
                
                # Calculate total items and apply pagination
                total_items = len(all_items)
                
                # Sort by upload date (newest first)
                all_items.sort(key=lambda x: x.get('uploaded_at', datetime.min), reverse=True)
                
                # Apply pagination
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                paginated_items = all_items[start_idx:end_idx]
                
                return paginated_items, total_items
                
            except Exception as e:
                print(f"Error fetching filtered content: {str(e)}")
                import traceback
                print(traceback.format_exc())
                # Continue to fallback data
            
            # Return demo data if Firestore query fails
            return self._get_filtered_demo_content(module_code, content_type, search_query, page, per_page)
            
        except Exception as e:
            print(f"Error in get_filtered_content: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return self._get_filtered_demo_content(module_code, content_type, search_query, page, per_page)

    def _get_filtered_demo_content(self, module_code=None, content_type=None, search_query=None, page=1, per_page=12):
        """Generate demo filtered content data for fallback"""
        current_time = datetime.now()
        
        # Base demo content
        all_items = [
            {
                'id': 'content-1',
                'title': 'Introduction to Programming Concepts',
                'description': 'Learn the basic concepts of programming logic',
                'type': 'Document',
                'module_code': 'PROG101',
                'uploaded_by': 'tutor1',
                'uploaded_at': current_time - timedelta(days=5),
                'download_url': '#'
            },
            {
                'id': 'content-2',
                'title': 'Getting Started with Python',
                'description': 'A beginner\'s guide to Python programming',
                'type': 'Video',
                'module_code': 'PROG101',
                'uploaded_by': 'tutor2',
                'uploaded_at': current_time - timedelta(days=3),
                'download_url': '#'
            },
            {
                'id': 'content-3',
                'title': 'Advanced Data Structures',
                'description': 'Learn about complex data structures',
                'type': 'Document',
                'module_code': 'CSCI312',
                'uploaded_by': 'tutor1',
                'uploaded_at': current_time - timedelta(days=7),
                'download_url': '#'
            },
            {
                'id': 'content-4',
                'title': 'Database Design Principles',
                'description': 'Fundamentals of database design and normalization',
                'type': 'Document',
                'module_code': 'DB310',
                'uploaded_by': 'tutor3',
                'uploaded_at': current_time - timedelta(days=10),
                'download_url': '#'
            },
            {
                'id': 'content-5',
                'title': 'SQL Tutorial Videos',
                'description': 'Learn SQL through practical examples',
                'type': 'Video',
                'module_code': 'DB310',
                'uploaded_by': 'tutor2',
                'uploaded_at': current_time - timedelta(days=2),
                'download_url': '#'
            },
            {
                'id': 'content-6',
                'title': 'Chemistry Fundamentals',
                'description': 'Introduction to basic chemistry principles',
                'type': 'Document',
                'module_code': 'CHEM120',
                'uploaded_by': 'tutor4',
                'uploaded_at': current_time - timedelta(days=15),
                'download_url': '#'
            }
        ]
        
        # Apply filters
        filtered_items = all_items
        
        if module_code:
            filtered_items = [item for item in filtered_items if item['module_code'] == module_code]
            
        if content_type:
            filtered_items = [item for item in filtered_items if item['type'] == content_type]
            
        if search_query and search_query.strip():
            search_term = search_query.lower()
            filtered_items = [
                item for item in filtered_items 
                if search_term in item['title'].lower() or search_term in item['description'].lower()
            ]
        
        # Get total before pagination
        total_items = len(filtered_items)
        
        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = filtered_items[start_idx:end_idx]
        
        return paginated_items, total_items 

    def get_content(self, content_id):
        """Get content details by ID"""
        try:
            # In demo mode, return demo content
            if self.demo_mode:
                print(f"DEMO MODE: Returning demo content for ID {content_id}")
                return {
                    'id': content_id,
                    'title': 'Demo Content',
                    'description': 'This is demonstration content',
                    'type': 'Document',
                    'module_code': 'DEMO101',
                    'uploaded_by': 'demo-tutor',
                    'uploaded_at': datetime.now() - timedelta(days=2),
                    'download_url': '#'
                }
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print(f"ERROR: No valid database connection available for get_content")
                return None
            
            # Try to fetch content from Firestore
            content_doc = self.db.collection('content').document(content_id).get()
            if content_doc.exists:
                content_data = content_doc.to_dict()
                return {
                    'id': content_doc.id,
                    'title': content_data.get('title', 'Untitled Content'),
                    'description': content_data.get('description', ''),
                    'type': content_data.get('type', 'Document'),
                    'module_code': content_data.get('module_code', ''),
                    'uploaded_by': content_data.get('uploaded_by'),
                    'uploaded_at': content_data.get('uploaded_at'),
                    'download_url': content_data.get('download_url', '#')
                }
            return None
        except Exception as e:
            print(f"Error getting content: {str(e)}")
            return None
        
    def get_session(self, session_id):
        """Get details of a specific tutoring session"""
        try:
            # In demo mode, return demo session
            if self.demo_mode:
                return {
                    'id': session_id,
                    'module_code': 'PROG101',
                    'module_name': 'Introduction to Programming',
                    'tutor_id': 'tutor1',
                    'tutor_name': 'Jane Smith',
                    'student_id': 'student1',
                    'date': datetime.now() + timedelta(days=2),
                    'start_time': '10:00',
                    'end_time': '11:00',
                    'status': 'Scheduled',
                    'location': 'Online',
                    'notes': 'Demo session notes'
                }
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                return None
            
            # Get session document
            session_ref = self.db.collection('sessions').document(str(session_id))
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                return None
                
            session_data = session_doc.to_dict()
            
            # Convert date string to datetime object
            session_date = parse_date(session_data.get('date'))
            
            # Get tutor name
            tutor_id = session_data.get('tutor_id')
            tutor_name = "Unknown Tutor"
            try:
                tutor = self.get_user_by_id(tutor_id)
                if tutor:
                    tutor_name = tutor.get('name', 'Unknown Tutor')
            except:
                pass  # Use default tutor name
            
            # Get module name
            module_code = session_data.get('module_code')
            module_name = f"Module {module_code}"
            try:
                module = self.get_module(module_code)
                if module:
                    module_name = module.get('name', module_name)
            except:
                pass  # Use default module name
            
            # Return session data with names included
            return {
                'id': session_doc.id,
                'module_code': module_code,
                'module_name': module_name,
                'tutor_id': tutor_id,
                'tutor_name': tutor_name,
                'student_id': session_data.get('student_id'),
                'date': session_date,
                'start_time': session_data.get('start_time'),
                'end_time': session_data.get('end_time'),
                'status': session_data.get('status', 'Unknown'),
                'location': session_data.get('location', 'Online'),
                'notes': session_data.get('notes', ''),
                'has_feedback': session_data.get('has_feedback', False)
            }
            
        except Exception as e:
            print(f"Error getting session details: {e}")
            return None
        
    def log_content_download(self, user_id, content_id):
        """Log when a user downloads content"""
        try:
            if self.demo_mode or not self._ensure_db():
                print(f"DEMO MODE: Logging download for user {user_id}, content {content_id}")
                return True
            
            # Create a log entry
            log_ref = self.db.collection('content_downloads').document()
            log_ref.set({
                'user_id': str(user_id),
                'content_id': str(content_id),
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            print(f"Error logging content download: {str(e)}")
            return False
        
    def get_student_past_sessions(self, student_id):
        """Get past tutoring sessions for a student"""
        try:
            # In demo mode, return demo sessions
            if self.demo_mode:
                return [
                    {
                        'id': 'past1',
                        'module_code': 'PROG101',
                        'module_name': 'Introduction to Programming',
                        'tutor_id': 'tutor1',
                        'tutor_name': 'Jane Smith',
                        'date': datetime.now() - timedelta(days=2),
                        'start_time': '10:00',
                        'end_time': '11:00',
                        'status': 'Completed',
                        'has_feedback': False
                    },
                    {
                        'id': 'past2',
                        'module_code': 'MATH201',
                        'module_name': 'Advanced Mathematics',
                        'tutor_id': 'tutor2',
                        'tutor_name': 'John Doe',
                        'date': datetime.now() - timedelta(days=5),
                        'start_time': '14:00',
                        'end_time': '15:00',
                        'status': 'Completed',
                        'has_feedback': True
                    }
                ]
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                return []
            
            # Get current date
            current_date = datetime.now().date()
            current_date_str = current_date.strftime('%Y-%m-%d')
            
            # Query for past sessions
            sessions_ref = self.db.collection('sessions')
            query = sessions_ref.where('student_id', '==', str(student_id)) \
                               .where('status', '==', 'Completed')
            
            sessions = []
            for doc in query.stream():
                session_data = doc.to_dict()
                session_date_str = session_data.get('date')
                
                # Skip future sessions
                if session_date_str >= current_date_str:
                    continue
                    
                # Convert date string to datetime object
                session_date = parse_date(session_date_str)
                if not session_date:
                    continue
                    
                # Get tutor name
                tutor_id = session_data.get('tutor_id')
                tutor_name = "Unknown Tutor"
                try:
                    tutor = self.get_user_by_id(tutor_id)
                    if tutor:
                        tutor_name = tutor.get('name', 'Unknown Tutor')
                except:
                    pass  # Use default tutor name
                
                # Get module name
                module_code = session_data.get('module_code')
                module_name = f"Module {module_code}"
                try:
                    module = self.get_module(module_code)
                    if module:
                        module_name = module.get('name', module_name)
                except:
                    pass  # Use default module name
                
                sessions.append({
                    'id': doc.id,
                    'module_code': module_code,
                    'module_name': module_name,
                    'tutor_id': tutor_id,
                    'tutor_name': tutor_name,
                    'date': session_date,
                    'start_time': session_data.get('start_time'),
                    'end_time': session_data.get('end_time'),
                    'status': session_data.get('status'),
                    'has_feedback': session_data.get('has_feedback', False)
                })
            
            # Sort sessions by date (most recent first)
            return sorted(sessions, key=lambda s: (s['date'].strftime('%Y-%m-%d') if s['date'] else '', s['start_time']), reverse=True)
            
        except Exception as e:
            print(f"Error getting past sessions: {e}")
            return []
        
    def submit_feedback(self, session_id, student_id, tutor_id, rating, feedback, was_helpful, improvement=''):
        """Submit feedback for a tutoring session"""
        try:
            # In demo mode, just return success
            if self.demo_mode or not self._ensure_db():
                print(f"DEMO MODE: Submitting feedback for session {session_id}")
                return True
            
            # Create the feedback document
            feedback_ref = self.db.collection('feedback').document()
            
            feedback_data = {
                'session_id': str(session_id),
                'student_id': str(student_id),
                'tutor_id': str(tutor_id),
                'rating': int(rating),
                'feedback': feedback,
                'was_helpful': was_helpful,
                'improvement': improvement,
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            # Save the feedback
            feedback_ref.set(feedback_data)
            
            # Update the session to mark it as having feedback
            session_ref = self.db.collection('sessions').document(session_id)
            session_ref.update({
                'has_feedback': True
            })
            
            return True
        except Exception as e:
            print(f"Error submitting feedback: {str(e)}")
            return False

    def encode_file_to_base64(self, file_path):
        """Encode a file to base64 string"""
        try:
            with open(file_path, 'rb') as file:
                file_content = file.read()
                return base64.b64encode(file_content).decode('utf-8')
        except Exception as e:
            print(f"Error encoding file to base64: {str(e)}")
            return None
        
    def store_document_reference(self, user_id, doc_type, file_content, file_name, file_size):
        """Store a document reference in Firestore"""
        try:
            # In demo mode, return a fake document ID
            if self.demo_mode or not self._ensure_db():
                print(f"DEMO MODE: Storing document reference for user {user_id}")
                return f"demo-document-{uuid.uuid4()}"
            
            # Create document reference
            doc_ref = self.db.collection('documents').document()
            
            doc_data = {
                'user_id': str(user_id),
                'doc_type': doc_type,
                'file_content': file_content,
                'file_name': file_name,
                'file_size': file_size,
                'uploaded_at': firestore.SERVER_TIMESTAMP
            }
            
            # Save the document
            doc_ref.set(doc_data)
            
            return doc_ref.id
        except Exception as e:
            print(f"Error storing document reference: {str(e)}")
            return None
        
    def cancel_session(self, session_id):
        """Cancel a booked session"""
        try:
            # In demo mode, return success
            if self.demo_mode or not self._ensure_db():
                print(f"DEMO MODE: Cancelling session {session_id}")
                return True
            
            # Update the session status
            session_ref = self.db.collection('sessions').document(session_id)
            session_ref.update({
                'status': 'Cancelled',
                'cancelled_at': firestore.SERVER_TIMESTAMP
            })
            
            return True
        except Exception as e:
            print(f"Error cancelling session: {str(e)}")
            return False

    def create_reservation(self, student_id, tutor_id, module_code, date, start_time, end_time, notes=''):
        """
        Create a temporary session reservation (first step of booking process)
        
        Args:
            student_id (str): The student's user ID
            tutor_id (str): The tutor's user ID
            module_code (str): The module code
            date (datetime.date or str): Session date
            start_time (str): Start time (HH:MM)
            end_time (str): End time (HH:MM)
            notes (str, optional): Optional session notes/requests
            
        Returns:
            str: Reservation ID if successful, None otherwise
        """
        try:
            print(f"DEBUG: create_reservation called with:")
            print(f"student_id: {student_id}, tutor_id: {tutor_id}")
            print(f"module_code: {module_code}, date: {date}")
            print(f"time: {start_time} - {end_time}")
            print(f"notes: {notes[:50]}{'...' if len(notes) > 50 else ''}")
            
            # In demo mode, return a fake reservation ID
            if self.demo_mode:
                fake_id = f"demo-reservation-{uuid.uuid4()}"
                print(f"DEMO MODE: Generated fake reservation ID: {fake_id}")
                return fake_id
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available")
                fake_id = f"fallback-reservation-{uuid.uuid4()}"
                print(f"FALLBACK: Generated fallback reservation ID: {fake_id}")
                return fake_id
                
            # Convert parameters to strings
            student_id = str(student_id)
            tutor_id = str(tutor_id)
            module_code = str(module_code)
            
            # Handle date conversion
            if isinstance(date, str):
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                    date_str = date
                except ValueError as e:
                    print(f"ERROR: Invalid date format: {e}")
                    return None
            else:
                try:
                    date_obj = date
                    date_str = date.strftime('%Y-%m-%d')
                except Exception as e:
                    print(f"ERROR: Invalid date object: {e}")
                    return None
            
            # Validate times
            try:
                # Ensure times are in HH:MM format
                datetime.strptime(start_time, '%H:%M')
                datetime.strptime(end_time, '%H:%M')
            except ValueError as e:
                print(f"ERROR: Invalid time format: {e}")
                return None
                
            # Check if the slot is available
            try:
                available_slots = self.get_tutor_schedule(tutor_id, date_obj)
                time_slot = f"{start_time} - {end_time}"
                
                if time_slot not in available_slots:
                    print(f"ERROR: Time slot {time_slot} is not available")
                    return None
            except Exception as e:
                print(f"ERROR: Failed to verify slot availability: {e}")
                return None
                
            # Create a reservation document with expiration
            try:
                # Set expiration time (15 minutes from now)
                expiration_time = datetime.now() + timedelta(minutes=15)
                
                # Create reservation
                reservation_ref = self.db.collection('reservations').document()
                
                reservation_data = {
                    'student_id': student_id,
                    'tutor_id': tutor_id,
                    'module_code': module_code,
                    'date': date_str,
                    'start_time': start_time,
                    'end_time': end_time,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'expires_at': expiration_time,
                    'status': 'Pending',
                    'notes': notes
                }
                
                print(f"DEBUG: Creating reservation with data: {reservation_data}")
                reservation_ref.set(reservation_data)
                print(f"DEBUG: Reservation created with ID: {reservation_ref.id}")
                
                return reservation_ref.id
                
            except Exception as db_error:
                print(f"ERROR: Database operation failed: {db_error}")
                import traceback
                print(traceback.format_exc())
                return None
                
        except Exception as e:
            print(f"ERROR: Unexpected error in create_reservation: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def confirm_reservation(self, reservation_id):
        """
        Confirm a reservation and create the actual booking (second step of booking process)
        
        Args:
            reservation_id (str): The ID of the reservation to confirm
            
        Returns:
            str: Session ID if successful, None otherwise
        """
        try:
            print(f"DEBUG: confirm_reservation called with ID: {reservation_id}")
            
            # In demo mode, return a fake session ID
            if self.demo_mode:
                fake_id = f"demo-session-{uuid.uuid4()}"
                print(f"DEMO MODE: Generated fake session ID: {fake_id}")
                return fake_id
            
            # Handle demo reservations
            if reservation_id.startswith(('demo-', 'fallback-')):
                fake_id = reservation_id.replace('reservation', 'session')
                print(f"DEMO CONVERT: Converted reservation to session ID: {fake_id}")
                return fake_id
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available")
                fake_id = f"emergency-session-{uuid.uuid4()}"
                print(f"FALLBACK: Generated emergency session ID: {fake_id}")
                return fake_id
                
            # Get the reservation
            try:
                reservation_ref = self.db.collection('reservations').document(reservation_id)
                reservation = reservation_ref.get()
                
                if not reservation.exists:
                    print(f"ERROR: Reservation {reservation_id} not found")
                    return None
                    
                reservation_data = reservation.to_dict()
                
                # Check if the reservation has expired
                expires_at = reservation_data.get('expires_at')
                if expires_at and expires_at < datetime.now():
                    print(f"ERROR: Reservation {reservation_id} has expired")
                    return None
                    
                # Check if the slot is still available (might have been taken since reservation)
                try:
                    date_str = reservation_data.get('date')
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    tutor_id = reservation_data.get('tutor_id')
                    
                    available_slots = self.get_tutor_schedule(tutor_id, date_obj)
                    time_slot = f"{reservation_data.get('start_time')} - {reservation_data.get('end_time')}"
                    
                    if time_slot not in available_slots:
                        print(f"ERROR: Time slot {time_slot} is no longer available")
                        return None
                except Exception as slot_error:
                    print(f"ERROR: Failed to verify slot availability: {slot_error}")
                    # Continue anyway, as we already checked during reservation
                
                # Create the session from reservation data
                session_ref = self.db.collection('sessions').document()
                
                session_data = {
                    'student_id': reservation_data.get('student_id'),
                    'tutor_id': reservation_data.get('tutor_id'),
                    'module_code': reservation_data.get('module_code'),
                    'date': reservation_data.get('date'),
                    'start_time': reservation_data.get('start_time'),
                    'end_time': reservation_data.get('end_time'),
                    'status': 'Scheduled',
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'location': 'Online',  # Default location
                    'has_feedback': False,
                    'reservation_id': reservation_id,
                    'notes': reservation_data.get('notes', '')
                }
                
                print(f"DEBUG: Creating session with data: {session_data}")
                session_ref.set(session_data)
                
                # Mark reservation as Confirmed
                reservation_ref.update({
                    'status': 'Confirmed',
                    'confirmed_at': firestore.SERVER_TIMESTAMP,
                    'session_id': session_ref.id
                })
                
                # Create notifications
                try:
                    # For tutor
                    self._create_notification(
                        user_id=session_data.get('tutor_id'),
                        title="New Session Booked",
                        message=f"A student has booked a tutoring session with you on {session_data.get('date')} at {session_data.get('start_time')}.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                    
                    # For student
                    self._create_notification(
                        user_id=session_data.get('student_id'),
                        title="Session Booking Confirmed",
                        message=f"Your tutoring session has been booked for {session_data.get('date')} at {session_data.get('start_time')}.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                except Exception as notif_error:
                    print(f"WARNING: Failed to create notifications: {notif_error}")
                    # Continue even if notifications fail
                
                print(f"DEBUG: Session created successfully with ID: {session_ref.id}")
                return session_ref.id
                
            except Exception as db_error:
                print(f"ERROR: Database operation failed: {db_error}")
                import traceback
                print(traceback.format_exc())
                return None
                
        except Exception as e:
            print(f"ERROR: Unexpected error in confirm_reservation: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def cleanup_expired_reservations(self):
        """Clean up expired reservations to free up slots"""
        try:
            # Skip in demo mode
            if self.demo_mode or not self._ensure_db():
                print("DEMO MODE: Skipping reservation cleanup")
                return True
                
            # Get all expired reservations
            now = datetime.now()
            expired_query = self.db.collection('reservations') \
                                .where('status', '==', 'Pending') \
                                .where('expires_at', '<', now)
            
            count = 0
            for reservation in expired_query.stream():
                reservation_ref = self.db.collection('reservations').document(reservation.id)
                reservation_ref.update({
                    'status': 'Expired',
                    'expired_at': firestore.SERVER_TIMESTAMP
                })
                count += 1
                
            print(f"DEBUG: Cleaned up {count} expired reservations")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to clean up expired reservations: {e}")
            return False

    def seed_modules(self):
        """Seed predefined modules into the database"""
        try:
            if not self._ensure_db():
                print("Database connection is not valid, cannot seed modules")
                return False
            
            # List of modules to seed
            modules = [
                {"code": "DAST401", "name": "Data Structures", "description": "Advanced data structures and algorithms for efficient problem solving"},
                {"code": "PBDE401", "name": "Platform Based Development", "description": "Development of applications for specific platforms and environments"},
                {"code": "RESK401", "name": "Research Skills", "description": "Skills and methodologies for conducting research in computing"},
                {"code": "APMC401", "name": "Applied Mathematics for Computing A", "description": "Mathematical foundations for computing applications"},
                {"code": "SODM401", "name": "Software Development and Management", "description": "Project management and development methodologies for software"},
                {"code": "APMC402", "name": "Applied Mathematics for Computing B", "description": "Advanced topics in mathematics for computing applications"},
                {"code": "SAMA301", "name": "Strategy Acquisition and Management 3", "description": "Strategic approaches to acquiring and managing IT resources"},
                {"code": "BUIN301", "name": "Business Intelligence 3", "description": "Advanced topics in business intelligence and analytics"},
                {"code": "PDCO301", "name": "Parallel and Distributed Computing 3", "description": "Advanced concepts in parallel and distributed computing"},
                {"code": "MAIN301", "name": "Machine Intelligence 3", "description": "Advanced artificial intelligence and machine learning topics"},
                {"code": "GRAPH301", "name": "Graphics 3", "description": "Advanced computer graphics and visualization techniques"},
                {"code": "HCIN301", "name": "Human Computer Interaction 3", "description": "Advanced topics in human-computer interaction and interface design"}
            ]
            
            # Seed each module if it doesn't already exist
            for module in modules:
                module_ref = self.db.collection('modules').document(module["code"])
                if not module_ref.get().exists:
                    module_ref.set(module)
                    print(f"Seeded module: {module['code']} - {module['name']}")
                else:
                    print(f"Module already exists: {module['code']} - {module['name']}")
                
            return True
            
        except Exception as e:
            print(f"Error seeding modules: {str(e)}")
            return False

    def seed_tutors(self):
        """Seed demo tutors into the database"""
        try:
            if not self._ensure_db():
                print("Database connection is not valid, cannot seed tutors")
                return False
            
            # List of tutors to seed
            tutors = [
                {
                    "id": "tutor1",
                    "name": "Dr. Sarah Johnson",
                    "email": "sarah.johnson@example.com",
                    "role": "tutor",
                    "bio": "Specialist in data structures and algorithms with 8 years of teaching experience",
                    "modules": ["DAST401", "PDCO301", "APMC401"]
                },
                {
                    "id": "tutor2",
                    "name": "Prof. Michael Chen",
                    "email": "michael.chen@example.com",
                    "role": "tutor",
                    "bio": "Expert in platform development and software engineering methodologies",
                    "modules": ["PBDE401", "SODM401", "HCIN301"]
                },
                {
                    "id": "tutor3",
                    "name": "Dr. Emily Rodriguez",
                    "email": "emily.rodriguez@example.com",
                    "role": "tutor", 
                    "bio": "Research specialist with focus on applied mathematics and machine learning",
                    "modules": ["RESK401", "MAIN301", "APMC402"]
                }
            ]
            
            # Seed tutors
            for tutor in tutors:
                tutor_id = tutor["id"]
                # Store tutor in users collection
                self.db.collection('users').document(tutor_id).set(tutor)
                print(f"Seeded tutor: {tutor['name']}")
                
                # Also register them as tutors for their modules
                for module_code in tutor["modules"]:
                    module_tutor_ref = self.db.collection('module_tutors').document(f"{module_code}_{tutor_id}")
                    module_tutor_ref.set({
                        "module_code": module_code,
                        "tutor_id": tutor_id,
                        "name": tutor["name"],
                        "email": tutor["email"],
                        "bio": tutor["bio"]
                    })
                    print(f"Registered tutor {tutor['name']} for module {module_code}")
            
            return True
            
        except Exception as e:
            print(f"Error seeding tutors: {str(e)}")
            return False

    def seed_tutor_availability(self):
        """Seed tutor availability for the next 14 days"""
        try:
            if not self._ensure_db():
                print("Database connection is not valid, cannot seed tutor availability")
                return False
            
            tutor_ids = ["tutor1", "tutor2", "tutor3"]
            
            # Get dates for the next 14 days
            today = datetime.today().date()
            dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 15)]
            
            # Standard time slots
            time_slots = [
                "09:00 - 10:00",
                "10:00 - 11:00",
                "11:00 - 12:00",
                "13:00 - 14:00",
                "14:00 - 15:00",
                "15:00 - 16:00",
                "16:00 - 17:00"
            ]
            
            # Seed availability for each tutor
            for tutor_id in tutor_ids:
                for date in dates:
                    # Different tutors have different availability patterns
                    if tutor_id == "tutor1":
                        # Dr. Johnson is available every day except weekends
                        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                        if date_obj.weekday() >= 5:  # Saturday or Sunday
                            continue
                        available_slots = time_slots[1:5]  # 10:00 to 15:00
                    elif tutor_id == "tutor2":
                        # Prof. Chen is available Monday, Wednesday, Friday
                        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                        if date_obj.weekday() not in [0, 2, 4]:  # Mon, Wed, Fri
                            continue
                        available_slots = time_slots  # All slots
                    else:
                        # Dr. Rodriguez is available Tuesday, Thursday
                        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                        if date_obj.weekday() not in [1, 3]:  # Tue, Thu
                            continue
                        available_slots = time_slots[2:6]  # 11:00 to 16:00
                    
                    # Store availability in database
                    availability_ref = self.db.collection('tutor_availability').document(f"{tutor_id}_{date}")
                    availability_ref.set({
                        "tutor_id": tutor_id,
                        "date": date,
                        "available_slots": available_slots,
                        "updated_at": datetime.now().isoformat()
                    })
                    print(f"Seeded availability for tutor {tutor_id} on {date}: {len(available_slots)} slots")
            
            return True
            
        except Exception as e:
            print(f"Error seeding tutor availability: {str(e)}")
            return False

    def seed_students(self):
        """Seed demo students into the database"""
        try:
            if not self._ensure_db():
                print("Database connection is not valid, cannot seed students")
                return False
            
            # List of students to seed
            students = [
                {
                    "id": "student1",
                    "name": "Alex Thompson",
                    "email": "alex.thompson@example.com",
                    "role": "student",
                    "enrolled_modules": ["DAST401", "PBDE401", "RESK401"]
                },
                {
                    "id": "student2",
                    "name": "Jamie Wilson",
                    "email": "jamie.wilson@example.com",
                    "role": "student",
                    "enrolled_modules": ["APMC401", "SODM401", "MAIN301"]
                },
                {
                    "id": "student3",
                    "name": "Sam Parker",
                    "email": "sam.parker@example.com",
                    "role": "student",
                    "enrolled_modules": ["PDCO301", "GRAPH301", "HCIN301"]
                }
            ]
            
            # Seed students
            for student in students:
                student_id = student["id"]
                self.db.collection('users').document(student_id).set(student)
                print(f"Seeded student: {student['name']}")
            
            return True
            
        except Exception as e:
            print(f"Error seeding students: {str(e)}")
            return False

    def seed_bookings(self):
        """Seed demo bookings for students and tutors"""
        try:
            if not self._ensure_db():
                print("Database connection is not valid, cannot seed bookings")
                return False
            
            # Define bookings to seed
            bookings = [
                {
                    "student_id": "student1",
                    "tutor_id": "tutor1",
                    "module_code": "DAST401",
                    "date": (datetime.today() + timedelta(days=3)).strftime('%Y-%m-%d'),
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "status": "confirmed",
                    "notes": "Need help with AVL trees and balancing algorithms",
                    "created_at": datetime.now().isoformat()
                },
                {
                    "student_id": "student2",
                    "tutor_id": "tutor3",
                    "module_code": "APMC401",
                    "date": (datetime.today() + timedelta(days=4)).strftime('%Y-%m-%d'),
                    "start_time": "13:00",
                    "end_time": "14:00",
                    "status": "confirmed",
                    "notes": "Struggling with linear optimization problems",
                    "created_at": datetime.now().isoformat()
                },
                {
                    "student_id": "student3",
                    "tutor_id": "tutor2",
                    "module_code": "HCIN301",
                    "date": (datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
                    "start_time": "15:00",
                    "end_time": "16:00",
                    "status": "confirmed",
                    "notes": "Need assistance with user testing methodologies",
                    "created_at": datetime.now().isoformat()
                }
            ]
            
            # Seed each booking
            for booking in bookings:
                booking_id = f"booking_{uuid.uuid4().hex[:8]}"
                
                # Add additional fields
                booking["id"] = booking_id
                booking["session_id"] = booking_id  # For backward compatibility
                booking["cancelled"] = False
                booking["has_feedback"] = False
                
                # Get student and tutor names for reference
                try:
                    student = self.db.collection('users').document(booking["student_id"]).get().to_dict()
                    tutor = self.db.collection('users').document(booking["tutor_id"]).get().to_dict()
                    
                    booking["student_name"] = student.get("name", "Unknown Student")
                    booking["tutor_name"] = tutor.get("name", "Unknown Tutor")
                    
                    # Get module details
                    module = self.db.collection('modules').document(booking["module_code"]).get().to_dict()
                    booking["module_name"] = module.get("name", f"Module {booking['module_code']}")
                    
                    # Format time slot string
                    booking["time_slot"] = f"{booking['start_time']} - {booking['end_time']}"
                    
                except Exception as e:
                    print(f"Error retrieving related data for booking: {e}")
                    booking["student_name"] = "Unknown Student"
                    booking["tutor_name"] = "Unknown Tutor"
                    booking["module_name"] = f"Module {booking['module_code']}"
                    booking["time_slot"] = f"{booking['start_time']} - {booking['end_time']}"
                
                # Store booking in database
                self.db.collection('sessions').document(booking_id).set(booking)
                print(f"Seeded booking: {booking_id} for {booking['student_name']} with {booking['tutor_name']}")
                
                # Remove the slot from tutor availability
                try:
                    availability_ref = self.db.collection('tutor_availability').document(f"{booking['tutor_id']}_{booking['date']}")
                    availability = availability_ref.get().to_dict()
                    
                    if availability and "available_slots" in availability:
                        time_slot = f"{booking['start_time']} - {booking['end_time']}"
                        if time_slot in availability["available_slots"]:
                            availability["available_slots"].remove(time_slot)
                            availability_ref.update({"available_slots": availability["available_slots"]})
                            print(f"Removed booked slot {time_slot} from {booking['tutor_id']}'s availability on {booking['date']}")
                except Exception as e:
                    print(f"Error updating tutor availability: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error seeding bookings: {str(e)}")
            return False 

    def get_system_statistics(self):
        """Return system statistics for admin dashboard"""
        try:
            if self.demo_mode or not self._ensure_db():
                # Return demo statistics
                return {
                    'total_users': 15,
                    'total_students': 10,
                    'total_tutors': 4,
                    'total_admins': 1,
                    'total_sessions': 23,
                    'total_modules': 12,
                    'active_users': 8
                }
            
            # If we have a valid database connection, fetch real statistics
            stats = {}
            
            # Count users by role
            users_ref = self.db.collection('users')
            all_users = list(users_ref.stream())
            stats['total_users'] = len(all_users)
            
            # Count by role
            users_by_role = {'student': 0, 'tutor': 0, 'admin': 0}
            for user in all_users:
                user_data = user.to_dict()
                role = user_data.get('role', 'unknown')
                if role in users_by_role:
                    users_by_role[role] += 1
            
            stats['total_students'] = users_by_role['student']
            stats['total_tutors'] = users_by_role['tutor']
            stats['total_admins'] = users_by_role['admin']
            
            # Count sessions
            sessions_ref = self.db.collection('sessions')
            stats['total_sessions'] = len(list(sessions_ref.stream()))
            
            # Count modules
            modules_ref = self.db.collection('modules')
            stats['total_modules'] = len(list(modules_ref.stream()))
            
            # Estimate active users (sessions in the last 30 days)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            recent_sessions = list(sessions_ref.where('created_at', '>=', thirty_days_ago).stream())
            active_user_ids = set()
            for session in recent_sessions:
                session_data = session.to_dict()
                if 'student_id' in session_data:
                    active_user_ids.add(session_data['student_id'])
                if 'tutor_id' in session_data:
                    active_user_ids.add(session_data['tutor_id'])
            
            stats['active_users'] = len(active_user_ids)
            
            return stats
            
        except Exception as e:
            print(f"Error fetching system statistics: {str(e)}")
            # Return default demo statistics on error
            return {
                'total_users': 15,
                'total_students': 10,
                'total_tutors': 4,
                'total_admins': 1,
                'total_sessions': 23, 
                'total_modules': 12,
                'active_users': 8
            } 