from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, ForeignKey, Text, Enum
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import enum

Base = declarative_base()

class UserStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    UNSUBSCRIBED = "UNSUBSCRIBED"

class JobStatus(enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED_TEMP = "FAILED_TEMP"
    FAILED_PERM = "FAILED_PERM"
    CANCELLED = "CANCELLED"

class User(Base):
    __tablename__ = 'users'

    target_chat_id = Column(Integer, primary_key=True)
    sequence_template_id = Column(String)
    current_message_index = Column(Integer, default=0)
    last_message_sent_timestamp = Column(DateTime, nullable=True)
    engagement_score = Column(Float, default=0.0)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)

    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")

class SequenceTemplate(Base):
    __tablename__ = 'sequence_templates'

    id = Column(Integer, primary_key=True)
    template_id = Column(String, index=True) # e.g. 'SEQ_100_STEP_ALPHA'
    message_index = Column(Integer) # 1 to 100
    phase = Column(String) # P1, P2, P3, P4
    content_payload = Column(Text) # JSON or simple text
    base_delay_minutes = Column(Integer) # Delay from previous message

class Job(Base):
    __tablename__ = 'job_queue'

    job_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.target_chat_id'))
    message_index = Column(Integer)
    content_payload = Column(Text)
    scheduled_timestamp = Column(DateTime, index=True)
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED)

    user = relationship("User", back_populates="jobs")

class GlobalState(Base):
    """
    Stores global state for the application, such as flood wait pause time.
    """
    __tablename__ = 'global_state'

    key = Column(String, primary_key=True)
    value = Column(String) # Can store ISO timestamp or JSON
    expires_at = Column(DateTime, nullable=True)

# Database setup
# Using SQLite for this implementation
# 'check_same_thread': False is required because we access the DB from
# executor threads (via run_in_executor) while the connection might be created/pooled.
engine = create_engine('sqlite:///jules_outreach.db', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db_sync():
    """Returns a new synchronous session. To be used within run_in_executor."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
