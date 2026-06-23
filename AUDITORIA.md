# Relatório de Auditoria — backend-nexgestor

> Auditoria sistemática em busca de bugs, riscos e armadilhas. Cada item foi **testado com código**, não só inspeção visual. Itens marcados como ✅ foram verificados e estão OK (registrados para não re-investigar depois).

Estado na auditoria: **74 testes passando**, motor + IA corrigidos.

Classificação: 🔴 bug/risco que afeta o usuário · 🟠 risco operacional · 🟡 débito técnico/cosmético · ✅ verificado OK

---

## 🔴 1. Score alto com cobertura baixa de métricas (risco de credibilidade) — ✅ RESOLVIDO

> **Resolvido** via Opção A: o response agora traz `score_coverage` (0–100, % do peso avaliado) e `score_confidence` (high/medium/low). O cálculo do score não mudou; a transparência foi adicionada. Ex.: campanha com só impressions/reach/spend → score 100, mas `coverage: 12`, `confidence: low`. Coberto por testes de regressão (`test_coverage_*`). Contrato do frontend atualizado.

**O problema mais sério.** `_calc_overall_score` divide pela soma dos pesos **presentes**, não pelo total (1.0). Consequência: uma campanha com pouquíssimos dados pode marcar **score 100 / status GREEN**.

Exemplo real testado — enviando só `impressions`, `reach`, `spend`:
- Métricas avaliadas: apenas CPM (100) e Frequência (100)
- `overall_score`: **100**, `final_status`: **GREEN**
- Mas **CPA, ROAS, Hook Rate, CTR nem foram medidos**

**Por que importa:** o gestor vê "100/verde" e confia numa campanha que, na verdade, não teve as métricas que mais importam (CPA, ROAS) sequer avaliadas. Falsa confiança é pior que score baixo — leva a decisão errada.

**Sugestão (não aplicar sem decisão de produto):**
- Expor um campo `coverage` / `metricas_avaliadas` no response (ex.: "4 de 10 métricas com peso"), para o frontend sinalizar baixa cobertura; **ou**
- Rebaixar o score quando faltam métricas críticas (CPA/ROAS ausentes → teto no score); **ou**
- No mínimo, documentar no contrato que score alto + poucos dados = baixa confiança.

---

## 🔴 2. Inconsistência detector ↔ semáforo de métrica (Frequência) — ✅ RESOLVIDO

> **Resolvido** via Opção A: o semáforo de Frequência agora fica RED quando `freq > max_frequency_fatigue` (2.8) — mesmo gatilho do Cenário E — e YELLOW em `freq > max_frequency_horizontal` (2.5), alinhado ao Cenário H. Antes o RED só vinha em 3.36, deixando o semáforo amarelo enquanto o card já acusava saturação. Coberto por `test_frequencia_red_alinhada_ao_detector_fadiga`.

O detector de **Fadiga (Cenário E)** dispara em `frequency > 2.8` (`max_frequency_fatigue`), mas o semáforo da métrica Frequência só fica RED em `frequency > 3.36` (`2.8 * 1.2`).

Resultado testado — em `freq = 2.9, 3.0, 3.3`:
- Cenário E **dispara** (problema crítico/urgente de fadiga)
- Mas o semáforo da Frequência mostra apenas **YELLOW**

**Por que importa:** o card do cenário grita "criativo saturado, reduza orçamento" enquanto o semáforo da métrica diz "amarelo, monitorar". O usuário vê duas mensagens contraditórias sobre o mesmo número. Mesma lógica pode valer para outras métricas com detector próprio.

**Sugestão:** alinhar o threshold RED do semáforo de Frequência ao gatilho do detector (RED quando `freq > max_frequency_fatigue`), ou documentar que "semáforo = saúde da métrica isolada" e "cenário = diagnóstico cruzado" são escalas diferentes de propósito.

---

## 🟠 3. `final_status` RED com `overall_score` alto — ✅ DOCUMENTADO

Testado: campanha com Cenário A crítico → `final_status = RED` mas `overall_score = 80`. Não é bug (são dimensões diferentes: status vem dos cenários, score é média ponderada), mas o frontend pode renderizar "vermelho + 80/100 verde" lado a lado e confundir.

**Sugestão:** documentar no contrato a relação entre os dois e como a UI deve priorizar (provavelmente: `final_status` manda na cor principal; `overall_score` é secundário).

---

## 🟠 4. Cliente Gemini singleton nunca reseta após rotação de key — ✅ RESOLVIDO

`_client` é global e criado uma vez (`_get_client`). Se a equipe **rotacionar a `GEMINI_API_KEY`** (ex.: após a exposição que causou suspensão), o cliente em memória continua com a key antiga até o processo reiniciar.

**Por que importa:** durante os testes de julho, trocar a key e "não funcionar" pode ser só o singleton velho — confunde o diagnóstico.

**Sugestão:** invalidar `_client` quando a key muda, ou expor um endpoint/admin para resetar, ou simplesmente documentar "trocou a key → reinicie o servidor".

---

## 🟠 5. `CORS_ORIGINS` mal-formatado derruba o boot — ✅ RESOLVIDO

Confirmado: se alguém puser `CORS_ORIGINS=http://a,http://b` (vírgula simples) no `.env`, o pydantic-settings v2 **não sobe o servidor** (`SettingsError`) — exige JSON: `CORS_ORIGINS=["http://a","http://b"]`.

Já está documentado no `.env.example`, mas é a causa nº1 provável de "o servidor não liga" para quem for configurar o ambiente.

**Sugestão:** manter o aviso no `.env.example` (já feito) e, se quiser robustez, adicionar um validator que aceite string vírgula-separada e converta para lista.

---

## 🟠 6. `GEMINI_API_KEY` pode vazar via traceback do SDK — ✅ RESOLVIDO

`call_gemini` usa `logger.exception(...)`, que loga o stack completo. Se o SDK do Gemini incluir a URL da requisição (com a key embutida) no traceback, a key vai parar no log.

**Por que importa:** key em log + log colado em chat/issue para reportar feedback = suspensão automática (já aconteceu uma vez no projeto).

**Sugestão:** ao reportar erros em julho, filtrar strings `AIza` antes de colar. Idealmente, sanitizar o log de exceção da IA (não logar a URL crua).

---

## 🟡 7. `DEBUG=True` como default — ✅ RESOLVIDO

`config.py` e `.env.example` trazem `DEBUG=True`. Hoje o handler de erro já devolve 500 genérico (não vaza stack ao cliente), então o impacto é baixo, mas o ideal é `DEBUG=False` por padrão e ligar só em dev.

---

## 🟡 8. `is_ai_available()` re-importa o SDK a cada chamada — ✅ RESOLVIDO

Faz `from google import genai` em toda invocação, e é chamado ~2x por request. Custo desprezível, mas é trabalho repetido. Poderia cachear o resultado do "SDK está instalado?" numa flag de módulo.

---

## 🟡 9. `campaign.name` sem limite de tamanho nem validação de vazio — ✅ RESOLVIDO

Testado: `name=""` e `name=10000 chars` retornam 200. Pydantic aceita por padrão. Sem risco de crash, mas pode poluir UI/logs.

**Sugestão:** `Field(min_length=1, max_length=200)` no `name`, se quiser robustez.

---

## ✅ Verificados e OK (sem ação)

- ✅ **`_calc_score`** em bordas (value=0, valores enormes, target=0, target/value negativos): sempre retorna 0–100. Sólido.
- ✅ **Divisão por zero** nos detectores (`reach=0`, `link_clicks=0`, `conversions=0`): guards `> 0` protegem, sem crash.
- ✅ **Pré-processamento** não sobrescreve métrica enviada pronta (taxa manual vence o bruto). Correto.
- ✅ **Validação de input**: negativos (`ge=0`), `id` não-inteiro, tipos errados → todos 422. Robusto.
- ✅ **inf/nan no JSON**: valores extremos não geram `inf`/`nan` — serialização estrita passa.
- ✅ **`_calc_overall_score`** com lista vazia ou só métricas peso-0 → retorna 50 (neutro). Correto.
- ✅ **Rotas**: sem paths duplicados; os dois health checks (`/` e `/campaign/health` oculto) coexistem.
- ✅ **Threshold exato**: `freq == 2.8` não dispara Cenário E (usa `>`, não `>=`). Correto.

---

## Prioridade sugerida

1. **Itens 1 e 2** antes de a equipe testar em julho — são os que geram diagnóstico contraditório/enganoso, exatamente o tipo de coisa que mina a confiança no produto no primeiro contato.
2. **Itens 4, 5, 6** são operacionais — resolver/documentar antes de ligar a key real.
3. **7, 8, 9** são higiene — quando sobrar tempo.

Nenhum item quebra a suíte atual; todos são comportamentos que os testes não cobriam.
