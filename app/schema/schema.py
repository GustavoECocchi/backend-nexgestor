from pydantic import Field, BaseModel
from typing import Optional
from app.enum.campaign import CampaignStatus, ScenarioCode


# ─────────────────────────────────────────────
# INPUT
# ─────────────────────────────────────────────

class Campaign(BaseModel):
    id: int
    name: str
    objective: Optional[str] = Field(
        default="conversion",
        description="conversion | lead | traffic"
    )
    platform: Optional[str] = Field(
        default="meta_ads",
        description="meta_ads | google_ads"
    )
    niche: Optional[str] = Field(
        default=None,
        description="Ex: SaaS, ecommerce, infoproduto"
    )


class Metrics(BaseModel):

    # ── ENTREGA ──────────────────────────────────────────────────────────────
    impressions: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total de impressões no período"
    )
    reach: Optional[int] = Field(
        default=None,
        ge=0,
        description="Alcance único (pessoas diferentes atingidas)"
    )
    spend: Optional[float] = Field(
        default=None,
        ge=0,
        description="Valor total gasto no período (R$)"
    )

    # ── CRIATIVO — FUNIL DE ATENÇÃO (vídeo) ──────────────────────────────────
    video_views_3s: Optional[int] = Field(
        default=None,
        ge=0,
        description="Visualizações de vídeo de pelo menos 3 segundos"
    )
    video_views_50pct: Optional[int] = Field(
        default=None,
        ge=0,
        description="Visualizações até 50% do vídeo (proxy de Hold Rate)"
    )
    thruplays: Optional[int] = Field(
        default=None,
        ge=0,
        description="ThruPlays: visualizações até 97% do vídeo ou 15s+"
    )
    hook_rate: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Taxa de Gancho (%): video_views_3s / impressions * 100. "
            "Pode ser enviado diretamente ou calculado pelo engine. Meta: >35%"
        )
    )
    hold_rate: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Taxa de Retenção (%): thruplays / impressions * 100. "
            "Pode ser enviado diretamente ou calculado pelo engine. Meta: >15%"
        )
    )

    # ── CRIATIVO — CLIQUES ────────────────────────────────────────────────────
    link_clicks: Optional[int] = Field(
        default=None,
        ge=0,
        description="Cliques no link do anúncio (saída para a LP)"
    )
    all_clicks: Optional[int] = Field(
        default=None,
        ge=0,
        description="Todos os cliques: curtidas, comentários, expandir texto, link"
    )
    ctr_link: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "CTR Link (%): link_clicks / impressions * 100. "
            "Pode ser enviado diretamente ou calculado. Meta: >1.5%"
        )
    )
    ctr_all: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "CTR Todos (%): all_clicks / impressions * 100. "
            "Alto + CTR Link baixo = sinal de Click-Bait. Meta referência: <3.5%"
        )
    )

    # ── CUSTO ─────────────────────────────────────────────────────────────────
    cpm: Optional[float] = Field(
        default=None,
        ge=0,
        description="Custo por Mil Impressões — reflete preço do leilão e relevância"
    )
    cpc: Optional[float] = Field(
        default=None,
        ge=0,
        description="Custo por Clique no Link — reflexo de CPM + CTR Link"
    )
    cpl: Optional[float] = Field(
        default=None,
        ge=0,
        description="Custo por Lead gerado"
    )
    cpa: Optional[float] = Field(
        default=None,
        ge=0,
        description="Custo por Aquisição (compra, assinatura, trial)"
    )
    roas: Optional[float] = Field(
        default=None,
        ge=0,
        description="Return on Ad Spend: receita gerada / valor gasto"
    )

    # ── LANDING PAGE ──────────────────────────────────────────────────────────
    landing_page_views: Optional[int] = Field(
        default=None,
        ge=0,
        description="Visualizações reais da LP (após carregamento — diferente de link_clicks)"
    )
    lp_conversion_rate: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Taxa de conversão na Landing Page (%): conversions / landing_page_views * 100. "
            "Meta mínima: >1%. Abaixo disso com CTR alto = Cenário D."
        )
    )

    # ── CONVERSÕES ────────────────────────────────────────────────────────────
    conversions: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total de conversões no período (compras, leads, trials)"
    )
    weekly_conversions: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Conversões nos últimos 7 dias no conjunto. "
            "Meta mínima para sair do aprendizado: 50/semana."
        )
    )

    # ── AUDIÊNCIA / SATURAÇÃO ─────────────────────────────────────────────────
    frequency: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Frequência média: impressions / reach. "
            "Acima de 2.8 em 7 dias = sinal de fadiga. Acima de 6 = saturação crítica."
        )
    )

    # ── APRENDIZADO DO ALGORITMO ──────────────────────────────────────────────
    learning_phase: Optional[bool] = Field(
        default=None,
        description="True se o conjunto está com status 'Aprendizado Limitado' no Meta Ads"
    )


class Targets(BaseModel):

    # ── CRIATIVO — FUNIL DE ATENÇÃO ───────────────────────────────────────────
    min_hook_rate: float = Field(
        default=35.0,
        gt=0,
        description=(
            "Hook Rate mínimo aceitável (%). "
            "Default do PDF: 35%. Abaixo de 70% deste valor = Cenário A crítico."
        )
    )
    min_hold_rate: float = Field(
        default=15.0,
        gt=0,
        description=(
            "Hold Rate mínimo aceitável (%). "
            "Default do PDF: 15%. Abaixo de 10% com Hook ok = Cenário B."
        )
    )

    # ── CRIATIVO — CLIQUES ────────────────────────────────────────────────────
    min_ctr_link: float = Field(
        default=1.5,
        gt=0,
        description=(
            "CTR Link mínimo aceitável (%). "
            "Default do PDF: 1.5%. Abaixo disso com Hook alto = problema de CTA."
        )
    )
    max_ctr_all_ratio: float = Field(
        default=3.5,
        gt=0,
        description=(
            "CTR Todos máximo antes de suspeitar Click-Bait (%). "
            "Quando CTR Todos > este valor E CTR Link < 0.7% = Cenário C."
        )
    )

    # ── CUSTO ─────────────────────────────────────────────────────────────────
    max_cpa: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "CPA máximo aceitável (R$). "
            "Obrigatório para detectar Cenários D, F, G, H. "
            "Sem este valor o engine não consegue avaliar eficiência de aquisição."
        )
    )
    max_cpc: Optional[float] = Field(
        default=None,
        gt=0,
        description="CPC máximo aceitável (R$). Usado para alertar leilão caro."
    )
    max_cpm: Optional[float] = Field(
        default=50.0,
        gt=0,
        description=(
            "CPM máximo aceitável (R$). "
            "Default: R$50. Acima disso = leilão competitivo ou público exaurido."
        )
    )
    max_cpl: Optional[float] = Field(
        default=None,
        gt=0,
        description="CPL máximo aceitável (R$). Relevante para campanhas de lead."
    )
    min_roas: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "ROAS mínimo aceitável. "
            "Obrigatório para detectar Cenário G (escala vertical) e Cenário K (canibalização)."
        )
    )

    # ── LANDING PAGE ──────────────────────────────────────────────────────────
    min_lp_conversion_rate: float = Field(
        default=1.0,
        gt=0,
        description=(
            "Taxa de conversão mínima na Landing Page (%). "
            "Default: 1%. CTR Link alto + LP abaixo disto = Cenário D."
        )
    )

    # ── AUDIÊNCIA / SATURAÇÃO ─────────────────────────────────────────────────
    max_frequency_fatigue: float = Field(
        default=2.8,
        gt=0,
        description=(
            "Frequência máxima antes de sinalizar fadiga de criativo. "
            "Default do PDF: 2.8 em 7 dias = Cenário E."
        )
    )
    max_frequency_critical: float = Field(
        default=6.0,
        gt=0,
        description=(
            "Frequência máxima antes de sinalizar saturação crítica. "
            "Default do PDF: >6 em retargeting = Cenário K (canibalização)."
        )
    )
    max_frequency_horizontal: float = Field(
        default=2.5,
        gt=0,
        description=(
            "Frequência que sinaliza necessidade de escala horizontal. "
            "Default do PDF: >2.5 com CPA ainda ok = Cenário H."
        )
    )

    # ── CONVERSÕES / APRENDIZADO ──────────────────────────────────────────────
    min_weekly_conversions: int = Field(
        default=50,
        gt=0,
        description=(
            "Mínimo de conversões por semana para sair do aprendizado limitado. "
            "Default do PDF: 50 conversões/semana."
        )
    )

    # ── ESCALA VERTICAL ───────────────────────────────────────────────────────
    scale_cpa_margin: float = Field(
        default=0.75,
        gt=0,
        le=1.0,
        description=(
            "Margem de CPA para liberar escala vertical (fração do max_cpa). "
            "Default do PDF: 75% — CPA deve estar 25% abaixo da meta para escalar."
        )
    )
    scale_frequency_ceiling: float = Field(
        default=1.8,
        gt=0,
        description=(
            "Frequência máxima permitida para autorizar escala vertical. "
            "Default do PDF: <1.8 — audiência ainda fresca para receber mais verba."
        )
    )


class AnalyzeInput(BaseModel):
    campaign: Campaign
    metrics: Metrics
    targets: Targets


# ─────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────

class ScenarioDetail(BaseModel):
    code: ScenarioCode
    title: str
    root_cause: str
    funnel_impact: str
    action: str
    execution_rule: str
    priority: int = Field(description="1 = crítico, 2 = urgente, 3 = monitorar")


class MetricEvaluation(BaseModel):
    metric: str
    value: Optional[float]
    status: CampaignStatus
    note: str


class CampaignAnalysisResponse(BaseModel):
    campaign_id: int
    campaign_name: str
    final_status: CampaignStatus
    summary: str
    scenarios: list[ScenarioDetail]
    metric_evaluations: list[MetricEvaluation]
    primary_action: str