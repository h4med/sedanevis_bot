# database.py

import datetime
from datetime import UTC
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    BigInteger,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# --- Database Setup ---
DATABASE_URL = "sqlite:///persistent_data/bot_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Database Models ---
class User(Base):
    """
    Represents a user in the database.
    Credit is now unified into a single `credit_minutes` field.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=False)
    username = Column(String, nullable=True)
    status = Column(String, nullable=False, default='pending') 
    
    credit_minutes = Column(Float, nullable=False, default=0.0)
    preferred_language = Column(String, nullable=False, default='fa')
    # created_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))

    # Relationship to ActivityLog
    logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<User(id={self.id}, user_id={self.user_id}, name='{self.first_name}', "
            f"status='{self.status}', credit_minutes={self.credit_minutes})>"
        )

class ActivityLog(Base):
    """
    Represents a log of a user's activity.
    This table tracks every action that consumes credit or is otherwise notable.
    """
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    action_type = Column(String, nullable=False)
    credit_change = Column(Float, nullable=False)
    details = Column(Text, nullable=True)

    # Relationship to User
    user = relationship("User", back_populates="logs")

    def __repr__(self):
        return (
            f"<ActivityLog(user_id={self.user_id}, action='{self.action_type}', "
            f"change={self.credit_change})>"
        )

class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    original_message_id = Column(Integer, nullable=False)
    status = Column(String, default="PENDING", nullable=False)  # PENDING, SUCCEEDED, FAILED
    cost_minutes = Column(Float, nullable=False)
    original_filename = Column(String, nullable=True)
    # created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(UTC))
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# --- Database Initialization ---
def create_db_and_tables():
    """
    Creates the database and all tables if they don't already exist.
    """
    try:
        print("Initializing database and creating tables...")
        Base.metadata.create_all(bind=engine)
        print("Database and tables created successfully (if they didn't exist).")
    except Exception as e:
        print(f"An error occurred during database initialization: {e}")