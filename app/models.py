from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    active = Column(Boolean, default=True)

    leads = relationship("Lead", back_populates="source")

    created_at = Column(DateTime, default=datetime.utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    city = Column(String, nullable=True)
    price = Column(String, nullable=True)
    deadline = Column(String, nullable=True)
    asset_type = Column(String, nullable=True)
    category = Column(String, default="inne")
    status = Column(String, default="new")
    notes = Column(Text, nullable=True)

    source_id = Column(Integer, ForeignKey("sources.id"))
    source = relationship("Source", back_populates="leads")

    created_at = Column(DateTime, default=datetime.utcnow)


class ScanSettings(Base):
    __tablename__ = "scan_settings"

    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=False)
    interval_hours = Column(Integer, default=24)
    last_run_at = Column(DateTime, nullable=True)