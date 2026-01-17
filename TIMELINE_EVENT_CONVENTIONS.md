# Timeline — Convenções de Eventos (v2)

Este documento define **convenções de contrato** para eventos gravados em `timeline_events`.

- Timeline é **append-only**: nenhum evento é editado ou deletado.
- Correções são modeladas por **supersede** (`supersedes_event_id`).
- Eventos têm **correlação** (`correlation_id`) e podem ter **idempotência** (`idempotency_key`).
- Visibilidade é controlada por `visibility` (`all` | `finance`).

## Objetivos

- Separar claramente eventos **system** (derivados de ações/fluxos do sistema) de eventos **human** (colaboração humana).
- Manter o histórico auditável e reprodutível, sem “reescrever” fatos.

## Campos e semântica

### `event_type`

- Deve ser um identificador estável (string) do evento.
- **Timeline v1**: a taxonomia está congelada e validada por whitelist (ver `app/core/timeline_v1.py`).
- **Timeline v2** (Fase 4+): expande a taxonomia com prefixos:
  - `human.*` — colaboração humana (comentários, correções, anexos, menções)
  - `workflow.*` — requisições e decisões de workflow/aprovação
  - `export.*` — solicitações e artefatos de exportação

### `subject_type` / `subject_id`

Identifica a entidade “assunto” principal do evento (ex.: `rfq:123`, `so:10`).

### `thread_key` (somente em `payload` de eventos `human.*`)

- Chave determinística de thread para agrupar colaboração humana.
- Formato: `${subject_type}:${subject_id}` (ex.: `rfq:123`).
- Deve ser derivada apenas de `subject_type`/`subject_id` para manter estabilidade.

### `occurred_at`

- Timestamp do fato.
- Para eventos `human.*`, é o momento do registro da ação humana.

### `correlation_id`

- Identificador para rastrear uma cadeia de ações.
- Preferencialmente derivado de `X-Request-ID` quando válido; caso contrário, gerado.

### `idempotency_key`

- Opcional.
- Quando presente, deve permitir repetição segura do mesmo evento sem duplicação.
- Regra existente: unicidade por `(event_type, idempotency_key)`.

### `supersedes_event_id`

- Quando presente, indica que este evento **supera/corrige** outro evento anterior.
- O evento original permanece imutável e continua consultável.

### `visibility`

- `all`: visível para todos os perfis com acesso à timeline do assunto.
- `finance`: visível apenas para Financeiro (e Admin quando aplicável), além de oculto na leitura para perfis não-finance.

## Payload e meta

- `payload`: dados específicos do evento.
- `meta`: metadados técnicos (ex.: origem, versão do schema, etc.).

## Exemplos (contratuais)

### System (v1)

- `event_type`: `SO_CREATED`
- `subject_type`: `so`
- `subject_id`: `10`
- `visibility`: `all`
- `payload`: `{ "so_number": "SO-0010" }`

### Human (v2 — Fase 4)

- `event_type`: `human.comment.created`
- `subject_type`: `rfq`
- `subject_id`: `123`
- `visibility`: `finance` (quando aplicável)
- `payload`: `{ "body": "texto...", "thread_key": "rfq:123", "mentions": [], "attachments": [] }`

### Mentioned (v2 — Fase 4)

- `event_type`: `human.mentioned`
- `subject_type`: mesmo do comentário
- `subject_id`: mesmo do comentário
- `payload`: `{ "thread_key": "rfq:123", "mention": "user@test.com", "comment_event_id": 987 }`

### Attachment added (v2 — Fase 4)

- `event_type`: `human.attachment.added`
- **Sem upload binário**: este evento registra apenas **referências/metadados** (ex.: `storage_uri`).
- `subject_type`: entidade do thread (ex.: `rfq`)
- `subject_id`: id da entidade do thread
- `payload`:
  - `thread_key`: `${subject_type}:${subject_id}`
  - `file_id`: identificador lógico do arquivo (client/storage)
  - `file_name`: nome original
  - `mime`: content-type
  - `size`: tamanho em bytes
  - `checksum`: opcional
  - `storage_uri`: URI de leitura/recuperação (S3/local/fs abstrato)

### Correção (supersede)

- `event_type`: `human.comment.corrected`
- `supersedes_event_id`: `<id do comment.created>`
- `subject_type`/`subject_id`: iguais ao evento supersedido
- `visibility`: **herdada** do evento supersedido (sem escalonamento)
- `payload`: `{ "body": "texto corrigido...", "thread_key": "rfq:123", "mentions": [], "attachments": [] }`
