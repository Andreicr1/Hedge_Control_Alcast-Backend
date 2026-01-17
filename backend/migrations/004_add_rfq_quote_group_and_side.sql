-- Campos para agrupar legs de trades e identificar direção
ALTER TABLE rfq_quotes
    ADD COLUMN IF NOT EXISTS quote_group_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS leg_side VARCHAR(8);

CREATE INDEX IF NOT EXISTS idx_rfq_quotes_group ON rfq_quotes(quote_group_id);
