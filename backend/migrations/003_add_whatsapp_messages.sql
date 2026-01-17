-- Tabela de mensagens WhatsApp para trilha auditável
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id SERIAL PRIMARY KEY,
    rfq_id INTEGER REFERENCES rfqs(id),
    counterparty_id INTEGER REFERENCES counterparties(id),
    direction VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    message_id VARCHAR(128),
    phone VARCHAR(32),
    content_text TEXT,
    raw_payload JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_rfq ON whatsapp_messages(rfq_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_message_id ON whatsapp_messages(message_id);
