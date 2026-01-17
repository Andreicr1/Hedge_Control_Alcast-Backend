-- Adições de campos para suportar cadastros internacionais (clientes, fornecedores, contrapartes)
-- Os campos são opcionais e não alteram dados existentes.

ALTER TABLE suppliers
    ADD COLUMN IF NOT EXISTS trade_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS entity_type VARCHAR(64),
    ADD COLUMN IF NOT EXISTS tax_id_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS tax_id_country VARCHAR(32),
    ADD COLUMN IF NOT EXISTS country VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_incorporation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_operation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_residence VARCHAR(64),
    ADD COLUMN IF NOT EXISTS base_currency VARCHAR(8),
    ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(128),
    ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(64),
    ADD COLUMN IF NOT EXISTS sanctions_flag BOOLEAN,
    ADD COLUMN IF NOT EXISTS internal_notes TEXT;

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS trade_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS entity_type VARCHAR(64),
    ADD COLUMN IF NOT EXISTS tax_id_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS tax_id_country VARCHAR(32),
    ADD COLUMN IF NOT EXISTS country VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_incorporation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_operation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_residence VARCHAR(64),
    ADD COLUMN IF NOT EXISTS base_currency VARCHAR(8),
    ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(128),
    ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(64),
    ADD COLUMN IF NOT EXISTS sanctions_flag BOOLEAN,
    ADD COLUMN IF NOT EXISTS internal_notes TEXT;

ALTER TABLE counterparties
    ADD COLUMN IF NOT EXISTS trade_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS legal_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS entity_type VARCHAR(64),
    ADD COLUMN IF NOT EXISTS address_line VARCHAR(255),
    ADD COLUMN IF NOT EXISTS city VARCHAR(128),
    ADD COLUMN IF NOT EXISTS state VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country VARCHAR(64),
    ADD COLUMN IF NOT EXISTS postal_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS country_incorporation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS country_operation VARCHAR(64),
    ADD COLUMN IF NOT EXISTS tax_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS tax_id_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS tax_id_country VARCHAR(32),
    ADD COLUMN IF NOT EXISTS base_currency VARCHAR(8),
    ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(128),
    ADD COLUMN IF NOT EXISTS risk_rating VARCHAR(64),
    ADD COLUMN IF NOT EXISTS sanctions_flag BOOLEAN,
    ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS kyc_notes TEXT,
    ADD COLUMN IF NOT EXISTS internal_notes TEXT;
