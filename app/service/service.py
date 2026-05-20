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
    data = m.model_copy()

    if data.impressions and data.impressions > 0:
        if data.hook_rate is None and data.video_views_3s is not None:
            data.hook_rate = round(data.video_views_3s / data.impressions * 100, 2)

        if data.hold_rate is None and data.thruplays is not None:
            data.hold_rate = round(data.thruplays / data.impressions * 100, 2)

        if data.ctr_link is None and data.link_clicks is not None:
            data.ctr_link = round(data.link_clicks / data.impressions * 100, 2)

        if data.ctr_all is None and data.all_clicks is not None:
            data.ctr_all = round(data.all_clicks / data.impressions * 100, 2)

        if data.frequency is None and data.reach and data.reach > 0:
            data.frequency = round(data.impressions / data.reach, 2)

        if data.cpm is None and data.spend:
            data.cpm = round(data.spend / data.impressions * 1000, 2)

    if data.lp_conversion_rate is None:
        if data.conversions is not None and data.landing_page_views and data.landing_page_views > 0:
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
    if inverted:
        if value > red:    return CampaignStatus.RED
        if value > yellow: return CampaignStatus.YELLOW
        return CampaignStatus.GREEN
    else:
        if value < red:    return CampaignStatus.RED
        if value < yellow: return CampaignStatus.YELLOW
        return CampaignStatus.GREEN


# ─────────────────────────────────────────────────────────────────────────────
# DETECTORES — CENÁRIOS A → K
# ─────────────────────────────────────────────────────────────────────────────

def _detect_weak_hook(m: Metrics, t: Targets) -> ScenarioDetail | None:
    """Cenário A — Gancho Fraco"""
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
    """Cenário B — Retenção Baixa"""
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
    """Cenário C — Click-Bait / Falta de Intenção Comercial"""
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
    """Cenário D — Desalinhamento com Landing Page"""
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
    """Cenário E — Fadiga de Criativo"""
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
    """Cenário F — Lead Frio / Persona Incorreta"""
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
    """Cenário G — Janela de Escala Vertical Ativa"""
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
    """Cenário H — Escala Horizontal por Fadiga Iminente"""
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
    """Cenário I — Learning Phase Hell"""
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
    """Cenário J — Overspending sem Retorno"""
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
    """Cenário K — Canibalização de Retargeting"""
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

def _evaluate_metrics(m: Metrics, t: Targets) -> list[MetricEvaluation]:
    evals = []

    def add(metric, value, st, note):
        if value is not None:
            evals.append(MetricEvaluation(metric=metric, value=float(value), status=st, note=note))

    if m.hook_rate is not None:
        st = _status(m.hook_rate, t.min_hook_rate * 0.7, t.min_hook_rate)
        add("Hook Rate", m.hook_rate, st, f"Meta: >{t.min_hook_rate:.0f}%. " + (
            "✓ Criativo capta atenção no feed." if st == CampaignStatus.GREEN else
            "⚠ Gancho fraco — público rola sem parar." if st == CampaignStatus.YELLOW else
            "✗ Crítico — criativo invisível no feed. Refazer abertura."
        ))

    if m.hold_rate is not None:
        st = _status(m.hold_rate, 10.0, t.min_hold_rate)
        add("Hold Rate", m.hold_rate, st, f"Meta: >{t.min_hold_rate:.0f}%. " + (
            "✓ Vídeo mantém atenção até a oferta." if st == CampaignStatus.GREEN else
            "⚠ Abandono precoce — revisar ritmo do vídeo." if st == CampaignStatus.YELLOW else
            "✗ Crítico — público abandona antes da CTA."
        ))

    if m.ctr_link is not None:
        st = _status(m.ctr_link, t.min_ctr_link * 0.5, t.min_ctr_link)
        add("CTR Link", m.ctr_link, st, f"Meta: >{t.min_ctr_link:.1f}%. " + (
            "✓ Intenção de clique saudável." if st == CampaignStatus.GREEN else
            "⚠ CTR Link abaixo do esperado." if st == CampaignStatus.YELLOW else
            "✗ Sem intenção comercial — CTA ausente ou fraca."
        ))

    if m.ctr_all is not None:
        if m.ctr_link is not None and m.ctr_all > t.max_ctr_all_ratio and m.ctr_link < 0.7:
            st, note = CampaignStatus.RED, f"✗ Click-Bait detectado: CTR Todos {m.ctr_all:.1f}% vs CTR Link {m.ctr_link:.2f}%."
        elif m.ctr_all > t.max_ctr_all_ratio:
            st, note = CampaignStatus.YELLOW, f"⚠ CTR Todos {m.ctr_all:.1f}% elevado — monitorar se CTR Link acompanha."
        else:
            st, note = CampaignStatus.GREEN, "✓ Proporção de engajamento saudável."
        add("CTR Todos", m.ctr_all, st, note)

    if m.cpa is not None and t.max_cpa is not None:
        st = _status(m.cpa, t.max_cpa * 1.3, t.max_cpa, inverted=True)
        delta = ((m.cpa / t.max_cpa) - 1) * 100
        add("CPA", m.cpa, st, f"Meta: <R${t.max_cpa:.2f}. " + (
            f"✓ CPA {abs(delta):.0f}% abaixo da meta." if st == CampaignStatus.GREEN else
            f"⚠ CPA {delta:.0f}% acima da meta." if st == CampaignStatus.YELLOW else
            f"✗ CPA {delta:.0f}% acima — campanha no vermelho."
        ))

    if m.cpl is not None and t.max_cpl is not None:
        st = _status(m.cpl, t.max_cpl * 1.3, t.max_cpl, inverted=True)
        add("CPL", m.cpl, st, f"Meta: <R${t.max_cpl:.2f}. " + (
            "✓ Custo por lead dentro da meta." if st == CampaignStatus.GREEN else
            "⚠ CPL acima da meta." if st == CampaignStatus.YELLOW else
            "✗ CPL crítico — lead saindo caro demais."
        ))

    if m.roas is not None and t.min_roas is not None:
        st = _status(m.roas, t.min_roas * 0.7, t.min_roas)
        add("ROAS", m.roas, st, f"Meta: >{t.min_roas:.1f}x. " + (
            f"✓ ROAS {m.roas:.1f}x — retorno saudável." if st == CampaignStatus.GREEN else
            "⚠ ROAS abaixo da meta." if st == CampaignStatus.YELLOW else
            "✗ ROAS crítico — campanha destruindo caixa."
        ))

    if m.cpm is not None:
        st = _status(m.cpm, t.max_cpm * 1.3, t.max_cpm, inverted=True)
        add("CPM", m.cpm, st, f"Referência: <R${t.max_cpm:.2f}. " + (
            "✓ Leilão eficiente." if st == CampaignStatus.GREEN else
            "⚠ CPM elevado — leilão competitivo." if st == CampaignStatus.YELLOW else
            "✗ CPM crítico — público exaurido ou anúncio penalizado."
        ))

    if m.cpc is not None and t.max_cpc is not None:
        st = _status(m.cpc, t.max_cpc * 1.3, t.max_cpc, inverted=True)
        add("CPC", m.cpc, st, f"Meta: <R${t.max_cpc:.2f}. " + (
            "✓ Custo por clique dentro do teto." if st == CampaignStatus.GREEN else
            "⚠ CPC acima do teto." if st == CampaignStatus.YELLOW else
            "✗ CPC crítico — cada clique caro demais."
        ))

    if m.frequency is not None:
        st = _status(m.frequency, t.max_frequency_fatigue * 1.2, t.max_frequency_fatigue, inverted=True)
        add("Frequência", m.frequency, st, f"Limite de fadiga: {t.max_frequency_fatigue}. " + (
            "✓ Audiência fresca." if st == CampaignStatus.GREEN else
            "⚠ Frequência alta — monitorar fadiga." if st == CampaignStatus.YELLOW else
            "✗ Saturação — criativo esgotado no público atual."
        ))

    if m.lp_conversion_rate is not None:
        st = _status(m.lp_conversion_rate, t.min_lp_conversion_rate * 0.5, t.min_lp_conversion_rate)
        add("Conversão LP", m.lp_conversion_rate, st, f"Meta: >{t.min_lp_conversion_rate:.1f}%. " + (
            "✓ Landing Page convertendo bem." if st == CampaignStatus.GREEN else
            "⚠ Conversão abaixo do esperado." if st == CampaignStatus.YELLOW else
            "✗ LP com problema crítico — gargalo fora da campanha."
        ))

    if m.weekly_conversions is not None:
        st = _status(m.weekly_conversions, t.min_weekly_conversions * 0.5, t.min_weekly_conversions)
        add("Conversões/semana", m.weekly_conversions, st, f"Meta: >{t.min_weekly_conversions}/semana. " + (
            "✓ Volume suficiente para aprendizado estável." if st == CampaignStatus.GREEN else
            "⚠ Volume baixo — risco de aprendizado limitado." if st == CampaignStatus.YELLOW else
            "✗ Volume crítico — algoritmo sem dados para otimizar."
        ))

    return evals


# ─────────────────────────────────────────────────────────────────────────────
# STATUS FINAL E SUMÁRIO
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_final_status(scenarios: list[ScenarioDetail]) -> CampaignStatus:
    if not scenarios:
        return CampaignStatus.GREEN

    nao_escala = [s for s in scenarios if s.code != ScenarioCode.VERTICAL_SCALE]

    if not nao_escala:
        return CampaignStatus.GREEN  # Só oportunidade de escala = saudável

    if any(s.priority == 1 for s in nao_escala):
        return CampaignStatus.RED

    return CampaignStatus.YELLOW


def _build_summary(scenarios: list[ScenarioDetail], status: CampaignStatus) -> str:
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

    # 3. Ordenar por prioridade (1 = crítico primeiro)
    scenarios.sort(key=lambda s: s.priority)

    # 4. Avaliar métricas individualmente
    metric_evals = _evaluate_metrics(m, t)

    # 5. Montar resposta
    final_status   = _resolve_final_status(scenarios)
    summary        = _build_summary(scenarios, final_status)
    primary_action = scenarios[0].action if scenarios else "Manter campanha ativa. Monitorar métricas nas próximas 48h."

    return CampaignAnalysisResponse(
        campaign_id=data.campaign.id,
        campaign_name=data.campaign.name,
        final_status=final_status,
        summary=summary,
        scenarios=scenarios,
        metric_evaluations=metric_evals,
        primary_action=primary_action,
    )   