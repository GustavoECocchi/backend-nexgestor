"""
Diagnostics module — NexGestor Decision Engine

Identifica cenários operacionais com base na relação entre métricas.
Determina causa raiz, gargalo do funil, sintomas, causas e consequências.
"""

from app.enum.campaign import MetricLevel, FunnelStage


# Helpers
def _is_bad(level): return level == MetricLevel.BAD
def _is_avg(level): return level == MetricLevel.AVERAGE
def _is_good(level): return level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD)


def detect_scenario(ctr: MetricLevel, cpc: MetricLevel, cpa: MetricLevel) -> dict:
    """
    Mapeia combinações de métricas para diagnósticos operacionais.
    Baseado nos cenários definidos na Decision Engine spec.
    """

    # Cenário 1: Tudo ruim — problema clássico de topo de funil
    if _is_bad(ctr) and _is_bad(cpc) and _is_bad(cpa):
        return {
            "primary_problem": "Baixa atratividade criativa causando ineficiência em toda a cadeia",
            "funnel_bottleneck": FunnelStage.TOP,
            "symptoms": [
                "CTR abaixo do mínimo aceitável",
                "CPC elevado indicando baixa relevância no leilão",
                "CPA comprometido como consequência do tráfego ineficiente",
            ],
            "possible_causes": [
                "Criativo fraco ou sem diferencial",
                "Copy sem aderência ao público",
                "Segmentação desalinhada com a oferta",
                "Possível fadiga criativa",
            ],
            "consequences": [
                "Tráfego caro e desqualificado",
                "Aquisição inviável no custo atual",
                "Desperdício de verba no topo do funil",
            ],
        }

    # Cenário 2: CTR alto, CPC baixo, CPA alto — problema pós-clique
    if _is_good(ctr) and _is_good(cpc) and _is_bad(cpa):
        return {
            "primary_problem": "Gargalo pós-clique: anúncio performa bem mas conversão falha",
            "funnel_bottleneck": FunnelStage.POST_CLICK,
            "symptoms": [
                "CTR saudável indica anúncio relevante e atrativo",
                "CPC eficiente indica bom aproveitamento do leilão",
                "CPA alto indica perda de conversão após o clique",
            ],
            "possible_causes": [
                "Landing page com baixa taxa de conversão",
                "Desalinhamento entre promessa do anúncio e oferta da página",
                "Problemas técnicos no checkout ou formulário",
                "Oferta sem percepção de valor suficiente",
            ],
            "consequences": [
                "Desperdício de tráfego qualificado",
                "Aquisição cara mesmo com tráfego barato",
                "ROI comprometido por problema fora do anúncio",
            ],
        }

    # Cenário 3: Tudo bom — campanha saudável
    if _is_good(ctr) and _is_good(cpc) and _is_good(cpa):
        return {
            "primary_problem": "Nenhum gargalo crítico identificado",
            "funnel_bottleneck": FunnelStage.BOTTOM,
            "symptoms": [
                "CTR dentro de faixa saudável",
                "CPC eficiente",
                "CPA dentro do target",
            ],
            "possible_causes": [],
            "consequences": [
                "Campanha com boa margem de escalabilidade",
                "Alta eficiência operacional no funil completo",
            ],
        }

    # Cenário 4: CTR médio/bom, CPA alto — possível problema de conversão ou qualidade
    if not _is_bad(ctr) and _is_bad(cpa):
        return {
            "primary_problem": "Problema de conversão ou qualidade do tráfego no meio/fundo do funil",
            "funnel_bottleneck": FunnelStage.MIDDLE,
            "symptoms": [
                "CTR razoável indica alguma atratividade do anúncio",
                "CPA alto indica perda de eficiência no funil",
            ],
            "possible_causes": [
                "Desalinhamento entre anúncio e landing page",
                "Público parcialmente qualificado",
                "Oferta com baixa conversão para o segmento atingido",
            ],
            "consequences": [
                "Aquisição acima do custo sustentável",
                "Tráfego parcialmente desperdiçado",
            ],
        }

    # Cenário 5: CTR baixo, CPC baixo, CPA baixo — converte mas com escala limitada
    if _is_bad(ctr) and _is_good(cpc) and _is_good(cpa):
        return {
            "primary_problem": "Campanha eficiente mas com baixa capacidade de escala",
            "funnel_bottleneck": FunnelStage.TOP,
            "symptoms": [
                "CTR baixo indica alcance limitado ou criativo pouco agressivo",
                "CPC baixo indica eficiência no leilão",
                "CPA saudável indica boa conversão do tráfego que chega",
            ],
            "possible_causes": [
                "Criativo conservador sem apelo de massa",
                "Segmentação muito restrita",
                "Alcance limitado pelo criativo",
            ],
            "consequences": [
                "Dificuldade de escalar volume sem comprometer CPA",
                "Potencial de crescimento travado no topo",
            ],
        }

    # Cenário 6: CTR ruim, resto médio/bom — topo problemático com absorção parcial
    if _is_bad(ctr):
        return {
            "primary_problem": "Baixa atratividade no topo do funil pressionando eficiência geral",
            "funnel_bottleneck": FunnelStage.TOP,
            "symptoms": [
                "CTR abaixo do esperado",
                "CPC e CPA ainda sustentáveis mas com risco de deterioração",
            ],
            "possible_causes": [
                "Criativo sem apelo suficiente",
                "Copy sem gancho claro",
                "Público parcialmente desalinhado",
            ],
            "consequences": [
                "Tendência de aumento de CPC conforme o leilão penaliza relevância",
                "Pressão crescente no CPA se CTR continuar baixando",
            ],
        }

    # Cenário 7: Tudo médio — campanha estável mas sem destaque
    if _is_avg(ctr) and _is_avg(cpc) and _is_avg(cpa):
        return {
            "primary_problem": "Campanha na média em todos os indicadores — sem gargalo crítico mas sem eficiência",
            "funnel_bottleneck": FunnelStage.MIDDLE,
            "symptoms": [
                "CTR dentro da faixa média — anúncio gera interesse moderado",
                "CPC em faixa aceitável mas com margem de melhoria",
                "CPA dentro do limite mas sem folga operacional",
            ],
            "possible_causes": [
                "Criativo funcional mas sem diferencial competitivo",
                "Segmentação razoável mas não otimizada",
                "Oferta sem elemento de urgência ou destaque",
            ],
            "consequences": [
                "Campanha vulnerável a variações de leilão e sazonalidade",
                "Sem margem para aumentar verba sem comprometer CPA",
                "Risco de deterioração gradual sem ação proativa",
            ],
        }

    # Cenário 8: CTR médio, CPA ruim — conversão fraca com tráfego razoável
    if _is_avg(ctr) and _is_bad(cpa):
        return {
            "primary_problem": "Tráfego razoável mas conversão insuficiente — gargalo no meio/fundo do funil",
            "funnel_bottleneck": FunnelStage.MIDDLE,
            "symptoms": [
                "CTR médio indica anúncio gerando cliques mas sem grande atratividade",
                "CPA crítico indica perda severa de eficiência após o clique",
            ],
            "possible_causes": [
                "Landing page sem aderência com a promessa do anúncio",
                "Oferta sem percepção de valor para o público atingido",
                "Público parcialmente qualificado chegando na página",
            ],
            "consequences": [
                "Verba sendo consumida sem retorno proporcional",
                "Aquisição inviável no modelo atual",
            ],
        }

    # Cenário 9: CTR bom, CPC médio, CPA médio — boa entrada, eficiência moderada
    if _is_good(ctr) and _is_avg(cpc) and _is_avg(cpa):
        return {
            "primary_problem": "Anúncio eficiente mas ganhos sendo perdidos no meio do funil",
            "funnel_bottleneck": FunnelStage.MIDDLE,
            "symptoms": [
                "CTR saudável indica criativo e público bem alinhados",
                "CPC e CPA em faixa média indicam eficiência parcial no funil",
            ],
            "possible_causes": [
                "Landing page convertendo abaixo do potencial",
                "Processo de conversão com fricção desnecessária",
                "Oferta funcional mas sem elemento de decisão forte",
            ],
            "consequences": [
                "Potencial de performance maior do que o atual entregado",
                "Otimização pós-clique pode melhorar CPA sem mexer no anúncio",
            ],
        }

    # Fallback genérico
    return {
        "primary_problem": "Performance mista — múltiplos pontos de atenção no funil",
        "funnel_bottleneck": FunnelStage.MIDDLE,
        "symptoms": ["Métricas com variação entre os estágios do funil"],
        "possible_causes": ["Necessário mais contexto para diagnóstico preciso"],
        "consequences": ["Risco de ineficiência crescente sem ação corretiva"],
    }