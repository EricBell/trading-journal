"""Journal routes: /journal"""

import zoneinfo
from datetime import timezone as dt_timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import login_required
from ...authorization import AuthContext
from ...database import db_manager
from ...models import JournalNote


def _to_user_tz(dt, user):
    """Convert a naive UTC datetime to the user's local timezone."""
    if dt is None:
        return None
    user_tz = zoneinfo.ZoneInfo(user.timezone or 'US/Eastern')
    return dt.replace(tzinfo=dt_timezone.utc).astimezone(user_tz)

bp = Blueprint('journal', __name__, url_prefix='/journal')


@bp.route('/')
@login_required
def index():
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        notes = (
            session.query(JournalNote)
            .filter(JournalNote.user_id == user.user_id)
            .order_by(JournalNote.created_at.desc())
            .all()
        )
        notes_data = [
            {
                'note_id': n.note_id,
                'title': n.title,
                'body': n.body,
                'created_at': _to_user_tz(n.created_at, user),
                'updated_at': _to_user_tz(n.updated_at, user),
            }
            for n in notes
        ]
    return render_template('journal/index.html', user=AuthContext.get_current_user(), notes=notes_data)


@bp.route('/new', methods=['GET'])
@login_required
def new():
    return render_template('journal/detail.html', user=AuthContext.get_current_user(), note=None)


@bp.route('/new', methods=['POST'])
@login_required
def create():
    user = AuthContext.require_user()
    title = request.form.get('title', '').strip() or None
    body = request.form.get('body', '').strip() or None

    with db_manager.get_session() as session:
        note = JournalNote(user_id=user.user_id, title=title, body=body)
        session.add(note)
        session.flush()
        note_id = note.note_id
        session.commit()

    return redirect(url_for('journal.detail', note_id=note_id))


@bp.route('/<int:note_id>', methods=['GET'])
@login_required
def detail(note_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        note = session.query(JournalNote).filter(
            JournalNote.note_id == note_id,
            JournalNote.user_id == user.user_id,
        ).first()
        if note is None:
            flash('Note not found.', 'danger')
            return redirect(url_for('journal.index'))
        note_data = {
            'note_id': note.note_id,
            'title': note.title,
            'body': note.body,
            'created_at': _to_user_tz(note.created_at, user),
            'updated_at': _to_user_tz(note.updated_at, user),
        }
    return render_template('journal/detail.html', user=AuthContext.get_current_user(), note=note_data)


@bp.route('/<int:note_id>', methods=['POST'])
@login_required
def update(note_id):
    user = AuthContext.require_user()
    title = request.form.get('title', '').strip() or None
    body = request.form.get('body', '').strip() or None

    with db_manager.get_session() as session:
        note = session.query(JournalNote).filter(
            JournalNote.note_id == note_id,
            JournalNote.user_id == user.user_id,
        ).first()
        if note is None:
            flash('Note not found.', 'danger')
            return redirect(url_for('journal.index'))
        note.title = title
        note.body = body
        session.commit()

    flash('Note saved.', 'success')
    return redirect(url_for('journal.detail', note_id=note_id))


@bp.route('/<int:note_id>/delete', methods=['POST'])
@login_required
def delete(note_id):
    user = AuthContext.require_user()
    with db_manager.get_session() as session:
        note = session.query(JournalNote).filter(
            JournalNote.note_id == note_id,
            JournalNote.user_id == user.user_id,
        ).first()
        if note is None:
            flash('Note not found.', 'danger')
            return redirect(url_for('journal.index'))
        session.delete(note)
        session.commit()

    flash('Note deleted.', 'success')
    return redirect(url_for('journal.index'))
