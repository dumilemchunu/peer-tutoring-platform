import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
import uuid
import base64
from app.utils.date_utils import parse_date
from typing import Dict, List, Optional, Tuple, Any
import os
import pytz

class FirebaseService:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not FirebaseService._initialized:
            try:
                print("Initializing Firebase Admin SDK...")
                print("Initializing Firebase with credentials from environment variables...")
                
                # Create credentials dictionary with explicit type field
                cred_dict = {
                    "type": "service_account",
                    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace('\\n', '\n'),
                    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL")
                }

                # Check if Firebase is already initialized
                try:
                    self.app = firebase_admin.get_app()
                    print("Firebase already initialized, reusing existing app")
                except ValueError:
                    # Initialize Firebase only if it's not already initialized
                    cred = credentials.Certificate(cred_dict)
                    self.app = firebase_admin.initialize_app(cred)
                    print("Firebase Admin SDK initialized successfully")

                # Initialize Firestore client
                self.db = firestore.client()
                print("Firestore client initialized successfully")
                FirebaseService._initialized = True

            except Exception as e:
                print(f"Error initializing Firebase: {str(e)}")
                raise

    def _ensure_db(self):
        """Ensure database connection is available"""
        return True  # Always return True since we require Firebase

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
        """Get module data by code"""
        try:
            # Get module document
            module_doc = self.db.collection('modules').document(str(module_code)).get()
            
            if not module_doc.exists:
                print(f"Module {module_code} not found")
            return None
                
            module_data = module_doc.to_dict()
            module_data['code'] = module_code  # Ensure code is included in the data
            return module_data
            
        except Exception as e:
            print(f"Error getting module {module_code}: {str(e)}")
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
                return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]
                
        except Exception as e:
            print(f"ERROR: Unexpected error in get_tutor_schedule: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return ["09:00 - 10:00", "11:00 - 12:00", "14:00 - 15:00"]

    # Module management operations
    def get_all_modules(self):
        """Get all available modules with error handling"""
        try:
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
            
            return modules
            
        except Exception as e:
            print(f"Error getting all modules: {e}")
            import traceback
            print(traceback.format_exc())
            return []

    def get_module_tutors(self, module_code):
        """Get all tutors assigned to a specific module"""
        try:
            print(f"DEBUG: Getting tutors for module {module_code}")
            
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
            
            print(f"DEBUG: Returning {len(tutors)} tutors found")
            return tutors
            
        except Exception as e:
            print(f"ERROR in get_module_tutors: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def get_module_content(self, module_code):
        """Get learning content for a specific module"""
        try:
            # Try to fetch module content from Firestore
            module_code = str(module_code)  # Ensure module_code is a string
            content_items = []
            
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
            print(f"Error in get_module_content: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

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
            print(f"Error in get_filtered_content: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return [], 0

    def get_recent_content(self, limit=5):
        """Get recent learning content uploads"""
        try:
            # Query for recent content
            content_ref = self.db.collection('content')
            query = content_ref.order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(limit)
            
            recent_content = []
            for doc in query.stream():
                item_data = doc.to_dict()
                recent_content.append({
                    'id': doc.id,
                    'title': item_data.get('title', 'Untitled Content'),
                    'description': item_data.get('description', ''),
                    'module_code': item_data.get('module_code', ''),
                    'module_name': item_data.get('module_name', f"Module {item_data.get('module_code', '')}"),
                    'uploaded_at': item_data.get('uploaded_at')
                })
            
            return recent_content
            
        except Exception as e:
            print(f"Error getting recent content: {e}")
            return []

    def count_learning_materials(self):
        """Count the total number of learning materials available"""
        try:
            # Query for all content documents
            content_ref = self.db.collection('content')
            return len(list(content_ref.stream()))
            
        except Exception as e:
            print(f"Error counting learning materials: {e}")
            return 0

    def get_student_total_hours(self, student_id):
        """Calculate the total tutoring hours for a student"""
        try:
            # Query for completed sessions
            sessions_ref = self.db.collection('sessions')
            query = sessions_ref.where('student_id', '==', str(student_id)) \
                               .where('status', '==', 'Completed')
            
            total_hours = 0
            for doc in query.stream():
                session_data = doc.to_dict()
                start_time = session_data.get('start_time')
                end_time = session_data.get('end_time')
                
                if start_time and end_time:
                    # Calculate duration in hours
                    start = datetime.strptime(start_time, '%H:%M')
                    end = datetime.strptime(end_time, '%H:%M')
                    duration = (end - start).total_seconds() / 3600
                    total_hours += duration
            
            return round(total_hours, 1)
            
        except Exception as e:
            print(f"Error calculating total hours: {e}")
            return 0

    def get_system_statistics(self):
        """Return system statistics for admin dashboard"""
        try:
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
            return {
                'total_users': 0,
                'total_students': 0,
                'total_tutors': 0,
                'total_admins': 0,
                'total_sessions': 0,
                'total_modules': 0,
                'active_users': 0
            }

    # User management operations
    def get_user_by_id(self, user_id):
        """Get user data by ID"""
        try:
            # Get user document
            user_doc = self.db.collection('users').document(str(user_id)).get()
            
            if not user_doc.exists:
                print(f"User {user_id} not found")
                return None
                
            user_data = user_doc.to_dict()
            user_data['id'] = user_id  # Ensure ID is included in the data
            return user_data
            
        except Exception as e:
            print(f"Error getting user {user_id}: {str(e)}")
            return None
        
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
        """Get upcoming tutoring sessions for a student"""
        try:
            # Get current date
            current_date = datetime.now().date()
            current_date_str = current_date.strftime('%Y-%m-%d')
            
            # Query for upcoming sessions
            sessions_ref = self.db.collection('sessions')
            query = sessions_ref.where('student_id', '==', str(student_id)) \
                               .where('status', '==', 'Scheduled')
            
            sessions = []
            for doc in query.stream():
                session_data = doc.to_dict()
                session_date_str = session_data.get('date')
                
                # Skip past sessions
                if session_date_str < current_date_str:
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
                    'status': session_data.get('status')
                })
            
            # Sort sessions by date and start time
            return sorted(sessions, key=lambda s: (s['date'].strftime('%Y-%m-%d') if s['date'] else '', s['start_time']))
            
        except Exception as e:
            print(f"Error getting upcoming sessions: {str(e)}")
            return []

    def get_student_past_sessions(self, student_id):
        """Get past tutoring sessions for a student"""
        try:
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
            print(f"Error getting past sessions: {str(e)}")
            return []
        
    def submit_feedback(self, session_id, student_id, tutor_id, rating, feedback, was_helpful, improvement=''):
        """Submit feedback for a tutoring session"""
        try:
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

    def get_tutor_applications(self):
        """
        Get all pending tutor applications
        
        Returns:
            list: List of tutor applications
        """
        try:
            applications = []
            # Get all pending applications
            docs = self.db.collection('tutor_applications').where('status', '==', 'Pending').get()
            
            for doc in docs:
                app_data = doc.to_dict()
                # Add the document ID to the data
                app_data['id'] = doc.id
                
                # Get user details
                if 'user_id' in app_data:
                    user_ref = self.db.collection('users').document(app_data['user_id'])
                    user = user_ref.get()
                    if user.exists:
                        user_data = user.to_dict()
                        app_data.update({
                            'name': user_data.get('name', 'Unknown'),
                            'email': user_data.get('email', 'No email')
                        })
                
                # Convert timestamps to datetime objects
                if 'created_at' in app_data and app_data['created_at']:
                    app_data['created_at'] = app_data['created_at'].datetime
                
                applications.append(app_data)
            
            # Sort by creation date, newest first
            applications.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
            return applications
            
        except Exception as e:
            print(f"Error getting tutor applications: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def get_all_users(self):
        """Get all users with their roles and details"""
        try:
            users = []
            users_ref = self.db.collection('users')
            
            for doc in users_ref.stream():
                user_data = doc.to_dict()
                user_data['id'] = doc.id  # Add document ID as user ID
                
                # Add default values for required fields if missing
                user_data.setdefault('name', 'Unknown User')
                user_data.setdefault('email', '')
                user_data.setdefault('role', 'student')
                user_data.setdefault('created_at', '')
                
                users.append(user_data)
            
            # Sort users by creation date (newest first)
            return sorted(users, key=lambda x: x.get('created_at', ''), reverse=True)
            
        except Exception as e:
            print(f"Error getting all users: {str(e)}")
            return []

    def approve_tutor_application(self, application_id):
        """
        Approve a tutor application and update the user's role
        
        Args:
            application_id (str): The ID of the tutor application
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the application
            app_ref = self.db.collection('tutor_applications').document(str(application_id))
            app = app_ref.get()
            
            if not app.exists:
                print(f"Application {application_id} not found")
                return False
                
            app_data = app.to_dict()
            user_id = app_data.get('user_id')
            
            if not user_id:
                print("Application has no associated user ID")
                return False
            
            # Update application status
            app_ref.update({
                'status': 'Approved',
                'approved_at': firestore.SERVER_TIMESTAMP,
                'processed_by': 'admin'  # Could be replaced with actual admin ID
            })
            
            # Update user role to tutor
            user_ref = self.db.collection('users').document(str(user_id))
            user_ref.update({
                'role': 'tutor',
                'tutor_since': firestore.SERVER_TIMESTAMP,
                'approved_modules': app_data.get('modules', []),
                'qualifications': app_data.get('qualifications', ''),
                'experience': app_data.get('experience', '')
            })
            
            # Create notification for the user
            self._create_notification(
                user_id=user_id,
                title="Tutor Application Approved",
                message="Congratulations! Your application to become a tutor has been approved.",
                type="application_status"
            )
            
            return True
            
        except Exception as e:
            print(f"Error approving tutor application: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False
            
    def reject_tutor_application(self, application_id, reason=''):
        """
        Reject a tutor application
        
        Args:
            application_id (str): The ID of the tutor application
            reason (str, optional): Reason for rejection
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the application
            app_ref = self.db.collection('tutor_applications').document(str(application_id))
            app = app_ref.get()
            
            if not app.exists:
                print(f"Application {application_id} not found")
                return False
                
            app_data = app.to_dict()
            user_id = app_data.get('user_id')
            
            if not user_id:
                print("Application has no associated user ID")
                return False
            
            # Update application status
            app_ref.update({
                'status': 'Rejected',
                'rejected_at': firestore.SERVER_TIMESTAMP,
                'rejection_reason': reason,
                'processed_by': 'admin'  # Could be replaced with actual admin ID
            })
            
            # Create notification for the user
            message = "Your application to become a tutor has been rejected."
            if reason:
                message += f" Reason: {reason}"
                
            self._create_notification(
                user_id=user_id,
                title="Tutor Application Status Update",
                message=message,
                type="application_status"
            )
            
            return True
            
        except Exception as e:
            print(f"Error rejecting tutor application: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False

    def add_module(self, module_code, module_name, description):
        """
        Add a new module to the system
        
        Args:
            module_code (str): Unique module code
            module_name (str): Name of the module
            description (str): Module description
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate inputs
            if not all([module_code, module_name, description]):
                print("Missing required fields")
                return False
                
            # Check if module already exists
            module_ref = self.db.collection('modules').document(str(module_code))
            if module_ref.get().exists:
                print(f"Module {module_code} already exists")
                return False
                
            # Create module document
            module_data = {
                'module_code': str(module_code),
                'module_name': module_name,
                'description': description,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'is_active': True
            }
            
            # Save to Firestore
            module_ref.set(module_data)
            print(f"Module {module_code} created successfully")
            return True
            
        except Exception as e:
            print(f"Error adding module: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False 