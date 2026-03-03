"""Authentication routes: /login, /logout."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..auth import authenticate_user

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = authenticate_user(username, password)
        if user:
            session.clear()
            session['user_id'] = user.user_id
            session.permanent = True
            return redirect(url_for('dashboard.index'))
        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
