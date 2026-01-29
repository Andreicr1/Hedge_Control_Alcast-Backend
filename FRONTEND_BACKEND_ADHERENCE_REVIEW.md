# Frontend–Backend Adherence Review

**Data:** 2026-01-13  
**Tipo:** Review-only (sem alterações de código)  
**Escopo:** Comparação entre capacidades do frontend vs APIs/comportamentos do backend  
**Repositórios analisados:**
- Backend: Hedge_Control_Alcast-Backend
- Frontend: Hedge_Control_Alcast_Frontend

---

## Sumário Executivo

| Categoria | Status | Criticidade |
|-----------|--------|-------------|
| **Role `auditoria`** | ❌ Não mapeado | **Blocking** |
| **Exports API** | ❌ Não exposto | **Blocking** |
| **ContractStatus enum** | ⚠️ Incompleto | Parcial |
| **Timeline Human Collaboration** | ⚠️ Não consumido | Parcial (de-scoped v1.0) |
| **MTM Snapshots** | ⚠️ Não consumido | Parcial |
| **RFQ Lifecycle** | ✔️ Aderente | — |
| **Dashboard** | ✔️ Aderente | — |
| **Inbox/Exposures** | ✔️ Aderente | — |
| **Contracts** | ✔️ Aderente | — |
| **Counterparties/KYC** | ✔️ Aderente | — |
| **Deals/PnL** | ✔️ Aderente | — |
| **Cashflow** | ✔️ Aderente | — |
| **Settlements** | ✔️ Aderente | — |
| **Market Aluminum** | ✔️ Aderente | — |
| **Sales/Purchase Orders** | ✔️ Aderente | — |
| **Auth** | ✔️ Aderente | — |

---

## Gap Analysis Detalhado

### ❌ BLOCKING: Role `auditoria` não mapeada no frontend

**Backend:** (`backend/app/models/domain.py` linhas 27-33)
```python
class RoleName(PyEnum):
    admin = "admin"
    compras = "compras"
    vendas = "vendas"
    financeiro = "financeiro"
    estoque = "estoque"
    auditoria = "auditoria"  # ← EXISTE NO BACKEND
```

**Frontend:** (`src/types/enums.ts` linhas 240-247)
```typescript
export enum RoleName {
  ADMIN = 'admin',
  COMPRAS = 'compras',
  VENDAS = 'vendas',
  FINANCEIRO = 'financeiro',
  ESTOQUE = 'estoque',
  // AUDITORIA = 'auditoria' ← FALTANDO
}
```

**Evidência adicional:**
- `App.tsx` usa `RequireRole allowed={["financeiro", "auditoria"]}` em várias rotas
- `RequireRole.tsx` faz match case-insensitive: `allowed.map(r => r.toLowerCase()).includes(role)`
- Usuário com role `auditoria` vindo do backend não terá o enum correspondente no TypeScript

**Impacto:** 
- Usuários com role `auditoria` podem ter comportamento imprevisível na UI
- TypeScript não reconhece o valor como válido do enum
- Guards de rota funcionam (string match) mas sem type safety

**Classificação:** ❌ **Blocking**

---

### ❌ BLOCKING: Exports API não exposta no frontend

**Backend APIs disponíveis:** (`backend/app/api/routes/exports.py`)
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/exports` | POST | Criar job de exportação |
| `/exports/{export_id}` | GET | Status do job |
| `/exports/{export_id}/download` | GET | Download de artefato |
| `/exports/manifest` | GET | Manifest determinístico |

**Frontend:**
- `src/api/client.ts` — Sem endpoint `/exports` definido
- `src/services/` — Sem `exports.service.ts`
- `src/hooks/` — Sem `useExports.ts`
- `src/app/pages/` — Sem página de exportação

**Impacto:** Funcionalidade de exportação institucional (audit log, state-at-time, PnL aggregate) não acessível via UI.

**Classificação:** ❌ **Blocking** (para auditoria institucional)

---

### ⚠️ PARCIAL: ContractStatus enum incompleto

**Backend:** (`backend/app/models/domain.py` linhas 164-167)
```python
class ContractStatus(PyEnum):
    active = "active"
    settled = "settled"
    cancelled = "cancelled"  # ← EXISTE NO BACKEND
```

**Frontend:** (`src/types/enums.ts` linhas 213-216)
```typescript
export enum ContractStatus {
  ACTIVE = 'active',
  SETTLED = 'settled',
  // CANCELLED = 'cancelled' ← FALTANDO
}
```

**Impacto:** Contratos cancelados podem causar TypeScript warnings ou erros de runtime.

**Classificação:** ⚠️ Parcial

---

### ⚠️ PARCIAL: Timeline Human Collaboration não consumido

**Backend APIs disponíveis:** (`backend/app/api/routes/timeline.py`)
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/timeline/human/comments` | POST | Criar comentário humano |
| `/timeline/human/comments/corrections` | POST | Corrigir comentário |
| `/timeline/human/attachments` | POST | Adicionar attachment |

**Frontend:** (`src/services/timeline.service.ts`)
- Apenas `GET /timeline` e `GET /timeline/recent` implementados
- Não há UI para criar/corrigir comentários nem adicionar anexos

**Nota:** De-scoped para v1.0 conforme PROJECT_CLOSEOUT.md, mas backend está ready.

**Classificação:** ⚠️ Parcial (esperado)

---

### ⚠️ PARCIAL: MTM Snapshots não consumido

**Backend APIs disponíveis:** (`backend/app/api/routes/mtm_snapshot.py`)
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/mtm/snapshots` | POST | Criar snapshot |
| `/mtm/snapshots` | GET | Listar snapshots |

**Frontend:** (`src/api/client.ts` linha 296)
```typescript
mtm: {
  compute: '/mtm/compute',
  portfolio: '/mtm/portfolio',
  snapshots: '/mtm-snapshot',  // Endpoint definido mas sem serviço
},
```

- Nenhum service implementado para consumir
- Nenhuma UI para visualizar/criar snapshots

**Classificação:** ⚠️ Parcial (Dashboard MTM widget é suficiente para v1.0)

---

## Itens Totalmente Aderentes

### ✔️ RFQ Lifecycle

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| `RfqStatus` enum | 7 estados (draft, pending, sent, quoted, awarded, expired, failed) | 7 estados idênticos | ✔️ |
| Transições de status | Validadas em `rfqs.py` | Respeitadas | ✔️ |
| Award flow | `POST /rfqs/{id}/award` → cria Contracts | `awardQuote()` → exibe contracts | ✔️ |
| KYC Gate | `so_kyc_gate.py` retorna 409 | Error handling com mensagem | ✔️ |
| Quote ranking | Backend calcula rank por spread | Frontend renderiza ranking | ✔️ |
| Contract creation | Automático no award | `AwardedContractInfo` component | ✔️ |
| Preview | `POST /rfqs/preview` | `previewRfq()` service | ✔️ |
| Send attempts | `GET /rfqs/{id}/send-attempts` | `listSendAttempts()` | ✔️ |
| Export CSV | `GET /rfqs/{id}/quotes/export` | `exportQuotesCsv()` | ✔️ |

---

### ✔️ Dashboard

| Widget | Backend Endpoint | Frontend Service | Status |
|--------|-----------------|------------------|--------|
| Summary | `GET /dashboard/summary` | `getDashboardSummary()` | ✔️ |
| MTM | `GET /dashboard/mtm` | Included in summary | ✔️ |
| Settlements | `GET /dashboard/settlements` | Included in summary | ✔️ |
| RFQs | `GET /dashboard/rfqs` | Included in summary | ✔️ |
| Contracts | `GET /dashboard/contracts` | Included in summary | ✔️ |
| Timeline | `GET /dashboard/timeline` | Included in summary | ✔️ |

---

### ✔️ Inbox/Financeiro Workbench

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Counts | `GET /inbox/counts` | `InboxCounts` type | ✔️ |
| Workbench | `GET /inbox/workbench` | `getInboxWorkbench()` | ✔️ |
| Net Exposure | `compute_net_exposure()` | Displayed in table | ✔️ |
| Decisions | `POST /inbox/exposures/{id}/decisions` | `createInboxDecision()` | ✔️ |
| No side-effects | Backend não muta Exposure | Frontend não espera mutação | ✔️ |
| RBAC | Financeiro-only | `RequireRole allowed={["financeiro"]}` | ✔️ |

---

### ✔️ Contracts

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| List | `GET /contracts` | `listContracts()` | ✔️ |
| Detail | `GET /contracts/{id}` | `getContract()` | ✔️ |
| By RFQ | `GET /contracts?rfq_id=X` | `getContractsByRfq()` | ✔️ |
| By Deal | `GET /contracts?deal_id=X` | `getContractsByDeal()` | ✔️ |
| Trade snapshot | `trade_snapshot` JSON | `extractTradeLegs()` helper | ✔️ |

---

### ✔️ Counterparties & KYC

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| CRUD | `/counterparties` endpoints | Full service | ✔️ |
| KYC Preflight | `GET /counterparties/{id}/kyc/preflight` | `getCounterpartyKycPreflight()` | ✔️ |
| UI integration | Response includes `allowed`, `reason_code` | Modal shows blocking message | ✔️ |

---

### ✔️ Deals & PnL

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| List | `GET /deals` | `listDeals()` | ✔️ |
| Detail | `GET /deals/{id}` | `getDeal()` | ✔️ |
| PnL | `GET /deals/{id}/pnl` | `getDealPnl()` | ✔️ |
| PnL Response | `DealPnlResponse` schema | `DealPnlResponse` type | ✔️ |

---

### ✔️ Cashflow

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Endpoint | `GET /cashflow` | `getCashflow()` | ✔️ |
| Query params | `start_date`, `end_date`, `as_of`, `contract_id`, etc. | `CashflowQueryParams` | ✔️ |
| Response | `CashflowResponseRead` | `CashflowResponse` type | ✔️ |
| Page | — | `CashflowPageIntegrated.tsx` | ✔️ |

---

### ✔️ Settlements

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Today | `GET /contracts/settlements/today` | `getSettlementsToday()` | ✔️ |
| Upcoming | `GET /contracts/settlements/upcoming` | `getSettlementsUpcoming()` | ✔️ |
| Response | `SettlementItemRead` | `SettlementItem` type | ✔️ |

---

### ✔️ Market Aluminum

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Quote | `GET /market/aluminum/quote` | `getAluminumQuote()` | ✔️ |
| History | `GET /market/aluminum/history?range=X` | `getAluminumHistory()` | ✔️ |
| Range options | `7d`, `30d`, `1y` | UI buttons for each | ✔️ |

---

### ✔️ Sales Orders

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| CRUD | `/sales-orders` endpoints | Full service | ✔️ |
| Types | `SalesOrderCreate`, `SalesOrderUpdate` | Matching types | ✔️ |

---

### ✔️ Purchase Orders

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| CRUD | `/purchase-orders` endpoints | Full service | ✔️ |
| Types | `PurchaseOrderCreate`, `PurchaseOrderUpdate` | Matching types | ✔️ |

---

### ✔️ Auth

| Aspecto | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Login | `POST /auth/token` (OAuth2) | `login()` with form-urlencoded | ✔️ |
| Me | `GET /auth/me` | `getCurrentUser()` | ✔️ |
| Token storage | — | localStorage + `setAuthToken()` | ✔️ |
| Auto-login dev | — | `autoLoginDev()` for testing | ✔️ |

---

## Backend APIs não consumidas pelo Frontend

| Endpoint | Método | Status Frontend |
|----------|--------|-----------------|
| `/exports` | POST | ❌ Não implementado |
| `/exports/{id}` | GET | ❌ Não implementado |
| `/exports/{id}/download` | GET | ❌ Não implementado |
| `/exports/manifest` | GET | ❌ Não implementado |
| `/timeline/human/comments` | POST | ❌ Não implementado (de-scoped v1.0) |
| `/timeline/human/comments/corrections` | POST | ❌ Não implementado (de-scoped v1.0) |
| `/timeline/human/attachments` | POST | ❌ Não implementado (de-scoped v1.0) |
| `/mtm/snapshots` | POST | ❌ Não implementado |
| `/mtm/snapshots` | GET | ❌ Não implementado |
| `/timeline/events` | POST | ❌ Não implementado (backend-only) |
| `/hedges` | CRUD | ⚠️ Parcial (endpoints definidos, service não exportado) |
| `/users` | CRUD | ⚠️ Parcial |
| `/suppliers` | CRUD | ⚠️ Parcial |
| `/customers` | CRUD | ⚠️ Parcial |

---

## Recomendações de Priorização

### 1. 🔴 Blocking — Deve ser corrigido imediatamente

| Gap | Ação Requerida | Esforço |
|-----|----------------|---------|
| Role `auditoria` faltando | Adicionar `AUDITORIA = 'auditoria'` ao enum `RoleName` em `enums.ts` | 5 min |
| Exports não expostos | Criar `exports.service.ts`, `useExports.ts`, e página de exports | 2-4h |

### 2. 🟡 Parcial — Funcionalidade reduzida mas operável

| Gap | Impacto | Prioridade |
|-----|---------|------------|
| `ContractStatus.CANCELLED` faltando | TypeScript warnings | Média |
| MTM Snapshots UI | Sem visualização histórica de MTM | Baixa |
| Timeline human collaboration | Sem comentários/anexos | Baixa (de-scoped) |

### 3. 🟢 Cosmético — Não afeta operação

| Gap | Nota |
|-----|------|
| Hedges/Users/Suppliers/Customers services | Endpoints definidos, faltam services completos |

---

## Inventário de Arquivos Analisados

### Frontend (Hedge_Control_Alcast_Frontend)

| Caminho | Propósito |
|---------|-----------|
| `src/types/enums.ts` | Enums espelhados do backend |
| `src/types/models.ts` | Interfaces de DTOs |
| `src/types/api.ts` | Tipos de resposta API |
| `src/api/client.ts` | Cliente HTTP + endpoints |
| `src/services/*.ts` | 13 services de API |
| `src/hooks/*.ts` | 10 hooks de estado |
| `src/app/pages/*.tsx` | 19 páginas (mock + integrated) |
| `src/app/components/RequireRole.tsx` | Guard de autorização |
| `src/app/App.tsx` | Roteamento principal |

### Backend (Hedge_Control_Alcast-Backend)

| Caminho | Propósito |
|---------|-----------|
| `backend/app/models/domain.py` | Enums e modelos SQLAlchemy |
| `backend/app/api/routes/*.py` | 38 arquivos de rotas |
| `backend/app/services/*.py` | Services de negócio |
| `backend/app/schemas/*.py` | Schemas Pydantic |

---

## Conclusão

O frontend está **majoritariamente aderente** ao backend para o escopo v1.0 (PROJECT_CLOSEOUT.md).

**Cobertura geral:** ~90% dos endpoints críticos estão consumidos corretamente.

**Gaps blocking (2):**
1. Role `auditoria` — correção trivial (5 min)
2. Exports API — requer implementação de service/hook/page (2-4h)

**Gaps parciais (3):** De-scoped ou cosméticos, não impedem operação.

Os demais gaps são funcionalidades explicitamente **de-scoped para v1.0** (human collaboration, MTM snapshots UI) onde o backend está pronto mas o frontend não expõe ainda.

---

## Referências

- `backend/app/models/domain.py` — Enums e modelos de domínio (fonte da verdade)
- `backend/app/api/routes/` — 38 arquivos de endpoints
- `frontend/src/types/enums.ts` — Enums do frontend (deve espelhar backend)
- `frontend/src/services/` — 13 services de API
- `PROJECT_CLOSEOUT.md` — Escopo v1.0
- `PHASES_4_5_6_CONSOLIDATED_PLAN.md` — Roadmap de features
- `alcast_hedge_control_reference.md` — Documento institucional de referência
