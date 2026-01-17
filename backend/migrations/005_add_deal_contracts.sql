-- Deals: adiciona campos de governança e FK em ordens/RFQ
ALTER TABLE deals
    ADD COLUMN IF NOT EXISTS deal_uuid VARCHAR(36) UNIQUE,
    ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(32) DEFAULT 'open',
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id);

UPDATE deals SET deal_uuid = gen_random_uuid() WHERE deal_uuid IS NULL;

ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS deal_id INTEGER REFERENCES deals(id);
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS deal_id INTEGER REFERENCES deals(id);
ALTER TABLE rfqs ADD COLUMN IF NOT EXISTS deal_id INTEGER REFERENCES deals(id);

-- Contracts: 1:1 com trade (snapshot)
CREATE TABLE IF NOT EXISTS contracts (
    contract_id VARCHAR(36) PRIMARY KEY,
    deal_id INTEGER NOT NULL REFERENCES deals(id),
    rfq_id INTEGER NOT NULL REFERENCES rfqs(id),
    counterparty_id INTEGER REFERENCES counterparties(id),
    status VARCHAR(32) DEFAULT 'active',
    trade_index INTEGER,
    quote_group_id VARCHAR(64),
    trade_snapshot JSONB NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_deal ON contracts(deal_id);
CREATE INDEX IF NOT EXISTS idx_contracts_rfq ON contracts(rfq_id);
