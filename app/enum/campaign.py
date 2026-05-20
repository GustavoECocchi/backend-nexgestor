from enum import Enum


class CampaignStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    PAUSED = "PAUSED"


class ScenarioCode(str, Enum):
    # Criativos
    WEAK_HOOK = "A"           # Gancho Fraco
    LOW_RETENTION = "B"       # Retenção Baixa
    CLICK_BAIT = "C"          # Click-Bait / Falta de Intenção Comercial
    LP_MISMATCH = "D"         # Desalinhamento com Landing Page

    # Audiência / Estrutura
    CREATIVE_FATIGUE = "E"    # Fadiga de Criativo
    COLD_LEAD = "F"           # Lead Frio / Persona Incorreta

    # Escala
    VERTICAL_SCALE = "G"      # Janela de Escala Vertical Ativa
    HORIZONTAL_SCALE = "H"    # Escala Horizontal por Fadiga de Público

    # Estrutura técnica
    LEARNING_PHASE = "I"      # Gargalo de Aprendizado Limitado
    OVERSPENDING = "J"        # Janela de Eficiência / Overspending
    RETARGETING_CANNIBAL = "K"  # Canibalização de Retargeting

    # Saudável sem cenário crítico
    HEALTHY = "HEALTHY"