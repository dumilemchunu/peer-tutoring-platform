# Tutor Booking Application

A Flask-based application for students to book tutoring sessions with tutors for various academic modules.

## Features

- User authentication for students and tutors
- Module browsing and tutor selection
- Session scheduling with availability checking
- Learning content management
- Student feedback collection
- Responsive design for all devices

## Technology Stack

- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **Backend**: Python, Flask
- **Database**: Firebase Firestore
- **Authentication**: Flask-Login with Firebase
- **Deployment**: Render

## Local Development Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd tutor-booking-app
```

2. **Set up a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Firebase Setup**

- Create a Firebase project at [firebase.google.com](https://firebase.google.com)
- Set up Firestore database
- Generate a private key for your service account
- Save the key as `service-account.json` in the project root

5. **Environment Configuration**

- Copy `.env.example` to `.env`
- Update the values in `.env` with your configuration

6. **Run the application**

```bash
python run.py
```

## Deploying to Render

This application can be deployed to [Render](https://render.com) using the included `render.yaml` file.

### One-Click Deployment

1. Fork this repository to your GitHub account
2. Create a new Render account or sign in to your existing account
3. Click "New +" and select "Blueprint"
4. Connect your GitHub account and select your forked repository
5. Render will detect the `render.yaml` file and automatically set up your services

### Manual Deployment

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Use the following settings:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn 'app:create_app()' --config gunicorn_config.py`
4. Configure environment variables:
   - `SECRET_KEY`: Generate a secure random key
   - `FLASK_ENV`: Set to `production`
   - `DEMO_MODE`: Set to `True` or `False` depending on whether you want to use demo data
   - `FIREBASE_CREDENTIALS`: Paste the entire contents of your `service-account.json` file

### Important Notes for Render Deployment

- Firebase credentials should be stored as an environment variable in Render, not as a file
- Set `DEMO_MODE=True` if you don't want to connect to a real Firebase instance
- Make sure to set `FLASK_ENV=production` for security

## License

[MIT License](LICENSE) 