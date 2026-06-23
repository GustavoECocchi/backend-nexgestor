from app.schema.schema import (
    AnalyzeInput,
    CampaignAnalysisResponse,
    ScenarioDetail,
    MetricEvaluation,
    Metrics,
    Targets,
)
from app.enum.campaign import CampaignStatus, ScenarioCode


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 — PRÉ-PROCESSAMENTO
# Calcula métricas derivadas se os dados brutos foram enviados mas a taxa não.
# ─────────────────────────────────────────────────────────────────────────────

def _preprocess(m: Metrics) -> Metrics:
    """
    Calcula métricas derivadas a partir dos dados brutos quando o usuário
    enviou os números absolutos mas não a taxa. Por exemplo: se enviou
    `video_views_3s=12000` e `impressions=50000`, calcula `hook_rate=24.0`.

    Não sobrescreve métricas que o usuário já enviou prontas.
    """
    data = m.model_copy()

    # Derivações que dependem de impressions > 0 — agrupadas para um único guard.
    # Cada tupla: (campo destino, valor numerador, fator multiplicador)
    if data.impressions and data.impressions > 0:
        rate_derivations = [
            ("hook_rate", data.video_views_3s, 100),
            ("hold_rate", data.thruplays, 100),
            ("ctr_link", data.link_clicks, 100),
            ("ctr_all", data.all_clicks, 100),
        ]
        for field, numerator, factor in rate_derivations:
            if getattr(data, field) is None and numerator is not None:
                setattr(data, field, round(numerator / data.impressions * factor, 2))

        if data.frequency is None and data.reach and data.reach > 0:
            data.frequency = round(data.impressions / data.reach, 2)

        if data.cpm is None and data.spend:
            data.cpm = round(data.spend / data.impressions * 1000, 2)

    # Derivações independentes de impressions.
    if data.lp_conversion_rate is None and data.conversions is not None \
            and data.landing_page_views and data.landing_page_views > 0:
        data.lp_conversion_rate = round(data.conversions / data.landing_page_views * 100, 2)

    if data.cpc is None and data.spend and data.link_clicks and data.link_clicks > 0:
        data.cpc = round(data.spend / data.link_clicks, 2)

    if data.cpa is None and data.spend and data.conversions and data.conversions > 0:
        data.cpa = round(data.spend / data.conversions, 2)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _status(value: float, red: float, yellow: float, inverted: bool = False) -> CampaignStatus:
    """
    Converte um valor numérico em CampaignStatus (GREEN/YELLOW/RED) com thresholds.

    Args:
        inverted=False: maior é melhor (Hook Rate, CTR, ROAS)
        inverted=True:  menor é melhor (CPA, CPM, Frequência)
    """
    if inverted:
        if value > red:    return CampaignStatus.RED
        if value > yellow: return CampaignStatus.YELLOW
        return CampaignStatus.GREEN
    else:
        if value < red:    return CampaignStatus.RED
        if value < yellow: return CampaignStatus.YELLOW
        return CampaignStatus.GREEN




# ─────────────────────────────────────────────────────────────────────────────
# SCORE — 0 a 100 por métrica
# Calcula a distância proporcional do valor ao target.
# inverted=False → maior é melhor (Hook Rate, CTR, ROAS)
# inverted=True  → menor é melhor (CPA, CPM, Frequência)
# ─────────────────────────────────────────────────────────────────────────────

def _calc_score(value: float, target: float, inverted: bool = False, floor: float = 0.3) -> int:
    """
    Retorna score 0–100.
    floor: pior caso relativo ao target (ex: 0.3 = valor 70% pior que o target = score 0)
    """
    if target <= 0:
        return 50

    if not inverted:
        # Maior é melhor: score 100 quando value >= target
        if value >= target:
            return 100
        # score 0 quando value <= target * floor
        worst = target * floor
        if value <= worst:
            return 0
        return round((value - worst) / (target - worst) * 100)
    else:
        # Menor é melhor: score 100 quando value <= target
        if value <= target:
            return 100
        # score 0 quando value >= target * (1 + (1 - floor))
        worst = target * (2 - floor)
        if value >= worst:
            return 0
        return round((worst - value) / (worst - target) * 100)


# Pesos por métrica para o overall_score (soma = 1.0)
_METRIC_WEIGHTS = {
    "CPA":              0.25,
    "ROAS":             0.20,
    "CTR Link":         0.12,
    "Hook Rate":        0.10,
    "Hold Rate":        0.08,
    "Conversão LP":     0.08,
    "Frequência":       0.07,
    "CPM":              0.05,
    "CPC":              0.03,
    "CPL":              0.02,
    "CTR Todos":        0.00,   # informativo — não entra no score geral
    "Conversões/semana": 0.00,  # informativo — não entra no score geral
}

# ─────────────────────────────────────────────────────────────────────────────
# DETECTORES — CENÁRIOS A → K
# ─────────────────────────────────────────────────────────────────────────────

def _detect_weak_hook(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário A — Hook Rate abaixo do target indica que o criativo não capta atenção."""
    if m.hook_rate is None:
        return None

    critico = m.hook_rate < t.min_hook_rate * 0.70
    alerta  = m.hook_rate < t.min_hook_rate

    if not alerta:
        return None

    evidencias = []
    if m.ctr_link is not None and m.ctr_link < t.min_ctr_link:
        evidencias.append(f"CTR Link {m.ctr_link:.2f}% abaixo do mínimo confirma abandono antes do clique")
    if m.cpc is not None and t.max_cpc is not None and m.cpc > t.max_cpc:
        evidencias.append(f"CPC R${m.cpc:.2f} inflado por baixo engajamento")
    if m.cpm is not None and m.cpm > t.max_cpm:
        evidencias.append(f"CPM R${m.cpm:.2f} — algoritmo penalizando anúncio com baixa relevância")

    suporte = ". ".join(evidencias) + "." if evidencias else ""

    return ScenarioDetail(
        code=ScenarioCode.WEAK_HOOK,
        title="Cenário A — Gancho Fraco (Falta de Atenção)",
        root_cause=(
            f"Hook Rate {m.hook_rate:.1f}% está {'criticamente ' if critico else ''}"
            f"abaixo da meta de {t.min_hook_rate:.0f}%. "
            f"O público ignora o anúncio nos primeiros 3 segundos. {suporte}"
        ),
        funnel_impact=(
            "Topo do funil comprometido. Menos usuários entram no funil, "
            "inflando CPC e CPA artificialmente."
        ),
        action="Pausar o criativo atual e substituir os primeiros 3 segundos.",
        execution_rule=(
            "Refazer abertura com 'Pattern Interrupt': headline visual agressiva, cores de alto contraste "
            "ou movimento rápido. Trocar abordagem institucional por dor imediata do usuário. "
            f"Meta: Hook Rate acima de {t.min_hook_rate:.0f}% antes de reativar."
        ),
        priority=1 if critico else 2,
    )


def _detect_low_retention(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário B — Hook OK mas Hold Rate baixo: vídeo perde o público no meio."""
    if m.hook_rate is None or m.hold_rate is None:
        return None

    hook_ok   = m.hook_rate >= t.min_hook_rate * 0.70
    hold_ruim = m.hold_rate < t.min_hold_rate

    if not (hook_ok and hold_ruim):
        return None

    critico = m.hold_rate < 10.0

    evidencias = []
    if m.thruplays is not None and m.video_views_3s and m.video_views_3s > 0:
        retencao = round(m.thruplays / m.video_views_3s * 100, 1)
        evidencias.append(f"Apenas {retencao}% dos que passaram dos 3s assistiram até o fim")

    suporte = ". ".join(evidencias) + "." if evidencias else ""

    return ScenarioDetail(
        code=ScenarioCode.LOW_RETENTION,
        title="Cenário B — Retenção Baixa (Vídeo Entediante ou Longo)",
        root_cause=(
            f"Hook Rate {m.hook_rate:.1f}% capta atenção inicial. "
            f"Porém Hold Rate {m.hold_rate:.1f}% {'criticamente ' if critico else ''}"
            f"abaixo da meta de {t.min_hold_rate:.0f}% — o vídeo perde o público logo após a abertura. {suporte}"
        ),
        funnel_impact=(
            "Usuário entra no funil mas abandona antes de ver a oferta e a CTA. "
            "CPL e CPA inflados por visualizações sem intenção."
        ),
        action="Solicitar edição do vídeo atual — não substituir, editar o desenvolvimento.",
        execution_rule=(
            "Encurtar criativo eliminando introduções corporativas. "
            "Aplicar cortes dinâmicos a cada 2–3 segundos. "
            "Adicionar B-rolls, legendas dinâmicas e capturas de tela da ferramenta em uso. "
            f"Meta: Hold Rate acima de {t.min_hold_rate:.0f}% antes de escalar."
        ),
        priority=1 if critico else 2,
    )


def _detect_click_bait(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário C — Muito engajamento (likes/coments) mas pouco clique no link."""
    if m.ctr_all is None or m.ctr_link is None:
        return None

    if not (m.ctr_all > t.max_ctr_all_ratio and m.ctr_link < 0.7):
        return None

    ratio = round(m.ctr_all / m.ctr_link, 1) if m.ctr_link > 0 else 0

    gasto_info = ""
    if m.spend is not None and m.all_clicks and m.all_clicks > 0:
        custo_engajamento = m.spend / m.all_clicks
        gasto_info = f" Custo médio por engajamento vazio: R${custo_engajamento:.2f}."

    return ScenarioDetail(
        code=ScenarioCode.CLICK_BAIT,
        title="Cenário C — Click-Bait / Falta de Intenção Comercial",
        root_cause=(
            f"CTR Todos {m.ctr_all:.1f}% muito alto com CTR Link {m.ctr_link:.2f}% crítico. "
            f"Razão de desperdício: {ratio}x mais engajamento social do que cliques comerciais. "
            f"O anúncio não deixa claro que é um produto/serviço.{gasto_info}"
        ),
        funnel_impact=(
            "Orçamento consumido por curtidas e comentários sem valor comercial. "
            "Algoritmo do Meta otimiza para engajamento em vez de intenção de compra."
        ),
        action="Substituir criativo por abordagem direta com CTA comercial explícita.",
        execution_rule=(
            "Inserir CTA clara no áudio e no visual, no meio e no fim do vídeo. "
            "Mostrar o produto sendo usado em contexto real. "
            "Usar linguagem que filtra intenção: 'Para quem quer X', 'Ideal para empresas que Y'."
        ),
        priority=1,
    )


def _detect_lp_mismatch(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário D — Anúncio funciona (CTR ótimo) mas Landing Page mata a conversão."""
    if m.ctr_link is None or m.lp_conversion_rate is None:
        return None

    ctr_excelente = m.ctr_link > t.min_ctr_link * 1.5
    lp_ruim       = m.lp_conversion_rate < t.min_lp_conversion_rate

    if not (ctr_excelente and lp_ruim):
        return None

    desperdicio = ""
    if m.spend is not None and m.landing_page_views and m.landing_page_views > 0:
        custo_por_view = m.spend / m.landing_page_views
        desperdicio = f" Custo por visita à LP: R${custo_por_view:.2f} sendo desperdiçado por baixa conversão."

    return ScenarioDetail(
        code=ScenarioCode.LP_MISMATCH,
        title="Cenário D — Desalinhamento com Landing Page (Quebra de Expectativa)",
        root_cause=(
            f"CTR Link {m.ctr_link:.2f}% excelente confirma que o anúncio funciona. "
            f"Taxa de conversão LP {m.lp_conversion_rate:.1f}% abaixo da meta de {t.min_lp_conversion_rate:.1f}% "
            f"— gargalo está na página: lenta, proposta de valor diferente ou alta fricção no formulário.{desperdicio}"
        ),
        funnel_impact=(
            "Cliques pagos desperdiçados na entrada da LP. "
            "CPA distorcido por problema externo à campanha. Pausar seria um erro."
        ),
        action="Manter campanhas ativas e abrir auditoria urgente na Landing Page.",
        execution_rule=(
            "1. Verificar carregamento no mobile — meta: abaixo de 3s. "
            "2. Primeira dobra da LP deve usar a mesma headline do anúncio campeão. "
            "3. Reduzir campos do formulário (cada campo extra reduz conversão ~10%). "
            "4. Testar versão simplificada com headline, benefícios e CTA único."
        ),
        priority=1,
    )


def _detect_creative_fatigue(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário E — Frequência alta indica que o criativo saturou no público atual."""
    if m.frequency is None:
        return None

    if m.frequency <= t.max_frequency_fatigue:
        return None

    critico = m.frequency > t.max_frequency_critical * 0.8

    sinais = []
    if m.ctr_link is not None and m.ctr_link < t.min_ctr_link:
        sinais.append(f"CTR Link {m.ctr_link:.2f}% despencando")
    if m.cpa is not None and t.max_cpa is not None and m.cpa > t.max_cpa:
        sinais.append(f"CPA R${m.cpa:.2f} acima do teto de R${t.max_cpa:.2f}")
    if m.cpm is not None and m.cpm > t.max_cpm:
        sinais.append(f"CPM R${m.cpm:.2f} subindo")

    confirmacao = (". Confirmado por: " + "; ".join(sinais)) if sinais else ""

    return ScenarioDetail(
        code=ScenarioCode.CREATIVE_FATIGUE,
        title="Cenário E — Fadiga de Criativo (Anúncio Saturado)",
        root_cause=(
            f"Frequência {m.frequency:.1f} — público viu o anúncio {m.frequency:.1f}x em média "
            f"(limite saudável: {t.max_frequency_fatigue}){confirmacao}. Criativo saturado."
        ),
        funnel_impact=(
            "CPA subindo progressivamente. CTR Link em queda. "
            "Orçamento queimado em audiência que já decidiu sobre o anúncio."
        ),
        action="Reduzir orçamento do conjunto saturado e subir novos criativos.",
        execution_rule=(
            "Reduzir orçamento em 30–50% imediatamente. "
            "Subir pelo menos 3 variações novas (ângulos diferentes, cores, formatos). "
            "Se usar Advantage+: inserir novas peças para forçar o algoritmo a testar novos caminhos. "
            f"Meta: frequência abaixo de {t.max_frequency_fatigue} antes de escalar novamente."
        ),
        priority=1 if critico else 2,
    )


def _detect_cold_lead(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário F — Custo de aquisição ok, mas qualidade dos leads é péssima."""
    if t.max_cpa is None or m.lp_conversion_rate is None:
        return None

    cpa_ok    = m.cpa is not None and m.cpa <= t.max_cpa
    cpl_ok    = m.cpl is not None and t.max_cpl is not None and m.cpl <= t.max_cpl
    lp_critica = m.lp_conversion_rate < t.min_lp_conversion_rate * 0.5

    if not ((cpa_ok or cpl_ok) and lp_critica):
        return None

    custo_info = f"CPA R${m.cpa:.2f}" if m.cpa else f"CPL R${m.cpl:.2f}"
    meta_info  = f"teto de R${t.max_cpa:.2f}" if m.cpa else f"teto de R${t.max_cpl:.2f}"

    return ScenarioDetail(
        code=ScenarioCode.COLD_LEAD,
        title="Cenário F — Lead Frio / Persona Incorreta",
        root_cause=(
            f"{custo_info} dentro do {meta_info} — anúncio atrai volume. "
            f"Porém conversão LP {m.lp_conversion_rate:.1f}% próxima de zero indica leads desqualificados: "
            "'caçadores de coisas grátis' ou público sem fit com o ticket do produto."
        ),
        funnel_impact=(
            "CAC real muito acima do CPA registrado. Leads chegando mas não virando clientes. "
            "Time de vendas sobrecarregado com leads que não convertem."
        ),
        action="Mudar comunicação dos anúncios para qualificar o público na entrada.",
        execution_rule=(
            "Adicionar barreiras de qualificação na cópia: mencionar ticket, porte ou perfil-alvo explicitamente. "
            "Mudar CTA de 'Cadastre-se grátis' para 'Solicitar Demonstração'. "
            "Testar LAL de clientes pagantes em vez de segmentação por interesse amplo."
        ),
        priority=2,
    )


def _detect_vertical_scale(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário G — Performance excelente com folga: janela para aumentar orçamento."""
    if m.cpa is None or t.max_cpa is None:
        return None

    cpa_otimo       = m.cpa <= t.max_cpa * t.scale_cpa_margin
    freq_controlada = m.frequency is None or m.frequency < t.scale_frequency_ceiling
    roas_ok         = m.roas is None or t.min_roas is None or m.roas >= t.min_roas
    nao_aprendendo  = not m.learning_phase if m.learning_phase is not None else True

    if not (cpa_otimo and freq_controlada and roas_ok and nao_aprendendo):
        return None

    margem_pct = round((1 - m.cpa / t.max_cpa) * 100, 1)
    roas_info  = f" ROAS {m.roas:.1f}x acima da meta de {t.min_roas:.1f}x." if (m.roas and t.min_roas) else ""
    freq_info  = f" Frequência {m.frequency:.1f} — audiência ainda fresca." if m.frequency else ""

    return ScenarioDetail(
        code=ScenarioCode.VERTICAL_SCALE,
        title="Cenário G — Janela de Escala Vertical Ativa (Alta Performance)",
        root_cause=(
            f"CPA R${m.cpa:.2f} está {margem_pct:.0f}% abaixo da meta de R${t.max_cpa:.2f}.{roas_info}{freq_info} "
            "Criativo com tração máxima. Leilão favorável. Margem para injetar orçamento sem estourar o CPA."
        ),
        funnel_impact=(
            "Orçamento estático nesta janela = oportunidade desperdiçada. "
            "Algoritmo estável e otimizado — cada R$ adicional tende a gerar retorno proporcional."
        ),
        action="Executar Escala Vertical Automatizada — aumentar orçamento agora.",
        execution_rule=(
            "Aumentar orçamento entre 15% e 20% a cada 24h. "
            "Nunca aumentar mais de 30% de uma vez — reinicia o aprendizado do algoritmo. "
            "Monitorar CPC e CPM nas próximas 48h após cada aumento. "
            f"Regra de parada: se CPA subir mais de 10% (acima de R${t.max_cpa * 1.1:.2f}), estabilizar."
        ),
        priority=1,
    )


def _detect_horizontal_scale(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário H — Frequência subindo mas CPA ainda ok: hora de expandir para novos públicos."""
    if m.frequency is None or m.cpa is None or t.max_cpa is None:
        return None

    freq_subindo = m.frequency > t.max_frequency_horizontal
    cpa_ok       = m.cpa <= t.max_cpa
    nao_fadiga   = m.frequency <= t.max_frequency_fatigue  # Fadiga plena já é Cenário E

    if not (freq_subindo and cpa_ok and nao_fadiga):
        return None

    cpm_info = f" CPM R${m.cpm:.2f} subindo — leilão ficando mais caro." if m.cpm and m.cpm > t.max_cpm else ""
    estimativa = round((t.max_frequency_fatigue - m.frequency) / 0.3)
    prazo = f" Estimativa: {estimativa} dia(s) antes do colapso se não agir." if estimativa > 0 else ""

    return ScenarioDetail(
        code=ScenarioCode.HORIZONTAL_SCALE,
        title="Cenário H — Escala Horizontal por Fadiga Iminente de Público",
        root_cause=(
            f"Frequência {m.frequency:.1f} crescendo (limite de alerta: {t.max_frequency_horizontal}). "
            f"CPA R${m.cpa:.2f} ainda dentro da meta — anúncio performa, mas audiência está saturando.{cpm_info}{prazo}"
        ),
        funnel_impact=(
            "Campanha ainda entrega, mas prestes a colapsar. "
            "Manter orçamento só na audiência atual vai causar queda abrupta de performance."
        ),
        action="Duplicar estrutura para novos públicos — Escala Horizontal.",
        execution_rule=(
            "Manter conjunto atual ativo sem alterar orçamento. "
            "Criar novos conjuntos com mesmo perfil comprador: LAL de 1% dos clientes com maior LTV. "
            "Distribuição: 80% verba para novos públicos, 20% para retenção. "
            "Excluir compradores dos últimos 180 dias nas campanhas de prospecção."
        ),
        priority=2,
    )


def _detect_learning_phase(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário I — Conjunto em aprendizado limitado ou volume insuficiente para o algoritmo otimizar."""
    em_aprendizado = m.learning_phase is True
    volume_baixo   = m.weekly_conversions is not None and m.weekly_conversions < t.min_weekly_conversions

    if not (em_aprendizado or volume_baixo):
        return None

    conv_info = ""
    if m.weekly_conversions is not None:
        deficit = t.min_weekly_conversions - m.weekly_conversions
        conv_info = (
            f" {m.weekly_conversions} conversões nos últimos 7 dias "
            f"(meta: {t.min_weekly_conversions}+ — deficit de {deficit})."
        )

    gasto_info = f" Gasto R${m.spend:.2f} com CPA instável de R${m.cpa:.2f}." if m.spend and m.cpa else ""

    return ScenarioDetail(
        code=ScenarioCode.LEARNING_PHASE,
        title="Cenário I — Gargalo de Aprendizado Limitado (Learning Phase Hell)",
        root_cause=(
            f"{'Conjunto com status Aprendizado Limitado no Meta Ads.' if em_aprendizado else ''}"
            f"{conv_info}{gasto_info} "
            "Estrutura muito fragmentada ou evento de otimização raro — Meta sem dados suficientes para otimizar."
        ),
        funnel_impact=(
            "Entrega instável, CPC volátil, CPA imprevisível. "
            "Orçamento consumido sem aprendizado real."
        ),
        action="Consolidação de conjuntos e subida de funil de otimização.",
        execution_rule=(
            "1. Fundir conjuntos semelhantes que competem no mesmo leilão. "
            f"2. Se orçamento insuficiente para {t.min_weekly_conversions} conversões/semana, "
            "mudar evento de otimização para passo anterior do funil: "
            "Purchase → Initiate Checkout → Add to Cart → Trial Started → Lead. "
            "3. Quando atingir volume no evento intermediário, subir o funil novamente."
        ),
        priority=1,
    )


def _detect_overspending(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário J — CPM caro com LP ok e CPA alto: orçamento além do ponto de eficiência."""
    if m.cpm is None or m.lp_conversion_rate is None or m.cpa is None or t.max_cpa is None:
        return None

    cpm_alto    = m.cpm > t.max_cpm
    lp_saudavel = m.lp_conversion_rate >= t.min_lp_conversion_rate
    cpa_alto    = m.cpa > t.max_cpa

    if not (cpm_alto and lp_saudavel and cpa_alto):
        return None

    economia = ""
    if m.spend and m.conversions and m.conversions > 0:
        cpa_estimado = (m.spend * 0.85) / m.conversions
        economia = f" Com redução de 15% do orçamento, CPA estimado: R${cpa_estimado:.2f}."

    return ScenarioDetail(
        code=ScenarioCode.OVERSPENDING,
        title="Cenário J — Janela de Eficiência (Overspending sem Retorno)",
        root_cause=(
            f"CPM R${m.cpm:.2f} acima do teto de R${t.max_cpm:.2f} com LP convertendo bem "
            f"({m.lp_conversion_rate:.1f}%). Orçamento ultrapassou ponto de inflexão do público — "
            f"campanha força entrega em horários de alta concorrência.{economia}"
        ),
        funnel_impact=(
            "Retornos decrescentes: vendas estagnadas com custo subindo. "
            "CPA acima do teto mesmo com funil saudável — problema estrutural de orçamento."
        ),
        action="Reduzir teto de gastos e ativar programação de horário.",
        execution_rule=(
            "1. Reduzir orçamento diário em 15%. "
            "2. Mudar para veiculação 'Programada' (Orçamento Total). "
            "3. Concentrar exibição nos horários com maior volume histórico de conversões "
            "(geralmente seg–sex 08h–20h para B2B; noite/fim de semana para B2C). "
            "4. Monitorar CPM e CPA nas 72h seguintes."
        ),
        priority=2,
    )


def _detect_retargeting_cannibal(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário K — ROAS absurdamente alto + frequência crítica: retargeting "roubando" vendas orgânicas."""
    if m.roas is None or m.frequency is None:
        return None

    if not (m.roas > 10.0 and m.frequency > t.max_frequency_critical):
        return None

    topo_info = ""
    if m.ctr_link is not None and m.ctr_link < t.min_ctr_link:
        topo_info = (
            f" CTR Link {m.ctr_link:.2f}% em queda — "
            "topo de funil desabastecido confirmando que não entram novos usuários na base."
        )

    return ScenarioDetail(
        code=ScenarioCode.RETARGETING_CANNIBAL,
        title="Cenário K — Otimização de Retargeting Ineficiente (Efeito Canibalização)",
        root_cause=(
            f"ROAS {m.roas:.1f}x com frequência {m.frequency:.1f} — ilusão estatística. "
            "Retargeting coletando apenas quem compraria organicamente de qualquer forma. "
            f"Marca pagando por cliques redundantes.{topo_info}"
        ),
        funnel_impact=(
            "Novas visitas caindo. Base de clientes estagnada. "
            "ROAS alto mascarando problema estrutural: sem topo de funil, retargeting colapsa em semanas."
        ),
        action="Rebalanceamento urgente de verba entre prospecção e retargeting.",
        execution_rule=(
            "1. Reduzir verba de retargeting para no máximo 10–15% do orçamento total. "
            "2. Redirecionar verba para campanhas de prospecção (topo de funil). "
            "3. Excluir visitantes dos últimos 30 dias e compradores dos últimos 180 dias nas campanhas de prospecção. "
            "4. Mudar criativo de retargeting de 'institucional' para 'quebra de objeções' ou 'oferta de urgência com escassez'."
        ),
        priority=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AVALIAÇÃO INDIVIDUAL DE MÉTRICAS
# ─────────────────────────────────────────────────────────────────────────────

# Tabela de configuração das métricas avaliáveis.
# Cada entrada: (campo do Metrics, label, attr_target, fator_red, inverted, notas_por_status)
# - fator_red: multiplicador aplicado ao target para definir o threshold de RED
# - notas_por_status: textos para GREEN/YELLOW/RED — usar {meta} e {value} como placeholders
_METRIC_EVAL_CONFIG = [
    ("hook_rate", "Hook Rate", "min_hook_rate", 0.7, False, {
        "GREEN":  "Meta: >{meta:.0f}%. ✓ Criativo capta atenção no feed.",
        "YELLOW": "Meta: >{meta:.0f}%. ⚠ Gancho fraco — público rola sem parar.",
        "RED":    "Meta: >{meta:.0f}%. ✗ Crítico — criativo invisível no feed. Refazer abertura.",
    }),
    # Hold Rate usa threshold fixo de 10% (não proporcional ao target)
    ("hold_rate", "Hold Rate", "min_hold_rate", None, False, {
        "GREEN":  "Meta: >{meta:.0f}%. ✓ Vídeo mantém atenção até a oferta.",
        "YELLOW": "Meta: >{meta:.0f}%. ⚠ Abandono precoce — revisar ritmo do vídeo.",
        "RED":    "Meta: >{meta:.0f}%. ✗ Crítico — público abandona antes da CTA.",
    }),
    ("ctr_link", "CTR Link", "min_ctr_link", 0.5, False, {
        "GREEN":  "Meta: >{meta:.1f}%. ✓ Intenção de clique saudável.",
        "YELLOW": "Meta: >{meta:.1f}%. ⚠ CTR Link abaixo do esperado.",
        "RED":    "Meta: >{meta:.1f}%. ✗ Sem intenção comercial — CTA ausente ou fraca.",
    }),
    ("cpa", "CPA", "max_cpa", 1.3, True, None),  # CPA tem nota customizada com delta %
    ("cpl", "CPL", "max_cpl", 1.3, True, {
        "GREEN":  "Meta: <R${meta:.2f}. ✓ Custo por lead dentro da meta.",
        "YELLOW": "Meta: <R${meta:.2f}. ⚠ CPL acima da meta.",
        "RED":    "Meta: <R${meta:.2f}. ✗ CPL crítico — lead saindo caro demais.",
    }),
    ("roas", "ROAS", "min_roas", 0.7, False, {
        "GREEN":  "Meta: >{meta:.1f}x. ✓ ROAS {value:.1f}x — retorno saudável.",
        "YELLOW": "Meta: >{meta:.1f}x. ⚠ ROAS abaixo da meta.",
        "RED":    "Meta: >{meta:.1f}x. ✗ ROAS crítico — campanha destruindo caixa.",
    }),
    ("cpc", "CPC", "max_cpc", 1.3, True, {
        "GREEN":  "Meta: <R${meta:.2f}. ✓ Custo por clique dentro do teto.",
        "YELLOW": "Meta: <R${meta:.2f}. ⚠ CPC acima do teto.",
        "RED":    "Meta: <R${meta:.2f}. ✗ CPC crítico — cada clique caro demais.",
    }),
    ("lp_conversion_rate", "Conversão LP", "min_lp_conversion_rate", 0.5, False, {
        "GREEN":  "Meta: >{meta:.1f}%. ✓ Landing Page convertendo bem.",
        "YELLOW": "Meta: >{meta:.1f}%. ⚠ Conversão abaixo do esperado.",
        "RED":    "Meta: >{meta:.1f}%. ✗ LP com problema crítico — gargalo fora da campanha.",
    }),
]


def _evaluate_one(field: str, label: str, target_attr: str, fator_red,
                  inverted: bool, notas: dict, m: Metrics, t: Targets) -> MetricEvaluation | None:
    """Avalia uma métrica genérica usando a config da tabela _METRIC_EVAL_CONFIG."""
    value = getattr(m, field, None)
    target = getattr(t, target_attr, None)
    if value is None or target is None:
        return None

    # Hold Rate usa threshold absoluto de 10% para RED em vez de proporção.
    threshold_red = (target * fator_red) if fator_red is not None else 10.0
    st = _status(value, threshold_red, target, inverted=inverted)
    note = notas[st.value].format(meta=target, value=value)
    score = _calc_score(value, target, inverted=inverted)
    return MetricEvaluation(
        metric=label, value=float(value), status=st,
        score=max(0, min(100, score)), note=note,
    )


def _evaluate_metrics(m: Metrics, t: Targets) -> list[MetricEvaluation]:
    """
    Avalia cada métrica individualmente — status semafórico + score 0–100.
    Métricas ausentes são puladas. Algumas métricas (CTR Todos, Conversões/semana,
    CPM, Frequência, CPA) têm lógica customizada e ficam fora da tabela.
    """
    evals: list[MetricEvaluation] = []

    # Métricas com avaliação padronizada (tabela)
    for field, label, target_attr, fator_red, inverted, notas in _METRIC_EVAL_CONFIG:
        if notas is None:
            continue  # CPA é tratado abaixo (precisa de delta %)
        result = _evaluate_one(field, label, target_attr, fator_red, inverted, notas, m, t)
        if result is not None:
            evals.append(result)

    # CPA — nota customizada com delta percentual em relação à meta
    if m.cpa is not None and t.max_cpa is not None:
        st = _status(m.cpa, t.max_cpa * 1.3, t.max_cpa, inverted=True)
        delta = ((m.cpa / t.max_cpa) - 1) * 100
        notas_cpa = {
            CampaignStatus.GREEN:  f"Meta: <R${t.max_cpa:.2f}. ✓ CPA {abs(delta):.0f}% abaixo da meta.",
            CampaignStatus.YELLOW: f"Meta: <R${t.max_cpa:.2f}. ⚠ CPA {delta:.0f}% acima da meta.",
            CampaignStatus.RED:    f"Meta: <R${t.max_cpa:.2f}. ✗ CPA {delta:.0f}% acima — campanha no vermelho.",
        }
        score = _calc_score(m.cpa, t.max_cpa, inverted=True)
        evals.append(MetricEvaluation(
            metric="CPA", value=float(m.cpa), status=st,
            score=max(0, min(100, score)), note=notas_cpa[st],
        ))

    # CTR Todos — lógica especial (cruza com CTR Link para detectar click-bait)
    if m.ctr_all is not None:
        if m.ctr_link is not None and m.ctr_all > t.max_ctr_all_ratio and m.ctr_link < 0.7:
            st = CampaignStatus.RED
            note = f"✗ Click-Bait detectado: CTR Todos {m.ctr_all:.1f}% vs CTR Link {m.ctr_link:.2f}%."
        elif m.ctr_all > t.max_ctr_all_ratio:
            st = CampaignStatus.YELLOW
            note = f"⚠ CTR Todos {m.ctr_all:.1f}% elevado — monitorar se CTR Link acompanha."
        else:
            st = CampaignStatus.GREEN
            note = "✓ Proporção de engajamento saudável."
        evals.append(MetricEvaluation(metric="CTR Todos", value=float(m.ctr_all), status=st, score=50, note=note))

    # CPM — threshold padrão de R$50 (sem target customizável)
    if m.cpm is not None:
        st = _status(m.cpm, t.max_cpm * 1.3, t.max_cpm, inverted=True)
        notas_cpm = {
            CampaignStatus.GREEN:  f"Referência: <R${t.max_cpm:.2f}. ✓ Leilão eficiente.",
            CampaignStatus.YELLOW: f"Referência: <R${t.max_cpm:.2f}. ⚠ CPM elevado — leilão competitivo.",
            CampaignStatus.RED:    f"Referência: <R${t.max_cpm:.2f}. ✗ CPM crítico — público exaurido ou anúncio penalizado.",
        }
        score = _calc_score(m.cpm, t.max_cpm, inverted=True)
        evals.append(MetricEvaluation(
            metric="CPM", value=float(m.cpm), status=st,
            score=max(0, min(100, score)), note=notas_cpm[st],
        ))

    # Frequência — thresholds alinhados aos detectores para não contradizer os cards:
    #   RED    quando freq > max_frequency_fatigue (2.8)  → mesmo gatilho do Cenário E (Fadiga)
    #   YELLOW quando freq > max_frequency_horizontal (2.5) → mesma zona do Cenário H (escala horizontal)
    # Antes o RED só vinha em 2.8*1.2=3.36, o que deixava o semáforo AMARELO enquanto
    # o card de Fadiga já gritava "saturado" — contradição na mesma tela.
    if m.frequency is not None:
        st = _status(m.frequency, t.max_frequency_fatigue, t.max_frequency_horizontal, inverted=True)
        notas_freq = {
            CampaignStatus.GREEN:  f"Limite de fadiga: {t.max_frequency_fatigue}. ✓ Audiência fresca.",
            CampaignStatus.YELLOW: f"Limite de fadiga: {t.max_frequency_fatigue}. ⚠ Frequência subindo — fadiga iminente, considerar escala horizontal.",
            CampaignStatus.RED:    f"Limite de fadiga: {t.max_frequency_fatigue}. ✗ Saturação — criativo esgotado no público atual.",
        }
        score = _calc_score(m.frequency, t.max_frequency_fatigue, inverted=True)
        evals.append(MetricEvaluation(
            metric="Frequência", value=float(m.frequency), status=st,
            score=max(0, min(100, score)), note=notas_freq[st],
        ))

    # Conversões/semana — score fixo 50 (informativo, não entra no overall)
    if m.weekly_conversions is not None:
        st = _status(m.weekly_conversions, t.min_weekly_conversions * 0.5, t.min_weekly_conversions)
        notas_conv = {
            CampaignStatus.GREEN:  f"Meta: >{t.min_weekly_conversions}/semana. ✓ Volume suficiente para aprendizado estável.",
            CampaignStatus.YELLOW: f"Meta: >{t.min_weekly_conversions}/semana. ⚠ Volume baixo — risco de aprendizado limitado.",
            CampaignStatus.RED:    f"Meta: >{t.min_weekly_conversions}/semana. ✗ Volume crítico — algoritmo sem dados para otimizar.",
        }
        evals.append(MetricEvaluation(
            metric="Conversões/semana", value=float(m.weekly_conversions),
            status=st, score=50, note=notas_conv[st],
        ))

    return evals




def _calc_overall_score(metric_evals: list) -> tuple[int, int]:
    """
    Agrega os scores individuais em um score único 0–100, ponderado por relevância.
    Métricas sem peso em _METRIC_WEIGHTS (ex: CTR Todos, Conversões/semana) são
    informativas e não entram no agregado.

    Retorna (score, coverage):
      • score: 0–100, média ponderada dos scores presentes. 50 (neutro) se nada presente.
      • coverage: 0–100, % do peso TOTAL possível que foi de fato avaliado.
        Score alto com coverage baixo = poucos dados → baixa confiança.
        (Ex: só CPM presente → score pode dar 100, mas coverage ≈ 5.)
    """
    total_peso  = 0.0
    total_score = 0.0

    for ev in metric_evals:
        peso = _METRIC_WEIGHTS.get(ev.metric, 0.0)
        if peso > 0:
            total_score += ev.score * peso
            total_peso  += peso

    # Soma de todos os pesos possíveis (≈1.0) — base para o coverage.
    peso_total_possivel = sum(_METRIC_WEIGHTS.values())
    coverage = round(total_peso / peso_total_possivel * 100) if peso_total_possivel > 0 else 0

    if total_peso == 0:
        return 50, coverage

    return round(total_score / total_peso), coverage


def _score_confidence(coverage: int) -> str:
    """Deriva a confiança no score a partir do coverage (% de peso avaliado)."""
    if coverage >= 70:
        return "high"
    if coverage >= 40:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────────────────
# REGRAS DE CONFLITO E SOBREPOSIÇÃO
#
# Hierarquia de supressão:
#   I  (Learning Phase)    → suprime G e H (não faz sentido escalar sem aprendizado)
#   E  (Fadiga Plena)      → suprime H (H é fadiga iminente, E já é o estado crítico)
#   D  (LP Mismatch)       → suprime F (não acusar lead frio quando o gargalo é a LP)
#   A  (Gancho Fraco)      → suprime B (se não capta atenção, retenção é irrelevante)
#   K  (Retargeting Caníbal) → suprime G (ROAS alto do retargeting não é janela de escala real)
#   G  (Escala Vertical)   → suprime H (escala vertical e horizontal são mutuamente exclusivas)
# ─────────────────────────────────────────────────────────────────────────────

def _apply_conflict_rules(scenarios: list[ScenarioDetail]) -> list[ScenarioDetail]:
    """
    Aplica regras de supressão entre cenários para evitar diagnósticos contraditórios.
    Ex: se A (Gancho Fraco) está ativo, suprime B (Retenção) — sem atenção inicial,
    falar de retenção é irrelevante.
    """
    if not scenarios:
        return scenarios

    active_codes = {s.code for s in scenarios}
    suppressed: set[ScenarioCode] = set()

    # Cada regra: SE cenário-pai presente, suprime cenários-filhos.
    suppression_rules = [
        # I (Learning Phase) → suprime G e H: não escalar sem aprendizado
        (ScenarioCode.LEARNING_PHASE, {ScenarioCode.VERTICAL_SCALE, ScenarioCode.HORIZONTAL_SCALE}),
        # E (Fadiga Plena) → suprime H: E já engloba o estado crítico
        (ScenarioCode.CREATIVE_FATIGUE, {ScenarioCode.HORIZONTAL_SCALE}),
        # D (LP Mismatch) → suprime F: gargalo é a LP, não a persona
        (ScenarioCode.LP_MISMATCH, {ScenarioCode.COLD_LEAD}),
        # A (Gancho Fraco) → suprime B: sem atenção inicial, retenção é secundária
        (ScenarioCode.WEAK_HOOK, {ScenarioCode.LOW_RETENTION}),
        # K (Retargeting Caníbal) → suprime G: ROAS alto do retargeting não é escala real
        (ScenarioCode.RETARGETING_CANNIBAL, {ScenarioCode.VERTICAL_SCALE}),
        # G (Escala Vertical) → suprime H: escalas vertical e horizontal são excludentes
        (ScenarioCode.VERTICAL_SCALE, {ScenarioCode.HORIZONTAL_SCALE}),
    ]

    for parent, children in suppression_rules:
        if parent in active_codes:
            suppressed.update(children)

    return [s for s in scenarios if s.code not in suppressed]

# ─────────────────────────────────────────────────────────────────────────────
# STATUS FINAL E SUMÁRIO
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_final_status(scenarios: list[ScenarioDetail]) -> CampaignStatus:
    """
    Calcula o status final da campanha a partir dos cenários detectados.
    Regra especial: cenário de escala (G) sozinho não é RED — é oportunidade.
    """
    if not scenarios:
        return CampaignStatus.GREEN

    # Cenários "negativos" (qualquer um exceto escala vertical)
    nao_escala = [s for s in scenarios if s.code != ScenarioCode.VERTICAL_SCALE]

    if not nao_escala:
        return CampaignStatus.GREEN  # Só oportunidade de escala = saudável

    if any(s.priority == 1 for s in nao_escala):
        return CampaignStatus.RED

    return CampaignStatus.YELLOW


def _build_summary(scenarios: list[ScenarioDetail], status: CampaignStatus) -> str:
    """Monta o resumo textual da análise — uma frase descrevendo os achados principais."""
    if not scenarios:
        return (
            "Campanha operando dentro dos parâmetros esperados. "
            "Nenhum gargalo crítico identificado. Manter monitoramento regular."
        )

    criticos = [s for s in scenarios if s.priority == 1 and s.code != ScenarioCode.VERTICAL_SCALE]
    urgentes = [s for s in scenarios if s.priority == 2]
    escala   = [s for s in scenarios if s.code == ScenarioCode.VERTICAL_SCALE]

    partes = []
    if criticos:
        partes.append(f"{len(criticos)} problema(s) crítico(s): {', '.join(s.title.split('—')[0].strip() for s in criticos)}")
    if urgentes:
        partes.append(f"{len(urgentes)} ponto(s) de atenção: {', '.join(s.title.split('—')[0].strip() for s in urgentes)}")
    if escala:
        partes.append("1 janela de escala vertical identificada — oportunidade de crescimento")

    return ". ".join(partes) + ". Resolver em ordem de prioridade."


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def analyze_campaign(data: AnalyzeInput) -> CampaignAnalysisResponse:
    """
    Entry point síncrono — analisa uma campanha usando apenas o engine de regras.
    NÃO chama a IA (para isso use `analyze_campaign_async`).
    Útil para testes, scripts em background, ou quando IA não é necessária.
    """
    # 1. Calcular métricas derivadas dos dados brutos
    m = _preprocess(data.metrics)
    t = data.targets

    # 2. Rodar todos os detectores
    detectors = [
        _detect_learning_phase,        # I — infra primeiro (compromete tudo)
        _detect_weak_hook,             # A — atenção
        _detect_low_retention,         # B — retenção
        _detect_click_bait,            # C — intenção comercial
        _detect_lp_mismatch,           # D — landing page
        _detect_creative_fatigue,      # E — saturação
        _detect_cold_lead,             # F — qualidade de lead
        _detect_vertical_scale,        # G — oportunidade de escala
        _detect_horizontal_scale,      # H — expansão de audiência
        _detect_overspending,          # J — eficiência de orçamento
        _detect_retargeting_cannibal,  # K — canibalização
    ]

    scenarios = []
    for detect in detectors:
        result = detect(m, t)
        if result:
            scenarios.append(result)

    # 3. Aplicar regras de conflito e sobreposição
    scenarios = _apply_conflict_rules(scenarios)

    # 4. Ordenar por prioridade (1 = crítico primeiro)
    scenarios.sort(key=lambda s: s.priority)

    # 5. Avaliar métricas individualmente
    metric_evals = _evaluate_metrics(m, t)

    # 6. Montar resposta
    final_status   = _resolve_final_status(scenarios)
    summary        = _build_summary(scenarios, final_status)
    overall_score, score_coverage = _calc_overall_score(metric_evals)
    score_confidence = _score_confidence(score_coverage)
    primary_action = scenarios[0].action if scenarios else "Manter campanha ativa. Monitorar métricas nas próximas 48h."

    return CampaignAnalysisResponse(
        campaign_id=data.campaign.id,
        campaign_name=data.campaign.name,
        final_status=final_status,
        overall_score=overall_score,
        score_coverage=score_coverage,
        score_confidence=score_confidence,
        summary=summary,
        scenarios=scenarios,
        metric_evaluations=metric_evals,
        primary_action=primary_action,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT ASYNC — engine + IA em paralelo
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_campaign_async(data: AnalyzeInput) -> CampaignAnalysisResponse:
    """
    Versão assíncrona que roda engine e IA em paralelo.

    Garantias:
      • Engine sempre roda (rápido, determinístico)
      • IA roda em paralelo se disponível (não bloqueia engine)
      • Se IA falhar/timeout, response.ai_insights = None — não afeta o resto
      • Se engine não detectar cenários E IA falhar, gera fallback mínimo
        para garantir que NUNCA retornamos análise vazia
    """
    import asyncio
    from app.service.ai_service import analyze_with_ai, is_ai_available

    # ── Engine roda em executor (é síncrono, não pode bloquear o event loop) ──
    loop = asyncio.get_running_loop()

    def run_engine():
        return analyze_campaign(data)

    engine_task = loop.run_in_executor(None, run_engine)

    # ── Preparar a tarefa da IA (se disponível) ──
    # A IA precisa do resultado do engine para o "modo complementar",
    # então rodamos engine primeiro em executor, depois disparamos IA em paralelo
    # com pré-processamento mínimo (engine roda muito rápido, <50ms).
    engine_response = await engine_task

    # Se IA não está disponível, retorna resposta do engine direta
    if not is_ai_available():
        # Fallback: se engine também não detectou nada, garantir análise mínima
        if not engine_response.scenarios:
            engine_response = _apply_minimal_fallback(engine_response, data)
        return engine_response

    # ── Disparar IA com contexto do engine ──
    m = _preprocess(data.metrics)

    try:
        ai_result = await analyze_with_ai(
            metrics=m,
            targets=data.targets,
            campaign=data.campaign,
            engine_scenarios=engine_response.scenarios,
            metric_evaluations=engine_response.metric_evaluations,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("IA falhou inesperadamente")
        ai_result = None

    # ── Converter resposta da IA em AIInsights (se veio) ──
    # ai_result é um dict. A validação aqui é a 2ª (o SDK já validou contra o
    # schema). Se falhar, logamos a CAUSA — não some silenciosamente.
    ai_insights = None
    if ai_result is not None:
        from app.schema.schema import AIInsights
        try:
            ai_insights = AIInsights.model_validate(ai_result)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "IA: resposta não bate com o schema AIInsights — ignorando. Causa: %s", e
            )
            ai_insights = None

    # ── Combinar resultado final ──
    engine_response.ai_insights = ai_insights

    # ── Fallback de garantia: engine vazio + IA falhou ──
    if not engine_response.scenarios and ai_insights is None:
        engine_response = _apply_minimal_fallback(engine_response, data)

    return engine_response


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK MÍNIMO
# Garante que NUNCA retornamos análise vazia, mesmo se engine e IA falharem.
# ─────────────────────────────────────────────────────────────────────────────

def _apply_minimal_fallback(response: CampaignAnalysisResponse, data: AnalyzeInput) -> CampaignAnalysisResponse:
    """
    Quando engine não detectou cenários E IA não está disponível/falhou,
    construímos uma análise mínima a partir das métricas avaliadas.
    Garantia: o usuário nunca vê uma resposta "vazia".
    """
    evals = response.metric_evaluations

    if not evals:
        # Caso extremo: nem métricas avaliáveis foram fornecidas
        response.summary = (
            "Dados insuficientes para análise. Forneça pelo menos: "
            "impressões, gasto, conversões e CPA-meta para receber diagnóstico."
        )
        response.primary_action = (
            "Adicione mais métricas no formulário para receber análise detalhada."
        )
        return response

    # Identificar pontos de atenção a partir dos status
    criticos = [e for e in evals if e.status.value == "RED"]
    atencao  = [e for e in evals if e.status.value == "YELLOW"]
    saudaveis = [e for e in evals if e.status.value == "GREEN"]

    partes = []
    if criticos:
        nomes = ", ".join(e.metric for e in criticos[:3])
        partes.append(f"{len(criticos)} métrica(s) crítica(s): {nomes}")
    if atencao:
        nomes = ", ".join(e.metric for e in atencao[:3])
        partes.append(f"{len(atencao)} em atenção: {nomes}")
    if saudaveis and not criticos and not atencao:
        partes.append(f"{len(saudaveis)} métrica(s) saudável(eis)")

    response.summary = (
        f"Análise baseada nas métricas individuais ({len(evals)} avaliadas). "
        + ". ".join(partes) + "."
    )

    # Ação principal: focar na pior métrica
    if criticos:
        pior = min(criticos, key=lambda e: e.score)
        response.primary_action = (
            f"Prioridade: investigar {pior.metric} (score {pior.score}/100). {pior.note}"
        )
    elif atencao:
        pior = min(atencao, key=lambda e: e.score)
        response.primary_action = (
            f"Atenção: {pior.metric} (score {pior.score}/100). {pior.note}"
        )
    else:
        response.primary_action = (
            "Métricas dentro do esperado. Continuar monitorando e considerar "
            "expansão de orçamento ou novos públicos para escalar."
        )

    return response
