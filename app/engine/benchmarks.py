"""
Benchmarks module — NexGestor Decision Engine

FASE 1: Baselines genéricos de mercado.
Estrutura preparada para evoluir com benchmarks contextuais (nicho, plataforma, objetivo).
"""

from app.enum.campaign import MetricLevel


# --- Generic baselines ---

CTR_RANGES = [
    (3.0, float("inf"), MetricLevel.VERY_GOOD),
    (2.0, 3.0, MetricLevel.GOOD),
    (1.0, 2.0, MetricLevel.AVERAGE),
    (0.0, 1.0, MetricLevel.BAD),
]

CPC_RANGES = [
    (0.0, 1.0, MetricLevel.VERY_GOOD),
    (1.0, 2.0, MetricLevel.GOOD),
    (2.0, 4.0, MetricLevel.AVERAGE),
    (4.0, float("inf"), MetricLevel.BAD),
]

CPA_RANGES = [
    (0.0, 20.0, MetricLevel.VERY_GOOD),
    (20.0, 40.0, MetricLevel.GOOD),
    (40.0, 70.0, MetricLevel.AVERAGE),
    (70.0, float("inf"), MetricLevel.BAD),
]


def classify_metric(value: float, ranges: list) -> MetricLevel:
    for low, high, level in ranges:
        if low <= value < high:
            return level
    return MetricLevel.BAD


def get_ctr_level(ctr: float, min_ctr: float = None, niche: str = None, platform: str = None, objective: str = None) -> MetricLevel:
    """
    Se min_ctr for fornecido pelo usuário, usa como referência relativa (igual ao CPA).
    FASE 2 (futuro): usar niche/platform/objective para selecionar benchmark contextual.
    FASE 1: baseline genérico como fallback.
    """
    if min_ctr:
        ratio = ctr / min_ctr
        if ratio >= 1.5:
            return MetricLevel.VERY_GOOD
        elif ratio >= 1.0:
            return MetricLevel.GOOD
        elif ratio >= 0.7:
            return MetricLevel.AVERAGE
        else:
            return MetricLevel.BAD
    return classify_metric(ctr, CTR_RANGES)


def get_cpc_level(cpc: float, niche: str = None, platform: str = None, objective: str = None) -> MetricLevel:
    return classify_metric(cpc, CPC_RANGES)


def get_cpa_level(cpa: float, max_cpa: float = None, niche: str = None, platform: str = None, objective: str = None) -> MetricLevel:
    """
    Se max_cpa for fornecido pelo usuário, prioriza proporção relativa ao target.
    """
    if max_cpa:
        ratio = cpa / max_cpa
        if ratio <= 0.7:
            return MetricLevel.VERY_GOOD
        elif ratio <= 1.0:
            return MetricLevel.GOOD
        elif ratio <= 1.3:
            return MetricLevel.AVERAGE
        else:
            return MetricLevel.BAD
    return classify_metric(cpa, CPA_RANGES)