from fastapi import FastAPI
from app.routes import routes
from app.core.config import settings
from app.db.database import engine
from app.db import models

# Cria as tabelas no banco ao iniciar
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)


@app.get("/")
def health_check():
    return {"status": "ok"}


app.include_router(routes.router, prefix=settings.API_V1_STR)
