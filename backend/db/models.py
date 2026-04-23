from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(256), primary_key=True)
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String(256))
    role = Column(String)  # user / assistant
    content = Column(Text)
    mode_used = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id = Column(Integer, primary_key=True)
    category = Column(String)
    content = Column(Text)
    state = Column(String)  # observed / tentative / confirmed
    weight = Column(Float, default=0.5)
    sensitivity = Column(String, default="low")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)
    archived = Column(Boolean, default=False)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String)


class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True)
    content = Column(Text)
    message_count_at_creation = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
