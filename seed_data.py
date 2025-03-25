from app import create_app
from app.services.firebase_service import FirebaseService

def seed_database():
    """Seed the database with initial data"""
    print("Starting database seeding...")
    
    # Create app context for Flask app
    app = create_app()
    with app.app_context():
        # Initialize Firebase service
        firebase_service = FirebaseService()
        
        # Seed modules
        print("\nSeeding modules...")
        firebase_service.seed_modules()
        
        # Seed tutors
        print("\nSeeding tutors...")
        firebase_service.seed_tutors()
        
        # Seed students
        print("\nSeeding students...")
        firebase_service.seed_students()
        
        # Seed tutor availability
        print("\nSeeding tutor availability...")
        firebase_service.seed_tutor_availability()
        
        # Seed bookings
        print("\nSeeding bookings...")
        firebase_service.seed_bookings()
        
        print("\nDatabase seeding completed!")

if __name__ == "__main__":
    seed_database() 