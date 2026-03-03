"""Admin routes: /admin/users."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..auth import admin_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import User
from ...user_management import UserManager

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/users')
@admin_required
def users():
    with db_manager.get_session() as session:
        manager = UserManager(session)
        user_list = manager.list_users(include_inactive=True)
    return render_template('admin/users.html', users=user_list, user=AuthContext.get_current_user())


@bp.route('/users/create', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    is_admin = bool(request.form.get('is_admin'))
    password = request.form.get('password', '').strip()

    if not username or not email:
        flash('Username and email are required.', 'danger')
        return redirect(url_for('admin.users'))

    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            user_obj, raw_api_key = manager.create_user(username, email, is_admin=is_admin)

            if password:
                user_obj.password_hash = generate_password_hash(password)

            session.commit()
            flash(
                f"User '{username}' created. API key: {raw_api_key} — save this now, it won't be shown again.",
                'success',
            )
    except ValueError as e:
        flash(f"Error: {e}", 'danger')
    except Exception as e:
        flash(f"Failed to create user: {e}", 'danger')

    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_user(target_user_id: int):
    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            manager.deactivate_user(target_user_id)
            session.commit()
            flash(f"User {target_user_id} deactivated.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/reactivate', methods=['POST'])
@admin_required
def reactivate_user(target_user_id: int):
    try:
        with db_manager.get_session() as session:
            manager = UserManager(session)
            manager.reactivate_user(target_user_id)
            session.commit()
            flash(f"User {target_user_id} reactivated.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:target_user_id>/set-password', methods=['POST'])
@admin_required
def set_password(target_user_id: int):
    password = request.form.get('password', '').strip()
    if not password:
        flash('Password cannot be empty.', 'danger')
        return redirect(url_for('admin.users'))
    try:
        with db_manager.get_session() as session:
            user_obj = session.get(User, target_user_id)
            if user_obj is None:
                flash('User not found.', 'danger')
                return redirect(url_for('admin.users'))
            user_obj.password_hash = generate_password_hash(password)
            session.commit()
            flash(f"Password set for user {target_user_id}.", 'success')
    except Exception as e:
        flash(f"Failed: {e}", 'danger')
    return redirect(url_for('admin.users'))
