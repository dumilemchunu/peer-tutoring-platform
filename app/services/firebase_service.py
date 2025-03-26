import os
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore, auth, initialize_app
from google.cloud.firestore import Client as FirestoreClient
from datetime import datetime, timedelta, timezone
import uuid
import base64
from app.utils.date_utils import parse_date
from typing import Dict, List, Optional, Tuple, Any
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
            print("Initializing Firebase Admin SDK...")
            try:
                # Try to get existing app
                self.app = firebase_admin.get_app()
                print("Firebase already initialized, reusing existing app")
            except ValueError:
                print("Initializing Firebase with credentials from environment variables...")
                # Initialize new app
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                    "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
                    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
                })
                self.app = initialize_app(cred)
            
            self.db = firestore.client()
            print("Firestore client initialized successfully")
            FirebaseService._initialized = True

    def _ensure_db(self):
        """Ensure database connection is available"""
        return True  # Always return True since we require Firebase

    # Booking related operations
    def create_booking(self, student_id, tutor_id, module_code, session_date, time_slot, notes=''):
        """
        Create a new tutoring session booking
        
        Args:
            student_id (str): The student's user ID
            tutor_id (str): The tutor's user ID
            module_code (str): The module code
            session_date (str): Session date in YYYY-MM-DD format
            time_slot (str): Time slot in format "HH:MM - HH:MM"
            notes (str, optional): Additional notes for the session
            
        Returns:
            dict: Result with success status and booking ID or error message
        """
        try:
            print(f"DEBUG: create_booking called with: student_id={student_id}, tutor_id={tutor_id}, module_code={module_code}")
            print(f"DEBUG: session_date={session_date}, time_slot={time_slot}")
            
            # Validate required fields
            if not all([student_id, tutor_id, module_code, session_date, time_slot]):
                return {
                    'success': False,
                    'error': 'Missing required fields for booking'
                }
                
            # Parse the time slot to get start and end times
            try:
                start_time, end_time = time_slot.split(' - ')
            except ValueError:
                return {
                    'success': False,
                    'error': 'Invalid time slot format'
                }
            
            # Create the session document
            session_ref = self.db.collection('sessions').document()
            
            # Get student and tutor data for reference
            try:
                student = self.db.collection('users').document(student_id).get().to_dict() or {}
                tutor = self.db.collection('users').document(tutor_id).get().to_dict() or {}
                module = self.db.collection('modules').document(module_code).get().to_dict() or {}
                
                student_name = student.get('name', 'Unknown Student')
                tutor_name = tutor.get('name', 'Unknown Tutor')
                module_name = module.get('name', f"Module {module_code}")
            except Exception as e:
                print(f"WARNING: Error retrieving related data: {e}")
                student_name = 'Unknown Student'
                tutor_name = 'Unknown Tutor'
                module_name = f"Module {module_code}"
            
            session_data = {
                'id': session_ref.id,  # Store ID in the document itself for easier reference
                'student_id': student_id,
                'tutor_id': tutor_id,
                'module_code': module_code,
                'date': session_date,
                'start_time': start_time,
                'end_time': end_time,
                'time_slot': time_slot,
                'status': 'pending',  # Start as pending for tutor to confirm
                'created_at': firestore.SERVER_TIMESTAMP,
                'location': 'Online',  # Default location
                'notes': notes,
                'has_feedback': False,
                'student_name': student_name,
                'tutor_name': tutor_name,
                'module_name': module_name
            }
            
            print(f"DEBUG: Creating session with data: {session_data}")
            session_ref.set(session_data)
            
            # Create notifications
            try:
                # Notification for tutor
                self._create_notification(
                    user_id=tutor_id,
                    title="New Session Booking Request",
                    message=f"A student has requested a tutoring session with you on {session_date} at {start_time}. Please confirm or reject this request.",
                    type="booking",
                    reference_id=session_ref.id
                )
                
                # Notification for student
                self._create_notification(
                    user_id=student_id,
                    title="Session Booking Submitted",
                    message=f"Your tutoring session request has been submitted for {session_date} at {start_time}. Waiting for tutor confirmation.",
                    type="booking",
                    reference_id=session_ref.id
                )
            except Exception as notif_error:
                print(f"WARNING: Failed to create notifications: {notif_error}")
                # Continue even if notifications fail
            
            print(f"DEBUG: Booking created successfully with ID: {session_ref.id}")
            return {
                'success': True,
                'booking_id': session_ref.id
            }
            
        except Exception as e:
            print(f"ERROR: Failed to create booking: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_tutor_bookings(self, tutor_id):
        """
        Get all bookings for a tutor
        
        Args:
            tutor_id (str): The tutor's ID
            
        Returns:
            list: List of booking objects
        """
        try:
            # Query sessions collection for bookings with this tutor
            bookings = []
            
            print(f"DEBUG: Querying for bookings with tutor_id={tutor_id}")
            
            try:
                # Ensure the tutor_id is a string
                tutor_id_str = str(tutor_id)
                
                # Query the sessions collection
                sessions_ref = self.db.collection('sessions')
                query = sessions_ref.where('tutor_id', '==', tutor_id_str)
                docs = list(query.stream())
                print(f"DEBUG: Query returned {len(docs)} results")
                
                for doc in docs:
                    booking_data = doc.to_dict()
                    booking_data['id'] = doc.id  # Ensure ID is set
                    
                    # Get student name if not present
                    if not booking_data.get('student_name'):
                        try:
                            student = self.db.collection('users').document(booking_data.get('student_id')).get().to_dict() or {}
                            booking_data['student_name'] = student.get('name', 'Unknown Student')
                            booking_data['student_email'] = student.get('email', '')
                            booking_data['student_number'] = student.get('student_number', '')
                        except Exception as e:
                            print(f"ERROR: Failed to get student data: {e}")
                            booking_data['student_name'] = 'Unknown Student'
                    
                    # Get module name if not present
                    if not booking_data.get('module_name') and booking_data.get('module_code'):
                        try:
                            module = self.db.collection('modules').document(booking_data.get('module_code')).get().to_dict() or {}
                            booking_data['module_name'] = module.get('name', f"Module {booking_data.get('module_code')}")
                        except Exception as e:
                            print(f"ERROR: Failed to get module data: {e}")
                            booking_data['module_name'] = f"Module {booking_data.get('module_code')}"
                    
                    # Ensure time_slot is set
                    if not booking_data.get('time_slot') and booking_data.get('start_time') and booking_data.get('end_time'):
                        booking_data['time_slot'] = f"{booking_data.get('start_time')} - {booking_data.get('end_time')}"
                    
                    # Ensure status is lowercase for consistency
                    if booking_data.get('status'):
                        booking_data['status'] = booking_data.get('status').lower()
                    else:
                        booking_data['status'] = 'pending'  # Default status
                    
                    bookings.append(booking_data)
                
                # Sort bookings by date and time
                bookings.sort(key=lambda x: (x.get('date', ''), x.get('start_time', '')))
                
                print(f"DEBUG: Found {len(bookings)} valid bookings for tutor {tutor_id}")
                return bookings
                
            except Exception as db_error:
                print(f"ERROR: Database query failed: {str(db_error)}")
                import traceback
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                return []
            
        except Exception as e:
            print(f"ERROR: Failed to get tutor bookings: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return []
    
    def _get_demo_tutor_bookings(self, tutor_id):
        """Generate demo bookings for a tutor"""
        today = datetime.now()
        
        # Generate demo bookings with various statuses
        return [
            {
                'id': f'demo_booking1_{tutor_id}',
                'student_id': 'demo_student1',
                'student_name': 'John Smith',
                'student_email': 'john.smith@dut4life.ac.za',
                'student_number': '21234567',
                'tutor_id': tutor_id,
                'module_code': 'DAST401',
                'module_name': 'Data Structures',
                'date': (today + timedelta(days=1)).strftime('%Y-%m-%d'),
                'time_slot': '10:00 - 11:00',
                'start_time': '10:00',
                'end_time': '11:00',
                'status': 'pending',
                'notes': 'Need help with arrays and linked lists'
            },
            {
                'id': f'demo_booking2_{tutor_id}',
                'student_id': 'demo_student2',
                'student_name': 'Emily Johnson',
                'student_email': 'emily.johnson@dut4life.ac.za',
                'student_number': '21345678',
                'tutor_id': tutor_id,
                'module_code': 'PBDE401',
                'module_name': 'Platform Based Development',
                'date': (today + timedelta(days=2)).strftime('%Y-%m-%d'),
                'time_slot': '14:00 - 15:00',
                'start_time': '14:00',
                'end_time': '15:00',
                'status': 'confirmed',
                'notes': 'Have questions about Flask routes'
            },
            {
                'id': f'demo_booking3_{tutor_id}',
                'student_id': 'demo_student3',
                'student_name': 'Michael Brown',
                'student_email': 'michael.brown@dut4life.ac.za',
                'student_number': '21456789',
                'tutor_id': tutor_id,
                'module_code': 'RESK401',
                'module_name': 'Research Skills',
                'date': (today + timedelta(days=3)).strftime('%Y-%m-%d'),
                'time_slot': '11:00 - 12:00',
                'start_time': '11:00',
                'end_time': '12:00',
                'status': 'completed',
                'notes': 'Need help with literature review'
            },
            {
                'id': f'demo_booking4_{tutor_id}',
                'student_id': 'demo_student4',
                'student_name': 'Sarah Wilson',
                'student_email': 'sarah.wilson@dut4life.ac.za',
                'student_number': '21567890',
                'tutor_id': tutor_id,
                'module_code': 'DAST401',
                'module_name': 'Data Structures',
                'date': (today + timedelta(days=1)).strftime('%Y-%m-%d'),
                'time_slot': '13:00 - 14:00',
                'start_time': '13:00',
                'end_time': '14:00',
                'status': 'rejected',
                'notes': 'Having trouble with binary trees'
            },
            {
                'id': f'demo_booking5_{tutor_id}',
                'student_id': 'demo_student5',
                'student_name': 'David Clark',
                'student_email': 'david.clark@dut4life.ac.za',
                'student_number': '21678901',
                'tutor_id': tutor_id,
                'module_code': 'PBDE401',
                'module_name': 'Platform Based Development',
                'date': (today + timedelta(days=4)).strftime('%Y-%m-%d'),
                'time_slot': '15:00 - 16:00',
                'start_time': '15:00',
                'end_time': '16:00',
                'status': 'canceled',
                'notes': 'Need help with database integration'
            }
        ]
    
    def update_booking_status(self, booking_id, action):
        """
        Update the status of a booking
        
        Args:
            booking_id (str): The booking ID
            action (str): The action to perform ('confirm', 'reject', 'cancel')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Map action to status
            status_map = {
                'confirm': 'confirmed',
                'reject': 'rejected',
                'cancel': 'canceled'
            }
            
            if action not in status_map:
                print(f"ERROR: Invalid action '{action}'")
                return False
            
            new_status = status_map[action]
            
            # Update booking status
            booking_ref = self.db.collection('sessions').document(booking_id)
            booking_data = booking_ref.get().to_dict()
            
            if not booking_data:
                print(f"ERROR: Booking {booking_id} not found")
                return False
            
            # Update status
            booking_ref.update({'status': new_status})
            
            # Create notification for student
            try:
                student_id = booking_data.get('student_id')
                date = booking_data.get('date')
                start_time = booking_data.get('start_time')
                
                if student_id:
                    message = f"Your tutoring session for {date} at {start_time} has been {new_status}."
                    self._create_notification(
                        user_id=student_id,
                        title=f"Session {new_status.capitalize()}",
                        message=message,
                        type="booking_update",
                        reference_id=booking_id
                    )
            except Exception as notif_error:
                print(f"WARNING: Failed to create notification: {notif_error}")
                # Continue even if notification fails
            
            print(f"DEBUG: Successfully updated booking {booking_id} status to {new_status}")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to update booking status: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return False

    def get_module(self, module_code):
        """Get module data by code"""
        try:
            print(f"Getting module data for code: {module_code}")
            # Get module document
            module_doc = self.db.collection('modules').document(str(module_code)).get()
            
            if not module_doc.exists:
                print(f"Module {module_code} not found")
                return None
                
            module_data = module_doc.to_dict()
            if module_data:
                module_data['code'] = module_code  # Ensure code is included in the data
                module_data['module_code'] = module_code  # Add for consistency
                print(f"Successfully retrieved module: {module_code}")
                return module_data
            else:
                print(f"Module {module_code} exists but has no data")
                return None
            
        except Exception as e:
            print(f"Error getting module {module_code}: {str(e)}")
            import traceback
            print(traceback.format_exc())
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
                return []
            
        except Exception as e:
            print(f"ERROR: Unexpected error in get_tutor_schedule: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return []

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
            
            # Validate module exists first
            module = self.get_module(module_code)
            if not module:
                print(f"WARNING: Module {module_code} not found")
                return []
            
            # Query for module-tutor assignments
            print(f"DEBUG: Querying module_tutors collection for module {module_code}")
            module_tutors_ref = self.db.collection('module_tutors')
            query = module_tutors_ref.where('module_code', '==', str(module_code))
            assignments = list(query.stream())  # Convert to list to check length
            print(f"DEBUG: Found {len(assignments)} assignments for module {module_code}")
            
            tutors = []
            for assignment in assignments:
                try:
                    assignment_data = assignment.to_dict()
                    tutor_id = assignment_data.get('tutor_id')
                    print(f"DEBUG: Processing assignment {assignment.id} for tutor_id: {tutor_id}")
                    
                    if not tutor_id:
                        print(f"WARNING: Missing tutor_id in assignment {assignment.id}")
                        continue
                    
                    # Get tutor details
                    tutor = self.get_user_by_id(tutor_id)
                    if tutor:
                        # Get assignment timestamp
                        assigned_at = assignment_data.get('assigned_at')
                        if assigned_at:
                            if hasattr(assigned_at, 'timestamp'):
                                # Convert Firestore timestamp to datetime
                                assigned_at = datetime.fromtimestamp(assigned_at.timestamp(), tz=timezone.utc)
                                assigned_at = assigned_at.strftime('%Y-%m-%d %H:%M:%S UTC')
                        else:
                            assigned_at = 'Unknown'

                        tutor_info = {
                            'assignment_id': assignment.id,
                            'id': tutor_id,
                            'tutor_id': tutor_id,
                            'name': tutor.get('name', 'Unknown Tutor'),
                            'email': tutor.get('email', ''),
                            'staff_number': tutor.get('staff_number', 'N/A'),
                            'assigned_at': assigned_at,
                            'qualifications': tutor.get('qualifications', ''),
                            'experience': tutor.get('experience', '')
                        }
                        tutors.append(tutor_info)
                        print(f"DEBUG: Added tutor {tutor_info['name']} to results with assignment date {assigned_at}")
                    else:
                        print(f"WARNING: Could not find tutor with ID {tutor_id}")
                        
                except Exception as assignment_error:
                    print(f"ERROR processing assignment {assignment.id}: {str(assignment_error)}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            # Sort tutors by assignment date, newest first
            tutors.sort(
                key=lambda x: x.get('assigned_at', ''),
                reverse=True
            )
            
            print(f"DEBUG: Returning {len(tutors)} tutors found for module {module_code}")
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
            
    def get_tutor_modules(self, tutor_id):
        """
        Get all modules assigned to a specific tutor
        
        Args:
            tutor_id (str): The tutor's ID
            
        Returns:
            list: List of module objects with assignment details
        """
        try:
            print(f"DEBUG: Getting modules for tutor {tutor_id}")
            
            # Query for module-tutor assignments
            print(f"DEBUG: Querying module_tutors collection for tutor {tutor_id}")
            module_tutors_ref = self.db.collection('module_tutors')
            query = module_tutors_ref.where('tutor_id', '==', str(tutor_id))
            assignments = list(query.stream())  # Convert to list to check length
            print(f"DEBUG: Found {len(assignments)} module assignments for tutor {tutor_id}")
            
            modules = []
            for assignment in assignments:
                try:
                    assignment_data = assignment.to_dict()
                    module_code = assignment_data.get('module_code')
                    print(f"DEBUG: Processing assignment {assignment.id} for module_code: {module_code}")
                    
                    if not module_code:
                        print(f"WARNING: Missing module_code in assignment {assignment.id}")
                        continue
                    
                    # Get module details
                    module = self.get_module(module_code)
                    if module:
                        # Get assignment timestamp
                        assigned_at = assignment_data.get('assigned_at')
                        if assigned_at and hasattr(assigned_at, 'timestamp'):
                            # Convert Firestore timestamp to datetime
                            assigned_at = datetime.fromtimestamp(assigned_at.timestamp())
                        else:
                            assigned_at = datetime.now()  # Default to current time

                        module_info = {
                            'assignment_id': assignment.id,
                            'module_code': module_code,
                            'module_name': module.get('name', f'Module {module_code}'),
                            'description': module.get('description', ''),
                            'assigned_at': assigned_at
                        }
                        modules.append(module_info)
                        print(f"DEBUG: Added module {module_info['module_name']} to results")
                    else:
                        print(f"WARNING: Could not find module with code {module_code}")
                        
                except Exception as assignment_error:
                    print(f"ERROR processing assignment {assignment.id}: {str(assignment_error)}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            # Sort modules by assignment date
            modules.sort(key=lambda x: x.get('assigned_at', datetime.now()), reverse=True)
            
            print(f"DEBUG: Returning {len(modules)} modules for tutor {tutor_id}")
            return modules
            
        except Exception as e:
            print(f"ERROR in get_tutor_modules: {str(e)}")
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
        """
        Get system statistics for the admin dashboard
        
        Returns:
            dict: System statistics
        """
        try:
            # Count active students
            student_query = self.db.collection('users').where('role', '==', 'student').where('is_verified', '==', True)
            student_count = len(list(student_query.stream()))
            
            # Count active tutors
            tutor_query = self.db.collection('users').where('role', '==', 'tutor').where('is_verified', '==', True)
            tutor_count = len(list(tutor_query.stream()))
            
            # Count modules
            modules_query = self.db.collection('modules')
            module_count = len(list(modules_query.stream()))
            
            # Count pending tutor applications
            pending_tutors_query = self.db.collection('tutor_applications').where('status', '==', 'pending')
            pending_tutors_count = len(list(pending_tutors_query.stream()))
            
            # Count pending student applications
            pending_students_query = self.db.collection('users').where('role', '==', 'student').where('is_verified', '==', False)
            pending_students_count = len(list(pending_students_query.stream()))
            
            # Count recent bookings (last 7 days)
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            recent_bookings_query = self.db.collection('sessions').where('created_at', '>=', seven_days_ago)
            recent_bookings_count = len(list(recent_bookings_query.stream()))
            
            # Calculate total session hours
            all_sessions_query = self.db.collection('sessions').where('status', '==', 'completed')
            total_hours = 0
            for session in all_sessions_query.stream():
                data = session.to_dict()
                # Extract hour from time slots like "14:00 - 15:00"
                try:
                    if 'time_slot' in data:
                        start, end = data['time_slot'].split(' - ')
                        start_hour = int(start.split(':')[0])
                        end_hour = int(end.split(':')[0])
                        session_duration = end_hour - start_hour
                        if session_duration > 0:
                            total_hours += session_duration
                except Exception as e:
                    print(f"Error calculating session hours: {str(e)}")
                    continue
            
            return {
                'student_count': student_count,
                'tutor_count': tutor_count,
                'module_count': module_count,
                'pending_tutors_count': pending_tutors_count,
                'pending_students_count': pending_students_count,
                'recent_bookings_count': recent_bookings_count,
                'total_hours': total_hours
            }
            
        except Exception as e:
            print(f"Error getting system statistics: {str(e)}")
            return {
                'student_count': 0,
                'tutor_count': 0,
                'module_count': 0,
                'pending_tutors_count': 0,
                'pending_students_count': 0,
                'recent_bookings_count': 0,
                'total_hours': 0
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

    def get_student_bookings(self, student_id):
        """Get all bookings for a student regardless of status"""
        try:
            print(f"Getting all bookings for student {student_id}")
            # Query for all sessions for this student
            sessions_ref = self.db.collection('sessions')
            query = sessions_ref.where('student_id', '==', str(student_id))
            
            bookings = []
            for doc in query.stream():
                booking_data = doc.to_dict()
                
                # Make sure it has required fields for display
                if not booking_data.get('id'):
                    booking_data['id'] = doc.id
                
                # Get tutor name if not present
                if not booking_data.get('tutor_name'):
                    try:
                        tutor = self.db.collection('users').document(booking_data.get('tutor_id', '')).get().to_dict() or {}
                        booking_data['tutor_name'] = tutor.get('name', 'Unknown Tutor')
                    except Exception as e:
                        print(f"ERROR: Failed to get tutor data: {e}")
                        booking_data['tutor_name'] = 'Unknown Tutor'
                
                # Get module name if not present
                if not booking_data.get('module_name') and booking_data.get('module_code'):
                    try:
                        module = self.db.collection('modules').document(booking_data.get('module_code', '')).get().to_dict() or {}
                        booking_data['module_name'] = module.get('name', f"Module {booking_data.get('module_code')}")
                    except Exception as e:
                        print(f"ERROR: Failed to get module data: {e}")
                        booking_data['module_name'] = f"Module {booking_data.get('module_code')}"
                
                bookings.append(booking_data)
            
            # Sort bookings by date (most recent first) and then by status (pending first)
            def sort_key(booking):
                # Define a priority for statuses (pending should be first)
                status_priority = {
                    'pending': 0,
                    'confirmed': 1,
                    'completed': 2,
                    'cancelled': 3
                }
                
                status = booking.get('status', '').lower()
                date_str = booking.get('date', '')
                if not date_str:
                    return (0, 999)  # Default to lowest priority if no date
                
                return (status_priority.get(status, 999), date_str)
            
            return sorted(bookings, key=sort_key)
            
        except Exception as e:
            print(f"Error getting student bookings: {str(e)}")
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
                return None
                
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
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                return None
                
        except Exception as e:
            print(f"ERROR: Unexpected error in create_reservation: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
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
            
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: No valid database connection available")
                return None
                
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
                    'status': 'pending',
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
                        title="New Session Booking Request",
                        message=f"A student has requested a tutoring session with you on {session_data.get('date')} at {session_data.get('start_time')}. Please confirm or reject this request.",
                        type="booking",
                        reference_id=session_ref.id
                    )
                    
                    # For student
                    self._create_notification(
                        user_id=session_data.get('student_id'),
                        title="Session Booking Submitted",
                        message=f"Your tutoring session request has been submitted for {session_data.get('date')} at {session_data.get('start_time')}. Waiting for tutor confirmation.",
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
                print(f"DEBUG: Traceback: {traceback.format_exc()}")
                return None
                
        except Exception as e:
            print(f"ERROR: Unexpected error in confirm_reservation: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return None
    
    def cleanup_expired_reservations(self):
        """Clean up expired reservations to free up slots"""
        try:
            # Ensure we have a valid database connection
            if not self._ensure_db():
                print("ERROR: Database connection is not valid")
                return False
                
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
        Get all pending tutor applications with user details
        
        Returns:
            list: List of tutor applications with user information
        """
        try:
            applications = []
            # Get all pending applications
            docs = self.db.collection('tutor_applications').where('status', '==', 'pending').stream()
            
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
                            'email': user_data.get('email', 'No email'),
                            'staff_number': user_data.get('staff_number', 'Not provided'),
                            'student_number': user_data.get('student_number', 'Not provided')
                        })
                    else:
                        print(f"User not found for application {doc.id}")
                        app_data.update({
                            'name': 'Unknown User',
                            'email': 'No email',
                            'staff_number': 'Not found',
                            'student_number': 'Not found'
                        })
                
                # Convert timestamps to datetime objects
                if 'created_at' in app_data and app_data['created_at']:
                    if hasattr(app_data['created_at'], 'timestamp'):
                        app_data['created_at'] = datetime.fromtimestamp(app_data['created_at'].timestamp())
                
                applications.append(app_data)
            
            # Sort by creation date, newest first
            applications.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
            print(f"Retrieved {len(applications)} tutor applications")
            return applications
            
        except Exception as e:
            print(f"Error getting tutor applications: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def get_all_users(self):
        """Get all users with their roles and details"""
        try:
            print("Starting to fetch users from Firebase...")
            users = []
            users_ref = self.db.collection('users')
            
            # Get all users
            docs = list(users_ref.stream())  # Convert to list to catch potential stream errors
            print(f"Successfully connected to users collection. Found {len(docs)} documents.")
            
            for doc in docs:
                try:
                    print(f"Processing user document: {doc.id}")
                    user_data = doc.to_dict()
                    if not user_data:
                        print(f"Warning: Empty user data for document {doc.id}")
                        continue
                        
                    # Add the document ID to the data
                    user_data['id'] = doc.id
                    
                    # Add default values for required fields if missing
                    user_data.setdefault('name', 'Unknown User')
                    user_data.setdefault('email', 'No email')
                    user_data.setdefault('role', 'student')
                    user_data.setdefault('is_verified', False)
                    user_data.setdefault('student_number', 'N/A')
                    user_data.setdefault('staff_number', 'N/A')
                    
                    # Handle created_at timestamp
                    created_at = user_data.get('created_at')
                    if not created_at:
                        user_data['created_at'] = datetime.now(timezone.utc)
                    elif isinstance(created_at, (firestore.SERVER_TIMESTAMP.__class__, type(None))):
                        user_data['created_at'] = datetime.now(timezone.utc)
                    elif hasattr(created_at, 'timestamp'):
                        # Convert to datetime if it's a Firestore timestamp
                        user_data['created_at'] = datetime.fromtimestamp(created_at.timestamp(), tz=timezone.utc)
                    
                    # Format the datetime for display
                    if isinstance(user_data['created_at'], datetime):
                        user_data['created_at'] = user_data['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')
                    
                    # Ensure role is properly formatted
                    user_data['role'] = user_data['role'].capitalize()
                    
                    # Format verification status
                    user_data['is_verified'] = 'Yes' if user_data['is_verified'] else 'No'
                    
                    print(f"Successfully processed user: {user_data.get('email', 'No email')}")
                    users.append(user_data)
                    
                except Exception as e:
                    print(f"Error processing user document {doc.id}: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            # Sort users by creation date (newest first)
            users.sort(
                key=lambda x: datetime.strptime(x['created_at'], '%Y-%m-%d %H:%M:%S UTC') 
                if isinstance(x['created_at'], str) else datetime.now(timezone.utc),
                reverse=True
            )
            
            print(f"Successfully retrieved {len(users)} users from database")
            return users
            
        except Exception as e:
            print(f"Error getting all users: {str(e)}")
            import traceback
            print(traceback.format_exc())
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
                'status': 'approved',
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
            reason (str): Reason for rejection
            
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
                'status': 'rejected',
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

    def get_available_tutors(self, exclude_module_code=None):
        """
        Get all available tutors that can be assigned to modules
        
        Args:
            exclude_module_code (str, optional): Module code to exclude tutors from (for reassignment)
            
        Returns:
            list: List of available tutors with their details
        """
        try:
            print(f"Getting available tutors (excluding module {exclude_module_code})")
            
            # Get all users with tutor role
            tutors = []
            users_ref = self.db.collection('users')
            tutor_docs = users_ref.where('role', '==', 'tutor').stream()
            
            for doc in tutor_docs:
                tutor_data = doc.to_dict()
                tutor_id = doc.id
                
                # Skip if no data
                if not tutor_data:
                    continue
                
                # If excluding a module, check if tutor is already assigned
                if exclude_module_code:
                    module_tutors_ref = self.db.collection('module_tutors')
                    existing_assignment = module_tutors_ref.where('tutor_id', '==', tutor_id)\
                                                         .where('module_code', '==', exclude_module_code)\
                                                         .limit(1)\
                                                         .stream()
                    
                    # Skip if already assigned to this module
                    if len(list(existing_assignment)) > 0:
                        continue
                
                # Add tutor to list with required fields
                tutors.append({
                    'id': tutor_id,
                    'name': tutor_data.get('name', 'Unknown Tutor'),
                    'email': tutor_data.get('email', ''),
                    'staff_number': tutor_data.get('staff_number', 'N/A'),
                    'qualifications': tutor_data.get('qualifications', ''),
                    'experience': tutor_data.get('experience', ''),
                    'modules': tutor_data.get('modules', [])
                })
            
            print(f"Found {len(tutors)} available tutors")
            return tutors
            
        except Exception as e:
            print(f"Error getting available tutors: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def assign_tutor_to_module(self, tutor_id, module_code):
        """
        Assign a tutor to a module
        
        Args:
            tutor_id (str): The ID of the tutor to assign
            module_code (str): The module code to assign the tutor to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print(f"Assigning tutor {tutor_id} to module {module_code}")
            
            # Validate inputs
            if not tutor_id or not module_code:
                print("Missing required fields")
                return False
            
            # Check if tutor exists and is actually a tutor
            tutor = self.get_user_by_id(tutor_id)
            if not tutor or tutor.get('role', '').lower() != 'tutor':
                print(f"Invalid tutor ID or user is not a tutor: {tutor_id}")
                return False
            
            # Check if module exists
            module = self.get_module(module_code)
            if not module:
                print(f"Module not found: {module_code}")
                return False
            
            # Check if assignment already exists
            module_tutors_ref = self.db.collection('module_tutors')
            existing_assignment = module_tutors_ref.where('tutor_id', '==', tutor_id)\
                                                 .where('module_code', '==', module_code)\
                                                 .limit(1)\
                                                 .stream()
            
            if len(list(existing_assignment)) > 0:
                print(f"Tutor {tutor_id} is already assigned to module {module_code}")
                return False
            
            # Create the assignment
            assignment_id = f"{module_code}_{tutor_id}"
            assignment_data = {
                'module_code': module_code,
                'tutor_id': tutor_id,
                'name': tutor.get('name', 'Unknown Tutor'),
                'email': tutor.get('email', ''),
                'assigned_at': firestore.SERVER_TIMESTAMP
            }
            
            # Save to Firestore
            module_tutors_ref.document(assignment_id).set(assignment_data)
            
            # Create notification for the tutor
            self._create_notification(
                user_id=tutor_id,
                title="New Module Assignment",
                message=f"You have been assigned to teach {module.get('module_name', module_code)}.",
                type="module_assignment",
                reference_id=assignment_id
            )
            
            print(f"Successfully assigned tutor {tutor_id} to module {module_code}")
            return True
            
        except Exception as e:
            print(f"Error assigning tutor to module: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False

    def unassign_tutor_from_module(self, assignment_id):
        """
        Remove a tutor's assignment from a module using the assignment ID
        
        Args:
            assignment_id (str): The ID of the assignment to remove (format: module_code_tutor_id)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print(f"Removing tutor assignment: {assignment_id}")
            
            # Validate input
            if not assignment_id:
                print("Missing assignment ID")
                return False
            
            # Get the assignment document
            module_tutors_ref = self.db.collection('module_tutors').document(assignment_id)
            assignment = module_tutors_ref.get()
            
            if not assignment.exists:
                print(f"No assignment found with ID: {assignment_id}")
                return False
                
            # Get assignment data for notification
            assignment_data = assignment.to_dict()
            module_code = assignment_data.get('module_code')
            tutor_id = assignment_data.get('tutor_id')
            
            # Delete the assignment
            module_tutors_ref.delete()
            
            # Create notification for the tutor if we have the necessary data
            if module_code and tutor_id:
                module = self.get_module(module_code)
                module_name = module.get('module_name', module_code) if module else module_code
                
                self._create_notification(
                    user_id=tutor_id,
                    title="Module Assignment Removed",
                    message=f"You have been removed from teaching {module_name}.",
                    type="module_assignment",
                    reference_id=assignment_id
                )
            
            print(f"Successfully removed assignment {assignment_id}")
            return True
            
        except Exception as e:
            print(f"Error removing tutor assignment: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False 

    def get_session(self, session_id):
        """Get session details by ID"""
        try:
            session_doc = self.db.collection('sessions').document(session_id).get()
            if not session_doc.exists:
                return None
                
            session_data = session_doc.to_dict()
            
            # Add ID to the data if not present
            if not session_data.get('id'):
                session_data['id'] = session_doc.id
                
            return session_data
            
        except Exception as e:
            print(f"Error getting session: {str(e)}")
            return None

    def update_session_status(self, session_id, new_status):
        """Update the status of a session"""
        try:
            # Valid statuses
            valid_statuses = ['pending', 'confirmed', 'completed', 'cancelled', 'rejected']
            
            # Check if the new status is valid
            if new_status.lower() not in valid_statuses:
                print(f"Invalid status: {new_status}")
                return False
            
            # Get the session document
            session_ref = self.db.collection('sessions').document(session_id)
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                print(f"Session {session_id} not found")
                return False
            
            # Update the status
            session_ref.update({
                'status': new_status.lower(),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            # Get the updated session data for notifications
            session_data = session_doc.to_dict()
            student_id = session_data.get('student_id')
            tutor_id = session_data.get('tutor_id')
            session_date = session_data.get('date')
            time_slot = session_data.get('time_slot')
            
            # Create notifications based on the new status
            try:
                # Notification for student
                student_message = ""
                if new_status.lower() == 'confirmed':
                    student_message = f"Your tutoring session on {session_date} at {time_slot} has been confirmed."
                elif new_status.lower() == 'cancelled':
                    student_message = f"Your tutoring session on {session_date} at {time_slot} has been cancelled."
                elif new_status.lower() == 'rejected':
                    student_message = f"Your tutoring session request for {session_date} at {time_slot} has been rejected."
                elif new_status.lower() == 'completed':
                    student_message = f"Your tutoring session on {session_date} at {time_slot} has been marked as completed."
                
                if student_message and student_id:
                    self._create_notification(
                        user_id=student_id,
                        title=f"Session {new_status.capitalize()}",
                        message=student_message,
                        type="booking",
                        reference_id=session_id
                    )
                
                # Notification for tutor
                tutor_message = ""
                if new_status.lower() == 'cancelled':
                    tutor_message = f"A session on {session_date} at {time_slot} has been cancelled."
                
                if tutor_message and tutor_id:
                    self._create_notification(
                        user_id=tutor_id,
                        title="Session Cancelled",
                        message=tutor_message,
                        type="booking",
                        reference_id=session_id
                    )
                    
            except Exception as notif_error:
                print(f"WARNING: Failed to create notifications: {notif_error}")
                # Continue even if notifications fail
            
            return True
            
        except Exception as e:
            print(f"Error updating session status: {str(e)}")
            return False

    def get_student_applications(self):
        """
        Get all pending student applications
        
        Returns:
            list: List of student applications
        """
        try:
            if not self._ensure_db():
                return []
                
            # Query for users with role='student' and is_verified=False
            query = self.db.collection('users').where('role', '==', 'student').where('is_verified', '==', False)
            
            applications = []
            docs = list(query.stream())
            
            for doc in docs:
                application = doc.to_dict()
                application['id'] = doc.id  # Add the document ID
                applications.append(application)
                
            # Sort by creation date, newest first
            applications.sort(key=lambda x: x.get('created_at', 0), reverse=True)
            
            return applications
            
        except Exception as e:
            print(f"Error getting student applications: {str(e)}")
            return []

    def approve_student_application(self, student_id):
        """
        Approve a student application
        
        Args:
            student_id (str): The ID of the student to approve
            
        Returns:
            bool: Success status
        """
        try:
            if not self._ensure_db():
                return False
                
            # Get the student document
            student_ref = self.db.collection('users').document(student_id)
            student_doc = student_ref.get()
            
            if not student_doc.exists:
                print(f"Student {student_id} not found")
                return False
                
            student_data = student_doc.to_dict()
            
            # Verify it's a student with pending status
            if student_data.get('role') != 'student' or student_data.get('is_verified', True):
                print(f"Invalid student application: {student_data}")
                return False
                
            # Update the student document
            student_ref.update({
                'is_verified': True,
                'student_status': 'approved',
                'approved_at': firestore.SERVER_TIMESTAMP,
            })
            
            # Create a notification for the student
            student_email = student_data.get('email')
            try:
                self._create_notification(
                    user_id=student_id,
                    title="Student Account Approved",
                    message="Your student account has been approved. You can now access the tutoring system.",
                    type="account",
                    reference_id=student_id
                )
            except Exception as notif_error:
                print(f"Error creating notification: {str(notif_error)}")
                
            print(f"Approved student application for {student_email}")
            return True
            
        except Exception as e:
            print(f"Error approving student application: {str(e)}")
            return False
    
    def reject_student_application(self, student_id, reason=''):
        """
        Reject a student application
        
        Args:
            student_id (str): The ID of the student to reject
            reason (str): The reason for rejection
            
        Returns:
            bool: Success status
        """
        try:
            if not self._ensure_db():
                return False
                
            # Get the student document
            student_ref = self.db.collection('users').document(student_id)
            student_doc = student_ref.get()
            
            if not student_doc.exists:
                print(f"Student {student_id} not found")
                return False
                
            student_data = student_doc.to_dict()
            
            # Verify it's a student with pending status
            if student_data.get('role') != 'student' or student_data.get('is_verified', True):
                print(f"Invalid student application: {student_data}")
                return False
                
            # Update the student document
            student_ref.update({
                'student_status': 'rejected',
                'rejection_reason': reason,
                'rejected_at': firestore.SERVER_TIMESTAMP,
            })
            
            # Create a notification for the student
            student_email = student_data.get('email')
            try:
                rejection_message = "Your student account application has been rejected."
                if reason:
                    rejection_message += f" Reason: {reason}"
                
                self._create_notification(
                    user_id=student_id,
                    title="Student Account Rejected",
                    message=rejection_message,
                    type="account",
                    reference_id=student_id
                )
            except Exception as notif_error:
                print(f"Error creating notification: {str(notif_error)}")
                
            print(f"Rejected student application for {student_email}")
            return True
            
        except Exception as e:
            print(f"Error rejecting student application: {str(e)}")
            return False