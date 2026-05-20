from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schema.schema import AnalyzeInput
from app.service.service import analyze_campaign
from app.db.database import get_db
from app.db.repository import get_or_create_account, save_analysis, get_recent_analyses

router = APIRouter(
    prefix="/campaign",
)


@router.post("/analyze")
async def analyze(data: AnalyzeInput, db: Session = Depends(get_db)):
    # Garante que a conta existe no banco
    get_or_create_account(db, account_id=data.account_id, name=data.account_name)

    # Busca histórico dessa campanha para esse gestor
    history = get_recent_analyses(db, account_id=data.account_id, campaign_id=data.campaign.id)

    # Roda a engine
    result = analyze_campaign(data)

    # Calcula tendência se houver análise anterior
    if history:
        previous = history[0]
        delta = result.score - previous.score
        result.previous_score = previous.score
        result.score_delta = delta

        if delta > 10:
            result.trend = f"Melhora de {delta} pontos em relação à última análise"
        elif delta < -10:
            result.trend = f"Queda de {abs(delta)} pontos em relação à última análise — atenção"
        elif delta == 0:
            result.trend = "Score estável em relação à última análise"
        else:
            result.trend = f"Variação pequena de {delta:+d} pontos — campanha estável"

    # Salva a análise atual
    save_analysis(db, account_id=data.account_id, data=data, result=result)

    return result