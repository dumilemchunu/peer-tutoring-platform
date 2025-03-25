import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# Initialize Firebase Admin if not already initialized
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate('service-account.json')
    firebase_admin.initialize_app(cred)

# Get Firestore client
db = firestore.client()

# Sample modules to seed
modules = [
    {
        'module_code': 'PROG101',
        'module_name': 'Introduction to Programming',
        'description': 'A beginner-friendly introduction to programming concepts and practices using Python.'
    },
    {
        'module_code': 'MATH201',
        'module_name': 'Advanced Mathematics',
        'description': 'Advanced mathematical concepts including calculus, linear algebra, and differential equations.'
    },
    {
        'module_code': 'CSCI312',
        'module_name': 'Data Structures and Algorithms',
        'description': 'Study of fundamental data structures and algorithms for efficient software development.'
    },
    {
        'module_code': 'PHYS110',
        'module_name': 'Introduction to Physics',
        'description': 'Basic physics principles, mechanics, thermodynamics, and electromagnetism.'
    },
    {
        'module_code': 'CHEM120',
        'module_name': 'General Chemistry',
        'description': 'Introduction to chemistry principles, atomic structure, and chemical reactions.'
    },
    {
        'module_code': 'STAT250',
        'module_name': 'Statistics and Probability',
        'description': 'Statistical methods, probability theory, and data analysis techniques.'
    },
    {
        'module_code': 'DB310',
        'module_name': 'Database Systems',
        'description': 'Design and implementation of database systems, SQL, and data modeling.'
    },
    {
        'module_code': 'WEB320',
        'module_name': 'Web Development',
        'description': 'Modern web development techniques, frameworks, and responsive design.'
    }
]

def seed_modules():
    """Seed modules into Firestore"""
    print("Starting module seeding process...")
    
    for module_data in modules:
        try:
            # Check if module already exists
            module_ref = db.collection('modules').document(module_data['module_code'])
            module = module_ref.get()
            
            if module.exists:
                print(f"Module {module_data['module_code']} already exists. Skipping.")
                continue
                
            # Add created_at timestamp
            module_data['created_at'] = datetime.datetime.now()
            
            # Add module to Firestore
            module_ref.set(module_data)
            
            print(f"Successfully created module: {module_data['module_name']} ({module_data['module_code']})")
            
        except Exception as e:
            print(f"Error creating module {module_data['module_code']}: {str(e)}")
    
    print("Module seeding completed!")

if __name__ == '__main__':
    seed_modules() 