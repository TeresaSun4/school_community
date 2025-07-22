import os
import sys
import shutil

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Get database file paths
COMMUNITY_DB = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'community.db')
CONTENT_DB = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'content.db')
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')

def reset_db(keep_uploads=True):
    """
    Delete and recreate the databases

    Args:
        keep_uploads (bool): If True, keeps uploaded files in static/uploads directory
    """
    # Delete existing database files
    for db_file in [COMMUNITY_DB, CONTENT_DB]:
        if os.path.exists(db_file):
            print(f"Deleting database file: {db_file}")
            os.remove(db_file)

    # Handle uploads
    if not keep_uploads and os.path.exists(UPLOAD_FOLDER):
        print(f"Clearing upload folder: {UPLOAD_FOLDER}")
        # Keep directory but delete all files
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"  - Deleted: {filename}")
            except Exception as e:
                print(f"  - Error deleting {filename}: {e}")
    else:
        print(f"Keeping files in upload folder: {UPLOAD_FOLDER}")

    # Ensure uploads directory exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        print(f"Created upload folder: {UPLOAD_FOLDER}")

    print("Database files have been deleted. Starting the application will automatically create new databases.")
    print("Please run: python app.py")

if __name__ == "__main__":
    confirm = input("This will delete all database data. Are you sure you want to continue? (y/n): ")
    if confirm.lower() == 'y':
        keep_uploads = input("Do you want to keep the uploaded files? (y/n, default: y): ").lower() != 'n'
        reset_db(keep_uploads)
    else:
        print("Operation cancelled")
