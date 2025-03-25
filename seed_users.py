import firebase_admin
from firebase_admin import credentials, auth, firestore
from werkzeug.security import generate_password_hash
import datetime

# Initialize Firebase Admin
cred = credentials.Certificate('service-account.json')
firebase_admin.initialize_app(cred)

# Get Firestore client
db = firestore.client()

# Sample users to seed
users = [
    # Admin users
    {
        'name': 'Nkosinathi Zulu',
        'email': 'nkosinathi.z@dut4life.ac.za',
        'password': 'Admin123!',
        'role': 'admin',
        'staff_number': None
    },
    {
        'name': 'Thembalihle Ndlovu',
        'email': 'thembalihle.n@dut4life.ac.za',
        'password': 'Admin123!',
        'role': 'admin',
        'staff_number': None
    },
    
    # Tutor users
    {
        'name': 'Zanele Buthelezi',
        'email': '216052@dut.ac.za',
        'password': 'Tutor123!',
        'role': 'tutor',
        'staff_number': '216052'
    },
    {
        'name': 'Sibusiso Dlamini',
        'email': '218034@dut.ac.za',
        'password': 'Tutor123!',
        'role': 'tutor',
        'staff_number': '218034'
    },
    
    # Student users
    {
        'name': 'Nokuthula Mtshali',
        'email': '22145632@dut.ac.za',
        'password': 'Student123!',
        'role': 'student',
        'student_number': '22145632'
    },
    {
        'name': 'Thabo Mkhize',
        'email': '21234567@dut.ac.za',
        'password': 'Student123!',
        'role': 'student',
        'student_number': '21234567'
    }
]

def seed_users():
    """Seed users into Firebase Authentication and Firestore"""
    for user_data in users:
        try:
            # Create user in Firebase Authentication
            user = auth.create_user(
                email=user_data['email'],
                password=user_data['password'],
                display_name=user_data['name']
            )
            
            # Prepare user document data
            user_doc = {
                'name': user_data['name'],
                'email': user_data['email'],
                'role': user_data['role'],
                'created_at': datetime.datetime.now(),
                'is_verified': True
            }
            
            # Add student/staff number if present
            if user_data.get('student_number'):
                user_doc['student_number'] = user_data['student_number']
            if user_data.get('staff_number'):
                user_doc['staff_number'] = user_data['staff_number']
            
            # Add user data to Firestore
            user_ref = db.collection('users').document(user.uid)
            user_ref.set(user_doc)
            
            print(f"Successfully created user: {user_data['name']} ({user_data['role']}) - {user_data['email']}")
            
        except Exception as e:
            print(f"Error creating user {user_data['name']}: {str(e)}")

if __name__ == '__main__':
    print("Starting user seeding process...")
    seed_users()
    print("User seeding completed!") 