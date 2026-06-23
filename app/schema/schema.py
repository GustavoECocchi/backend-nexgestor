"""
Schemas Pydantic do domínio NexGestor.

Organizado em 3 blocos:
  1. INPUT — modelos que o backend RECEBE (Campaign, Metrics, Targets, AnalyzeInput)
  2. OUTPUT do engine — diagnóstico determinístico (ScenarioDetail, MetricEvaluation)
  3. OUTPUT da IA — análise complementar (AIScenario, AIInsight, AIRisk, AIInsights)
  4. RESPONSE final — agregação dos itens acima (CampaignAnalysisResponse)
"""
from typing import Optional, Literal
from pydantic import Field, BaseModel

from app.enum.campaign import CampaignStatus, ScenarioCode


# ─────────────────────────────────────────────────────────────────────────────
# 1. INPUT — o que o backend recebe via POST /api/v1/campaign/analyze
# ─────────────────────────────────────────────────────────────────────────────

class Campaign(BaseModel):
    """Identificação e contexto da campanha sendo analisada."""
    id: int
    name: str = Field(min_length=1, max_length=200, description="Nome da campanha (1–200 chars)")
    objective: Optional[str] = Field(default="conversion", description="conversion | lead | traffic")
    platform: Optional[str] = Field(default="meta_ads", description="meta_ads | google_ads")
    niche: Optional[str] = Field(default=None, description="Ex: SaaS, ecommerce, infoproduto")


class Metrics(BaseModel):
    """
    Métricas brutas da campanha. Todas opcionais — o engine analisa o que receber.
    Métricas derivadas (hook_rate, hold_rate, ctr_link, ctr_all, cpm, cpc, cpa,
    lp_conversion_rate, frequency) podem ser enviadas prontas OU calculadas pelo
    engine a partir dos dados brutos correspondentes.
    """

    # ── Entrega ──
    impressions: Optional[int] = Field(default=None, ge=0, description="Total de impressões")
    reach: Optional[int] = Field(default=None, ge=0, description="Alcance único")
    spend: Optional[float] = Field(default=None, ge=0, description="Gasto total (R$)")

    # ── Vídeo / atenção ──
    video_views_3s: Optional[int] = Field(default=None, ge=0, description="Views de pelo menos 3s")
    video_views_50pct: Optional[int] = Field(default=None, ge=0, description="Views até 50%")
    thruplays: Optional[int] = Field(default=None, ge=0, description="ThruPlays (97% ou 15s+)")
    hook_rate: Optional[float] = Field(default=None, ge=0, description="% — Meta: >35%")
    hold_rate: Optional[float] = Field(default=None, ge=0, description="% — Meta: >15%")

    # ── Cliques ──
    link_clicks: Optional[int] = Field(default=None, ge=0, description="Cliques no link")
    all_clicks: Optional[int] = Field(default=None, ge=0, description="Cliques (todos os tipos)")
    ctr_link: Optional[float] = Field(default=None, ge=0, description="% — Meta: >1.5%")
    ctr_all: Optional[float] = Field(default=None, ge=0, description="% — Click-bait se >3.5% com CTR Link baixo")

    # ── Custo ──
    cpm: Optional[float] = Field(default=None, ge=0, description="Custo por mil impressões")
    cpc: Optional[float] = Field(default=None, ge=0, description="Custo por clique no link")
    cpl: Optional[float] = Field(default=None, ge=0, description="Custo por lead")
    cpa: Optional[float] = Field(default=None, ge=0, description="Custo por aquisição")
    roas: Optional[float] = Field(default=None, ge=0, description="Return on Ad Spend")

    # ── Landing Page ──
    landing_page_views: Optional[int] = Field(default=None, ge=0, description="Views reais da LP")
    lp_conversion_rate: Optional[float] = Field(default=None, ge=0, description="% — Meta: >1%")

    # ── Conversões ──
    conversions: Optional[int] = Field(default=None, ge=0, description="Conversões no período")
    weekly_conversions: Optional[int] = Field(default=None, ge=0, description="Conversões nos últimos 7 dias (mínimo: 50)")

    # ── Audiência ──
    frequency: Optional[float] = Field(default=None, ge=0, description="Frequência média — fadiga em >2.8")
    learning_phase: Optional[bool] = Field(default=None, description="True = conjunto em Aprendizado Limitado")


class Targets(BaseModel):
    """
    Metas/thresholds que o gestor define para a campanha.
    Defaults são baseados nos benchmarks do PDF de referência.
    """

    # ── Criativo ──
    min_hook_rate: float = Field(default=35.0, gt=0, description="Hook Rate mínimo (%)")
    min_hold_rate: float = Field(default=15.0, gt=0, description="Hold Rate mínimo (%)")

    # ── Cliques ──
    min_ctr_link: float = Field(default=1.5, gt=0, description="CTR Link mínimo (%)")
    max_ctr_all_ratio: float = Field(default=3.5, gt=0, description="CTR Todos máximo antes de suspeitar click-bait")

    # ── Custo ──
    max_cpa: Optional[float] = Field(default=None, gt=0, description="CPA máximo — obrigatório p/ cenários D,F,G,H")
    max_cpc: Optional[float] = Field(default=None, gt=0, description="CPC máximo aceitável")
    max_cpm: float = Field(default=50.0, gt=0, description="CPM máximo aceitável")
    max_cpl: Optional[float] = Field(default=None, gt=0, description="CPL máximo (para campanhas de lead)")
    min_roas: Optional[float] = Field(default=None, gt=0, description="ROAS mínimo — obrigatório p/ cenários G e K")

    # ── Landing Page ──
    min_lp_conversion_rate: float = Field(default=1.0, gt=0, description="Conversão LP mínima (%)")

    # ── Frequência ──
    max_frequency_fatigue: float = Field(default=2.8, gt=0, description="Disparo de Cenário E")
    max_frequency_critical: float = Field(default=6.0, gt=0, description="Disparo de Cenário K")
    max_frequency_horizontal: float = Field(default=2.5, gt=0, description="Disparo de Cenário H")

    # ── Aprendizado ──
    min_weekly_conversions: int = Field(default=50, gt=0, description="Mínimo p/ sair do aprendizado limitado")

    # ── Escala vertical ──
    scale_cpa_margin: float = Field(default=0.75, gt=0, le=1.0, description="CPA deve estar abaixo de max_cpa*margin")
    scale_frequency_ceiling: float = Field(default=1.8, gt=0, description="Frequency máxima p/ liberar escala")


class AnalyzeInput(BaseModel):
    """Payload completo do POST /api/v1/campaign/analyze."""
    campaign: Campaign
    metrics: Metrics
    targets: Targets


# ─────────────────────────────────────────────────────────────────────────────
# 2. OUTPUT do engine determinístico
# ─────────────────────────────────────────────────────────────────────────────

class ScenarioDetail(BaseModel):
    """
    Cenário detectado pelo engine (A–K).
    Cada cenário traz causa raiz, impacto no funil, ação e regra de execução.
    """
    code: ScenarioCode
    title: str
    root_cause: str         # Por que está acontecendo, com números reais
    funnel_impact: str      # O que isso causa no funil
    action: str             # Ação curta e direta
    execution_rule: str     # Passo-a-passo da ação
    priority: int = Field(description="1=crítico, 2=urgente, 3=monitorar")


class MetricEvaluation(BaseModel):
    """Avaliação individual de uma métrica — status semafórico + score 0–100."""
    metric: str
    value: Optional[float]
    status: CampaignStatus
    score: int = Field(description="0–100 — distância proporcional ao target")
    note: str


# ─────────────────────────────────────────────────────────────────────────────
# 3. OUTPUT da IA (Gemini) — opcional, complementa o engine
# ─────────────────────────────────────────────────────────────────────────────

class AIScenario(BaseModel):
    """Cenário identificado pela IA que NÃO está coberto pelos 11 do engine."""
    title: str = Field(description="Nome curto (5–10 palavras)")
    description: str = Field(description="Por que está acontecendo, citando dados")
    recommended_action: str = Field(description="Ação concreta — 1 frase")
    confidence: Literal["high", "medium", "low"]


class AIInsight(BaseModel):
    """Padrão cruzado entre métricas que o engine isolado não vê."""
    title: str
    explanation: str


class AIRisk(BaseModel):
    """Alerta preventivo — algo que ainda não é problema mas pode virar."""
    title: str
    explanation: str
    timeframe: str = Field(description="Janela estimada (ex: '48h', '1 semana')")


class AIInsights(BaseModel):
    """
    Resposta da camada de IA. Sempre complementa, nunca substitui o engine.
    Quantidade limitada (3+3+2) para forçar foco em qualidade > quantidade.
    """
    executive_summary: str = Field(description="Resumo executivo em 1–2 frases")
    extra_scenarios: list[AIScenario] = Field(default_factory=list, description="Máx 3")
    contextual_insights: list[AIInsight] = Field(default_factory=list, description="Máx 3")
    risk_warnings: list[AIRisk] = Field(default_factory=list, description="Máx 2")


# ─────────────────────────────────────────────────────────────────────────────
# 4. RESPONSE final do POST /api/v1/campaign/analyze
# ─────────────────────────────────────────────────────────────────────────────

class CampaignAnalysisResponse(BaseModel):
    """
    Resposta agregada do POST /api/v1/campaign/analyze.
    Engine sempre preenche; ai_insights só existe se IA está configurada e funcionou.
    """
    campaign_id: int
    campaign_name: str
    final_status: CampaignStatus
    overall_score: int = Field(description="0–100 — média ponderada das métricas")
    score_coverage: int = Field(
        description=(
            "0–100 — % do peso total das métricas que foi efetivamente avaliado. "
            "Score alto com coverage baixo = poucos dados, baixa confiança."
        )
    )
    score_confidence: Literal["high", "medium", "low"] = Field(
        description="Confiança no overall_score, derivada do coverage (high≥70 | medium≥40 | low<40)"
    )
    summary: str
    scenarios: list[ScenarioDetail]
    metric_evaluations: list[MetricEvaluation]
    primary_action: str
    ai_insights: Optional[AIInsights] = Field(
        default=None,
        description="Camada de IA — null se desativada ou falhou"
    )
