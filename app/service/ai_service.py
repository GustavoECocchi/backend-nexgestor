"""
Camada de IA — única porta de comunicação entre o backend e o Gemini.

Princípios:
  • IA é OPCIONAL — se falhar, o engine de regras continua entregando
  • Timeout agressivo (8s default) — não trava o request principal
  • Função assíncrona p/ integração com asyncio.gather no service.py

Se trocar de provedor (OpenAI, Claude, etc.) no futuro, apenas este arquivo muda.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


# Padrão de API key do Google (AIza + 35 chars). Usado para não vazar a key em logs.
_API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")


def _redact_key(text: str) -> str:
    """Mascara qualquer API key do Google que apareça em mensagens de erro/log."""
    return _API_KEY_PATTERN.sub("AIza***REDACTED***", text)


# ─────────────────────────────────────────────────────────────────────────────
# Disponibilidade — checa se vale a pena tentar chamar a IA
# ─────────────────────────────────────────────────────────────────────────────

def is_ai_available() -> bool:
    """
    Retorna False se: GEMINI_API_KEY vazia, GEMINI_ENABLED=False,
    ou SDK do Gemini não está instalado.
    """
    if not settings.ai_available:
        return False
    return _sdk_installed()


# Cache do "SDK está instalado?" — o resultado não muda em runtime, então
# evitamos re-importar o google-genai a cada request (era chamado ~2x por análise).
_sdk_ok: Optional[bool] = None


def _sdk_installed() -> bool:
    """Checa (uma vez) se o SDK google-genai está disponível."""
    global _sdk_ok
    if _sdk_ok is None:
        try:
            from google import genai  # noqa: F401
            _sdk_ok = True
        except ImportError:
            logger.warning("google-genai não está instalado — IA desativada")
            _sdk_ok = False
    return _sdk_ok


# ─────────────────────────────────────────────────────────────────────────────
# Cliente — singleton para evitar criar a cada chamada
# ─────────────────────────────────────────────────────────────────────────────

_client = None
_client_key = None  # key usada para criar o _client atual — detecta rotação


def _get_client():
    """
    Retorna o client do Gemini, criando-o na primeira chamada.

    Recria o client se a GEMINI_API_KEY mudou desde a última criação — assim a
    rotação de key tem efeito sem precisar reiniciar o processo (antes o client
    em memória ficava preso na key antiga).
    """
    global _client, _client_key
    current_key = settings.GEMINI_API_KEY
    if _client is None or _client_key != current_key:
        from google import genai
        _client = genai.Client(api_key=current_key)
        _client_key = current_key
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# Chamada genérica ao Gemini — usada por todas as funções de IA do backend
# ─────────────────────────────────────────────────────────────────────────────

async def call_gemini(prompt: str, response_schema: Optional[Any] = None) -> Optional[dict]:
    """
    Faz uma chamada ao Gemini com prompt + schema esperado da resposta.

    `response_schema` deve ser a CLASSE Pydantic (ex: AIInsights), NÃO o dict de
    `model_json_schema()`. O SDK resolve os sub-modelos inline; passar o dict gera
    `$defs`/`$ref`, que a API do Gemini rejeita (extra_forbidden) — era o bug que
    fazia a IA "morrer" silenciosamente.

    NUNCA lança exceção — toda falha é capturada e logada com a causa específica.
    Retorna o dict parseado em caso de sucesso, ou None em qualquer falha.
    """
    if not is_ai_available():
        return None

    try:
        return await asyncio.wait_for(
            _execute_call(prompt, response_schema),
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Gemini: timeout após %.1fs — seguindo só com o engine.",
            settings.GEMINI_TIMEOUT_SECONDS,
        )
        return None
    except Exception as e:
        # Inclui erros de schema, auth (key inválida/revogada), modelo sem acesso,
        # rede etc. Logamos a causa SEM o stack cru do SDK (que pode conter a URL
        # com a API key embutida) e sanitizamos qualquer 'AIza...' que escape.
        logger.warning(
            "Gemini: falha na chamada (%s) — seguindo só com o engine. Detalhe: %s",
            type(e).__name__, _redact_key(str(e)),
        )
        return None


async def _execute_call(prompt: str, response_schema: Optional[Any]) -> Optional[dict]:
    """
    Executa a chamada real ao Gemini.
    O SDK do google-genai é síncrono — rodamos em executor pra não bloquear o event loop.
    """
    loop = asyncio.get_running_loop()
    client = _get_client()

    def sync_call() -> Optional[dict]:
        from google.genai import types

        # response_schema (CLASSE Pydantic) força JSON estruturado.
        config = None
        if response_schema is not None:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
            )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        # 1) Caminho preferido: o SDK já parseou e validou contra o schema.
        #    Com response_schema setado, response.parsed traz o objeto pronto.
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()
            if isinstance(parsed, dict):
                return parsed

        # 2) Fallback: parsear o texto cru. Mais frágil — o modelo às vezes
        #    embrulha o JSON em cercas ```json ... ```.
        text = (response.text or "").strip()
        if not text:
            logger.warning("Gemini: resposta sem .parsed e sem texto.")
            return None

        text = _strip_code_fences(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Gemini: JSON inválido na resposta — %s", e)
            logger.debug("Gemini: resposta bruta (500 chars): %s", text[:500])
            return None

    return await loop.run_in_executor(None, sync_call)


def _strip_code_fences(text: str) -> str:
    """Remove cercas markdown (```json ... ```) que o modelo às vezes adiciona."""
    if not text.startswith("```"):
        return text
    # Remove a primeira linha de abertura (``` ou ```json) e a cerca final.
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — chamado pelo service.py em paralelo com o engine de regras
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_with_ai(
    metrics: Any,
    targets: Any,
    campaign: Any,
    engine_scenarios: Optional[list] = None,
    metric_evaluations: Optional[list] = None,
) -> Optional[dict]:
    """
    Roda análise da IA — opera em 2 modos automaticamente:

      • MODO COMPLEMENTAR: engine_scenarios não vazio → IA adiciona cenários
        extras, padrões cruzados e riscos futuros (sem repetir o que engine viu).

      • MODO PRINCIPAL: engine_scenarios vazio → IA assume o diagnóstico
        principal. Não pode retornar vazio.

    Returns:
        dict no formato AIInsights, ou None se IA indisponível/falhou.
    """
    if not is_ai_available():
        return None

    # Imports tardios — só carrega quando IA está realmente ativa.
    from app.service.prompts import SYSTEM_PROMPT, build_user_prompt
    from app.schema.schema import AIInsights

    engine_scenarios = engine_scenarios or []
    metric_evaluations = metric_evaluations or []

    user_prompt = build_user_prompt(
        metrics=metrics,
        targets=targets,
        campaign=campaign,
        engine_scenarios=engine_scenarios,
        metric_evaluations=metric_evaluations,
    )

    # Gemini não tem role "system" nativo — concatenamos com separador claro.
    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"

    # response_schema → passamos a CLASSE Pydantic. O SDK resolve os sub-modelos
    # (AIScenario/AIInsight/AIRisk) inline. Passar AIInsights.model_json_schema()
    # geraria $defs/$ref, que a API do Gemini rejeita.
    return await call_gemini(full_prompt, response_schema=AIInsights)
