"""
Insights module — NexGestor Decision Engine

Gera insights explicativos e recomendações operacionais.
Baseado nos níveis de métricas e no cenário detectado.
"""

from app.enum.campaign import MetricLevel


METRIC_LABELS = {
    MetricLevel.VERY_GOOD: "excelente",
    MetricLevel.GOOD: "saudável",
    MetricLevel.AVERAGE: "abaixo do ideal",
    MetricLevel.BAD: "crítico",
}


def generate_insights(ctr_level: MetricLevel, cpc_level: MetricLevel, cpa_level: MetricLevel, metrics) -> list[str]:
    insights = []

    # CTR insights
    if ctr_level == MetricLevel.BAD:
        insights.append(
            f"CTR de {metrics.ctr:.2f}% está crítico — indica baixa atratividade inicial do anúncio. "
            "O algoritmo tende a penalizar relevância, pressionando o CPC para cima."
        )
    elif ctr_level == MetricLevel.AVERAGE:
        insights.append(
            f"CTR de {metrics.ctr:.2f}% está abaixo do ideal — anúncio gera interesse moderado, "
            "mas há margem de melhoria antes que o leilão comece a penalizar."
        )
    elif ctr_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        insights.append(
            f"CTR de {metrics.ctr:.2f}% indica anúncio relevante e atrativo para o público atingido."
        )

    # CPC insights
    if cpc_level == MetricLevel.BAD:
        insights.append(
            f"CPC de {metrics.cpc:.2f} está elevado — pode ser consequência do CTR baixo "
            "ou reflexo de alta concorrência no leilão para esse público."
        )
    elif cpc_level == MetricLevel.AVERAGE:
        insights.append(
            f"CPC de {metrics.cpc:.2f} está em faixa de atenção — "
            "tráfego ainda viável mas com pressão crescente no custo."
        )
    elif cpc_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        insights.append(
            f"CPC de {metrics.cpc:.2f} está eficiente — plataforma está entregando cliques a custo competitivo."
        )

    # CPA insights
    if cpa_level == MetricLevel.BAD:
        insights.append(
            f"CPA de {metrics.cpa:.2f} está crítico — aquisição acima do sustentável. "
            "O problema pode estar no tráfego, na conversão ou no desalinhamento de oferta."
        )
    elif cpa_level == MetricLevel.AVERAGE:
        insights.append(
            f"CPA de {metrics.cpa:.2f} está em zona de atenção — aquisição ainda viável "
            "mas sem margem para ineficiências adicionais."
        )
    elif cpa_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        insights.append(
            f"CPA de {metrics.cpa:.2f} está saudável — campanha convertendo dentro do custo esperado."
        )

    # Insight relacional: CTR ruim + CPA ruim = problema no topo causando efeito cascata
    if ctr_level == MetricLevel.BAD and cpa_level == MetricLevel.BAD:
        insights.append(
            "A relação CTR → CPC → CPA sugere efeito cascata: a baixa atratividade no topo do funil "
            "está gerando tráfego caro e desqualificado, comprometendo a aquisição."
        )

    # Insight relacional: CTR bom + CPA ruim = gargalo pós-clique
    if ctr_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD) and cpa_level == MetricLevel.BAD:
        insights.append(
            "O anúncio está funcionando bem — o problema está após o clique. "
            "A landing page, oferta ou processo de conversão precisam ser revisados."
        )

    return insights


def generate_recommendations(ctr_level: MetricLevel, cpc_level: MetricLevel, cpa_level: MetricLevel, scenario: dict) -> list[str]:
    recs = []

    bottleneck = scenario.get("funnel_bottleneck")

    # Recomendações baseadas no CTR
    if ctr_level == MetricLevel.BAD:
        recs.extend([
            "Testar novos criativos com gancho visual diferente",
            "Revisar a headline e o copy principal do anúncio",
            "Avaliar fadiga criativa e rotacionar peças",
            "Testar segmentação mais específica ou interesses diferentes",
        ])
    elif ctr_level == MetricLevel.AVERAGE:
        recs.extend([
            "Realizar testes A/B com variações de headline e criativo",
            "Validar se o público está bem alinhado com a oferta",
        ])

    # Recomendações baseadas no CPA com CTR bom (gargalo pós-clique)
    if cpa_level == MetricLevel.BAD and ctr_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        recs.extend([
            "Auditar a landing page: clareza da oferta, velocidade e conversão",
            "Revisar alinhamento entre promessa do anúncio e página de destino",
            "Validar se o processo de conversão (formulário/checkout) está funcionando",
            "Testar variações da oferta com diferentes propostas de valor",
        ])

    # CPA ruim com CTR ruim (problema sistêmico)
    if cpa_level == MetricLevel.BAD and ctr_level == MetricLevel.BAD:
        recs.extend([
            "Pausar e reestruturar o conjunto de anúncios antes de continuar gastando",
            "Priorizar resolução do CTR antes de otimizar CPA",
        ])

    # Campanha saudável — recomendação de escala
    if ctr_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD) and cpa_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        recs.extend([
            "Avaliar aumento gradual de orçamento (10-20% por período)",
            "Monitorar estabilidade do CPA durante a escala",
            "Explorar novos públicos semelhantes para ampliar alcance com eficiência",
        ])

    # Escala travada (CTR baixo, CPA bom)
    if ctr_level == MetricLevel.BAD and cpa_level in (MetricLevel.GOOD, MetricLevel.VERY_GOOD):
        recs.extend([
            "Testar criativos mais agressivos para ampliar o alcance",
            "Explorar públicos maiores mantendo a qualidade de conversão",
        ])

    # Remove duplicatas mantendo ordem
    seen = set()
    unique_recs = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            unique_recs.append(r)

    # Fallback garantido — nunca retorna lista vazia
    if not unique_recs:
        unique_recs = [
            "Monitorar as métricas nos próximos dias antes de fazer alterações",
            "Comparar performance com períodos anteriores para identificar tendências",
            "Avaliar se há variações de sazonalidade afetando os resultados atuais",
        ]

    return unique_recs