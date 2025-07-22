
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
