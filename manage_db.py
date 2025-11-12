# manage_db.py

import json
import os
import argparse
import shutil  # Import the shutil module for file copying
from datetime import datetime

from database import SessionLocal, User, create_db_and_tables, DATABASE_URL

BACKUP_DIR = "persistent_data/backups"

def backup_users():
    """
    Connects to the database and exports all records from the 'users' table
    to a timestamped JSON file. Safely handles both old and new table schemas.
    """
    print("Starting user data backup (JSON)...")
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found in the database. Nothing to back up.")
            return

        user_data_list = []
        for user in users:
            user_data = {
                "user_id": user.user_id,
                "first_name": user.first_name,
                "username": user.username,
                "status": user.status,
                "preferred_language": user.preferred_language,
                "credit_minutes": user.credit_minutes,
                "created_at": user.created_at.isoformat() if user.created_at else None,     
            }
            user_data_list.append(user_data)
        
        os.makedirs(BACKUP_DIR, exist_ok=True)
        filename = f"users_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(BACKUP_DIR, filename)
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(user_data_list, f, ensure_ascii=False, indent=4)
        
        print(f"Successfully backed up {len(user_data_list)} users to '{backup_path}'.")
        print("The backup file is available on your host machine in the 'backups' directory.")

    except Exception as e:
        print(f"An error occurred during user backup: {e}")
    finally:
        db.close()


def backup_full_database():
    """
    Creates a direct copy of the entire SQLite database file.
    """
    print("Starting full database backup (.db file)...")
    
    db_file_path = DATABASE_URL.split('///')[1]
    
    if not os.path.exists(db_file_path):
        print(f"Error: Database file not found at '{db_file_path}'. Cannot create backup.")
        return

    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"full_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Use shutil.copy to create a safe copy of the file
        shutil.copy(db_file_path, backup_path)
        
        print(f"Successfully created a full database backup at '{backup_path}'.")
        print("The backup file is available on your host machine in the 'backups' directory.")
        
    except Exception as e:
        print(f"An error occurred during full database backup: {e}")


def initialize_database():
    """
    Calls the function to create all database tables based on the models.
    """
    print("Executing standalone database initialization...")
    create_db_and_tables()
    print("Database initialization complete.")

def main():
    """
    Main function to parse command-line arguments and run the requested action.
    """
    parser = argparse.ArgumentParser(description="Database management script for Dr. Typer.")
    parser.add_argument(
        'action', 
        choices=['backup-users', 'backup-all', 'init'], 
        help="Action: 'backup-users' (users), 'backup-all' (.db), 'init' (create tables)."
    )
    
    args = parser.parse_args()

    if args.action == 'backup-users':
        backup_users()
    elif args.action == 'backup-all':
        backup_full_database()
    elif args.action == 'init':
        print("\nWARNING: The 'init' action creates tables but does not migrate data.")
        print("Ensure you have a backup if you are running this on an existing database.")
        confirm = input("Are you sure you want to proceed? (yes/no): ")
        if confirm.lower() == 'yes':
            initialize_database()
        else:
            print("Initialization cancelled.")

if __name__ == "__main__":
    main()