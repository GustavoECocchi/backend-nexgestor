from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    analyses = relationship("AnalysisRecord", back_populates="account")


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id         = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    # Contexto da campanha
    campaign_id   = Column(Integer, nullable=False)
    campaign_name = Column(String, nullable=False)
    platform      = Column(String, nullable=True)
    niche         = Column(String, nullable=True)
    objective     = Column(String, nullable=True)

    # Métricas enviadas
    ctr = Column(Float, nullable=False)
    cpc = Column(Float, nullable=False)
    cpa = Column(Float, nullable=False)

    # Targets
    min_ctr = Column(Float, nullable=False)
    max_cpa = Column(Float, nullable=False)

    # Resultado da engine
    score          = Column(Integer, nullable=False)
    health         = Column(String, nullable=False)
    primary_problem = Column(String, nullable=False)
    funnel_bottleneck = Column(String, nullable=False)

    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    account = relationship("Account", back_populates="analyses")