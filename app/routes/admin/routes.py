from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import User
from app.services.firebase_service import FirebaseService

admin_bp = Blueprint('admin', __name__)
firebase_service = FirebaseService()

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Get all modules and their content
    modules = firebase_service.get_all_modules()
    module_content = {}
    for module in modules:
        module_content[module['module_code']] = firebase_service.get_module_content(module['module_code'])
    
    return render_template('admin/admin.html',
                         modules=modules,
                         module_content=module_content)

@admin_bp.route('/add-module', methods=['GET', 'POST'])
@login_required
def add_module():
    if not current_user.is_admin:
        flash('Access denied. You must be an administrator to view this page.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        module_code = request.form.get('module_code')
        module_name = request.form.get('module_name')
        description = request.form.get('description')
        
        try:
            firebase_service.add_module(
                module_code=module_code,
                module_name=module_name,
                description=description
            )
            flash('Module added successfully', 'success')
        except Exception as e:
            flash(f'Error adding module: {str(e)}', 'error')
        
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/add_module.html') 