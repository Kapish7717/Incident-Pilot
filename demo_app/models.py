from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from demo_app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, default=generate_uuid)
    alert_name = Column(String, nullable=False)
    status = Column(String, default="active")  # active, analyzing, awaiting_approval, resolved
    severity = Column(String, default="warning")
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    metrics_snapshot = Column(Text, nullable=True)  # JSON snapshot of Prometheus metrics
    system_metrics = Column(Text, nullable=True)   # JSON snapshot of system resources
    analysis_summary = Column(Text, nullable=True)

    timeline = relationship("IncidentTimeline", back_populates="incident", cascade="all, delete-orphan")
    actions = relationship("RemediationAction", back_populates="incident", cascade="all, delete-orphan")

class IncidentTimeline(Base):
    __tablename__ = "incident_timeline"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String, nullable=False)  # ingest, context_collected, analysis_complete, action_proposed, action_approved, resolved
    description = Column(Text, nullable=False)

    incident = relationship("Incident", back_populates="timeline")

class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id = Column(String, primary_key=True, default=generate_uuid)
    incident_id = Column(String, ForeignKey("incidents.id"), nullable=False)
    action_type = Column(String, nullable=False)  # clear_cache, rollback_deploy, scale_up
    risk_level = Column(String, nullable=False)    # safe, risky
    status = Column(String, default="pending_approval")  # pending_approval, approved, rejected, executed, failed
    details = Column(Text, nullable=True)
    execution_output = Column(Text, nullable=True)

    incident = relationship("Incident", back_populates="actions")
