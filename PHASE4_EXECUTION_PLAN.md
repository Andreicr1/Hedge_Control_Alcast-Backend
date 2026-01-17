# Fase 4 — Execução (Governança, Compliance & Rastreabilidade)

**Status:** Plano de execução (pré‑implementação)

**Data:** 2026‑01‑13

**Fonte de verdade do escopo:** [PHASES_4_5_6_CONSOLIDATED_PLAN.md](PHASES_4_5_6_CONSOLIDATED_PLAN.md)

## Objetivo

Executar exatamente a Fase 4, como bloco inicial do projeto estendido:

- 4.1 Timeline v2 com colaboração humana (append‑only)
- 4.2 Exportação & compliance (cadeia completa + state-at-time-T + audit export)
- 4.3 Workflow & aprovações institucionais (declarativo simples)

Sem reinterpretação conceitual. Fases 5 e 6 ficam fora desta execução.

---

## Gates (CI / qualidade) — antes de merge

**Obrigatório em toda entrega (cada PR):**

- `\.venv\Scripts\python -m ruff check .`
- `\.venv\Scripts\python -m ruff format --check .`
- `\.venv\Scripts\python -m pytest -q`

**Regras de PR:**

- Cada PR deve ter **testes** cobrindo o comportamento novo.
- Nada “sensível” editável/deletável.
- Todas ações sensíveis geram **Audit + Timeline event**.

---

## Sequência (backend-first) e dependências

### Milestone 4.0 — Fundacional (pré-requisitos de F4)

**T4.0.1 — Normalizar contratos de evento para Timeline (system vs human)**
- Output: convenção documentada de `event_type` e payload; sem mudar comportamento ainda.
- Acceptance:
  - Documento curto no repositório (ex.: `TIMELINE_EVENT_CONVENTIONS.md`) com exemplos.

**T4.0.2 — Permissões e RBAC: matriz de escrita para Timeline humana**
- Output: matriz “quem pode postar o quê” (Auditoria read-only).
- Acceptance:
  - Testes de RBAC cobrindo: Auditoria não cria comentário; Financeiro cria comentário `finance`.

---

## 4.1 Timeline v2 — Colaboração Humana (append-only)

### Epic F4.1 — Human Collaboration

**T4.1.1 — Threads por entidade (chave determinística)**
- Backend:
  - Definir `thread_key` determinístico: `${subject_type}:${subject_id}` (ex.: `rfq:123`).
  - (Se necessário) adicionar campos/padrões no payload de eventos `human.*`.
- Acceptance:
  - `GET /timeline?subject_type=&subject_id=` retorna eventos `human.*` associados.

**T4.1.2 — Endpoint de comentário humano (append-only)**
- Backend:
  - Novo endpoint: `POST /timeline/human/comments`.
  - Persistência via `timeline_events` com `event_type="human.comment.created"`.
  - `payload`: `{ body, thread_key, mentions: [...], attachments: [...] }`.
  - `idempotency_key` suportado (cliente pode repetir sem duplicar).
- RBAC:
  - Auditoria: proibido.
  - Financeiro/Admin: pode escrever `visibility=finance`.
  - Demais: apenas `visibility=all` (se aplicável).
- Acceptance:
  - Teste: comment criado aparece em `GET /timeline`.
  - Teste: Auditoria recebe 403.
  - Teste: idempotency retorna o mesmo evento (não duplica).

**T4.1.3 — @mentions (resolução e persistência)**
- Backend:
  - Menções declaradas no payload (ex.: emails/ids).
  - Gerar evento auxiliar `human.mentioned` OU persistir lista em `human.comment.created` (decisão a fixar no plano).
- Acceptance:
  - Teste: payload contém `mentions` e é retornado na leitura.

**T4.1.4 — Correções via supersede (comment corrected)**
- Backend:
  - Endpoint: `POST /timeline/human/comments/{event_id}/corrections`.
  - Cria novo evento `human.comment.corrected` com `supersedes_event_id=event_id`.
  - Nunca edita o evento original.
- Acceptance:
  - Teste: correção cria novo evento e mantém original intacto.

**T4.1.5 — Anexos: storage abstraction + metadata**
- Backend:
  - Definir interface `StorageProvider` (local filesystem default; S3 future).
  - Endpoint: `POST /timeline/human/attachments` (gera `upload_url`/`storage_uri` + checksum metadata).
  - Evento: `human.attachment.added` vinculado a `thread_key`.
- Acceptance:
  - Teste: metadata persistida e retornável.
  - Teste: Auditoria não pode subir/anexar.

---

## 4.2 Exportação & Compliance

### Epic F4.2 — Export Engine

**T4.2.1 — Modelo de export request + status**
- Backend:
  - Tabelas (ou modelos) mínimos:
    - `exports` (id, type, params_json, status, created_at, created_by)
    - `export_artifacts` (export_id, kind, storage_uri, checksum, size)
  - Estados: `queued/running/succeeded/failed`.
- Acceptance:
  - Teste: criar export cria registro em DB e status inicial.

**T4.2.2 — Export “Audit Log” (CSV) determinístico**
- Backend:
  - `POST /exports` com `type=audit_log` e filtros.
  - `GET /exports/{id}/download` retorna CSV.
  - Manifest com checksum.
- Acceptance:
  - Teste: export reproduzível (mesma seed → mesmo checksum/bytes).

**T4.2.3 — Export “State at time T” (cadeia) (CSV + manifest)**
- Backend:
  - `type=state_at_time`
  - Param: `as_of`.
  - Exporta as entidades relevantes com join keys e timestamps.
  - Sem duplicar lógica (somente leitura; sem recalcular).
- Acceptance:
  - Teste: export contém SO/PO/Exposure/RFQ/Contract/MTM/Cashflow/Audit quando existirem.

**T4.2.4 — PDF (onde fizer sentido) — faseada**
- Observação:
  - PDF é incluído no escopo, mas deve começar com um único relatório “executivo” mínimo para provar o pipeline.
- Acceptance:
  - Teste: endpoint retorna PDF com conteúdo mínimo e checksum.

---

## 4.3 Workflow & Aprovações Institucionais

### Epic F4.3 — Approvals

**T4.3.1 — Modelo declarativo de workflow**
- Backend:
  - Tabelas:
    - `workflow_requests` (type, subject_type, subject_id, reason, sla_deadline, status)
    - `workflow_decisions` (request_id, decision, decided_by, justification, decided_at)
  - Status: `requested/approved/rejected/expired`.
- Acceptance:
  - Teste: request cria timeline event `workflow.requested` e audit.

**T4.3.2 — Aprovação de award manual (gating)**
- Backend:
  - Gating no endpoint de award (RFQ): se “award manual” ⇒ precisa de workflow `approved`.
  - Timeline registra `WORKFLOW_APPROVED/REJECTED`.
- Acceptance:
  - Teste: award manual bloqueado sem aprovação; permitido com aprovação.

**T4.3.3 — Exceções (KYC/pricing/hedge policy) (gating)**
- Backend:
  - Definir pontos de gate (ex.: `rfq_create`, `rfq_award`, `contract_create`).
  - Workflow required por tipo.
- Acceptance:
  - Testes cobrindo ao menos 1 fluxo por tipo de exceção.

**T4.3.4 — SLA e timestamps**
- Backend:
  - Job/endpoint para marcar `sla_breached`.
  - Evento `WORKFLOW_SLA_BREACHED`.
- Acceptance:
  - Teste: request vencido produz evento.

---

## Entregáveis frontend (apenas após backend estável)

- Timeline UI: threads + comentários + menções + anexos.
- Exports UI: solicitar export + baixar + manifest.
- Approvals UI: lista de requests + decisão + justificativa + SLA.

---

## Checklist final (DoD da Fase 4)

- Timeline suporta eventos `human.*` com append-only, correções via supersede e anexos.
- Exports reproduzíveis + auditáveis (manifest + checksum) para audit log e state-at-time-T.
- Aprovações bloqueiam ações sensíveis quando exigido; histórico completo (Audit + Timeline).
- CI gate verde (ruff + pytest).
