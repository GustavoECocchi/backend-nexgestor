"""
Scoring module — NexGestor Decision Engine

Score base: 100
Penalidades aplicadas conforme nível de cada métrica.
Ajustes contextuais entre métricas (causa/consequência).
"""

from app.enum.campaign import MetricLevel, HealthStatus


PENALTIES = {
    "ctr": {
        MetricLevel.VERY_GOOD: 0,
        MetricLevel.GOOD: 0,
        MetricLevel.AVERAGE: 10,
        MetricLevel.BAD: 30,
    },
    "cpc": {
        MetricLevel.VERY_GOOD: 0,
        MetricLevel.GOOD: 0,
        MetricLevel.AVERAGE: 10,
        MetricLevel.BAD: 20,
    },
    "cpa": {
        MetricLevel.VERY_GOOD: 0,
        MetricLevel.GOOD: 0,
        MetricLevel.AVERAGE: 15,
        MetricLevel.BAD: 40,
    },
}


def calculate_score(ctr_level: MetricLevel, cpc_level: MetricLevel, cpa_level: MetricLevel) -> int:
    score = 100

    score -= PENALTIES["ctr"][ctr_level]
    score -= PENALTIES["cpc"][cpc_level]
    score -= PENALTIES["cpa"][cpa_level]

    # Ajuste contextual: CTR ruim amplifica o impacto do CPC
    if ctr_level == MetricLevel.BAD and cpc_level in (MetricLevel.AVERAGE, MetricLevel.BAD):
        score -= 5

    # Ajuste contextual: CTR alto atenua impacto do CPC
    if ctr_level in (MetricLevel.VERY_GOOD, MetricLevel.GOOD) and cpc_level == MetricLevel.AVERAGE:
        score += 5

    return max(0, min(100, score))


def score_to_health(score: int) -> HealthStatus:
    if score >= 80:
        return HealthStatus.HEALTHY
    elif score >= 60:
        return HealthStatus.ATTENTION
    elif score >= 40:
        return HealthStatus.WARNING
    else:
        return HealthStatus.CRITICAL
