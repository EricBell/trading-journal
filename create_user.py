import logging
from trading_journal.database import db_manager
from trading_journal.models import User
from trading_journal.auth.utils import generate_api_key
from sqlalchemy.exc import IntegrityError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_default_user():
    """Creates a default user if one doesn't exist and prints their API key."""
    username = "default_user"
    email = "user@example.com"
    
    with db_manager.get_session() as session:
        # Check if user already exists
        existing_user = session.query(User).filter_by(username=username).one_or_none()
        if existing_user:
            logger.info(f"User '{username}' already exists. Skipping creation.")
            # If you need to get the key, you'd have to reset it, since we don't store the raw key.
            # For this script's purpose, we'll just assume if the user exists, we're done.
            return

        raw_key, hashed_key = generate_api_key()

        new_user = User(
            username=username,
            email=email,
            api_key_hash=hashed_key,
            is_active=True,
            is_admin=False, # Or True, depending on needs
        )

        try:
            session.add(new_user)
            session.commit()
            logger.info(f"Successfully created user '{username}'.")
            print(f"\nIMPORTANT: Store this API key securely. It will not be shown again.")
            print(f"API Key for {username}: {raw_key}\n")
        except IntegrityError:
            session.rollback()
            logger.error(f"User '{username}' or email '{email}' already exists.")
        except Exception as e:
            session.rollback()
            logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    create_default_user()
