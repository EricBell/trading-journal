from werkzeug.security import generate_password_hash                                           
from trading_journal.database import db_manager                                                
from trading_journal.models import User

new_hash = generate_password_hash(YourNewPasswordHere)  # Replace with your new password                                 
with db_manager.get_session() as s:                                                            
    u = s.query(User).filter_by(username='YourUsername').one()
    u.password_hash = new_hash                                                                 
    s.commit()                                            
    print(f'Password updated for {u.username}')                                                