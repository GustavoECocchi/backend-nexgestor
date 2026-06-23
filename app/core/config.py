"""
Configurações da aplicação carregadas do .env via pydantic-settings.

Adicione novas variáveis criando atributos tipados na classe `Settings`.
Os valores podem ser sobrescritos via .env ou variável de ambiente.
"""
from typing import Optional
from typing_extensions import Annotated
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class Settings(BaseSettings):
    """Schema central de configuração — todos os módulos importam `settings` daqui."""

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "NexGestor"
    # Default seguro: False. Ligue DEBUG=True no .env apenas em desenvolvimento.
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # ── CORS ─────────────────────────────────────────────
    # Aceita no .env tanto JSON quanto vírgula-separada (o validator abaixo
    # normaliza). Exemplos equivalentes:
    #   CORS_ORIGINS=["http://localhost:5173","https://app.nexgestor.com"]
    #   CORS_ORIGINS=http://localhost:5173,https://app.nexgestor.com
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # A extensão (Plasmo) emite requisições de chrome-extension://<EXTENSION_ID>.
    # O <EXTENSION_ID> muda entre a extensão carregada localmente (unpacked) e a
    # publicada na store, então em dev usamos um regex que aceita qualquer
    # extensão Chrome/Brave. Em produção, troque por uma origin fixa em
    # CORS_ORIGINS e, se quiser travar, defina CORS_ORIGIN_REGEX="" no .env.
    CORS_ORIGIN_REGEX: str = r"chrome-extension://.*"

    # ── Gemini (IA) ──────────────────────────────────────
    # Sem chave configurada => IA fica desligada e o engine funciona normalmente.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TIMEOUT_SECONDS: float = 8.0
    GEMINI_ENABLED: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """
        Aceita CORS_ORIGINS no .env como JSON (["a","b"]) OU vírgula-separada
        (a,b). Usamos NoDecode no campo para o pydantic-settings NÃO tentar o
        json.loads automático (que derrubava o boot com vírgula simples) —
        este validator assume o parsing dos dois formatos.
        """
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                import json
                return json.loads(s)  # formato JSON explícito
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    @property
    def ai_available(self) -> bool:
        """True se a IA tem chave configurada E está habilitada via toggle."""
        return self.GEMINI_ENABLED and bool(self.GEMINI_API_KEY)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Singleton — importe `settings` em qualquer módulo que precise.
settings = Settings()
