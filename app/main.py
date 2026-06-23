"""
NexGestor — Entry point da aplicação FastAPI.

Este arquivo monta a aplicação, configura CORS e registra as rotas.
Para subir o servidor em dev: `uvicorn app.main:app --reload`
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import routes
from app.core.config import settings


# Instância principal do FastAPI — exposta no /docs e /redoc.
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "NexGestor — Decision Engine para Tráfego Pago.\n\n"
        "Analisa métricas de campanhas Meta Ads/Google Ads, detecta cenários "
        "de performance e gera diagnósticos com causa raiz e ação executável. "
        "Combina engine de regras determinístico com camada de IA (Gemini)."
    ),
    version="1.0.0",
)

# CORS — origens permitidas vêm do .env (CORS_ORIGINS) para facilitar
# trocar dev/staging/produção sem mexer em código.
#
# allow_origins        → lista explícita (localhost de dev, domínios de produção)
# allow_origin_regex   → casa chrome-extension://<id> sem precisar fixar o ID
#                        (o ID muda entre extensão unpacked e publicada)
# Uma origin é aceita se bater na LISTA *ou* no REGEX. Não usamos ["*"]
# porque é inválido em conjunto com allow_credentials=True.
_cors_kwargs = {
    "allow_origins": settings.CORS_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
# Só passa o regex se ele estiver preenchido (string vazia desliga o recurso).
if settings.CORS_ORIGIN_REGEX:
    _cors_kwargs["allow_origin_regex"] = settings.CORS_ORIGIN_REGEX

app.add_middleware(CORSMiddleware, **_cors_kwargs)


@app.get("/", tags=["Health"], summary="Health check")
def health_check():
    """Endpoint público para verificar se a aplicação está no ar."""
    return {"status": "ok", "app": settings.APP_NAME}


# Registra as rotas do módulo `campaign` sob o prefixo /api/v1.
app.include_router(routes.router, prefix=settings.API_V1_STR)
