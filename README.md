# Peer Tutoring Platform

A web-based platform that facilitates peer tutoring sessions between students and tutors at DUT. The platform allows students to book tutoring sessions, tutors to manage their availability and content, and administrators to oversee the system.

## Project Structure

```
app/
├── routes/
│   ├── admin/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── student/
│   │   ├── __init__.py
│   │   └── routes.py
│   └── tutor/
│       ├── __init__.py
│       └── routes.py
├── services/
│   └── firebase_service.py
├── templates/
│   ├── admin/
│   │   ├── admin.html
│   │   └── add_module.html
│   ├── student/
│   │   ├── student_home.html
│   │   ├── Book_tutor.html
│   │   └── submit_feedback.html
│   └── tutor/
│       ├── Tutor-Dashboard.html
│       ├── set_availability.html
│       └── upload_content.html
├── __init__.py
├── auth.py
├── main.py
└── models.py
```

## Features

### For Students
- View available tutors and their schedules
- Book tutoring sessions
- Submit feedback for completed sessions
- Access uploaded course content

### For Tutors
- Manage availability
- Upload course content
- View booked sessions
- See student feedback

### For Administrators
- Add and manage modules
- Monitor tutoring sessions
- Review feedback
- Manage user accounts

## Setup Instructions

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Firebase:
   - Create a Firebase project
   - Download the service account key and save it as `service-account.json` in the project root
   - Enable Firebase Authentication and Firestore

4. Configure environment variables:
   - Create a `.env` file in the project root
   - Add the following variables:
     ```
     FLASK_APP=run.py
     FLASK_ENV=development
     SECRET_KEY=your-secret-key
     ```

5. Initialize the database:
   ```bash
   python seed_users.py
   ```

6. Run the application:
   ```bash
   python run.py
   ```

## Dependencies

- Flask
- Flask-Login
- Firebase Admin SDK
- Python-dotenv

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a pull request

## License

This project is licensed under the MIT License. 