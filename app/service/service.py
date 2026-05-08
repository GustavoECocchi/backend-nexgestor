"""
Service layer — NexGestor Decision Engine

Orquestra o pipeline de análise:
1. Classificação de métricas (benchmarks)
2. Scoring
3. Diagnóstico de cenário
4. Geração de insights e recomendações
5. Composição da resposta final
"""

from app.enum.campaign import CampaignStatus, MetricLevel
from app.schema.schema import AnalyzeInput, CampaignAnalysisResponse, MetricDiagnosis
from app.engine.benchmarks import get_ctr_level, get_cpc_level, get_cpa_level
from app.engine.scoring import calculate_score, score_to_health
from app.engine.diagnostics import detect_scenario
from app.engine.insights import generate_insights, generate_recommendations


METRIC_LEVEL_LABELS = {
    MetricLevel.VERY_GOOD: "Muito bom",
    MetricLevel.GOOD: "Bom",
    MetricLevel.AVERAGE: "Abaixo do ideal",
    MetricLevel.BAD: "Crítico",
}


def _level_to_legacy_status(level: MetricLevel) -> CampaignStatus:
    if level in (MetricLevel.VERY_GOOD, MetricLevel.GOOD):
        return CampaignStatus.GREEN
    elif level == MetricLevel.AVERAGE:
        return CampaignStatus.YELLOW
    else:
        return CampaignStatus.RED


def analyze_campaign(data: AnalyzeInput) -> CampaignAnalysisResponse:
    metrics = data.metrics
    targets = data.targets
    campaign = data.campaign

    context = {
        "niche": campaign.niche,
        "platform": campaign.platform,
        "objective": campaign.objective,
    }

    # 1. Classificação de métricas
    ctr_level = get_ctr_level(metrics.ctr, min_ctr=targets.min_ctr, **context)
    cpc_level = get_cpc_level(metrics.cpc, **context)
    cpa_level = get_cpa_level(metrics.cpa, max_cpa=targets.max_cpa, **context)

    # 2. Score e health
    score = calculate_score(ctr_level, cpc_level, cpa_level)
    health = score_to_health(score)

    # 3. Diagnóstico de cenário
    scenario = detect_scenario(ctr_level, cpc_level, cpa_level)

    # 4. Insights e recomendações
    insights = generate_insights(ctr_level, cpc_level, cpa_level, metrics)
    recommendations = generate_recommendations(ctr_level, cpc_level, cpa_level, scenario)

    # 5. Diagnóstico por métrica
    metrics_diagnosis = {
        "ctr": MetricDiagnosis(
            value=metrics.ctr,
            level=ctr_level,
            label=METRIC_LEVEL_LABELS[ctr_level],
        ),
        "cpc": MetricDiagnosis(
            value=metrics.cpc,
            level=cpc_level,
            label=METRIC_LEVEL_LABELS[cpc_level],
        ),
        "cpa": MetricDiagnosis(
            value=metrics.cpa,
            level=cpa_level,
            label=METRIC_LEVEL_LABELS[cpa_level],
        ),
    }

    # 6. Legacy compatibility
    cpa_status = _level_to_legacy_status(cpa_level)
    ctr_status = _level_to_legacy_status(ctr_level)

    if cpa_level == MetricLevel.BAD or ctr_level == MetricLevel.BAD:
        final_status = CampaignStatus.RED
    elif cpa_level == MetricLevel.AVERAGE or ctr_level == MetricLevel.AVERAGE:
        final_status = CampaignStatus.YELLOW
    else:
        final_status = CampaignStatus.GREEN

    # Recomendação legada (resumo)
    legacy_rec = recommendations[0] if recommendations else "Monitorar campanha"

    return CampaignAnalysisResponse(
        # Legacy
        cpa_status=cpa_status,
        ctr_status=ctr_status,
        final_status=final_status,
        recommendation=legacy_rec,

        # Engine v2
        score=score,
        health=health,
        primary_problem=scenario["primary_problem"],
        funnel_bottleneck=scenario["funnel_bottleneck"],
        metrics_diagnosis=metrics_diagnosis,
        symptoms=scenario["symptoms"],
        possible_causes=scenario["possible_causes"],
        consequences=scenario["consequences"],
        insights=insights,
        recommendations=recommendations,
    )