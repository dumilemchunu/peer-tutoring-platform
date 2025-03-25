from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from firebase_admin import firestore

main_bp = Blueprint('main', __name__)
db = firestore.client()

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'student':
            return redirect(url_for('student.home'))
        elif current_user.role == 'tutor':
            return redirect(url_for('tutor.dashboard'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'student':
        return redirect(url_for('student.home'))
    elif current_user.role == 'tutor':
        return redirect(url_for('tutor.dashboard'))
    elif current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('main.index'))
