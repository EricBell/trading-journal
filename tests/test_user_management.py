"""Comprehensive test suite for user management functionality."""

import pytest
from datetime import datetime

from trading_journal.user_management import UserManager
from trading_journal.models import User, CompletedTrade
from trading_journal.authorization.context import AuthContext
from trading_journal.auth.base import AuthUser
from trading_journal.auth.utils import hash_api_key


@pytest.fixture
def admin_user(db_session):
    """Create an admin user and set in auth context."""
    # Create admin user
    admin = User(
        username='test_admin',
        email='admin@test.com',
        is_admin=True,
        is_active=True,
        api_key_hash=hash_api_key('admin_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    # Set auth context
    auth_user = AuthUser(
        user_id=admin.user_id,
        username=admin.username,
        email=admin.email,
        is_admin=True,
        is_active=True,
        auth_method='api_key'
    )
    AuthContext.set_current_user(auth_user)

    yield admin

    # Cleanup
    AuthContext.clear()


@pytest.fixture
def regular_user(db_session):
    """Create a regular (non-admin) user."""
    user = User(
        username='regular_user',
        email='user@test.com',
        is_admin=False,
        is_active=True,
        api_key_hash=hash_api_key('user_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


@pytest.fixture
def inactive_user(db_session):
    """Create an inactive user."""
    user = User(
        username='inactive_user',
        email='inactive@test.com',
        is_admin=False,
        is_active=False,
        api_key_hash=hash_api_key('inactive_key'),
        api_key_created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


@pytest.fixture
def user_with_trades(db_session, regular_user):
    """Create a user with completed trades."""
    # Create completed trades for the user
    for i in range(3):
        trade = CompletedTrade(
            user_id=regular_user.user_id,
            symbol=f'TEST{i}',
            instrument_type='EQUITY',
            total_qty=100,
            entry_avg_price=10.0,
            exit_avg_price=11.0,
            net_pnl=100.0,
            is_winning_trade=True,
            opened_at=datetime.utcnow(),
            closed_at=datetime.utcnow()
        )
        db_session.add(trade)
    db_session.commit()

    return regular_user


class TestUserCreation:
    """Tests for user creation functionality."""

    def test_create_user_success(self, db_session, admin_user):
        """Test successful user creation."""
        manager = UserManager(db_session)
        user, api_key = manager.create_user(
            username='newuser',
            email='newuser@test.com',
            is_admin=False
        )

        assert user.username == 'newuser'
        assert user.email == 'newuser@test.com'
        assert user.is_admin is False
        assert user.is_active is True
        assert api_key is not None
        assert len(api_key) > 20  # API keys should be reasonably long

    def test_create_admin_user(self, db_session, admin_user):
        """Test creating a user with admin privileges."""
        manager = UserManager(db_session)
        user, api_key = manager.create_user(
            username='newadmin',
            email='newadmin@test.com',
            is_admin=True
        )

        assert user.is_admin is True

    def test_create_user_invalid_username_too_short(self, db_session, admin_user):
        """Test user creation with username too short."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="must be 3-100 characters"):
            manager.create_user(username='ab', email='test@test.com')

    def test_create_user_invalid_username_special_chars(self, db_session, admin_user):
        """Test user creation with invalid characters in username."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="must be 3-100 characters"):
            manager.create_user(username='user@name!', email='test@test.com')

    def test_create_user_invalid_email(self, db_session, admin_user):
        """Test user creation with invalid email format."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="Invalid email format"):
            manager.create_user(username='testuser', email='not-an-email')

    def test_create_user_duplicate_username(self, db_session, admin_user, regular_user):
        """Test user creation with duplicate username."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username='regular_user', email='new@test.com')

    def test_create_user_duplicate_email(self, db_session, admin_user, regular_user):
        """Test user creation with duplicate email."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username='newuser', email='user@test.com')

    def test_create_user_case_insensitive_username(self, db_session, admin_user, regular_user):
        """Test that username uniqueness is case-insensitive."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username='REGULAR_USER', email='new@test.com')

    def test_create_user_case_insensitive_email(self, db_session, admin_user, regular_user):
        """Test that email uniqueness is case-insensitive."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_user(username='newuser', email='USER@TEST.COM')


class TestUserListing:
    """Tests for user listing functionality."""

    def test_list_active_users_only(self, db_session, admin_user, regular_user, inactive_user):
        """Test listing only active users."""
        manager = UserManager(db_session)
        users = manager.list_users(include_inactive=False)

        assert len(users) == 2  # admin_user and regular_user
        usernames = [u['username'] for u in users]
        assert 'test_admin' in usernames
        assert 'regular_user' in usernames
        assert 'inactive_user' not in usernames

    def test_list_all_users(self, db_session, admin_user, regular_user, inactive_user):
        """Test listing all users including inactive."""
        manager = UserManager(db_session)
        users = manager.list_users(include_inactive=True)

        assert len(users) == 3
        usernames = [u['username'] for u in users]
        assert 'test_admin' in usernames
        assert 'regular_user' in usernames
        assert 'inactive_user' in usernames

    def test_list_users_with_trade_counts(self, db_session, admin_user, user_with_trades):
        """Test that user listing includes accurate trade counts."""
        manager = UserManager(db_session)
        users = manager.list_users()

        # Find the user with trades
        user_data = next(u for u in users if u['username'] == 'regular_user')
        assert user_data['trade_count'] == 3

        # Admin should have 0 trades
        admin_data = next(u for u in users if u['username'] == 'test_admin')
        assert admin_data['trade_count'] == 0

    def test_list_users_includes_all_fields(self, db_session, admin_user):
        """Test that user listing includes all expected fields."""
        manager = UserManager(db_session)
        users = manager.list_users()

        user = users[0]
        assert 'user_id' in user
        assert 'username' in user
        assert 'email' in user
        assert 'is_active' in user
        assert 'is_admin' in user
        assert 'trade_count' in user
        assert 'created_at' in user
        assert 'last_login_at' in user


class TestUserStatusManagement:
    """Tests for user activation/deactivation."""

    def test_deactivate_user_success(self, db_session, admin_user, regular_user):
        """Test successful user deactivation."""
        manager = UserManager(db_session)
        user = manager.deactivate_user(regular_user.user_id)

        db_session.refresh(user)
        assert user.is_active is False

    def test_deactivate_self_fails(self, db_session, admin_user):
        """Test that users cannot deactivate themselves."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="cannot deactivate your own account"):
            manager.deactivate_user(admin_user.user_id)

    def test_deactivate_last_admin_fails(self, db_session, admin_user):
        """Test that the last admin cannot be deactivated."""
        # Create a regular (non-admin) user to be the current user
        regular = User(
            username='regular',
            email='regular@test.com',
            is_admin=False,
            is_active=True,
            api_key_hash=hash_api_key('regular_key'),
            api_key_created_at=datetime.utcnow(),
            auth_method='api_key'
        )
        db_session.add(regular)
        db_session.commit()
        db_session.refresh(regular)

        # Set context to regular user so we're not the admin trying to deactivate themselves
        # (Note: In real app, only admins can deactivate users, but for this test
        # we're bypassing that to test the "last admin" logic)
        auth_user = AuthUser(
            user_id=regular.user_id,
            username=regular.username,
            email=regular.email,
            is_admin=False,
            is_active=True,
            auth_method='api_key'
        )
        AuthContext.set_current_user(auth_user)

        # Try to deactivate the only admin (admin_user)
        # This should fail because it's the last admin
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="At least one active admin must remain"):
            manager.deactivate_user(admin_user.user_id)

    def test_deactivate_admin_with_another_admin_succeeds(self, db_session, admin_user):
        """Test that an admin can be deactivated if another admin exists."""
        # Create second admin
        second_admin = User(
            username='admin2',
            email='admin2@test.com',
            is_admin=True,
            is_active=True,
            api_key_hash=hash_api_key('admin2_key'),
            api_key_created_at=datetime.utcnow()
        )
        db_session.add(second_admin)
        db_session.commit()

        # Deactivate first admin (should succeed)
        manager = UserManager(db_session)
        user = manager.deactivate_user(second_admin.user_id)
        assert user.is_active is False

    def test_reactivate_user_success(self, db_session, admin_user, inactive_user):
        """Test successful user reactivation."""
        manager = UserManager(db_session)
        user = manager.reactivate_user(inactive_user.user_id)

        db_session.refresh(user)
        assert user.is_active is True

    def test_deactivate_nonexistent_user_fails(self, db_session, admin_user):
        """Test deactivating a nonexistent user."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            manager.deactivate_user(99999)


class TestAdminPrivilegeManagement:
    """Tests for granting and revoking admin privileges."""

    def test_make_admin_success(self, db_session, admin_user, regular_user):
        """Test successfully granting admin privileges."""
        manager = UserManager(db_session)
        user = manager.make_admin(regular_user.user_id)

        db_session.refresh(user)
        assert user.is_admin is True

    def test_revoke_admin_success(self, db_session, admin_user):
        """Test successfully revoking admin privileges when multiple admins exist."""
        # Create second admin
        second_admin = User(
            username='admin2',
            email='admin2@test.com',
            is_admin=True,
            is_active=True,
            api_key_hash=hash_api_key('admin2_key'),
            api_key_created_at=datetime.utcnow()
        )
        db_session.add(second_admin)
        db_session.commit()

        # Revoke admin from second admin
        manager = UserManager(db_session)
        user = manager.revoke_admin(second_admin.user_id)

        db_session.refresh(user)
        assert user.is_admin is False

    def test_revoke_admin_self_fails(self, db_session, admin_user):
        """Test that users cannot revoke their own admin privileges."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="cannot revoke your own admin privileges"):
            manager.revoke_admin(admin_user.user_id)

    def test_revoke_last_admin_fails(self, db_session, admin_user):
        """Test that the last admin's privileges cannot be revoked."""
        # Create a regular user to be the current user
        regular = User(
            username='regular',
            email='regular@test.com',
            is_admin=False,
            is_active=True,
            api_key_hash=hash_api_key('regular_key'),
            api_key_created_at=datetime.utcnow(),
            auth_method='api_key'
        )
        db_session.add(regular)
        db_session.commit()
        db_session.refresh(regular)

        # Set context to regular user so we're not the admin trying to revoke themselves
        auth_user = AuthUser(
            user_id=regular.user_id,
            username=regular.username,
            email=regular.email,
            is_admin=False,
            is_active=True,
            auth_method='api_key'
        )
        AuthContext.set_current_user(auth_user)

        # Try to revoke last active admin
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="At least one active admin must remain"):
            manager.revoke_admin(admin_user.user_id)

    def test_revoke_admin_from_non_admin_fails(self, db_session, admin_user, regular_user):
        """Test revoking admin from a user who isn't an admin."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="is not an admin"):
            manager.revoke_admin(regular_user.user_id)


class TestUserDeletion:
    """Tests for user deletion functionality."""

    def test_delete_user_without_trades_success(self, db_session, admin_user, regular_user):
        """Test successful deletion of user without trades."""
        user_id = regular_user.user_id

        manager = UserManager(db_session)
        manager.delete_user(user_id)
        db_session.commit()

        # Verify user is deleted
        deleted_user = db_session.query(User).filter_by(user_id=user_id).first()
        assert deleted_user is None

    def test_delete_user_with_trades_fails(self, db_session, admin_user, user_with_trades):
        """Test that users with trades cannot be deleted."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="has 3 completed trade"):
            manager.delete_user(user_with_trades.user_id)

    def test_delete_self_fails(self, db_session, admin_user):
        """Test that users cannot delete themselves."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="cannot delete your own account"):
            manager.delete_user(admin_user.user_id)

    def test_delete_last_admin_fails(self, db_session, admin_user):
        """Test that the last admin cannot be deleted."""
        # Create a regular user to be the current user
        regular = User(
            username='regular',
            email='regular@test.com',
            is_admin=False,
            is_active=True,
            api_key_hash=hash_api_key('regular_key'),
            api_key_created_at=datetime.utcnow(),
            auth_method='api_key'
        )
        db_session.add(regular)
        db_session.commit()
        db_session.refresh(regular)

        # Set context to regular user so we're not the admin trying to delete themselves
        auth_user = AuthUser(
            user_id=regular.user_id,
            username=regular.username,
            email=regular.email,
            is_admin=False,
            is_active=True,
            auth_method='api_key'
        )
        AuthContext.set_current_user(auth_user)

        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="At least one active admin must remain"):
            manager.delete_user(admin_user.user_id)

    def test_delete_nonexistent_user_fails(self, db_session, admin_user):
        """Test deleting a nonexistent user."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            manager.delete_user(99999)


class TestAPIKeyRegeneration:
    """Tests for API key regeneration."""

    def test_regenerate_api_key_success(self, db_session, admin_user, regular_user):
        """Test successful API key regeneration."""
        old_api_key_hash = regular_user.api_key_hash

        manager = UserManager(db_session)
        user, new_api_key = manager.regenerate_api_key(regular_user.user_id)

        db_session.refresh(user)

        # Verify new API key is different
        assert user.api_key_hash != old_api_key_hash
        assert new_api_key is not None
        assert len(new_api_key) > 20

        # Verify old key doesn't match
        from trading_journal.auth.utils import hash_api_key
        assert user.api_key_hash == hash_api_key(new_api_key)

    def test_regenerate_api_key_updates_timestamp(self, db_session, admin_user, regular_user):
        """Test that API key regeneration updates the timestamp."""
        old_timestamp = regular_user.api_key_created_at

        manager = UserManager(db_session)
        user, _ = manager.regenerate_api_key(regular_user.user_id)

        db_session.refresh(user)
        assert user.api_key_created_at > old_timestamp

    def test_regenerate_api_key_nonexistent_user_fails(self, db_session, admin_user):
        """Test regenerating API key for nonexistent user."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            manager.regenerate_api_key(99999)


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_user_or_raise_success(self, db_session, admin_user, regular_user):
        """Test successfully retrieving a user."""
        manager = UserManager(db_session)
        user = manager.get_user_or_raise(regular_user.user_id)

        assert user.user_id == regular_user.user_id
        assert user.username == regular_user.username

    def test_get_user_or_raise_nonexistent_fails(self, db_session, admin_user):
        """Test retrieving a nonexistent user."""
        manager = UserManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            manager.get_user_or_raise(99999)


class TestCompleteUserLifecycle:
    """Integration tests for complete user lifecycle."""

    def test_complete_lifecycle(self, db_session, admin_user):
        """Test complete user lifecycle: create -> list -> deactivate -> reactivate -> make-admin -> revoke-admin -> delete."""
        manager = UserManager(db_session)

        # Create user
        user, api_key = manager.create_user('lifecycle_user', 'lifecycle@test.com')
        assert user.is_active is True
        assert user.is_admin is False

        # List users (should include new user)
        users = manager.list_users()
        assert any(u['username'] == 'lifecycle_user' for u in users)

        # Deactivate user
        manager.deactivate_user(user.user_id)
        db_session.refresh(user)
        assert user.is_active is False

        # List active users (should not include deactivated user)
        users = manager.list_users(include_inactive=False)
        assert not any(u['username'] == 'lifecycle_user' for u in users)

        # Reactivate user
        manager.reactivate_user(user.user_id)
        db_session.refresh(user)
        assert user.is_active is True

        # Make admin
        manager.make_admin(user.user_id)
        db_session.refresh(user)
        assert user.is_admin is True

        # Revoke admin
        manager.revoke_admin(user.user_id)
        db_session.refresh(user)
        assert user.is_admin is False

        # Regenerate API key
        _, new_key = manager.regenerate_api_key(user.user_id)
        assert new_key is not None

        # Delete user
        manager.delete_user(user.user_id)
        db_session.commit()

        # Verify deleted
        deleted_user = db_session.query(User).filter_by(user_id=user.user_id).first()
        assert deleted_user is None
