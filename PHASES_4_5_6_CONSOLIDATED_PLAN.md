# Escopo Consolidado — Fases 4, 5 e 6 (Projeto Estendido)

**Status:** As-built (F6.3 entregue/fechado) + backlog (T1–T5)

**Data:** 2026‑01‑13

Este documento consolida o escopo estendido (Fases 4, 5, 6), com dependências explícitas, definição institucional (escopo / não‑escopo), contratos de API propostos, eventos de Timeline, tickets backend/frontend e acceptance criteria.

---

## 0) Princípios não‑negociáveis

- **Append-only + rastreabilidade:** nada “sensível” é editável/deletável; correções sempre via `supersedes_event_id`.
- **Timeline ≠ workflow engine:** Timeline registra e dá contexto; decisões/aprovações acontecem em fluxos dedicados.
- **Determinismo:** pipeline diário e exports devem ser reprocessáveis e produzir o mesmo resultado dado o mesmo input.
- **P&L é read model (não contabilidade):** sem livro razão/ERP, sem escrituração fiscal.
- **Separação explícita:** `realized` vs `unrealized` sempre rotulados e auditáveis.

---

## 1) Dependências (ordem proposital)

1. **Fase 4 (Governança/Compliance/Rastreabilidade)** — habilita auditoria, colaboração humana rastreável, exports e aprovações.
2. **Fase 5 (Mercado/Operações/Valuation)** — fecha paridade institucional de estados (RFQ), exposures e MTM institucional.
3. **Fase 6 (Financeiro avançado)** — cashflow avançado, P&L engine e pipeline diário.

---

## 2) Definições institucionais (escopo / não‑escopo)

### 2.1 O que é “Projeto Completo” (critério final)

O projeto é considerado 100% concluído quando:

- Implementação = diagrama institucional (sem domínios críticos mock/manual/aspiracional).
- Existe e é auditável:
  - **MTM** (somente contratos ativos; marcado como `unrealized`)
  - **Cashflow** (projetado; e, na Fase 6, cenários/sensitividade)
  - **P&L** (read model com separação clara `realized`/`unrealized`)
- Toda decisão sensível é:
  - justificada
  - aprovada quando aplicável
  - auditável
  - reproduzível

### 2.2 Não‑escopo (continua fora, mesmo no projeto estendido)

- Contabilidade legal / fiscal, razão contábil, ERP, escrituração.
- BPM engine completo (Camunda/Temporal-like). Workflow aqui é declarativo simples.

---

## 3) Fase 4 — Governança, Compliance & Rastreabilidade

### 4.1 Timeline v2 — Colaboração Humana

**Objetivo:** adicionar colaboração humana rastreável, mantendo a Timeline como registro append-only e não como workflow.

**Incluir**
- Comentários append-only
- `@mentions`
- Discussões por entidade (SO, Exposure, RFQ, Contract)
- Correções via `supersedes_event_id`
- Anexos (metadata + storage abstraction)

**Não é**
- Workflow
- Aprovação
- Engine de decisão

**Proposta de modelo (planejamento)**
- **Manter** `timeline_events` como tabela única (event sourcing leve).
- **Padrão de `event_type` (fonte da verdade = produção):**
  - eventos automáticos/legado permanecem em **CONSTANT_CASE** (ex.: `SO_CREATED`, `MTM_SNAPSHOT_CREATED`).
  - eventos humanos usam namespace `human.*` em lower/dot (ex.: `human.comment.created`).
  - o endpoint `POST /timeline/events` é v1 (lista travada); eventos humanos entram via endpoints dedicados `/timeline/human/*`.
- Padronizar payloads para human events:
  - `human.comment.created` → `{ body, thread_key, mentions: [user_id|email], attachments: [...] }`
  - `human.attachment.added` → `{ file_id, file_name, mime, size, checksum, storage_uri }`
  - `human.comment.corrected` → usa `supersedes_event_id`

**Storage abstraction (anexos)**
- Interface `StorageProvider` (S3/local/fs) + tabela de metadados (ou só `payload.meta` com `storage_uri`).

**RBAC**
- Leitura segue visibilidade (`all` vs `finance`).
- Escrita humana:
  - `Auditoria`: read-only (sem comentários).
  - Demais perfis: permitido conforme política.

**DoD / Acceptance**
- Eventos humanos aparecem na Timeline e são filtráveis por entidade.
- RBAC respeitado.
- Nada editável/deletável; correções sempre via `supersedes_event_id`.

**APIs (contrato proposto)**
- `POST /timeline/human/comments` (criar comentário)
- `GET /timeline?subject_type=&subject_id=` (já existe; garantir inclusão de human events)
- `POST /timeline/human/attachments` (registrar upload metadata)

**Eventos Timeline (mínimo)**
- `human.comment.created`
- `human.comment.corrected` (via supersede)
- `human.attachment.added`
- `human.mentioned`

---

### 4.2 Exportação & Compliance

**Objetivo:** export reproduzível e auditável da cadeia completa, sem duplicar lógica de negócio.

**Incluir**
- Export completo da cadeia:
  `SO → PO → Exposure → RFQ → Contract → MTM → Cashflow → Audit → (P&L na revisão final)`
- Export “estado do sistema em T”
- Export de audit log
- CSV + PDF (onde fizer sentido)

**Modelo**
- Export como **read model** (queries determinísticas) + manifest.
- “State at time T” = snapshot lógico baseado em `as_of` + filtros.

**DoD / Acceptance**
- Export reproduzível (mesma entrada → mesma saída).
- Assinável/auditável (manifest com hash/checksum; opcional assinatura).
- Sem lógica de negócio duplicada (reuso de serviços/read models).

**APIs (contrato proposto)**
- `POST /exports` (cria job/export request; retorna `export_id`)
- `GET /exports/{export_id}` (status + links)
- `GET /exports/{export_id}/download` (arquivo)

**Máquina de estados do Export Job (planning-only; explícita)**

- **Estados permitidos**
  - `queued`: job criado/persistido; ainda não iniciou geração.
  - `running`: geração em andamento (worker iniciou).
  - `done`: geração concluída com sucesso; artefatos/links (quando existirem) prontos.
  - `failed`: geração terminou com falha; nenhum artefato confiável.

- **Transições válidas (somente forward)**
  - `queued -> running`
  - `running -> done`
  - `running -> failed`
  - (Opcional, se for necessário no worker) `queued -> failed` apenas para erro imediato/validação.

- **Invariantes (governança)**
  - `export_id` é **determinístico** e **imutável**: derivado de `(schema_version, export_type, as_of, filters)`.
  - O `status` **não afeta o determinismo** do conteúdo; expressa apenas progresso.
  - `done` implica que o conjunto de artefatos/manifest (quando implementado) corresponde exatamente ao `inputs_hash` do job.
  - `failed` não deve expor conteúdo parcial: links/arquivos só existem em `done`.

- **RBAC (alinhado ao modelo institucional)**
  - Criar job (`POST /exports`): `financeiro | admin`.
  - Consultar status (`GET /exports/{export_id}`): `financeiro | admin | auditoria`.
  - `auditoria` é read-only (defesa em profundidade).

- **Eventos de Audit (mínimo)**
  - `exports.job.requested` (criação/solicitação; idempotente quando aplicável)
  - `exports.job.started` (transição `queued -> running`)
  - `exports.job.completed` (transição `running -> done`; inclui `artifacts_count` + hashes)
  - `exports.job.failed` (transição `running -> failed`; inclui `error_code`)

---

### 4.3 Workflow & Aprovações Institucionais

**Objetivo:** garantir que ações sensíveis não ocorram sem aprovação exigida, mantendo histórico completo.

**Incluir**
- Aprovação de exceções:
  - KYC exception
  - pricing exception
  - hedge fora de política
- Aprovação de award manual
- SLA e timestamps

**Modelo**
- Workflow declarativo simples:
  - `workflow_requests` (tipo, alvo, contexto, SLA)
  - `workflow_decisions` (approved/rejected, actor, justification)
- Gating nos endpoints sensíveis.
- Timeline registra solicitações e decisões.

**DoD / Acceptance**
- Nenhuma ação sensível ocorre sem aprovação quando aplicável.
- Histórico completo rastreável (Audit + Timeline).

**Eventos Timeline (mínimo)**
- `WORKFLOW_REQUESTED`
- `WORKFLOW_APPROVED`
- `WORKFLOW_REJECTED`
- `WORKFLOW_SLA_BREACHED`

---

## 4) Fase 5 — Mercado, Operações & Valuation

### 5.1 RFQ State Machine Completa

**Estados alvo (institucional)**
- `DRAFT`
- `SENDING`
- `PARTIAL_RESPONSE`
- `FULL_RESPONSE`
- `AWARDED`
- `CLOSED`
- `ARCHIVED`
- `CANCELLED`

**Situação atual (inventário)**
- Enum atual inclui: `draft`, `pending`, `sent`, `quoted`, `awarded`, `expired`, `failed`.

**Plano de paridade**
- Definir enum institucional e mapear migração/compatibilidade.
- Introduzir transições validadas por regras:
  - `DRAFT -> SENDING` (inicia envio)
  - `SENDING -> PARTIAL_RESPONSE/FULL_RESPONSE` (respostas recebidas)
  - `*_RESPONSE -> AWARDED` (award)
  - `AWARDED -> CLOSED` (finalização)
  - `* -> CANCELLED` (cancelamento)
  - `CLOSED -> ARCHIVED` (retenção)

**DoD / Acceptance**
- Estados explícitos; transições validadas.
- Timeline reflete mudanças de estado.

**Eventos Timeline (mínimo)**
- `RFQ_STATE_CHANGED` (payload: from/to/reason)
- `RFQ_SENDING_STARTED`
- `RFQ_RESPONSE_RECEIVED`
- `RFQ_AWARDED`
- `RFQ_CLOSED`
- `RFQ_ARCHIVED`
- `RFQ_CANCELLED`

---

### 5.2 Exposure Engine — Paridade Institucional

**Objetivo:** exposures só existem para pricing flutuante e são sempre consistentes.

**Incluir**
- Exposures apenas para pricing flutuante.
- Recalculo automático em:
  - novo SO
  - novo PO
  - Contract criado
  - Hedge manual
- Trigger contínuo (event-driven ou job).

**Gap identificado (inventário)**
- `compute_net_exposure` hoje agrega `Exposure` + `HedgeExposure` links; não há garantia (aqui, no serviço) de que exposures existentes sejam apenas de floating.

**Plano**
- Definir regras de geração/atualização de Exposure:
  - source_type (SO/PO)
  - pricing_type (somente flutuante)
  - status (open/partially_hedged/hedged/closed)
  - residual = (gross - hedged)
- Definir “no phantom exposures”:
  - se origem muda para preço fixo, exposure correspondente deve ser encerrada/supersedida (auditável).

**DoD / Acceptance**
- Exposure sempre consistente; residual correto.
- Nenhuma exposição fantasma.

**Eventos Timeline (mínimo)**
- `EXPOSURE_RECALCULATED`
- `EXPOSURE_CREATED`
- `EXPOSURE_CLOSED`

---

### 5.3 MTM — Regra Institucional

**Regra final**
- MTM:
  - calculado somente para **contratos ativos**
  - sempre rotulado como **unrealized**
  - nenhum P&L inferido automaticamente do MTM sem regra explícita

**Inventário relevante**
- Existem MTM snapshots hoje para `exposure`, `hedge`, `net` (objetos não-contrato). Isso precisa ser:
  - removido/banido, OU
  - mantido como **proxy claramente rotulado** (e nunca confundido com valuation real de hedge).

**Plano**
- Introduzir snapshots de MTM por `contract_id` (novo object type ou tabela dedicada).
- Restringir cálculo aos contratos `status=active`.

**DoD / Acceptance**
- MTM = valuation real (contrato ativo).
- Proxy claramente separado.
- Nenhuma ambiguidade financeira.

---

## 5) Fase 6 — Financeiro Avançado (com P&L)

### 6.1 P&L Engine (Realized + Unrealized)

**O que o P&L É**
- Um **read model financeiro** derivado de:
  - Contracts
  - MTM snapshots
  - Settlements
  - Cashflows realizados

**O que o P&L NÃO É**
- Contabilidade legal
- Livro razão
- ERP
- Escrituração fiscal

**Componentes**
- **Unrealized P&L**
  - baseado em MTM snapshots
  - por Contract/Deal/Commodity
  - rotulado: `unrealized`, `as_of_date`
- **Realized P&L**
  - derivado exclusivamente de settlements finais
  - por Contract/settlement_date
  - imutável após fechado
- **Total P&L**
  - soma explícita: realized + unrealized

**Data model (proposto)**
- `pnl_contract_snapshots`
  - `as_of_date`, `contract_id`, `deal_id`, `currency`, `unrealized_pnl`, `data_quality_flags`, `inputs_hash`
- `pnl_contract_realized`
  - `contract_id`, `settlement_date`, `realized_pnl`, `locked_at`, `source_settlement_id`
- `pnl_deal_aggregate`
  - `as_of_date`, `deal_id`, `realized`, `unrealized`, `total`

**API (proposta)**
- `GET /pnl`
  - filtros: date range, deal_id, contract_id, counterparty, commodity
  - response: `realized_pnl`, `unrealized_pnl`, `total_pnl`, `currency`, `data_quality_flags`
- `GET /pnl/contracts/{contract_id}` (detalhe + trilha)
- `GET /pnl/deals/{deal_id}`

**Timeline & Audit (mínimo)**
- `PNL_SNAPSHOT_CREATED` (linka MTM snapshot inputs)
- `PNL_REALIZED` (linka settlement)

**Acceptance**
- Separação realized/unrealized explícita em todas as telas e APIs.
- Reprocessamento determinístico (inputs iguais → outputs iguais).
- Trilha auditável: cada P&L referencia MTM snapshot/settlement/contract.

---

### 6.2 Cashflow Avançado (com P&L integrado)

**Incluir**
- Cenários: otimista/base/pessimista
- Sensitividade: ±5%, ±10%
- Multi-moeda
- Consolidação por: data, counterparty, deal, currency
- Cashflow mostra impacto esperado no P&L futuro

**Decisões fechadas (para evitar ambiguidade/auditabilidade fraca)**

- **Cenários vs Sensitividade (sem duplicidade)**
  - Cenário = baseline (define a regra de projeção da parte **não observada** do driver)
  - Sensitividade = shift percentual aplicado **somente** na parte não observada do driver (±5%, ±10%)
  - Default: `base = 0%`, `optimistic = +5%`, `pessimistic = -5%` (aliases sobre o mesmo baseline)
- **Projeção do “não observado” (baseline padrão)**
  - Default institucional: **Método C (input explícito)** — usuário informa premissa (ex.: preço forward/base), e isso vira o baseline
  - Fallback (se usuário não fornecer): **Método A (proxy 3M)** quando existir série suportada
  - Se não existir série suportada: retorna `not_available` + flags (sem “chutar”)
- **Multi-moeda (política explícita, zero FX inferido)**
  - Motor calcula nativamente em USD (como hoje)
  - Conversão para moeda de reporte só quando houver FX explícito (via request ou policy map auditável)
  - Se faltar FX: retorna USD + `fx_not_available`, sem conversão
- **Integração com P&L (impacto futuro separado)**
  - Cashflow avançado retorna, por cenário/sensitividade:
    - `expected_settlement_value` (projeção)
    - `pnl_current_unrealized` (do snapshot P&L do `as_of`)
    - `future_pnl_impact = expected_settlement_value − pnl_current_unrealized_component`
  - Tudo explicitamente rotulado: `realized`/`unrealized`/`future_impact` (sem campo genérico “pnl”)
- **Premissas econômicas/preço (parte do contrato)**
  - Request inclui um bloco `assumptions` enviado pelo usuário (ex.: `forward_price_assumption`, FX policy override, etc.)
  - `assumptions` entra no `inputs_hash` e volta na resposta (auditável/reprodutível)

**API (travado para implementação — MVP recomendado)**

- `POST /cashflow/advanced/preview`
  - compute-only, não persiste run, sem Timeline event
  - retorna `inputs_hash`, itens + agregações + flags + referências (datas publicadas, `fx_as_of`, metodologia)
  - Observação: apesar de ser `POST`, deve ser tratado como **read-only** (side-effect free)

**Contrato do endpoint (campos exatos, planning-only)**

Request (`CashflowAdvancedPreviewRequest`)
- `as_of` (date, obrigatório; determinismo depende disso)
- `filters` (opcional)
  - `contract_id?: string`
  - `deal_id?: int`
  - `counterparty_id?: int`
  - `settlement_date_from?: date`
  - `settlement_date_to?: date`
- `reporting` (opcional)
  - `reporting_currency?: string` (ex.: `BRL`; default omitido = sem conversão)
  - `fx` (opcional; **obrigatório** se `reporting_currency` for diferente de USD)
    - `mode`: `explicit` | `policy_map`
    - `fx_symbol?: string` (ex.: `USDBRL=X`)  
    - `fx_source?: string` (ex.: `yahoo`) 
    - `policy_key?: string` (chave para mapeamento auditável; ex.: `BRL:USDBRL=X@yahoo`)
- `scenario` (obrigatório)
  - `baseline_method`: `explicit_assumption` | `proxy_3m`
  - `aliases_enabled`: boolean (default `true`)  
    - quando `true`, o servidor inclui automaticamente: `base(0%)`, `optimistic(+5%)`, `pessimistic(-5%)`
  - `sensitivities_pct`: lista (default `[ -0.10, -0.05, 0.05, 0.10 ]`)
- `assumptions` (obrigatório, mas pode estar vazio)
  - `forward_price_assumption?: float`
  - `forward_price_currency?: string` (default `USD`)
  - `forward_price_symbol?: string` (opcional; se preenchido, deve ser auditável/referenciável)
  - `forward_price_as_of?: date` (opcional; se preenchido, entra no `inputs_hash`)
  - `notes?: string` (opcional; auditável, entra no `inputs_hash`)

Response (`CashflowAdvancedPreviewResponse`)
- `inputs_hash: string`
- `as_of: date`
- `assumptions: object` (eco do request)
- `references`
  - `cash_last_published_date?: date`
  - `proxy_3m_last_published_date?: date`
  - `fx_as_of?: datetime`
  - `fx_rate?: float`
  - `fx_symbol?: string`
  - `fx_source?: string`
- `items: CashflowAdvancedItem[]`
- `aggregates: CashflowAdvancedAggregateRow[]`

`CashflowAdvancedItem`
- `contract_id: string`
- `deal_id: int`
- `counterparty_id?: int`
- `settlement_date?: date`
- `native_currency: string` (sempre `USD` no MVP)
- `projections: CashflowAdvancedProjection[]`

`CashflowAdvancedProjection`
- `scenario: base | optimistic | pessimistic`
- `sensitivity_pct: float` (permitidos: `-0.10`, `-0.05`, `0.0`, `0.05`, `0.10`)
- `expected_settlement_value_usd?: float`
- `pnl_current_unrealized_usd?: float`
- `future_pnl_impact_usd?: float`
- `expected_settlement_value_reporting?: float` (presente somente se houver FX)
- `pnl_current_unrealized_reporting?: float` (presente somente se houver FX)
- `future_pnl_impact_reporting?: float` (presente somente se houver FX)
- `methodology: string`
- `flags: string[]`

`CashflowAdvancedAggregateRow`
- `bucket_date: date` (data de referência do bucket, alinhada ao cashflow)
- `counterparty_id?: int`
- `deal_id?: int`
- `currency: string` (`USD` ou `reporting_currency` quando aplicável)
- `scenario: base | optimistic | pessimistic`
- `sensitivity_pct: float`
- `expected_settlement_total?: float`
- `pnl_current_unrealized_total?: float`
- `future_pnl_impact_total?: float`
- `flags: string[]`

**Flags (mínimo; extensível)**
- `assumptions_missing` (baseline exige premissa e ela não veio)
- `proxy_3m_not_available` (fallback não disponível)
- `projected_not_available`
- `pnl_not_available` (não há snapshot P&L para o `as_of`/contrato)
- `fx_not_available`
- `currency_not_supported`

**DoD / Acceptance (inclui critérios de teste)**
- Cashflow vira ferramenta de risco (cenários + sensitividade + consolidação) sem booking/contábil.
- `POST /cashflow/advanced/preview` é side-effect-free e não gera Timeline event.
- Determinismo:
  - Mesmo request (incluindo `assumptions`) + mesmo estado de `MarketPrice`/P&L no `as_of` ⇒ mesmo `inputs_hash` e mesmo output.
  - Mudança em `assumptions` ou `as_of` ⇒ `inputs_hash` diferente.
- RBAC:
  - Permitido: `financeiro` e `auditoria` (read-only compute).
  - `auditoria` continua proibida para endpoints que persistem/mutam (fora do MVP).
- Multi-moeda:
  - Se `reporting_currency != USD` e FX não fornecido/resolvido ⇒ retorna só USD + `fx_not_available` (sem conversão).
- Consolidação:
  - Sempre retorna `aggregates` por `date, counterparty, deal, currency` (com labels e flags).

**DoD / Acceptance**
- Cashflow vira ferramenta de risco.
- Sem booking/contábil.

---

### 6.3 Pipeline Diário Financeiro

**Status (6.3): DELIVERED / CLOSED (as-built)**

**Objetivo**
- Rodar um **pipeline diário** (batch) que materializa **read models financeiros** e registros de rastreabilidade para um `as_of_date`.
- Ser **determinístico** (mesmo input + mesma base de dados ⇒ mesmo output) e **idempotente** (re-trigger não duplica efeitos).

**Reusar padrões já existentes no backend**
- `inputs_hash` por JSON canônico (`sort_keys=True`, `separators=(",", ":")`) + `sha256`
- idempotência de Timeline via `(event_type, idempotency_key)`
- state machine “forward-only” para jobs (como `exports`)

**Não é / Não-escopo (6.3)**
- Não é workflow/BPM engine.
- Não faz approvals, não cria decisões humanas, não executa gating de exceções.
- Não faz contabilidade/razão/ERP/escrituração.
- Não pode **mutar entidades de domínio** (Contracts/Deals/Exposures/RFQs etc.).
- Não pode “buscar mercado externo” durante a execução (sem HTTP para Yahoo etc.). Market data deve estar **persistido**.

**Input canônico (contrato institucional)**
- `as_of_date: date` (obrigatório)
- `pipeline_version: string` (obrigatório; ex.: `finance.pipeline.daily.v1.usd_only`)
- `scope_filters: object` (opcional; default `{}`; mesma lógica de normalização dos filtros do P&L)
- `mode: "materialize" | "dry_run"` (default `materialize`)
- `emit_exports: boolean` (default `true`)
- `correlation_id: string` (opcional; se omitido, derivar do request id)

**inputs_hash (obrigatório)**
- `inputs_hash = sha256(canonical_json(input))`.
- Qualquer alteração em `as_of_date`, `scope_filters`, `pipeline_version`, `mode` ou `emit_exports` deve alterar o hash.

**Idempotência / Side-effects (regras fechadas)**
- A execução é idempotente por `inputs_hash`.
- Side-effects permitidos:
  - escrita em tabelas de **read model** (ex.: MTM snapshots, P&L snapshots, flags)
  - escrita em tabela de controle do pipeline (run/steps + status)
  - criação de `exports` jobs (que por si são determinísticos e auditáveis)
  - emissão de Timeline events e Audit events (sempre idempotentes)
- Side-effects proibidos:
  - alterar status/valores de Contracts/Deals/RFQs
  - alterar “verdade de negócio” (sem booking)
  - dependência de relógio de parede para conteúdo (timestamps só como metadado operacional)

**Execução (nota)**
- A execução/ordem interna de steps é considerada parte da implementação entregue; este documento mantém apenas o contrato institucional + endpoints/resultados, para evitar replanejamento.

**Eventos Timeline (mínimo; nomes fechados)**
- `FINANCE_PIPELINE_REQUESTED`
- `FINANCE_PIPELINE_STARTED`
- `FINANCE_PIPELINE_COMPLETED`
- `FINANCE_PIPELINE_FAILED`

**RBAC (fechado)**
- Executar (materialize): `financeiro | admin`.
- Consultar status/resultados: `financeiro | admin | auditoria`.
- `auditoria` é read-only (não pode disparar escrita).

**DoD / Acceptance (6.3)**
- Determinismo: mesma entrada + mesma base ⇒ mesmo `inputs_hash` e mesmos read models gerados.
- Idempotência: re-trigger com mesmo `inputs_hash` não duplica snapshots/events/exports.
- Observabilidade: logs por step + Timeline events por run.
- Pipeline não muta domínio; escreve apenas read models + run status + rastreabilidade.

**Endpoints (as-built)**
- `POST /pipelines/finance/daily/run`
  - `mode=materialize` executa e persiste run/steps.
  - `mode=dry_run` retorna plano (`inputs_hash`, `ordered_steps`) sem side-effects.
- `GET /pipelines/finance/daily/runs/{run_id|inputs_hash}` (status + steps; RBAC inclui `auditoria` read-only)

**Resultados finais (as-built)**
- Persistência de `run` + `steps` com status forward-only, idempotentes por `inputs_hash`.
- Emissão idempotente de Timeline: `FINANCE_PIPELINE_*` por run.
- Hook opcional de exports por `emit_exports` (criação de job determinístico e rastreável quando habilitado).

**Histórico (6.3.x) — executado/entregue (não replanejar)**
- 6.3.1 — Modelo de Run/Steps (persistência + estados)
- 6.3.2 — Orquestrador do pipeline (service layer)
- 6.3.3 — Timeline emitters do pipeline (idempotentes)
- 6.3.4 — API endpoints (run + status)
- 6.3.5 — Integração P&L (reuse do serviço existente)
- 6.3.6 — Integração MTM por contrato (depende F5.3)
- 6.3.7 — Cashflow baseline diário + flags
- 6.3.8 — Exports hook (opcional por flag)

---

## 6) Tickets (backlog proposto)

### Backlog consolidado pós-limpeza (T1–T5) — planning-only

**Princípios de execução (fechado)**
- Cada ticket inclui uma **UX mínima** (institucional) — rigor técnico, precisão e qualidade formal.
- **PDF não é opcional**: T2 inclui CSV + PDF onde fizer sentido.
- Não reabrir o que já está fechado na Fase 6.3 (pipeline diário determinístico, hooks e gates) salvo bug objetivo.

### Ordem recomendada (confirmada)

**T1 → T2 → T3 → T4 → T5**

**Dependências críticas (resumo)**
- T3 depende de decisão da **matriz de aprovação** (Pergunta 4).
- T4 depende de definição objetiva de **FULL_RESPONSE** (Pergunta 5).
- T5 depende de fonte de **settlement final** e **política FX/moeda base** (Perguntas 1 e 2).

---

### T1 — Timeline v2 (human events) + anexos + UX mínima

**Objetivo**
- Habilitar colaboração humana rastreável (comentários, menções e anexos) mantendo Timeline como append-only (não workflow).

**Escopo**
- Backend: eventos `human.*` (comment created/corrected, attachment added, mentioned), `supersedes_event_id`, RBAC (auditoria read-only), storage abstraction e metadados.
- Frontend (UX mínima): thread por entidade, criação/correção de comentário, menções visíveis, anexos com metadados; filtros por entidade/data.

**RBAC (explícito para UX)**
- Criar eventos `human.*`:
  - `auditoria`: **nunca** (read-only; não exibe composer/botões de ação).
  - demais roles autenticadas: permitido em `visibility=all`.
  - `visibility=finance`: somente `financeiro | admin`.

**Dependências**
- Nenhuma bloqueante para iniciar.

**DoD / Acceptance**
- Append-only garantido; correções via `supersedes_event_id`.
- RBAC respeitado; `auditoria` não escreve.
- Anexos rastreáveis (metadata + checksum + storage_uri) e exibidos na Timeline.

---

### T2 — Exports institucionais (state-at-time-T + audit + chain) com CSV + PDF + UX mínima

**Objetivo**
- Export reproduzível/auditável da cadeia completa e “estado em T”, com manifest/checksums e artefatos consistentes.

**Escopo**
- Backend:
  - **Export types existentes (não renomear):** `audit_log`, `state_at_time`, `pnl_aggregate`.
  - **Export types novos (apenas adicionar):** `chain_export` (SO→PO→Exposure→RFQ→Contract→MTM→Cashflow→Audit→(P&L quando aplicável)).
  - Artefatos: CSV e **PDF** (onde fizer sentido), manifest com hashes/checksums por arquivo.
  - RBAC: criar `financeiro|admin`; consultar `financeiro|admin|auditoria`.
- Frontend (UX mínima): tela/lista de exports, detalhe de job (status, inputs_hash, manifest) e links de download.

**Dependências**
- Requer T1 apenas se UX do export precisar de comentários/anexos (opcional).
- Assinatura criptográfica (Pergunta 3) pode ser definida em paralelo; não bloqueia o MVP (hash/checksum + manifest).

**DoD / Acceptance**
- Reprocessável: mesma entrada → mesmo `export_id` e mesmos checksums.
- `done` só existe com artefatos + manifest coerentes com `inputs_hash`.
- PDF incluído e validado visualmente (layout institucional mínimo, legível e consistente).

---

### T3 — Workflow & Aprovações (gating + SLA) + inbox UX mínima

**Status (T3): DELIVERED / CLOSED (as-built)**

**Objetivo**
- Garantir que ações sensíveis não ocorram sem aprovação exigida, com trilha completa (Timeline/Audit) e SLA.

**Escopo**
- Backend: `workflow_requests` + `workflow_decisions`, regras de gating nos endpoints sensíveis, SLA timestamps e eventos de Timeline.
- Frontend (UX mínima): inbox de pendências, detalhe do request, decisão (approve/reject) com justificativa, status/SLA.

**Dependências**
- Bloqueado para “fechar regras” até decisão da **matriz de aprovação** (Pergunta 4).
- T1 recomendado para colaboração/justificativas ricas, mas não obrigatório para iniciar T3.

**DoD / Acceptance**
- Nenhuma ação sensível passa sem aprovação quando aplicável.
- Histórico rastreável (request + decision + actor + justificativa + timestamps).

---

### T4 — Paridade institucional RFQ + Exposure + UX mínima de ciclo de vida

**Status (T4): DELIVERED / CLOSED (as-built; escopo estrito em SO/PO)**

**Objetivo**
- Fechar estados/transições institucionais de RFQ e garantir Exposure engine consistente (floating-only, recalculation triggers, no phantom exposures).

**Escopo**
- Backend:
  - RFQ: enum institucional + transições validadas + Timeline events.
  - Exposure: regras de criação/atualização, triggers de recálculo e invariantes de consistência.
- Frontend (UX mínima): telas/ações state-aware de RFQ e visualização de exposures com status/residual.

**Dependências**
- A definição objetiva de **FULL_RESPONSE** (Pergunta 5) bloqueia apenas a evolução/fechamento formal do enum institucional de estados de RFQ.
- O as-built entregue aqui foi congelado propositalmente com escopo estrito em Exposure (SO/PO) + compat mínima de RFQ, para reduzir risco.

**DoD / Acceptance**
- RFQ com estados e transições explícitos; Timeline refletindo mudanças.
- Exposures apenas para floating e sem exposições “fantasmas”.

---

### T5 — Fechamento financeiro (realized P&L + FX policy map) + UX mínima de P&L

**Status (T5): DELIVERED / CLOSED (as-built)**

**Objetivo**
- Entregar P&L institucional completo (realized + unrealized) com trilha auditável e política explícita de FX/moeda base.

**Escopo**
- Backend:
  - Realized P&L baseado exclusivamente em settlements finais (imutável após locked).
  - Policy map de FX / moeda base e regras auditáveis de conversão (sem FX inferido).
  - APIs e eventos mínimos (snapshot + realized).
- Frontend (UX mínima): P&L **agregado por deal** (KPIs + tabela), com labels realized/unrealized e flags de qualidade.

**Decisão (T5 — UX mínima)**
- Não incluir agora lookup/detalhe por `contract_id` na UI.
- Justificativa: reduz risco/escopo, não bloqueia auditoria/comitê e mantém o projeto em linha de encerramento.
- Follow-up opcional (não bloqueante): adicionar drill-down por contrato e trilha detalhada via `GET /pnl/contracts/{contract_id}`.

**Dependências**
- Nenhuma dependência bloqueante no as-built entregue (Perguntas 1/2 decididas; ver Seção 7).

**DoD / Acceptance**
- Separação realized/unrealized explícita em todas as telas/APIs.
- Determinismo e trilha auditável: cada P&L referencia inputs (MTM/settlement/FX policy) via hashes/referências.

---

## 7) Decisões institucionais e extensões futuras (fora do escopo entregue)

Esta seção registra decisões e itens deliberadamente adiados. **Não há engenharia pendente neste ciclo** por conta destes pontos.

1) **Fonte de “settlement final” (DECIDIDO / AS-BUILT)**
- O settlement final é calculado exclusivamente a partir do **Official Cash Settlement da LME** (driver já introduzido no engine em `compute_final_avg_cash`).
- Não foi criada entidade/tabela adicional de settlement; o realized P&L permanece **derivado, determinístico e reprocessável**.

2) **Política de FX + moeda base do P&L (FUTURO / FORA DO ESCOPO ENTREGUE)**
- Reclassificado como decisão estratégica futura.
- O projeto entregue assume **P&L USD-only**.
- FX permanece **explícito e compute-only** apenas no cashflow advanced (via `policy-map` auditável), sem conversão no P&L MVP.
- Este ponto **não bloqueia mais nenhum ticket** do ciclo entregue.

4) **Matriz de aprovação (BASELINE DEFINIDA — MVP ENTREGUE)**
- O T3 foi corretamente fechado com thresholds simples e gating efetivo.
- Expansões futuras são possíveis, mas não fazem parte deste ciclo.

5) **Definição objetiva de FULL_RESPONSE (ADIADA DELIBERADAMENTE)**
- Trata-se de regra institucional sensível.
- Qualquer definição futura deve reabrir governança de RFQ em um ticket separado (ex.: **T4.2**), sem impacto no escopo entregue.

3) **Assinatura de exports (FUTURO / OPCIONAL)**
- O MVP de exports segue com `hash/checksum + manifest`.
- Assinatura criptográfica pode ser adotada futuramente (PKI/keys), sem impacto no escopo entregue.

6) **Follow-up (ticket separado): inventário de origens de Exposure além de SO/PO**
- Racional: exposure institucional nasce de SO/PO; ampliar sem inventário fechado introduz risco.
- Ação futura: auditar paths de criação/atualização/fechamento de Exposure fora de SO/PO e decidir tratamento (sem reabrir T4 as-built).

---

## 8) Acceptance criteria (macro)

- **Sem mocks** em domínios críticos.
- **Determinismo** validado por reprocessamento (mesmo input → mesmo output).
- **Auditabilidade**: toda métrica financeira tem trilha para inputs.
- **RBAC** consistente em Timeline/Exports/Approvals/P&L.
