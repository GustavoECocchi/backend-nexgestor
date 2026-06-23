# Contrato da API — NexGestor Backend (para o Frontend)

> Documento de integração frontend ↔ backend. Todos os exemplos abaixo foram **gerados executando o engine real** — não são inventados.

---

## Endpoint

```
POST /api/v1/campaign/analyze
Content-Type: application/json
```

Path único e definitivo. O prefixo `/api/v1` vem de `main.py`; o `/campaign` vem do router. **Não** existe `/api/v1/analyze`.

Endpoint auxiliar (catálogo dos 11 cenários, útil para a UI documentar/legendar):

```
GET /api/v1/campaign/scenarios
```

---

## Estrutura do request

O corpo tem três blocos: `campaign`, `metrics`, `targets`.

### `campaign` — identificação

| Campo | Tipo | Obrigatório | Default | Observação |
|---|---|---|---|---|
| `id` | int | **sim** | — | ID da campanha |
| `name` | string | **sim** | — | Nome exibido |
| `objective` | string | não | `"conversion"` | `conversion` \| `lead` \| `traffic` |
| `platform` | string | não | `"meta_ads"` | `meta_ads` \| `google_ads` |
| `niche` | string | não | `null` | Ex.: `SaaS`, `ecommerce`, `infoproduto` |

### `metrics` — todas opcionais

Nenhuma métrica é obrigatória; o engine analisa o que receber. Métricas de taxa podem ser **enviadas prontas** ou **derivadas** pelo backend a partir dos números brutos.

**Métricas deriváveis automaticamente** (se a taxa não vier mas os brutos vierem):

| Métrica derivada | Fórmula | Brutos necessários |
|---|---|---|
| `hook_rate` | `video_views_3s / impressions * 100` | `video_views_3s`, `impressions` |
| `hold_rate` | `thruplays / impressions * 100` | `thruplays`, `impressions` |
| `ctr_link` | `link_clicks / impressions * 100` | `link_clicks`, `impressions` |
| `ctr_all` | `all_clicks / impressions * 100` | `all_clicks`, `impressions` |
| `frequency` | `impressions / reach` | `impressions`, `reach` |
| `cpm` | `spend / impressions * 1000` | `spend`, `impressions` |
| `cpc` | `spend / link_clicks` | `spend`, `link_clicks` |
| `cpa` | `spend / conversions` | `spend`, `conversions` |
| `lp_conversion_rate` | `conversions / landing_page_views * 100` | `conversions`, `landing_page_views` |

> O frontend pode mandar os brutos e deixar o backend calcular, **ou** mandar a taxa pronta. Se mandar a taxa, ela tem prioridade (não é sobrescrita). Todas as métricas têm validação `>= 0`.

**Campos de `metrics` aceitos:** `impressions`, `reach`, `spend`, `video_views_3s`, `video_views_50pct`, `thruplays`, `hook_rate`, `hold_rate`, `link_clicks`, `all_clicks`, `ctr_link`, `ctr_all`, `cpm`, `cpc`, `cpl`, `cpa`, `roas`, `landing_page_views`, `lp_conversion_rate`, `conversions`, `weekly_conversions`, `frequency`, `learning_phase` (bool).

### `targets` — metas do gestor (todos têm default)

Pode enviar `"targets": {}` que o backend usa os defaults. **Atenção:** alguns cenários só disparam se o target correspondente for informado.

| Target | Default | Obrigatório para detectar |
|---|---|---|
| `min_hook_rate` | `35.0` | — |
| `min_hold_rate` | `15.0` | — |
| `min_ctr_link` | `1.5` | — |
| `max_ctr_all_ratio` | `3.5` | — |
| `max_cpa` | `null` | **Cenários D, F, G, H, J** |
| `max_cpc` | `null` | — |
| `max_cpm` | `50.0` | — |
| `max_cpl` | `null` | — |
| `min_roas` | `null` | **Cenários G, K** (recomendado) |
| `min_lp_conversion_rate` | `1.0` | — |
| `max_frequency_fatigue` | `2.8` | — |
| `max_frequency_critical` | `6.0` | — |
| `max_frequency_horizontal` | `2.5` | — |
| `min_weekly_conversions` | `50` | — |
| `scale_cpa_margin` | `0.75` | — |
| `scale_frequency_ceiling` | `1.8` | — |

> Regra prática para o frontend: para campanhas de conversão, **sempre peça `max_cpa` ao usuário** — sem ele, metade dos cenários (incluindo a janela de escala G) não dispara. Targets são decisões de negócio: nunca preencher automaticamente.

---

## Estrutura do response

```
{
  campaign_id:        int
  campaign_name:      string
  final_status:       "GREEN" | "YELLOW" | "RED" | "PAUSED"
  overall_score:      int (0–100)
  score_coverage:     int (0–100)   // % do peso das métricas que foi avaliado
  score_confidence:   "high" | "medium" | "low"   // confiança no score, derivada do coverage
  summary:            string
  scenarios:          ScenarioDetail[]
  metric_evaluations: MetricEvaluation[]
  primary_action:     string
  ai_insights:        AIInsights | null   // sempre presente; null nesta fase (IA desligada)
}
```

`ScenarioDetail`: `{ code, title, root_cause, funnel_impact, action, execution_rule, priority }`
`code` ∈ `A..K`. `priority`: `1` = crítico, `2` = urgente, `3` = monitorar.

`MetricEvaluation`: `{ metric, value, status, score, note }`
`status` ∈ `GREEN | YELLOW | RED`. `score`: 0–100.

---

## Interpretação de `final_status`

| Valor | Significado | Como tratar na UI |
|---|---|---|
| `GREEN` | Saudável — sem problemas críticos | Verde |
| `YELLOW` | Pontos de atenção (cenários de prioridade 2) | Amarelo |
| `RED` | Pelo menos um problema crítico (prioridade 1) | Vermelho |
| `PAUSED` | Reservado, uso futuro | Cinza |

---

## Confiança do score: `score_coverage` e `score_confidence`

O `overall_score` é média ponderada das métricas **presentes**. Uma campanha com poucos dados pode marcar score alto sem ter medido o que importa (CPA, ROAS). Por isso o response traz dois campos de contexto:

- **`score_coverage`** (0–100): % do peso total das métricas que foi efetivamente avaliado. Ex.: enviando só `impressions/reach/spend`, derivam apenas CPM e Frequência → coverage ≈ 12%.
- **`score_confidence`**: `high` (coverage ≥ 70) · `medium` (≥ 40) · `low` (< 40).

**Regra para a UI:** quando `score_confidence` for `low` ou `medium`, sinalize que o score é baseado em poucos dados (ex.: badge "baseado em X% das métricas"). Score 100 com `coverage: 12` **não** é uma campanha perfeita — é uma campanha pouco medida. Não exibir o score alto como sucesso sem o aviso de cobertura.

**`final_status` vs `overall_score` podem divergir — é esperado.** Eles medem coisas diferentes: `final_status` vem dos **cenários detectados** (um único problema crítico já pinta RED), enquanto `overall_score` é a **média ponderada das métricas**. Uma campanha pode ter `final_status: RED` (por um gargalo pontual, ex. Gancho Fraco) e ainda assim `overall_score: 80` (porque CPA, CPM etc. estão saudáveis). Na UI, **`final_status` deve mandar na cor/severidade principal** (é o diagnóstico acionável); o `overall_score` é um indicador secundário de saúde geral. Não tratar score alto como "tudo bem" quando há cenário crítico.

---

## ⚠️ Regra do status BLUE (escalável) — responsabilidade do frontend

**O backend NÃO retorna BLUE.** BLUE é exclusivamente camada de apresentação (`UIStatus`). O backend só conhece `GREEN/YELLOW/RED/PAUSED`.

Uma campanha com janela de escala vem com `final_status = "GREEN"` (escala é oportunidade, não problema), **mas traz o cenário `G` na lista `scenarios`**. O frontend deve pintar BLUE inspecionando os cenários, **não** o `final_status`:

```ts
const isEscalavel = response.scenarios.some(s => s.code === "G");
const uiStatus = isEscalavel ? "BLUE" : mapStatus(response.final_status);
```

> Não dá para inferir BLUE só do `final_status` — ele virá `GREEN`. **Tem que olhar `scenarios`.**

---

## Exemplos reais (validados contra o schema atual)

### 1. Campanha crítica (Gancho Fraco → `final_status: RED`)

**Request:**
```json
{
  "campaign": {
    "id": 101, "name": "Black Friday - Topo",
    "objective": "conversion", "platform": "meta_ads", "niche": "ecommerce"
  },
  "metrics": {
    "impressions": 50000, "reach": 42000, "spend": 1500.0,
    "video_views_3s": 9000, "link_clicks": 600, "conversions": 18
  },
  "targets": { "max_cpa": 80.0, "min_roas": 3.0 }
}
```

**Response (trecho):**
```json
{
  "campaign_id": 101,
  "campaign_name": "Black Friday - Topo",
  "final_status": "RED",
  "overall_score": 80,
  "summary": "1 problema(s) crítico(s): Cenário A. Resolver em ordem de prioridade.",
  "scenarios": [
    {
      "code": "A",
      "title": "Cenário A — Gancho Fraco (Falta de Atenção)",
      "root_cause": "Hook Rate 18.0% está criticamente abaixo da meta de 35%. ...",
      "funnel_impact": "Topo do funil comprometido. ...",
      "action": "Pausar o criativo atual e substituir os primeiros 3 segundos.",
      "execution_rule": "Refazer abertura com 'Pattern Interrupt': ...",
      "priority": 1
    }
  ],
  "metric_evaluations": [
    { "metric": "Hook Rate", "value": 18.0, "status": "RED", "score": 31, "note": "Meta: >35%. ✗ Crítico ..." },
    { "metric": "CTR Link", "value": 1.2, "status": "YELLOW", "score": 71, "note": "Meta: >1.5%. ⚠ ..." },
    { "metric": "CPA", "value": 83.33, "status": "YELLOW", "score": 94, "note": "Meta: <R$80.00. ⚠ CPA 4% acima ..." },
    { "metric": "CPM", "value": 30.0, "status": "GREEN", "score": 100, "note": "✓ Leilão eficiente." },
    { "metric": "Frequência", "value": 1.19, "status": "GREEN", "score": 100, "note": "✓ Audiência fresca." }
  ],
  "primary_action": "Pausar o criativo atual e substituir os primeiros 3 segundos.",
  "ai_insights": null
}
```

> Note: `hook_rate`, `ctr_link`, `cpa`, `cpm` e `frequency` foram **derivados** dos brutos — o request não os enviou.

### 2. Campanha escalável (BLUE no frontend → `final_status: GREEN` + cenário `G`)

**Request:**
```json
{
  "campaign": {
    "id": 102, "name": "Lookalike 1% - Compradores",
    "objective": "conversion", "platform": "meta_ads", "niche": "SaaS"
  },
  "metrics": {
    "impressions": 80000, "reach": 70000, "spend": 2000.0,
    "conversions": 60, "link_clicks": 2000, "frequency": 1.5,
    "weekly_conversions": 60, "learning_phase": false,
    "lp_conversion_rate": 3.0, "roas": 5.0
  },
  "targets": { "max_cpa": 50.0, "min_roas": 3.0 }
}
```

**Response (trecho):**
```json
{
  "campaign_id": 102,
  "campaign_name": "Lookalike 1% - Compradores",
  "final_status": "GREEN",
  "overall_score": 100,
  "scenarios": [
    {
      "code": "G",
      "title": "Cenário G — Janela de Escala Vertical Ativa (Alta Performance)",
      "priority": 1
    }
  ],
  "primary_action": "Executar Escala Vertical Automatizada — aumentar orçamento agora.",
  "ai_insights": null
}
```

> **Este é o caso da regra BLUE:** `final_status = "GREEN"`, mas `scenarios` contém `G`. UI deve pintar BLUE.

### 3. Payload mínimo (fallback do engine → orientação útil)

**Request:**
```json
{
  "campaign": { "id": 103, "name": "Campanha sem dados" },
  "metrics": { "impressions": 1000, "reach": 800, "spend": 50.0 },
  "targets": {}
}
```

**Response:**
```json
{
  "campaign_id": 103,
  "campaign_name": "Campanha sem dados",
  "final_status": "GREEN",
  "overall_score": 100,
  "summary": "Análise baseada nas métricas individuais (2 avaliadas). 2 métrica(s) saudável(eis).",
  "scenarios": [],
  "metric_evaluations": [
    { "metric": "CPM", "value": 50.0, "status": "GREEN", "score": 100, "note": "✓ Leilão eficiente." },
    { "metric": "Frequência", "value": 1.25, "status": "GREEN", "score": 100, "note": "✓ Audiência fresca." }
  ],
  "primary_action": "Métricas dentro do esperado. Continuar monitorando e considerar expansão ...",
  "ai_insights": null
}
```

> Com poucos dados, `scenarios` vem vazio e o backend gera um `summary`/`primary_action` mínimos via fallback. A resposta **nunca** é vazia.

---

## Códigos de erro

| Status | Quando | Corpo |
|---|---|---|
| `200` | Sucesso | `CampaignAnalysisResponse` |
| `422` | Payload mal-formado (faltou `campaign.id` ou `name`, tipo errado) | Erro de validação do FastAPI |
| `400` | Erro de validação semântica do domínio | `{ "detail": "..." }` |
| `500` | Bug inesperado | `{ "detail": "Erro interno ao processar análise. ..." }` |

---

## Notas para o frontend

1. `ai_insights` **sempre existe** no response, mas vem `null` nesta fase (IA desligada). Trate como opcional.
2. Os campos `value` em `metric_evaluations` podem ser `null` (métrica não fornecida nem derivável).
3. As `note` de métrica já vêm com emoji semafórico (`✓ ⚠ ✗`) — pode exibir direto.
4. `scenarios` vem ordenado por `priority` (crítico primeiro).
5. BLUE = inspecionar `scenarios` por cenário `G`, nunca `final_status`.
