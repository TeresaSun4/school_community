
from app import app, db

def init_db():
    """
    Initialize the database by creating all tables.
    This script should be run directly to set up the database.
    """
    with app.app_context():
        # Create all database tables
        db.create_all()
        print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()
    print("Database setup completed. You can now run the application.")





# Add database constraints (AS91892 advanced technique)
db.execute("""
  -- Email format validation
  ALTER TABLE users 
    ADD CONSTRAINT chk_valid_email 
    CHECK (email LIKE '%@%.%');
  
  -- Username length requirement
  ALTER TABLE users 
    ADD CONSTRAINT chk_username_length 
    CHECK (LENGTH(username) BETWEEN 4 AND 30);
  
  -- Post content validation
  ALTER TABLE posts 
    ADD CONSTRAINT chk_content_length 
    CHECK (LENGTH(content) BETWEEN 10 AND 2000);
""")