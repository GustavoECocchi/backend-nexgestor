"""
NexGestor — Testes da Integração engine + IA
==============================================

Cobertura:
  - IA desativada (sem GEMINI_API_KEY)
  - IA disponível + engine detectou cenário (modo complementar)
  - IA disponível + engine vazio (modo principal — IA assume)
  - IA falhou silenciosamente (timeout, erro de API)
  - IA retornou JSON inválido
  - Engine vazio + IA falha → fallback mínimo ativa
  - Payload super mínimo → orientação útil
  - Schema do AIInsights respeitando limites

Executar:
  pytest test_ai_integration.py -v
"""

import sys
import json
import asyncio
from unittest.mock import patch, AsyncMock

sys.path.insert(0, ".")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schema.schema import (
    AnalyzeInput, Campaign, Metrics, Targets,
    AIInsights, AIScenario, AIInsight, AIRisk,
)
from app.service.service import analyze_campaign_async, _apply_minimal_fallback
from app.enum.campaign import ScenarioCode, CampaignStatus

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES — payloads reutilizáveis
# ─────────────────────────────────────────────────────────────────────────────

def make_payload_with_scenario():
    """Payload que dispara Cenário A (Gancho Fraco) no engine."""
    return {
        "campaign": {"id": 1, "name": "Hook fraco"},
        "metrics": {
            "impressions": 50000, "reach": 42000, "spend": 1500.0,
            "video_views_3s": 8000,  # hook 16% — crítico
            "thruplays": 2000, "link_clicks": 500, "conversions": 15,
        },
        "targets": {"max_cpa": 60.0},
    }


def make_payload_atypical():
    """Payload atípico — nenhum dos 11 cenários do PDF dispara."""
    return {
        "campaign": {"id": 2, "name": "Atípico"},
        "metrics": {
            "impressions": 30000, "spend": 500.0,
            "reach": 25000, "link_clicks": 300,
            "conversions": 10, "cpa": 50.0,
        },
        "targets": {"max_cpa": 80.0},
    }


def make_payload_minimo():
    """Payload super mínimo — quase nenhum dado."""
    return {
        "campaign": {"id": 3, "name": "Mínimo"},
        "metrics": {"impressions": 1000, "reach": 800, "spend": 50.0},
        "targets": {},
    }


def make_ai_response_completa():
    """Resposta simulada da IA — formato completo."""
    return {
        "executive_summary": "Análise da IA: campanha com padrão de saturação iminente.",
        "extra_scenarios": [
            {
                "title": "Sobreposição de público suspeita",
                "description": "Padrões nas métricas sugerem possível overlap entre conjuntos.",
                "recommended_action": "Auditar overlap via Audience Manager.",
                "confidence": "medium",
            }
        ],
        "contextual_insights": [
            {
                "title": "CPM e frequência subindo juntos",
                "explanation": "Padrão duplo: leilão competitivo + audiência cansada.",
            }
        ],
        "risk_warnings": [
            {
                "title": "Risco de learning phase reset",
                "explanation": "Pacing irregular pode disparar reaprendizado.",
                "timeframe": "próximas 48h",
            }
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# IA DESATIVADA — comportamento sem GEMINI_API_KEY
# ─────────────────────────────────────────────────────────────────────────────

class TestIADesativada:
    """Quando GEMINI_API_KEY está vazia, IA fica desativada silenciosamente."""

    def test_engine_detecta_cenario_ai_none(self):
        """Engine detecta cenário, ai_insights deve ser None."""
        r = client.post("/api/v1/campaign/analyze", json=make_payload_with_scenario())
        assert r.status_code == 200
        body = r.json()
        assert len(body["scenarios"]) >= 1, "Engine deve detectar Cenário A"
        assert body["ai_insights"] is None, "IA desativada → ai_insights=None"

    def test_engine_vazio_aciona_fallback(self):
        """Engine vazio + IA desativada → fallback mínimo ativa."""
        r = client.post("/api/v1/campaign/analyze", json=make_payload_minimo())
        assert r.status_code == 200
        body = r.json()
        # Nunca deve retornar análise vazia
        assert body["summary"], "summary não pode estar vazio"
        assert body["primary_action"], "primary_action não pode estar vazio"

    def test_payload_minimo_retorna_orientacao(self):
        """Payload sem métricas avaliáveis recebe mensagem orientativa."""
        payload = {
            "campaign": {"id": 1, "name": "Quase vazio"},
            "metrics": {},   # nenhuma métrica
            "targets": {},
        }
        r = client.post("/api/v1/campaign/analyze", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["summary"], "Deve ter summary mesmo sem dados"
        assert body["scenarios"] == [], "Sem dados, sem cenários"


# ─────────────────────────────────────────────────────────────────────────────
# IA DISPONÍVEL — comportamento com Gemini mockado
# ─────────────────────────────────────────────────────────────────────────────

class TestIADisponivel:
    """Simula IA disponível usando mocks."""

    @pytest.mark.asyncio
    async def test_modo_complementar_anexa_insights(self):
        """Engine detecta cenário + IA retorna insights → ambos no response."""
        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(return_value=make_ai_response_completa())):

            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Test"),
                metrics=Metrics(
                    impressions=50000, reach=42000, spend=1500.0,
                    video_views_3s=8000, thruplays=2000,
                    link_clicks=500, conversions=15,
                ),
                targets=Targets(max_cpa=60.0),
            )

            response = await analyze_campaign_async(data)

            # Engine detectou cenário
            assert len(response.scenarios) >= 1
            assert response.scenarios[0].code == ScenarioCode.WEAK_HOOK

            # IA também respondeu
            assert response.ai_insights is not None
            assert response.ai_insights.executive_summary
            assert len(response.ai_insights.extra_scenarios) == 1
            assert len(response.ai_insights.contextual_insights) == 1
            assert len(response.ai_insights.risk_warnings) == 1

    @pytest.mark.asyncio
    async def test_modo_principal_ia_assume_quando_engine_vazio(self):
        """Engine não detecta nada + IA disponível → IA preenche."""
        ai_response = {
            "executive_summary": "IA detectou um padrão atípico não coberto pelo engine.",
            "extra_scenarios": [
                {
                    "title": "Padrão atípico detectado",
                    "description": "Conversões existem mas taxa LP baixa pode indicar tracking.",
                    "recommended_action": "Verificar configuração do pixel.",
                    "confidence": "low",
                }
            ],
            "contextual_insights": [],
            "risk_warnings": [],
        }

        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(return_value=ai_response)):

            # Dados que não disparam nenhum cenário
            data = AnalyzeInput(
                campaign=Campaign(id=2, name="Atípico"),
                metrics=Metrics(
                    impressions=30000, spend=500.0, reach=25000,
                    link_clicks=300, conversions=10, cpa=50.0,
                ),
                targets=Targets(max_cpa=80.0),
            )

            response = await analyze_campaign_async(data)

            # IA assumiu o diagnóstico
            assert response.ai_insights is not None
            assert response.ai_insights.executive_summary
            assert len(response.ai_insights.extra_scenarios) == 1


# ─────────────────────────────────────────────────────────────────────────────
# CAMADA SDK GEMINI — regressão dos bugs de integração corrigidos
# Mocka só a chamada HTTP (generate_content); todo o resto do fluxo é real:
# montagem do config, response_schema, leitura de .parsed, validação.
# ─────────────────────────────────────────────────────────────────────────────

class TestGeminiSDKLayer:
    """Protege as correções: schema sem $ref, uso de .parsed, fluxo end-to-end."""

    def _fake_response(self, payload: dict):
        """Simula o objeto que o SDK retorna: .parsed (objeto) + .text (json)."""
        from unittest.mock import MagicMock
        from app.schema.schema import AIInsights
        resp = MagicMock()
        resp.parsed = AIInsights.model_validate(payload)
        resp.text = json.dumps(payload)
        return resp

    def _payload(self):
        return {
            "executive_summary": "Padrão de saturação iminente detectado.",
            "extra_scenarios": [{
                "title": "Overlap de público",
                "description": "Conjuntos disputando o mesmo leilão.",
                "recommended_action": "Auditar overlap no Audience Manager.",
                "confidence": "medium",
            }],
            "contextual_insights": [{
                "title": "CPM e frequência subindo juntos",
                "explanation": "Leilão competitivo + audiência cansada.",
            }],
            "risk_warnings": [{
                "title": "Risco de reset de aprendizado",
                "explanation": "Pacing irregular pode disparar reaprendizado.",
                "timeframe": "48h",
            }],
        }

    @pytest.mark.asyncio
    async def test_response_schema_e_a_classe_nao_o_dict(self):
        """REGRESSÃO Buraco 1: o schema enviado ao Gemini é a CLASSE AIInsights,
        nunca model_json_schema() (que geraria $defs/$ref e seria rejeitado)."""
        from unittest.mock import patch, MagicMock
        from app.schema.schema import AIInsights

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = self._fake_response(self._payload())

        with patch("app.service.ai_service.settings") as ms, \
             patch("app.service.ai_service._get_client", return_value=fake_client):
            ms.ai_available = True
            ms.GEMINI_ENABLED = True
            ms.GEMINI_API_KEY = "AIzaFAKE"
            ms.GEMINI_MODEL = "gemini-2.5-flash"
            ms.GEMINI_TIMEOUT_SECONDS = 8.0

            from app.service.service import analyze_campaign_async

            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Test", niche="SaaS"),
                metrics=Metrics(impressions=50000, reach=42000, spend=1500.0,
                                video_views_3s=8000, link_clicks=500, conversions=15),
                targets=Targets(max_cpa=60.0),
            )
            response = await analyze_campaign_async(data)

            # IA respondeu via fluxo real
            assert response.ai_insights is not None
            assert len(response.ai_insights.extra_scenarios) == 1

            # O schema passado ao SDK é a classe — não um dict com $defs/$ref
            cfg = fake_client.models.generate_content.call_args.kwargs.get("config")
            assert cfg.response_schema is AIInsights
            assert not isinstance(cfg.response_schema, dict)

    @pytest.mark.asyncio
    async def test_usa_parsed_quando_disponivel(self):
        """REGRESSÃO Buraco 2: prioriza response.parsed em vez de json.loads(text)."""
        from unittest.mock import patch, MagicMock

        # .text é JSON quebrado de propósito; só .parsed é válido.
        # Se o código usar .parsed (correto), funciona mesmo com text inválido.
        from app.schema.schema import AIInsights
        resp = MagicMock()
        resp.parsed = AIInsights.model_validate(self._payload())
        resp.text = "isso não é json {{{"

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = resp

        with patch("app.service.ai_service.settings") as ms, \
             patch("app.service.ai_service._get_client", return_value=fake_client):
            ms.ai_available = True
            ms.GEMINI_ENABLED = True
            ms.GEMINI_API_KEY = "AIzaFAKE"
            ms.GEMINI_MODEL = "gemini-2.5-flash"
            ms.GEMINI_TIMEOUT_SECONDS = 8.0

            from app.service.ai_service import call_gemini
            result = await call_gemini("prompt", response_schema=AIInsights)

            # Veio do .parsed (text era inválido) → dict com o executive_summary
            assert result is not None
            assert result["executive_summary"] == self._payload()["executive_summary"]

    @pytest.mark.asyncio
    async def test_fallback_para_texto_com_cercas_markdown(self):
        """REGRESSÃO Buraco 2b: se .parsed vier None, parseia texto removendo ```json."""
        from unittest.mock import patch, MagicMock

        resp = MagicMock()
        resp.parsed = None  # força o fallback de texto
        resp.text = "```json\n" + json.dumps(self._payload()) + "\n```"

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = resp

        with patch("app.service.ai_service.settings") as ms, \
             patch("app.service.ai_service._get_client", return_value=fake_client):
            ms.ai_available = True
            ms.GEMINI_ENABLED = True
            ms.GEMINI_API_KEY = "AIzaFAKE"
            ms.GEMINI_MODEL = "gemini-2.5-flash"
            ms.GEMINI_TIMEOUT_SECONDS = 8.0

            from app.service.ai_service import call_gemini
            from app.schema.schema import AIInsights
            result = await call_gemini("prompt", response_schema=AIInsights)

            assert result is not None
            assert result["executive_summary"] == self._payload()["executive_summary"]


# ─────────────────────────────────────────────────────────────────────────────
# IA FALHA — diferentes tipos de falha não devem quebrar a resposta
# ─────────────────────────────────────────────────────────────────────────────

class TestFalhasDaIA:
    """IA pode falhar de várias formas. Engine continua entregando."""

    @pytest.mark.asyncio
    async def test_ia_timeout_engine_continua(self):
        """Se IA dá timeout, engine entrega normal e ai_insights=None."""
        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(return_value=None)):

            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Test"),
                metrics=Metrics(
                    impressions=50000, reach=42000, spend=1500.0,
                    video_views_3s=8000, link_clicks=500,
                ),
                targets=Targets(max_cpa=60.0),
            )

            response = await analyze_campaign_async(data)

            assert response.ai_insights is None
            assert response.scenarios, "Engine deve continuar funcionando"

    @pytest.mark.asyncio
    async def test_ia_json_invalido_e_descartado(self):
        """Se IA retorna dict inválido, é descartado sem quebrar."""
        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(return_value={"campos": "errados"})):

            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Test"),
                metrics=Metrics(
                    impressions=50000, reach=42000, spend=1500.0,
                    video_views_3s=8000, link_clicks=500,
                ),
                targets=Targets(max_cpa=60.0),
            )

            response = await analyze_campaign_async(data)

            # IA inválida ignorada, mas engine entregou
            assert response.ai_insights is None
            assert response.scenarios, "Engine continua entregando"

    @pytest.mark.asyncio
    async def test_ia_lanca_excecao_nao_quebra_analise(self):
        """Se IA lança exceção inesperada, captura silenciosa e continua."""
        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(side_effect=RuntimeError("API down"))):

            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Test"),
                metrics=Metrics(
                    impressions=50000, reach=42000, spend=1500.0,
                    link_clicks=500,
                ),
                targets=Targets(max_cpa=60.0),
            )

            response = await analyze_campaign_async(data)

            assert response.ai_insights is None
            # Resposta válida mesmo com IA quebrada
            assert response.campaign_id == 1


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK MÍNIMO — última linha de defesa
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackMinimo:
    """Quando engine vazio + IA falha, fallback gera análise mínima."""

    @pytest.mark.asyncio
    async def test_fallback_ativa_quando_tudo_falha(self):
        """Engine sem cenários + IA falha → fallback gera summary baseado em métricas."""
        with patch("app.service.ai_service.is_ai_available", return_value=True), \
             patch("app.service.ai_service.call_gemini", new=AsyncMock(return_value=None)):

            # Payload que NÃO dispara nenhum cenário do engine
            # (CPA não otimizado, frequência alta o suficiente para sair de G)
            data = AnalyzeInput(
                campaign=Campaign(id=1, name="Atípico"),
                metrics=Metrics(
                    impressions=30000, spend=500.0, reach=25000,
                    link_clicks=300, conversions=10,
                    cpa=50.0,
                    # Sem learning_phase, sem hook_rate, sem ROAS, sem freq alta
                ),
                targets=Targets(),  # Sem max_cpa → G não dispara
            )

            response = await analyze_campaign_async(data)

            # Não tem cenários nem IA
            assert response.scenarios == [], f"Engine não deveria detectar nada, mas detectou: {[s.code.value for s in response.scenarios]}"
            assert response.ai_insights is None

            # Fallback gerou conteúdo
            assert response.summary, "Fallback deve gerar summary"
            assert response.primary_action, "Fallback deve gerar primary_action"

    def test_fallback_funcao_direta_sem_evaluations(self):
        """Função _apply_minimal_fallback funciona com response vazio."""
        from app.schema.schema import CampaignAnalysisResponse, AnalyzeInput, Campaign, Metrics, Targets

        response = CampaignAnalysisResponse(
            campaign_id=1,
            campaign_name="Test",
            final_status=CampaignStatus.GREEN,
            overall_score=50,
            score_coverage=0,
            score_confidence="low",
            summary="",
            scenarios=[],
            metric_evaluations=[],
            primary_action="",
        )

        data = AnalyzeInput(
            campaign=Campaign(id=1, name="Test"),
            metrics=Metrics(),
            targets=Targets(),
        )

        result = _apply_minimal_fallback(response, data)
        assert "insuficientes" in result.summary.lower() or "forneça" in result.summary.lower()
        assert result.primary_action


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA AI INSIGHTS — limites e validação
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaAIInsights:
    """Validações do schema AIInsights."""

    def test_aceita_apenas_executive_summary(self):
        """executive_summary é único obrigatório, outros campos têm default."""
        ai = AIInsights(executive_summary="Análise mínima.")
        assert ai.executive_summary
        assert ai.extra_scenarios == []
        assert ai.contextual_insights == []
        assert ai.risk_warnings == []

    def test_confidence_aceita_apenas_high_medium_low(self):
        """Confidence é Literal restrito."""
        # Válido
        AIScenario(
            title="x", description="y",
            recommended_action="z", confidence="high",
        )

        # Inválido
        with pytest.raises(Exception):
            AIScenario(
                title="x", description="y",
                recommended_action="z", confidence="invalido",
            )

    def test_ai_insights_aceita_lista_vazia(self):
        """Engine pode retornar IA sem extra_scenarios."""
        ai = AIInsights(
            executive_summary="Tudo ok.",
            extra_scenarios=[],
            contextual_insights=[],
            risk_warnings=[],
        )
        assert ai.executive_summary


# ─────────────────────────────────────────────────────────────────────────────
# CONTRATO DA API — garantir que response sempre tem ai_insights (mesmo None)
# ─────────────────────────────────────────────────────────────────────────────

class TestContratoAPI:
    """Garantir que o response sempre tem o campo ai_insights, mesmo que None."""

    def test_response_sempre_tem_campo_ai_insights(self):
        """Campo deve existir no response mesmo quando vazio."""
        r = client.post("/api/v1/campaign/analyze", json=make_payload_with_scenario())
        body = r.json()
        assert "ai_insights" in body, "Campo ai_insights é obrigatório no response"

    def test_estrutura_response_todos_os_casos(self):
        """Todos os campos esperados estão presentes em qualquer payload."""
        for payload_fn in [make_payload_with_scenario, make_payload_atypical, make_payload_minimo]:
            r = client.post("/api/v1/campaign/analyze", json=payload_fn())
            assert r.status_code == 200
            body = r.json()

            campos = {
                "campaign_id", "campaign_name", "final_status",
                "overall_score", "score_coverage", "score_confidence",
                "summary", "scenarios",
                "metric_evaluations", "primary_action", "ai_insights",
            }
            assert set(body.keys()) == campos, f"Resposta inconsistente para {payload_fn.__name__}"
