from pydantic import Field, BaseModel
from typing import Optional
from app.enum.campaign import CampaignStatus, MetricLevel, HealthStatus, FunnelStage


# --- Input ---

class Campaign(BaseModel):
    id: int
    name: str
    niche: Optional[str] = None
    platform: Optional[str] = None
    objective: Optional[str] = None


class Metrics(BaseModel):
    cpc: float = Field(..., gt=0, description='Custo por clique')
    cpa: float = Field(..., gt=0, description='Custo por aquisição')
    ctr: float = Field(..., gt=0, description='Taxa de clique (%)')


class Targets(BaseModel):
    max_cpa: float = Field(..., gt=0)
    min_ctr: float = Field(..., gt=0)


class AnalyzeInput(BaseModel):
    account_id: int = Field(..., description='ID do gestor/conta')
    account_name: str = Field(..., description='Nome do gestor ou conta')
    campaign: Campaign
    metrics: Metrics
    targets: Targets


# --- Output ---

class MetricDiagnosis(BaseModel):
    value: float
    level: MetricLevel
    label: str


class CampaignAnalysisResponse(BaseModel):
    # Legacy - mantido para compatibilidade
    cpa_status: CampaignStatus
    ctr_status: CampaignStatus
    final_status: CampaignStatus
    recommendation: str

    # Engine v2
    score: int
    health: HealthStatus
    primary_problem: str
    funnel_bottleneck: FunnelStage
    metrics_diagnosis: dict[str, MetricDiagnosis]
    symptoms: list[str]
    possible_causes: list[str]
    consequences: list[str]
    insights: list[str]
    recommendations: list[str]

    # Histórico e tendência
    trend: Optional[str] = None
    previous_score: Optional[int] = None
    score_delta: Optional[int] = None