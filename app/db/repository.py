from sqlalchemy.orm import Session
from app.db.models import Account, AnalysisRecord


def get_or_create_account(db: Session, account_id: int, name: str) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        account = Account(id=account_id, name=name)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def save_analysis(db: Session, account_id: int, data, result) -> AnalysisRecord:
    record = AnalysisRecord(
        account_id        = account_id,
        campaign_id       = data.campaign.id,
        campaign_name     = data.campaign.name,
        platform          = data.campaign.platform,
        niche             = data.campaign.niche,
        objective         = data.campaign.objective,
        ctr               = data.metrics.ctr,
        cpc               = data.metrics.cpc,
        cpa               = data.metrics.cpa,
        min_ctr           = data.targets.min_ctr,
        max_cpa           = data.targets.max_cpa,
        score             = result.score,
        health            = result.health.value,
        primary_problem   = result.primary_problem,
        funnel_bottleneck = result.funnel_bottleneck.value,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_recent_analyses(db: Session, account_id: int, campaign_id: int, limit: int = 5) -> list[AnalysisRecord]:
    return (
        db.query(AnalysisRecord)
        .filter(
            AnalysisRecord.account_id == account_id,
            AnalysisRecord.campaign_id == campaign_id,
        )
        .order_by(AnalysisRecord.analyzed_at.desc())
        .limit(limit)
        .all()
    )