# Cashflow Advanced Preview — 6.2.2 Handoff (Frontend)

**Endpoint:** `POST /cashflow/advanced/preview`

**Objetivo (6.2.2):** o payload deve ser **ready-to-render**, com consolidações e metadados **explicitamente materializados** (sem inferência no frontend).

**Fora do escopo:** nenhuma mudança no motor de cálculo do 6.2.1; sem persistência/run/timeline.

---

## Garantias do contrato

- **Separação explícita (sempre presente nos DTOs):**
  - `expected_settlement_*`
  - `pnl_current_unrealized_*`
  - `future_pnl_impact_*`
  - Observação: valores podem ser `null` quando não disponíveis, mas os campos existem.

- **Ordenação estável (render determinístico):**
  - `items`: ordenado por `settlement_date`, `deal_id`, `contract_id`.
  - `projections` (por item): ordenado por `scenario` (base/optimistic/pessimistic) e depois `sensitivity_pct`.
  - `bucket_totals` e `aggregates`: ordenados por `bucket_date`, `currency`, `scenario` (base/optimistic/pessimistic), `sensitivity_pct`.

- **Metadados sem inferência no frontend:**
  - `references`: disponível em nível de `response`, `item`, `bucket_totals`, `aggregates`.
  - `methodologies` e `flags`: disponível em nível de `item`, `bucket_totals`, `aggregates`.

---

## Tipos (TS-ready)

### Request

```ts
export type ScenarioName = "base" | "optimistic" | "pessimistic";
export type BaselineMethod = "explicit_assumption" | "proxy_3m";
export type FxMode = "explicit" | "policy_map";

export interface CashflowAdvancedFilters {
  contract_id?: string;
  deal_id?: number;
  counterparty_id?: number;
  settlement_date_from?: string; // YYYY-MM-DD
  settlement_date_to?: string;   // YYYY-MM-DD
  limit?: number;               // default 200
}

export interface CashflowAdvancedFx {
  mode: FxMode;
  fx_symbol?: string;  // ex: "USDBRL=X"
  fx_source?: string;  // ex: "yahoo"
  policy_key?: string; // ex: "BRL:USDBRL=X@yahoo"
}

export interface CashflowAdvancedReporting {
  reporting_currency?: string; // ex: "BRL" (omitido/"USD" => sem conversão)
  fx?: CashflowAdvancedFx;
}

export interface CashflowAdvancedScenario {
  baseline_method: BaselineMethod;
  aliases_enabled: boolean;      // default true
  sensitivities_pct: number[];   // default [-0.10, -0.05, 0.05, 0.10]
}

export interface CashflowAdvancedAssumptions {
  forward_price_assumption?: number;
  forward_price_currency?: string; // default "USD"
  forward_price_symbol?: string;
  forward_price_as_of?: string;    // YYYY-MM-DD
  notes?: string;
}

export interface CashflowAdvancedPreviewRequest {
  as_of: string; // YYYY-MM-DD
  filters?: CashflowAdvancedFilters;
  reporting?: CashflowAdvancedReporting;
  scenario: CashflowAdvancedScenario;
  assumptions: CashflowAdvancedAssumptions;
}
```

### Response

```ts
export interface CashflowAdvancedReferences {
  cash_last_published_date?: string;      // YYYY-MM-DD
  proxy_3m_last_published_date?: string;  // YYYY-MM-DD

  fx_as_of?: string;   // ISO datetime
  fx_rate?: number;
  fx_symbol?: string;
  fx_source?: string;
}

export interface CashflowAdvancedProjection {
  scenario: ScenarioName;
  sensitivity_pct: number;

  expected_settlement_value_usd: number | null;
  pnl_current_unrealized_usd: number | null;
  future_pnl_impact_usd: number | null;

  expected_settlement_value_reporting: number | null;
  pnl_current_unrealized_reporting: number | null;
  future_pnl_impact_reporting: number | null;

  methodology: string;
  flags: string[];
}

export interface CashflowAdvancedItem {
  contract_id: string;
  deal_id: number;
  rfq_id: number;
  counterparty_id?: number;
  settlement_date?: string; // YYYY-MM-DD

  bucket_date?: string; // YYYY-MM-DD
  native_currency: "USD";

  // Pre-materialized metadata for frontend
  references: CashflowAdvancedReferences;
  methodologies: string[];
  flags: string[];

  projections: CashflowAdvancedProjection[];
}

export interface CashflowAdvancedBucketTotalRow {
  bucket_date: string; // YYYY-MM-DD
  currency: string;    // "USD" or reporting currency when FX resolved

  scenario: ScenarioName;
  sensitivity_pct: number;

  expected_settlement_total: number | null;
  pnl_current_unrealized_total: number | null;
  future_pnl_impact_total: number | null;

  references: CashflowAdvancedReferences;
  methodologies: string[];
  flags: string[];
}

export interface CashflowAdvancedAggregateRow {
  bucket_date: string; // YYYY-MM-DD
  counterparty_id?: number;
  deal_id?: number;
  currency: string;

  scenario: ScenarioName;
  sensitivity_pct: number;

  expected_settlement_total: number | null;
  pnl_current_unrealized_total: number | null;
  future_pnl_impact_total: number | null;

  references: CashflowAdvancedReferences;
  methodologies: string[];
  flags: string[];
}

export interface CashflowAdvancedPreviewResponse {
  inputs_hash: string;
  as_of: string; // YYYY-MM-DD

  assumptions: CashflowAdvancedAssumptions;
  references: CashflowAdvancedReferences;

  items: CashflowAdvancedItem[];

  // Totals per bucket_date (risk view / summary)
  bucket_totals: CashflowAdvancedBucketTotalRow[];

  // Consolidation per bucket_date + counterparty + deal + currency
  aggregates: CashflowAdvancedAggregateRow[];
}
```

---

## Flags (mínimo; extensível)

- `assumptions_missing`: baseline exige premissa e ela não veio.
- `proxy_3m_not_available`: fallback proxy 3M não disponível.
- `projected_not_available`: projeção não pôde ser calculada.
- `pnl_not_available`: não há snapshot P&L para o `as_of`/contrato.
- `fx_not_available`: reporting_currency != USD e FX não resolvido explicitamente.
- `currency_not_supported`: moeda diferente de USD em premissas (MVP USD-only).
- `market_data_missing_days`: janela observada com gaps.

---

## Exemplos

### Exemplo de request (USD-only)

```json
{
  "as_of": "2025-01-10",
  "scenario": {"baseline_method": "explicit_assumption", "aliases_enabled": true, "sensitivities_pct": [-0.1, -0.05, 0.05, 0.1]},
  "assumptions": {"forward_price_assumption": 120.0}
}
```

### Exemplo de request (BRL com FX explícito)

```json
{
  "as_of": "2025-01-10",
  "reporting": {
    "reporting_currency": "BRL",
    "fx": {"mode": "explicit", "fx_symbol": "USDBRL=X", "fx_source": "yahoo"}
  },
  "scenario": {"baseline_method": "explicit_assumption", "aliases_enabled": true, "sensitivities_pct": [-0.1, -0.05, 0.05, 0.1]},
  "assumptions": {"forward_price_assumption": 120.0}
}
```

### Exemplos reais (gerados via script)

Fonte: `backend/scripts/cashflow_advanced_preview_examples.py`.

```text
=== REQUEST (USD-only) ===
{
  "as_of": "2025-01-10",
  "assumptions": {
    "forward_price_assumption": 120.0
  }
}
=== RESPONSE (USD-only) ===
{
  "inputs_hash": "0005023b6a00f0e0156f3f414142b4e188a335814aa0a416b10e7ef413eac11d",
  "as_of": "2025-01-10",
  "assumptions": {
    "forward_price_assumption": 120.0,
    "forward_price_currency": "USD",
    "forward_price_symbol": null,
    "forward_price_as_of": null,
    "notes": null
  },
  "references": {
    "cash_last_published_date": "2025-01-01",
    "proxy_3m_last_published_date": null,
    "fx_as_of": null,
    "fx_rate": null,
    "fx_symbol": null,
    "fx_source": null
  },
  "items": [
    {
      "contract_id": "C-CF-ADV-1",
      "deal_id": 1,
      "rfq_id": 1,
      "counterparty_id": 1,
      "settlement_date": "2025-02-05",
      "bucket_date": "2025-02-05",
      "native_currency": "USD",
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": [],
      "projections": [
        {
          "scenario": "base",
          "sensitivity_pct": -0.1,
          "expected_settlement_value_usd": 80.64516129032256,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 30.645161290322562,
          "expected_settlement_value_reporting": null,
          "pnl_current_unrealized_reporting": null,
          "future_pnl_impact_reporting": null,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "base",
          "sensitivity_pct": 0.0,
          "expected_settlement_value_usd": 196.77419354838705,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 146.77419354838705,
          "expected_settlement_value_reporting": null,
          "pnl_current_unrealized_reporting": null,
          "future_pnl_impact_reporting": null,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "base",
          "sensitivity_pct": 0.1,
          "expected_settlement_value_usd": 312.90322580645153,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 262.90322580645153,
          "expected_settlement_value_reporting": null,
          "pnl_current_unrealized_reporting": null,
          "future_pnl_impact_reporting": null,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "optimistic",
          "sensitivity_pct": 0.05,
          "expected_settlement_value_usd": 254.83870967741936,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 204.83870967741936,
          "expected_settlement_value_reporting": null,
          "pnl_current_unrealized_reporting": null,
          "future_pnl_impact_reporting": null,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "pessimistic",
          "sensitivity_pct": -0.05,
          "expected_settlement_value_usd": 138.70967741935488,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 88.70967741935488,
          "expected_settlement_value_reporting": null,
          "pnl_current_unrealized_reporting": null,
          "future_pnl_impact_reporting": null,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        }
      ]
    }
  ],
  "bucket_totals": [
    {
      "bucket_date": "2025-02-05",
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": -0.1,
      "expected_settlement_total": 80.64516129032256,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 30.645161290322562,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": 0.0,
      "expected_settlement_total": 196.77419354838705,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 146.77419354838705,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": 0.1,
      "expected_settlement_total": 312.90322580645153,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 262.90322580645153,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "USD",
      "scenario": "optimistic",
      "sensitivity_pct": 0.05,
      "expected_settlement_total": 254.83870967741936,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 204.83870967741936,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "USD",
      "scenario": "pessimistic",
      "sensitivity_pct": -0.05,
      "expected_settlement_total": 138.70967741935488,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 88.70967741935488,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    }
  ],
  "aggregates": [
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": -0.1,
      "expected_settlement_total": 80.64516129032256,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 30.645161290322562,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": 0.0,
      "expected_settlement_total": 196.77419354838705,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 146.77419354838705,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "USD",
      "scenario": "base",
      "sensitivity_pct": 0.1,
      "expected_settlement_total": 312.90322580645153,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 262.90322580645153,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "USD",
      "scenario": "optimistic",
      "sensitivity_pct": 0.05,
      "expected_settlement_total": 254.83870967741936,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 204.83870967741936,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "USD",
      "scenario": "pessimistic",
      "sensitivity_pct": -0.05,
      "expected_settlement_total": 138.70967741935488,
      "pnl_current_unrealized_total": 50.0,
      "future_pnl_impact_total": 88.70967741935488,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": null,
        "fx_rate": null,
        "fx_symbol": null,
        "fx_source": null
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    }
  ]
}
=== REQUEST (BRL + explicit FX) ===
{
  "as_of": "2025-01-10",
  "reporting": {
    "reporting_currency": "BRL",
    "fx": {
      "mode": "explicit",
      "fx_symbol": "USDBRL=X",
      "fx_source": "yahoo"
    }
  },
  "assumptions": {
    "forward_price_assumption": 120.0
  }
}
=== RESPONSE (BRL + explicit FX) ===
{
  "inputs_hash": "9f9e7a60b2bfb2e1ee434ad2321d3beed00fa41e46de68ebf1ee38809e46d709",
  "as_of": "2025-01-10",
  "assumptions": {
    "forward_price_assumption": 120.0,
    "forward_price_currency": "USD",
    "forward_price_symbol": null,
    "forward_price_as_of": null,
    "notes": null
  },
  "references": {
    "cash_last_published_date": "2025-01-01",
    "proxy_3m_last_published_date": null,
    "fx_as_of": "2025-01-09T00:00:00",
    "fx_rate": 5.0,
    "fx_symbol": "USDBRL=X",
    "fx_source": "yahoo"
  },
  "items": [
    {
      "contract_id": "C-CF-ADV-1",
      "deal_id": 1,
      "rfq_id": 1,
      "counterparty_id": 1,
      "settlement_date": "2025-02-05",
      "bucket_date": "2025-02-05",
      "native_currency": "USD",
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": [],
      "projections": [
        {
          "scenario": "base",
          "sensitivity_pct": -0.1,
          "expected_settlement_value_usd": 80.64516129032256,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 30.645161290322562,
          "expected_settlement_value_reporting": 403.2258064516128,
          "pnl_current_unrealized_reporting": 250.0,
          "future_pnl_impact_reporting": 153.2258064516128,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "base",
          "sensitivity_pct": 0.0,
          "expected_settlement_value_usd": 196.77419354838705,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 146.77419354838705,
          "expected_settlement_value_reporting": 983.8709677419353,
          "pnl_current_unrealized_reporting": 250.0,
          "future_pnl_impact_reporting": 733.8709677419353,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "base",
          "sensitivity_pct": 0.1,
          "expected_settlement_value_usd": 312.90322580645153,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 262.90322580645153,
          "expected_settlement_value_reporting": 1564.5161290322576,
          "pnl_current_unrealized_reporting": 250.0,
          "future_pnl_impact_reporting": 1314.5161290322576,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "optimistic",
          "sensitivity_pct": 0.05,
          "expected_settlement_value_usd": 254.83870967741936,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 204.83870967741936,
          "expected_settlement_value_reporting": 1274.1935483870968,
          "pnl_current_unrealized_reporting": 250.0,
          "future_pnl_impact_reporting": 1024.1935483870968,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        },
        {
          "scenario": "pessimistic",
          "sensitivity_pct": -0.05,
          "expected_settlement_value_usd": 138.70967741935488,
          "pnl_current_unrealized_usd": 50.0,
          "future_pnl_impact_usd": 88.70967741935488,
          "expected_settlement_value_reporting": 693.5483870967744,
          "pnl_current_unrealized_reporting": 250.0,
          "future_pnl_impact_reporting": 443.5483870967744,
          "methodology": "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT",
          "flags": []
        }
      ]
    }
  ],
  "bucket_totals": [
    {
      "bucket_date": "2025-02-05",
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": -0.1,
      "expected_settlement_total": 403.2258064516128,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 153.2258064516128,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": 0.0,
      "expected_settlement_total": 983.8709677419353,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 733.8709677419353,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": 0.1,
      "expected_settlement_total": 1564.5161290322576,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 1314.5161290322576,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "BRL",
      "scenario": "optimistic",
      "sensitivity_pct": 0.05,
      "expected_settlement_total": 1274.1935483870968,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 1024.1935483870968,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "currency": "BRL",
      "scenario": "pessimistic",
      "sensitivity_pct": -0.05,
      "expected_settlement_total": 693.5483870967744,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 443.5483870967744,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    }
  ],
  "aggregates": [
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": -0.1,
      "expected_settlement_total": 403.2258064516128,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 153.2258064516128,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": 0.0,
      "expected_settlement_total": 983.8709677419353,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 733.8709677419353,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "BRL",
      "scenario": "base",
      "sensitivity_pct": 0.1,
      "expected_settlement_total": 1564.5161290322576,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 1314.5161290322576,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "BRL",
      "scenario": "optimistic",
      "sensitivity_pct": 0.05,
      "expected_settlement_total": 1274.1935483870968,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 1024.1935483870968,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    },
    {
      "bucket_date": "2025-02-05",
      "counterparty_id": 1,
      "deal_id": 1,
      "currency": "BRL",
      "scenario": "pessimistic",
      "sensitivity_pct": -0.05,
      "expected_settlement_total": 693.5483870967744,
      "pnl_current_unrealized_total": 250.0,
      "future_pnl_impact_total": 443.5483870967744,
      "references": {
        "cash_last_published_date": "2025-01-01",
        "proxy_3m_last_published_date": null,
        "fx_as_of": "2025-01-09T00:00:00",
        "fx_rate": 5.0,
        "fx_symbol": "USDBRL=X",
        "fx_source": "yahoo"
      },
      "methodologies": [
        "contract.avg.expected_final_avg|baseline.explicit_assumption|driver=ALUMINUM_CASH_SETTLEMENT"
      ],
      "flags": []
    }
  ]
}
```

---

## Renderização (sem lógica)

- **Tabela por cenário/sensitividade:** renderizar `item.projections` diretamente.
- **Visão consolidada (risk view):** renderizar `bucket_totals` e/ou `aggregates` conforme o agrupamento desejado.
- **Destaque do future_pnl_impact:** usar `future_pnl_impact_*` (por projeção/linha agregada), sem recalcular nada.
