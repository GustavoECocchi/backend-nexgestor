"""
Rotas HTTP do módulo Campaign.

Todas as rotas ficam sob /api/v1/campaign (prefixo definido aqui + em main.py).
A lógica de negócio fica em `service.py` — esta camada só roteia e trata erros.
"""
import logging
from fastapi import APIRouter, HTTPException

from app.schema.schema import AnalyzeInput, CampaignAnalysisResponse
from app.service.service import analyze_campaign_async
from app.enum.campaign import ScenarioCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaign", tags=["Campaign"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /campaign/analyze  →  path completo: POST /api/v1/campaign/analyze
#   (prefixo /api/v1 vem de main.py; prefixo /campaign vem deste router)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=CampaignAnalysisResponse,
    summary="Analisar campanha",
    description=(
        "Recebe métricas e targets de uma campanha e devolve diagnóstico "
        "completo: cenários detectados, score por métrica, overall score e "
        "ação primária. A IA (Gemini) roda em paralelo quando configurada."
    ),
)
async def analyze(data: AnalyzeInput) -> CampaignAnalysisResponse:
    """Handler único do endpoint de análise — delega 100% ao service."""
    try:
        return await analyze_campaign_async(data)
    except ValueError as e:
        # Erros de validação semântica do domínio.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # Bugs inesperados — logamos o stack completo e respondemos
        # genericamente para não vazar detalhes internos ao cliente.
        logger.exception("Erro interno em analyze_campaign")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar análise. A equipe foi notificada.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /campaign/scenarios
# Catálogo dos cenários que o engine sabe detectar.
# ─────────────────────────────────────────────────────────────────────────────

# Estrutura compacta: cada tupla é (código, título, condição, prioridade).
# Mantida aqui (não no enum) porque é metadado de documentação, não de domínio.
_SCENARIO_CATALOG: list[dict] = [
    {
        "code": ScenarioCode.WEAK_HOOK,
        "title": "Cenário A — Gancho Fraco",
        "trigger": "Hook Rate < 70% do target (default <24.5%)",
        "metrics": ["hook_rate", "ctr_link", "cpc"],
        "priority": "1 crítico se <70% target | 2 urgente caso contrário",
    },
    {
        "code": ScenarioCode.LOW_RETENTION,
        "title": "Cenário B — Retenção Baixa",
        "trigger": "Hook ok E Hold Rate < min_hold_rate (default 15%)",
        "metrics": ["hook_rate", "hold_rate", "thruplays"],
        "priority": "1 se Hold <10% | 2 entre 10–15%",
    },
    {
        "code": ScenarioCode.CLICK_BAIT,
        "title": "Cenário C — Click-Bait",
        "trigger": "CTR Todos > 3.5% E CTR Link < 0.7%",
        "metrics": ["ctr_all", "ctr_link"],
        "priority": "1 crítico",
    },
    {
        "code": ScenarioCode.LP_MISMATCH,
        "title": "Cenário D — LP Mismatch",
        "trigger": "CTR Link > 1.5x meta E LP conv. < min_lp_conversion_rate",
        "metrics": ["ctr_link", "lp_conversion_rate"],
        "priority": "1 crítico",
    },
    {
        "code": ScenarioCode.CREATIVE_FATIGUE,
        "title": "Cenário E — Fadiga de Criativo",
        "trigger": "Frequency > max_frequency_fatigue (default 2.8)",
        "metrics": ["frequency", "ctr_link", "cpa"],
        "priority": "1 se >80% do limite crítico | 2 caso contrário",
    },
    {
        "code": ScenarioCode.COLD_LEAD,
        "title": "Cenário F — Lead Frio",
        "trigger": "CPA/CPL ok E LP conv. < 50% do mínimo",
        "metrics": ["cpa", "cpl", "lp_conversion_rate"],
        "priority": "2 urgente",
    },
    {
        "code": ScenarioCode.VERTICAL_SCALE,
        "title": "Cenário G — Janela de Escala Vertical",
        "trigger": "CPA ≤ max_cpa*0.75 E freq < 1.8 E ROAS ok E não learning",
        "metrics": ["cpa", "roas", "frequency", "learning_phase"],
        "priority": "1 oportunidade",
    },
    {
        "code": ScenarioCode.HORIZONTAL_SCALE,
        "title": "Cenário H — Escala Horizontal",
        "trigger": "Frequency > 2.5 E CPA ok E não em fadiga plena",
        "metrics": ["frequency", "cpa", "cpm"],
        "priority": "2 urgente",
    },
    {
        "code": ScenarioCode.LEARNING_PHASE,
        "title": "Cenário I — Learning Phase Hell",
        "trigger": "learning_phase=True OU weekly_conv < min (default 50)",
        "metrics": ["learning_phase", "weekly_conversions"],
        "priority": "1 crítico",
    },
    {
        "code": ScenarioCode.OVERSPENDING,
        "title": "Cenário J — Overspending",
        "trigger": "CPM > max_cpm E LP saudável E CPA > max_cpa",
        "metrics": ["cpm", "lp_conversion_rate", "cpa"],
        "priority": "2 urgente",
    },
    {
        "code": ScenarioCode.RETARGETING_CANNIBAL,
        "title": "Cenário K — Canibalização de Retargeting",
        "trigger": "ROAS > 10x E frequency > max_frequency_critical (default 6)",
        "metrics": ["roas", "frequency", "ctr_link"],
        "priority": "1 crítico",
    },
]


@router.get(
    "/scenarios",
    summary="Listar cenários detectáveis",
    description="Catálogo dos 11 cenários do engine com condições de disparo.",
)
async def list_scenarios():
    """Devolve o catálogo de cenários — útil para frontend documentar a UI."""
    return {
        "total": len(_SCENARIO_CATALOG),
        "scenarios": [{**s, "code": s["code"].value} for s in _SCENARIO_CATALOG],
    }


@router.get("/health", include_in_schema=False)
async def health():
    """Health check interno do módulo Campaign (escondido do Swagger)."""
    return {"status": "ok", "engine": "nexgestor-decision-engine"}
