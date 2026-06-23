"""
Enums centrais do domínio NexGestor.

Use estes enums em vez de strings literais para garantir consistência
e habilitar validação automática pelo Pydantic.
"""
from enum import Enum


class CampaignStatus(str, Enum):
    """Status semafórico geral de uma campanha ou métrica individual."""
    GREEN = "GREEN"     # saudável, dentro dos parâmetros
    YELLOW = "YELLOW"   # atenção, monitorar
    RED = "RED"         # crítico, ação imediata
    PAUSED = "PAUSED"   # reservado — pausa automática (uso futuro)


class ScenarioCode(str, Enum):
    """
    Códigos dos cenários determinísticos do engine.
    Cada letra corresponde a um detector específico em `service.py`.
    Os textos vieram do PDF de referência do produto.
    """
    # ── Criativo (problema no anúncio) ──
    WEAK_HOOK = "A"             # Hook Rate baixo — anúncio invisível no feed
    LOW_RETENTION = "B"         # Hold Rate baixo — vídeo entediante
    CLICK_BAIT = "C"            # CTR Todos alto, CTR Link baixo
    LP_MISMATCH = "D"           # Anúncio ok, Landing Page derruba

    # ── Audiência / Estrutura ──
    CREATIVE_FATIGUE = "E"      # Frequência alta — público saturado
    COLD_LEAD = "F"             # Custo ok, qualidade péssima

    # ── Escala (oportunidades) ──
    VERTICAL_SCALE = "G"        # Janela de aumento de orçamento aberta
    HORIZONTAL_SCALE = "H"      # Expandir para novos públicos

    # ── Estrutura técnica ──
    LEARNING_PHASE = "I"        # Aprendizado limitado do Meta
    OVERSPENDING = "J"          # Orçamento além do ponto de eficiência
    RETARGETING_CANNIBAL = "K"  # Retargeting "roubando" vendas orgânicas

    # ── Estado saudável (uso futuro) ──
    HEALTHY = "HEALTHY"
