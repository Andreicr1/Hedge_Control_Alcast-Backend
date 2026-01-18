


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE TYPE "public"."documentownertype" AS ENUM (
    'customer',
    'supplier',
    'counterparty'
);


ALTER TYPE "public"."documentownertype" OWNER TO "postgres";


CREATE TYPE "public"."exposurestatus" AS ENUM (
    'open',
    'hedged',
    'closed'
);


ALTER TYPE "public"."exposurestatus" OWNER TO "postgres";


CREATE TYPE "public"."exposuretype" AS ENUM (
    'active',
    'passive'
);


ALTER TYPE "public"."exposuretype" OWNER TO "postgres";


CREATE TYPE "public"."hedgeside" AS ENUM (
    'buy',
    'sell'
);


ALTER TYPE "public"."hedgeside" OWNER TO "postgres";


CREATE TYPE "public"."hedgetaskstatus" AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'cancelled'
);


ALTER TYPE "public"."hedgetaskstatus" OWNER TO "postgres";


CREATE TYPE "public"."hedgetype" AS ENUM (
    'purchase',
    'sale'
);


ALTER TYPE "public"."hedgetype" OWNER TO "postgres";


CREATE TYPE "public"."marketobjecttype" AS ENUM (
    'hedge',
    'po',
    'so',
    'portfolio',
    'exposure',
    'net'
);


ALTER TYPE "public"."marketobjecttype" OWNER TO "postgres";


CREATE TYPE "public"."rfqtype" AS ENUM (
    'hedge_buy',
    'hedge_sell'
);


ALTER TYPE "public"."rfqtype" OWNER TO "postgres";


CREATE TYPE "public"."sendstatus" AS ENUM (
    'queued',
    'sent',
    'delivered',
    'read',
    'failed'
);


ALTER TYPE "public"."sendstatus" OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."alembic_version" (
    "version_num" character varying(128) NOT NULL
);


ALTER TABLE "public"."alembic_version" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."audit_logs" (
    "id" integer NOT NULL,
    "action" character varying(128) NOT NULL,
    "user_id" integer,
    "rfq_id" integer,
    "payload_json" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "request_id" character varying(64),
    "ip" character varying(64),
    "user_agent" character varying(256),
    "idempotency_key" character varying(128)
);


ALTER TABLE "public"."audit_logs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."audit_logs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."audit_logs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."audit_logs_id_seq" OWNED BY "public"."audit_logs"."id";



CREATE TABLE IF NOT EXISTS "public"."cashflow_baseline_items" (
    "id" integer NOT NULL,
    "run_id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "contract_id" character varying(36) NOT NULL,
    "deal_id" integer NOT NULL,
    "rfq_id" integer NOT NULL,
    "counterparty_id" integer,
    "settlement_date" "date",
    "currency" character varying(8) NOT NULL,
    "projected_value_usd" double precision,
    "projected_methodology" character varying(128),
    "projected_as_of" "date",
    "final_value_usd" double precision,
    "final_methodology" character varying(128),
    "observation_start" "date",
    "observation_end_used" "date",
    "last_published_cash_date" "date",
    "data_quality_flags" json,
    "references" json,
    "inputs_hash" character varying(64) NOT NULL,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."cashflow_baseline_items" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cashflow_baseline_items_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cashflow_baseline_items_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cashflow_baseline_items_id_seq" OWNED BY "public"."cashflow_baseline_items"."id";



CREATE TABLE IF NOT EXISTS "public"."cashflow_baseline_runs" (
    "id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "scope_filters" json,
    "inputs_hash" character varying(64) NOT NULL,
    "requested_by_user_id" integer,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."cashflow_baseline_runs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."cashflow_baseline_runs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."cashflow_baseline_runs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."cashflow_baseline_runs_id_seq" OWNED BY "public"."cashflow_baseline_runs"."id";



CREATE TABLE IF NOT EXISTS "public"."contract_exposures" (
    "id" integer NOT NULL,
    "contract_id" character varying(36) NOT NULL,
    "exposure_id" integer NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE "public"."contract_exposures" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."contract_exposures_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."contract_exposures_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."contract_exposures_id_seq" OWNED BY "public"."contract_exposures"."id";



CREATE TABLE IF NOT EXISTS "public"."contracts" (
    "contract_id" character varying(36) NOT NULL,
    "deal_id" integer NOT NULL,
    "rfq_id" integer NOT NULL,
    "counterparty_id" integer,
    "status" character varying(32) DEFAULT 'active'::character varying NOT NULL,
    "trade_index" integer,
    "quote_group_id" character varying(64),
    "trade_snapshot" json NOT NULL,
    "settlement_date" "date",
    "settlement_meta" json,
    "created_by" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "contract_number" character varying(50)
);


ALTER TABLE "public"."contracts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."counterparties" (
    "id" integer NOT NULL,
    "name" character varying(255) NOT NULL,
    "type" character varying(32) NOT NULL,
    "contact_name" character varying(255),
    "contact_email" character varying(255),
    "contact_phone" character varying(64),
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "rfq_channel_type" character varying(32) DEFAULT 'BROKER_LME'::character varying,
    "code" character varying(64),
    "address_line" character varying(255),
    "city" character varying(128),
    "state" character varying(64),
    "country" character varying(64),
    "postal_code" character varying(32),
    "tax_id" character varying(32),
    "tax_id_type" character varying(32),
    "risk_rating" character varying(64),
    "credit_limit" double precision,
    "credit_score" integer,
    "kyc_status" character varying(32),
    "kyc_notes" "text",
    "payment_terms" character varying(128),
    "base_currency" character varying(8),
    "notes" "text",
    "trade_name" character varying(255),
    "legal_name" character varying(255),
    "entity_type" character varying(64),
    "country_incorporation" character varying(64),
    "country_operation" character varying(64),
    "tax_id_country" character varying(32),
    "sanctions_flag" boolean,
    "internal_notes" "text"
);


ALTER TABLE "public"."counterparties" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."counterparties_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."counterparties_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."counterparties_id_seq" OWNED BY "public"."counterparties"."id";



CREATE TABLE IF NOT EXISTS "public"."credit_checks" (
    "id" integer NOT NULL,
    "owner_type" "public"."documentownertype" NOT NULL,
    "owner_id" integer NOT NULL,
    "bureau" character varying(128),
    "score" integer,
    "status" character varying(64),
    "raw_response" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."credit_checks" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."credit_checks_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."credit_checks_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."credit_checks_id_seq" OWNED BY "public"."credit_checks"."id";



CREATE TABLE IF NOT EXISTS "public"."customers" (
    "id" integer NOT NULL,
    "name" character varying(255) NOT NULL,
    "code" character varying(32),
    "contact_email" character varying(255),
    "contact_phone" character varying(64),
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "legal_name" character varying(255),
    "tax_id" character varying(32),
    "state_registration" character varying(64),
    "address_line" character varying(255),
    "city" character varying(128),
    "state" character varying(8),
    "postal_code" character varying(32),
    "credit_limit" double precision,
    "credit_score" integer,
    "kyc_status" character varying(32),
    "kyc_notes" "text",
    "trade_name" character varying(255),
    "entity_type" character varying(64),
    "tax_id_type" character varying(32),
    "tax_id_country" character varying(32),
    "country" character varying(64),
    "country_incorporation" character varying(64),
    "country_operation" character varying(64),
    "country_residence" character varying(64),
    "base_currency" character varying(8),
    "payment_terms" character varying(128),
    "risk_rating" character varying(64),
    "sanctions_flag" boolean,
    "internal_notes" "text"
);


ALTER TABLE "public"."customers" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."customers_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."customers_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."customers_id_seq" OWNED BY "public"."customers"."id";



CREATE TABLE IF NOT EXISTS "public"."deal_links" (
    "id" integer NOT NULL,
    "deal_id" integer NOT NULL,
    "entity_type" character varying(32) NOT NULL,
    "entity_id" integer NOT NULL,
    "direction" character varying(16) NOT NULL,
    "quantity_mt" double precision,
    "allocation_type" character varying(16) DEFAULT 'auto'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."deal_links" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."deal_links_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."deal_links_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."deal_links_id_seq" OWNED BY "public"."deal_links"."id";



CREATE TABLE IF NOT EXISTS "public"."deal_pnl_snapshots" (
    "id" integer NOT NULL,
    "deal_id" integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"() NOT NULL,
    "physical_revenue" double precision DEFAULT '0'::double precision NOT NULL,
    "physical_cost" double precision DEFAULT '0'::double precision NOT NULL,
    "hedge_pnl_realized" double precision DEFAULT '0'::double precision NOT NULL,
    "hedge_pnl_mtm" double precision DEFAULT '0'::double precision NOT NULL,
    "net_pnl" double precision DEFAULT '0'::double precision NOT NULL
);


ALTER TABLE "public"."deal_pnl_snapshots" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."deal_pnl_snapshots_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."deal_pnl_snapshots_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."deal_pnl_snapshots_id_seq" OWNED BY "public"."deal_pnl_snapshots"."id";



CREATE TABLE IF NOT EXISTS "public"."deals" (
    "id" integer NOT NULL,
    "deal_uuid" character varying(36) NOT NULL,
    "commodity" character varying(255),
    "currency" character varying(8) DEFAULT 'USD'::character varying NOT NULL,
    "status" character varying(32) DEFAULT 'open'::character varying NOT NULL,
    "lifecycle_status" character varying(32) DEFAULT 'open'::character varying NOT NULL,
    "created_by" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "reference_name" character varying(255)
);


ALTER TABLE "public"."deals" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."deals_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."deals_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."deals_id_seq" OWNED BY "public"."deals"."id";



CREATE TABLE IF NOT EXISTS "public"."document_monthly_sequences" (
    "id" integer NOT NULL,
    "doc_type" character varying(16) NOT NULL,
    "year_month" character varying(6) NOT NULL,
    "last_seq" integer DEFAULT 0 NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."document_monthly_sequences" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."document_monthly_sequences_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."document_monthly_sequences_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."document_monthly_sequences_id_seq" OWNED BY "public"."document_monthly_sequences"."id";



CREATE TABLE IF NOT EXISTS "public"."export_jobs" (
    "id" integer NOT NULL,
    "export_id" character varying(40) NOT NULL,
    "inputs_hash" character varying(64) NOT NULL,
    "export_type" character varying(64) NOT NULL,
    "as_of" timestamp with time zone,
    "filters" json,
    "status" character varying(32) DEFAULT 'queued'::character varying NOT NULL,
    "requested_by_user_id" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "artifacts" json
);


ALTER TABLE "public"."export_jobs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."export_jobs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."export_jobs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."export_jobs_id_seq" OWNED BY "public"."export_jobs"."id";



CREATE TABLE IF NOT EXISTS "public"."exposures" (
    "id" integer NOT NULL,
    "source_type" "public"."marketobjecttype" NOT NULL,
    "source_id" integer NOT NULL,
    "exposure_type" "public"."exposuretype" NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "product" character varying(255),
    "payment_date" "date",
    "delivery_date" "date",
    "sale_date" "date",
    "status" "public"."exposurestatus" DEFAULT 'open'::"public"."exposurestatus" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."exposures" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."exposures_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."exposures_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."exposures_id_seq" OWNED BY "public"."exposures"."id";



CREATE TABLE IF NOT EXISTS "public"."finance_pipeline_runs" (
    "id" integer NOT NULL,
    "pipeline_version" character varying(128) NOT NULL,
    "as_of_date" "date" NOT NULL,
    "scope_filters" json,
    "mode" character varying(16) DEFAULT 'materialize'::character varying NOT NULL,
    "emit_exports" boolean DEFAULT true NOT NULL,
    "inputs_hash" character varying(64) NOT NULL,
    "status" character varying(32) DEFAULT 'queued'::character varying NOT NULL,
    "requested_by_user_id" integer,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "error_code" character varying(64),
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."finance_pipeline_runs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."finance_pipeline_runs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."finance_pipeline_runs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."finance_pipeline_runs_id_seq" OWNED BY "public"."finance_pipeline_runs"."id";



CREATE TABLE IF NOT EXISTS "public"."finance_pipeline_steps" (
    "id" integer NOT NULL,
    "run_id" integer NOT NULL,
    "step_name" character varying(64) NOT NULL,
    "status" character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "error_code" character varying(64),
    "error_message" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "artifacts" json
);


ALTER TABLE "public"."finance_pipeline_steps" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."finance_pipeline_steps_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."finance_pipeline_steps_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."finance_pipeline_steps_id_seq" OWNED BY "public"."finance_pipeline_steps"."id";



CREATE TABLE IF NOT EXISTS "public"."finance_risk_flag_runs" (
    "id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "scope_filters" json,
    "inputs_hash" character varying(64) NOT NULL,
    "requested_by_user_id" integer,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."finance_risk_flag_runs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."finance_risk_flag_runs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."finance_risk_flag_runs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."finance_risk_flag_runs_id_seq" OWNED BY "public"."finance_risk_flag_runs"."id";



CREATE TABLE IF NOT EXISTS "public"."finance_risk_flags" (
    "id" integer NOT NULL,
    "run_id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "subject_type" character varying(32) NOT NULL,
    "subject_id" character varying(64) NOT NULL,
    "deal_id" integer,
    "contract_id" character varying(36),
    "flag_code" character varying(64) NOT NULL,
    "severity" character varying(16),
    "message" character varying(256),
    "references" json,
    "inputs_hash" character varying(64) NOT NULL,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."finance_risk_flags" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."finance_risk_flags_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."finance_risk_flags_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."finance_risk_flags_id_seq" OWNED BY "public"."finance_risk_flags"."id";



CREATE TABLE IF NOT EXISTS "public"."fx_policy_map" (
    "id" integer NOT NULL,
    "policy_key" character varying(128) NOT NULL,
    "reporting_currency" character varying(8) NOT NULL,
    "fx_symbol" character varying(64) NOT NULL,
    "fx_source" character varying(64) NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    "notes" "text",
    "created_by_user_id" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."fx_policy_map" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."fx_policy_map_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."fx_policy_map_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."fx_policy_map_id_seq" OWNED BY "public"."fx_policy_map"."id";



CREATE TABLE IF NOT EXISTS "public"."hedge_exposures" (
    "id" integer NOT NULL,
    "hedge_id" integer NOT NULL,
    "exposure_id" integer NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."hedge_exposures" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hedge_exposures_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hedge_exposures_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hedge_exposures_id_seq" OWNED BY "public"."hedge_exposures"."id";



CREATE TABLE IF NOT EXISTS "public"."hedge_tasks" (
    "id" integer NOT NULL,
    "exposure_id" integer NOT NULL,
    "status" "public"."hedgetaskstatus" DEFAULT 'pending'::"public"."hedgetaskstatus" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."hedge_tasks" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hedge_tasks_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hedge_tasks_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hedge_tasks_id_seq" OWNED BY "public"."hedge_tasks"."id";



CREATE TABLE IF NOT EXISTS "public"."hedge_trades" (
    "id" integer NOT NULL,
    "hedge_type" "public"."hedgetype" NOT NULL,
    "side" "public"."hedgeside" NOT NULL,
    "lme_contract" character varying(32) NOT NULL,
    "contract_month" character varying(16) NOT NULL,
    "expiry_date" "date",
    "lots" integer NOT NULL,
    "lot_size_tons" double precision DEFAULT 25.0,
    "price" double precision NOT NULL,
    "currency" character varying(8) DEFAULT 'USD'::character varying,
    "notional_tons" double precision NOT NULL,
    "purchase_order_id" integer,
    "sales_order_id" integer,
    "rfq_id" integer,
    "executed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."hedge_trades" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hedge_trades_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hedge_trades_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hedge_trades_id_seq" OWNED BY "public"."hedge_trades"."id";



CREATE TABLE IF NOT EXISTS "public"."hedges" (
    "id" integer NOT NULL,
    "so_id" integer,
    "counterparty_id" integer NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "contract_price" double precision NOT NULL,
    "current_market_price" double precision,
    "mtm_value" double precision,
    "period" character varying(20) NOT NULL,
    "status" character varying(32) DEFAULT 'active'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "instrument" character varying(128),
    "maturity_date" "date",
    "reference_code" character varying(128)
);


ALTER TABLE "public"."hedges" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hedges_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hedges_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hedges_id_seq" OWNED BY "public"."hedges"."id";



CREATE TABLE IF NOT EXISTS "public"."kyc_checks" (
    "id" integer NOT NULL,
    "owner_type" "public"."documentownertype" NOT NULL,
    "owner_id" integer NOT NULL,
    "check_type" character varying(32) NOT NULL,
    "status" character varying(32) NOT NULL,
    "score" integer,
    "details_json" json,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "expires_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."kyc_checks" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."kyc_checks_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."kyc_checks_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."kyc_checks_id_seq" OWNED BY "public"."kyc_checks"."id";



CREATE TABLE IF NOT EXISTS "public"."kyc_documents" (
    "id" integer NOT NULL,
    "owner_type" "public"."documentownertype" NOT NULL,
    "owner_id" integer NOT NULL,
    "filename" character varying(255) NOT NULL,
    "content_type" character varying(128),
    "path" character varying(500) NOT NULL,
    "uploaded_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "metadata_json" json
);


ALTER TABLE "public"."kyc_documents" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."kyc_documents_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."kyc_documents_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."kyc_documents_id_seq" OWNED BY "public"."kyc_documents"."id";



CREATE TABLE IF NOT EXISTS "public"."market_prices" (
    "id" integer NOT NULL,
    "source" character varying(64) NOT NULL,
    "symbol" character varying(64) NOT NULL,
    "contract_month" character varying(16),
    "price" double precision NOT NULL,
    "currency" character varying(8) DEFAULT 'USD'::character varying,
    "as_of" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "fx" boolean DEFAULT false
);


ALTER TABLE "public"."market_prices" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."market_prices_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."market_prices_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."market_prices_id_seq" OWNED BY "public"."market_prices"."id";



CREATE TABLE IF NOT EXISTS "public"."mtm_contract_snapshot_runs" (
    "id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "scope_filters" json,
    "inputs_hash" character varying(64) NOT NULL,
    "requested_by_user_id" integer,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."mtm_contract_snapshot_runs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."mtm_contract_snapshot_runs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."mtm_contract_snapshot_runs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."mtm_contract_snapshot_runs_id_seq" OWNED BY "public"."mtm_contract_snapshot_runs"."id";



CREATE TABLE IF NOT EXISTS "public"."mtm_contract_snapshots" (
    "id" integer NOT NULL,
    "run_id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "contract_id" character varying(36) NOT NULL,
    "deal_id" integer NOT NULL,
    "currency" character varying(8) NOT NULL,
    "mtm_usd" double precision NOT NULL,
    "methodology" character varying(128),
    "references" json,
    "inputs_hash" character varying(64) NOT NULL,
    "created_at" timestamp with time zone NOT NULL
);


ALTER TABLE "public"."mtm_contract_snapshots" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."mtm_contract_snapshots_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."mtm_contract_snapshots_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."mtm_contract_snapshots_id_seq" OWNED BY "public"."mtm_contract_snapshots"."id";



CREATE TABLE IF NOT EXISTS "public"."mtm_records" (
    "id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "object_type" "public"."marketobjecttype" NOT NULL,
    "object_id" integer,
    "forward_price" double precision,
    "fx_rate" double precision,
    "mtm_value" double precision NOT NULL,
    "methodology" character varying(255),
    "computed_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."mtm_records" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."mtm_records_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."mtm_records_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."mtm_records_id_seq" OWNED BY "public"."mtm_records"."id";



CREATE TABLE IF NOT EXISTS "public"."mtm_snapshots" (
    "id" integer NOT NULL,
    "object_type" "public"."marketobjecttype" NOT NULL,
    "object_id" integer,
    "product" character varying(255),
    "period" character varying(32),
    "price" double precision NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "mtm_value" double precision NOT NULL,
    "as_of_date" "date" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."mtm_snapshots" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."mtm_snapshots_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."mtm_snapshots_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."mtm_snapshots_id_seq" OWNED BY "public"."mtm_snapshots"."id";



CREATE TABLE IF NOT EXISTS "public"."pnl_contract_realized" (
    "id" integer NOT NULL,
    "contract_id" character varying(36) NOT NULL,
    "settlement_date" "date" NOT NULL,
    "deal_id" integer NOT NULL,
    "currency" character varying(8) DEFAULT 'USD'::character varying NOT NULL,
    "realized_pnl_usd" double precision NOT NULL,
    "methodology" character varying(128),
    "inputs_hash" character varying(64) NOT NULL,
    "locked_at" timestamp with time zone,
    "source_hint" json,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."pnl_contract_realized" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."pnl_contract_realized_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."pnl_contract_realized_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."pnl_contract_realized_id_seq" OWNED BY "public"."pnl_contract_realized"."id";



CREATE TABLE IF NOT EXISTS "public"."pnl_contract_snapshots" (
    "id" integer NOT NULL,
    "run_id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "contract_id" character varying(36) NOT NULL,
    "deal_id" integer NOT NULL,
    "currency" character varying(8) DEFAULT 'USD'::character varying NOT NULL,
    "unrealized_pnl_usd" double precision NOT NULL,
    "methodology" character varying(128),
    "data_quality_flags" json,
    "inputs_hash" character varying(64) NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."pnl_contract_snapshots" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."pnl_contract_snapshots_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."pnl_contract_snapshots_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."pnl_contract_snapshots_id_seq" OWNED BY "public"."pnl_contract_snapshots"."id";



CREATE TABLE IF NOT EXISTS "public"."pnl_snapshot_runs" (
    "id" integer NOT NULL,
    "as_of_date" "date" NOT NULL,
    "scope_filters" json,
    "inputs_hash" character varying(64) NOT NULL,
    "requested_by_user_id" integer,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."pnl_snapshot_runs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."pnl_snapshot_runs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."pnl_snapshot_runs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."pnl_snapshot_runs_id_seq" OWNED BY "public"."pnl_snapshot_runs"."id";



CREATE TABLE IF NOT EXISTS "public"."purchase_orders" (
    "id" integer NOT NULL,
    "po_number" character varying(50) NOT NULL,
    "supplier_id" integer NOT NULL,
    "total_quantity_mt" double precision NOT NULL,
    "pricing_type" character varying(32) DEFAULT 'monthly_average'::character varying NOT NULL,
    "lme_premium" double precision DEFAULT '0'::double precision,
    "status" character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "product" character varying(255),
    "unit" character varying(16),
    "unit_price" double precision,
    "pricing_period" character varying(32),
    "premium" double precision,
    "reference_price" character varying(64),
    "fixing_deadline" "date",
    "expected_delivery_date" "date",
    "location" character varying(128),
    "avg_cost" double precision,
    "deal_id" integer NOT NULL
);


ALTER TABLE "public"."purchase_orders" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."purchase_orders_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."purchase_orders_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."purchase_orders_id_seq" OWNED BY "public"."purchase_orders"."id";



CREATE TABLE IF NOT EXISTS "public"."rfq_invitations" (
    "id" integer NOT NULL,
    "rfq_id" integer NOT NULL,
    "counterparty_id" integer NOT NULL,
    "counterparty_name" character varying(255),
    "status" character varying(32) DEFAULT 'sent'::character varying NOT NULL,
    "sent_at" timestamp with time zone DEFAULT "now"(),
    "responded_at" timestamp with time zone,
    "expires_at" timestamp with time zone,
    "message_text" "text"
);


ALTER TABLE "public"."rfq_invitations" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."rfq_invitations_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."rfq_invitations_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."rfq_invitations_id_seq" OWNED BY "public"."rfq_invitations"."id";



CREATE TABLE IF NOT EXISTS "public"."rfq_quotes" (
    "id" integer NOT NULL,
    "rfq_id" integer NOT NULL,
    "counterparty_id" integer,
    "counterparty_name" character varying(255),
    "quote_price" double precision NOT NULL,
    "status" character varying(32) DEFAULT 'quoted'::character varying NOT NULL,
    "quoted_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "price_type" character varying(128),
    "volume_mt" double precision,
    "valid_until" timestamp with time zone,
    "notes" "text",
    "channel" character varying(64)
);


ALTER TABLE "public"."rfq_quotes" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."rfq_quotes_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."rfq_quotes_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."rfq_quotes_id_seq" OWNED BY "public"."rfq_quotes"."id";



CREATE TABLE IF NOT EXISTS "public"."rfq_send_attempts" (
    "id" integer NOT NULL,
    "rfq_id" integer NOT NULL,
    "channel" character varying(32) NOT NULL,
    "status" "public"."sendstatus" DEFAULT 'queued'::"public"."sendstatus" NOT NULL,
    "provider_message_id" character varying(128),
    "error" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "metadata_json" "text",
    "idempotency_key" character varying(128),
    "retry_of_attempt_id" integer
);


ALTER TABLE "public"."rfq_send_attempts" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."rfq_send_attempts_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."rfq_send_attempts_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."rfq_send_attempts_id_seq" OWNED BY "public"."rfq_send_attempts"."id";



CREATE TABLE IF NOT EXISTS "public"."rfqs" (
    "id" integer NOT NULL,
    "rfq_number" character varying(50) NOT NULL,
    "so_id" integer NOT NULL,
    "quantity_mt" double precision NOT NULL,
    "period" character varying(20) NOT NULL,
    "status" character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "winner_quote_id" integer,
    "decision_reason" "text",
    "decided_by" integer,
    "decided_at" timestamp with time zone,
    "winner_rank" integer,
    "hedge_id" integer,
    "hedge_reference" character varying(128),
    "trade_specs" json,
    "deal_id" integer NOT NULL,
    "message_text" "text"
);


ALTER TABLE "public"."rfqs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."rfqs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."rfqs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."rfqs_id_seq" OWNED BY "public"."rfqs"."id";



CREATE TABLE IF NOT EXISTS "public"."roles" (
    "id" integer NOT NULL,
    "name" character varying(32) NOT NULL,
    "description" character varying(255)
);


ALTER TABLE "public"."roles" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."roles_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."roles_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."roles_id_seq" OWNED BY "public"."roles"."id";



CREATE TABLE IF NOT EXISTS "public"."sales_orders" (
    "id" integer NOT NULL,
    "so_number" character varying(50) NOT NULL,
    "customer_id" integer NOT NULL,
    "total_quantity_mt" double precision NOT NULL,
    "pricing_type" character varying(32) DEFAULT 'monthly_average'::character varying NOT NULL,
    "lme_premium" double precision DEFAULT '0'::double precision,
    "status" character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "product" character varying(255),
    "unit" character varying(16),
    "unit_price" double precision,
    "pricing_period" character varying(32),
    "premium" double precision,
    "reference_price" character varying(64),
    "fixing_deadline" "date",
    "expected_delivery_date" "date",
    "location" character varying(128),
    "deal_id" integer NOT NULL
);


ALTER TABLE "public"."sales_orders" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."sales_orders_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."sales_orders_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."sales_orders_id_seq" OWNED BY "public"."sales_orders"."id";



CREATE TABLE IF NOT EXISTS "public"."so_po_links" (
    "id" integer NOT NULL,
    "sales_order_id" integer NOT NULL,
    "purchase_order_id" integer NOT NULL,
    "link_ratio" double precision
);


ALTER TABLE "public"."so_po_links" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."so_po_links_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."so_po_links_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."so_po_links_id_seq" OWNED BY "public"."so_po_links"."id";



CREATE TABLE IF NOT EXISTS "public"."suppliers" (
    "id" integer NOT NULL,
    "name" character varying(255) NOT NULL,
    "code" character varying(32),
    "contact_email" character varying(255),
    "contact_phone" character varying(64),
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "legal_name" character varying(255),
    "tax_id" character varying(32),
    "state_registration" character varying(64),
    "address_line" character varying(255),
    "city" character varying(128),
    "state" character varying(8),
    "postal_code" character varying(32),
    "credit_limit" double precision,
    "credit_score" integer,
    "kyc_status" character varying(32),
    "kyc_notes" "text",
    "trade_name" character varying(255),
    "entity_type" character varying(64),
    "tax_id_type" character varying(32),
    "tax_id_country" character varying(32),
    "country" character varying(64),
    "country_incorporation" character varying(64),
    "country_operation" character varying(64),
    "country_residence" character varying(64),
    "base_currency" character varying(8),
    "payment_terms" character varying(128),
    "risk_rating" character varying(64),
    "sanctions_flag" boolean,
    "internal_notes" "text"
);


ALTER TABLE "public"."suppliers" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."suppliers_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."suppliers_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."suppliers_id_seq" OWNED BY "public"."suppliers"."id";



CREATE TABLE IF NOT EXISTS "public"."timeline_events" (
    "id" integer NOT NULL,
    "event_type" character varying(64) NOT NULL,
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "subject_type" character varying(32) NOT NULL,
    "subject_id" integer NOT NULL,
    "correlation_id" character varying(36) NOT NULL,
    "supersedes_event_id" integer,
    "idempotency_key" character varying(128),
    "actor_user_id" integer,
    "audit_log_id" integer,
    "visibility" character varying(16) DEFAULT 'all'::character varying NOT NULL,
    "payload" json,
    "meta" json,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."timeline_events" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."timeline_events_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."timeline_events_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."timeline_events_id_seq" OWNED BY "public"."timeline_events"."id";



CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" integer NOT NULL,
    "email" character varying(255) NOT NULL,
    "name" character varying(255) NOT NULL,
    "hashed_password" character varying(255) NOT NULL,
    "role_id" integer NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."users" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."users_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."users_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."users_id_seq" OWNED BY "public"."users"."id";



CREATE TABLE IF NOT EXISTS "public"."warehouse_locations" (
    "id" integer NOT NULL,
    "name" character varying(128) NOT NULL,
    "type" character varying(64),
    "current_stock_mt" double precision,
    "capacity_mt" double precision,
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."warehouse_locations" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."warehouse_locations_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."warehouse_locations_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."warehouse_locations_id_seq" OWNED BY "public"."warehouse_locations"."id";



CREATE TABLE IF NOT EXISTS "public"."workflow_decisions" (
    "id" integer NOT NULL,
    "workflow_request_id" integer NOT NULL,
    "decision" character varying(16) NOT NULL,
    "justification" "text" NOT NULL,
    "decided_by_user_id" integer NOT NULL,
    "decided_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "idempotency_key" character varying(128),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."workflow_decisions" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."workflow_decisions_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."workflow_decisions_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."workflow_decisions_id_seq" OWNED BY "public"."workflow_decisions"."id";



CREATE TABLE IF NOT EXISTS "public"."workflow_requests" (
    "id" integer NOT NULL,
    "request_key" character varying(40) NOT NULL,
    "inputs_hash" character varying(64) NOT NULL,
    "action" character varying(64) NOT NULL,
    "subject_type" character varying(32) NOT NULL,
    "subject_id" character varying(64) NOT NULL,
    "status" character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    "notional_usd" double precision,
    "threshold_usd" double precision,
    "required_role" character varying(32) NOT NULL,
    "context" json,
    "requested_by_user_id" integer,
    "requested_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sla_due_at" timestamp with time zone,
    "decided_at" timestamp with time zone,
    "executed_at" timestamp with time zone,
    "executed_by_user_id" integer,
    "correlation_id" character varying(36),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."workflow_requests" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."workflow_requests_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."workflow_requests_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."workflow_requests_id_seq" OWNED BY "public"."workflow_requests"."id";



ALTER TABLE ONLY "public"."audit_logs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."audit_logs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cashflow_baseline_items" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cashflow_baseline_items_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."cashflow_baseline_runs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."cashflow_baseline_runs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."contract_exposures" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."contract_exposures_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."counterparties" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."counterparties_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."credit_checks" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."credit_checks_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."customers" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."customers_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."deal_links" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."deal_links_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."deal_pnl_snapshots" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."deal_pnl_snapshots_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."deals" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."deals_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."document_monthly_sequences" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."document_monthly_sequences_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."export_jobs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."export_jobs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."exposures" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."exposures_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."finance_pipeline_runs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."finance_pipeline_runs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."finance_pipeline_steps" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."finance_pipeline_steps_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."finance_risk_flag_runs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."finance_risk_flag_runs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."finance_risk_flags" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."finance_risk_flags_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."fx_policy_map" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."fx_policy_map_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hedge_exposures" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hedge_exposures_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hedge_tasks" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hedge_tasks_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hedge_trades" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hedge_trades_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hedges" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hedges_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."kyc_checks" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."kyc_checks_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."kyc_documents" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."kyc_documents_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."market_prices" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."market_prices_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."mtm_contract_snapshot_runs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."mtm_contract_snapshot_runs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."mtm_contract_snapshots" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."mtm_contract_snapshots_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."mtm_records" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."mtm_records_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."mtm_snapshots" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."mtm_snapshots_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."pnl_contract_realized" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."pnl_contract_realized_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."pnl_contract_snapshots" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."pnl_contract_snapshots_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."pnl_snapshot_runs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."pnl_snapshot_runs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."purchase_orders" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."purchase_orders_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."rfq_invitations" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."rfq_invitations_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."rfq_quotes" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."rfq_quotes_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."rfq_send_attempts" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."rfq_send_attempts_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."rfqs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."rfqs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."roles" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."roles_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."sales_orders" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."sales_orders_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."so_po_links" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."so_po_links_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."suppliers" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."suppliers_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."timeline_events" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."timeline_events_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."users" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."users_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."warehouse_locations" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."warehouse_locations_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."workflow_decisions" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."workflow_decisions_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."workflow_requests" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."workflow_requests_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."alembic_version"
    ADD CONSTRAINT "alembic_version_pkc" PRIMARY KEY ("version_num");



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cashflow_baseline_items"
    ADD CONSTRAINT "cashflow_baseline_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cashflow_baseline_runs"
    ADD CONSTRAINT "cashflow_baseline_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."contract_exposures"
    ADD CONSTRAINT "contract_exposures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."contracts"
    ADD CONSTRAINT "contracts_pkey" PRIMARY KEY ("contract_id");



ALTER TABLE ONLY "public"."counterparties"
    ADD CONSTRAINT "counterparties_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."counterparties"
    ADD CONSTRAINT "counterparties_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."credit_checks"
    ADD CONSTRAINT "credit_checks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."customers"
    ADD CONSTRAINT "customers_code_key" UNIQUE ("code");



ALTER TABLE ONLY "public"."customers"
    ADD CONSTRAINT "customers_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."customers"
    ADD CONSTRAINT "customers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."deal_links"
    ADD CONSTRAINT "deal_links_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."deal_pnl_snapshots"
    ADD CONSTRAINT "deal_pnl_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."deals"
    ADD CONSTRAINT "deals_deal_uuid_key" UNIQUE ("deal_uuid");



ALTER TABLE ONLY "public"."deals"
    ADD CONSTRAINT "deals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."document_monthly_sequences"
    ADD CONSTRAINT "document_monthly_sequences_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."export_jobs"
    ADD CONSTRAINT "export_jobs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."exposures"
    ADD CONSTRAINT "exposures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."finance_pipeline_runs"
    ADD CONSTRAINT "finance_pipeline_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."finance_pipeline_steps"
    ADD CONSTRAINT "finance_pipeline_steps_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."finance_risk_flag_runs"
    ADD CONSTRAINT "finance_risk_flag_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."finance_risk_flags"
    ADD CONSTRAINT "finance_risk_flags_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fx_policy_map"
    ADD CONSTRAINT "fx_policy_map_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hedge_exposures"
    ADD CONSTRAINT "hedge_exposures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hedge_tasks"
    ADD CONSTRAINT "hedge_tasks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hedge_trades"
    ADD CONSTRAINT "hedge_trades_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hedges"
    ADD CONSTRAINT "hedges_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."kyc_checks"
    ADD CONSTRAINT "kyc_checks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."kyc_documents"
    ADD CONSTRAINT "kyc_documents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."market_prices"
    ADD CONSTRAINT "market_prices_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mtm_contract_snapshot_runs"
    ADD CONSTRAINT "mtm_contract_snapshot_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mtm_contract_snapshots"
    ADD CONSTRAINT "mtm_contract_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mtm_records"
    ADD CONSTRAINT "mtm_records_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mtm_snapshots"
    ADD CONSTRAINT "mtm_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pnl_contract_realized"
    ADD CONSTRAINT "pnl_contract_realized_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pnl_contract_snapshots"
    ADD CONSTRAINT "pnl_contract_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pnl_snapshot_runs"
    ADD CONSTRAINT "pnl_snapshot_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."purchase_orders"
    ADD CONSTRAINT "purchase_orders_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."purchase_orders"
    ADD CONSTRAINT "purchase_orders_po_number_key" UNIQUE ("po_number");



ALTER TABLE ONLY "public"."rfq_invitations"
    ADD CONSTRAINT "rfq_invitations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rfq_quotes"
    ADD CONSTRAINT "rfq_quotes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rfq_send_attempts"
    ADD CONSTRAINT "rfq_send_attempts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_rfq_number_key" UNIQUE ("rfq_number");



ALTER TABLE ONLY "public"."roles"
    ADD CONSTRAINT "roles_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."roles"
    ADD CONSTRAINT "roles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sales_orders"
    ADD CONSTRAINT "sales_orders_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."sales_orders"
    ADD CONSTRAINT "sales_orders_so_number_key" UNIQUE ("so_number");



ALTER TABLE ONLY "public"."so_po_links"
    ADD CONSTRAINT "so_po_links_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."suppliers"
    ADD CONSTRAINT "suppliers_code_key" UNIQUE ("code");



ALTER TABLE ONLY "public"."suppliers"
    ADD CONSTRAINT "suppliers_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."suppliers"
    ADD CONSTRAINT "suppliers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."timeline_events"
    ADD CONSTRAINT "timeline_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cashflow_baseline_items"
    ADD CONSTRAINT "uq_cashflow_baseline_items_contract_date_currency" UNIQUE ("contract_id", "as_of_date", "currency");



ALTER TABLE ONLY "public"."cashflow_baseline_runs"
    ADD CONSTRAINT "uq_cashflow_baseline_runs_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."contract_exposures"
    ADD CONSTRAINT "uq_contract_exposures" UNIQUE ("contract_id", "exposure_id");



ALTER TABLE ONLY "public"."document_monthly_sequences"
    ADD CONSTRAINT "uq_doc_seq_doc_type_year_month" UNIQUE ("doc_type", "year_month");



ALTER TABLE ONLY "public"."export_jobs"
    ADD CONSTRAINT "uq_export_jobs_export_id" UNIQUE ("export_id");



ALTER TABLE ONLY "public"."finance_pipeline_runs"
    ADD CONSTRAINT "uq_finance_pipeline_runs_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."finance_pipeline_steps"
    ADD CONSTRAINT "uq_finance_pipeline_steps_run_step" UNIQUE ("run_id", "step_name");



ALTER TABLE ONLY "public"."finance_risk_flag_runs"
    ADD CONSTRAINT "uq_finance_risk_flag_runs_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."finance_risk_flags"
    ADD CONSTRAINT "uq_finance_risk_flags_run_subject_flag" UNIQUE ("run_id", "subject_type", "subject_id", "flag_code");



ALTER TABLE ONLY "public"."fx_policy_map"
    ADD CONSTRAINT "uq_fx_policy_map_policy_key" UNIQUE ("policy_key");



ALTER TABLE ONLY "public"."market_prices"
    ADD CONSTRAINT "uq_market_price" UNIQUE ("source", "symbol", "contract_month", "as_of");



ALTER TABLE ONLY "public"."mtm_contract_snapshot_runs"
    ADD CONSTRAINT "uq_mtm_contract_snapshot_runs_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."mtm_contract_snapshots"
    ADD CONSTRAINT "uq_mtm_contract_snapshots_contract_date_currency" UNIQUE ("contract_id", "as_of_date", "currency");



ALTER TABLE ONLY "public"."pnl_contract_realized"
    ADD CONSTRAINT "uq_pnl_contract_realized_contract_settlement_currency" UNIQUE ("contract_id", "settlement_date", "currency");



ALTER TABLE ONLY "public"."pnl_contract_snapshots"
    ADD CONSTRAINT "uq_pnl_contract_snapshots_contract_date_currency" UNIQUE ("contract_id", "as_of_date", "currency");



ALTER TABLE ONLY "public"."pnl_snapshot_runs"
    ADD CONSTRAINT "uq_pnl_snapshot_runs_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."so_po_links"
    ADD CONSTRAINT "uq_so_po" UNIQUE ("sales_order_id", "purchase_order_id");



ALTER TABLE ONLY "public"."timeline_events"
    ADD CONSTRAINT "uq_timeline_events_event_type_idempotency_key" UNIQUE ("event_type", "idempotency_key");



ALTER TABLE ONLY "public"."workflow_decisions"
    ADD CONSTRAINT "uq_workflow_decisions_idempotency_key" UNIQUE ("idempotency_key");



ALTER TABLE ONLY "public"."workflow_requests"
    ADD CONSTRAINT "uq_workflow_requests_inputs_hash" UNIQUE ("inputs_hash");



ALTER TABLE ONLY "public"."workflow_requests"
    ADD CONSTRAINT "uq_workflow_requests_request_key" UNIQUE ("request_key");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."warehouse_locations"
    ADD CONSTRAINT "warehouse_locations_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."warehouse_locations"
    ADD CONSTRAINT "warehouse_locations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."workflow_decisions"
    ADD CONSTRAINT "workflow_decisions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."workflow_requests"
    ADD CONSTRAINT "workflow_requests_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_contracts_settlement_date" ON "public"."contracts" USING "btree" ("settlement_date");



CREATE UNIQUE INDEX "ix_audit_logs_idempotency_key" ON "public"."audit_logs" USING "btree" ("idempotency_key");



CREATE INDEX "ix_audit_logs_request_id" ON "public"."audit_logs" USING "btree" ("request_id");



CREATE INDEX "ix_cashflow_baseline_items_as_of_date" ON "public"."cashflow_baseline_items" USING "btree" ("as_of_date");



CREATE INDEX "ix_cashflow_baseline_items_contract_id" ON "public"."cashflow_baseline_items" USING "btree" ("contract_id");



CREATE INDEX "ix_cashflow_baseline_items_counterparty_id" ON "public"."cashflow_baseline_items" USING "btree" ("counterparty_id");



CREATE INDEX "ix_cashflow_baseline_items_deal_id" ON "public"."cashflow_baseline_items" USING "btree" ("deal_id");



CREATE INDEX "ix_cashflow_baseline_items_inputs_hash" ON "public"."cashflow_baseline_items" USING "btree" ("inputs_hash");



CREATE INDEX "ix_cashflow_baseline_items_rfq_id" ON "public"."cashflow_baseline_items" USING "btree" ("rfq_id");



CREATE INDEX "ix_cashflow_baseline_items_run_id" ON "public"."cashflow_baseline_items" USING "btree" ("run_id");



CREATE INDEX "ix_cashflow_baseline_items_settlement_date" ON "public"."cashflow_baseline_items" USING "btree" ("settlement_date");



CREATE INDEX "ix_cashflow_baseline_runs_as_of_date" ON "public"."cashflow_baseline_runs" USING "btree" ("as_of_date");



CREATE INDEX "ix_cashflow_baseline_runs_inputs_hash" ON "public"."cashflow_baseline_runs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_cashflow_baseline_runs_requested_by_user_id" ON "public"."cashflow_baseline_runs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_contract_exposures_contract_id" ON "public"."contract_exposures" USING "btree" ("contract_id");



CREATE INDEX "ix_contract_exposures_exposure_id" ON "public"."contract_exposures" USING "btree" ("exposure_id");



CREATE UNIQUE INDEX "ix_contracts_contract_number" ON "public"."contracts" USING "btree" ("contract_number");



CREATE INDEX "ix_contracts_deal_id" ON "public"."contracts" USING "btree" ("deal_id");



CREATE INDEX "ix_contracts_quote_group_id" ON "public"."contracts" USING "btree" ("quote_group_id");



CREATE INDEX "ix_contracts_rfq_id" ON "public"."contracts" USING "btree" ("rfq_id");



CREATE INDEX "ix_contracts_status" ON "public"."contracts" USING "btree" ("status");



CREATE INDEX "ix_counterparties_active" ON "public"."counterparties" USING "btree" ("active");



CREATE INDEX "ix_counterparties_contact_email" ON "public"."counterparties" USING "btree" ("contact_email");



CREATE INDEX "ix_counterparties_contact_phone" ON "public"."counterparties" USING "btree" ("contact_phone");



CREATE INDEX "ix_counterparties_tax_id" ON "public"."counterparties" USING "btree" ("tax_id");



CREATE INDEX "ix_credit_checks_owner" ON "public"."credit_checks" USING "btree" ("owner_id");



CREATE INDEX "ix_customers_active" ON "public"."customers" USING "btree" ("active");



CREATE INDEX "ix_customers_contact_email" ON "public"."customers" USING "btree" ("contact_email");



CREATE INDEX "ix_customers_contact_phone" ON "public"."customers" USING "btree" ("contact_phone");



CREATE INDEX "ix_customers_tax_id" ON "public"."customers" USING "btree" ("tax_id");



CREATE INDEX "ix_deal_links_deal_id" ON "public"."deal_links" USING "btree" ("deal_id");



CREATE INDEX "ix_deal_links_entity_id" ON "public"."deal_links" USING "btree" ("entity_id");



CREATE INDEX "ix_deal_pnl_snapshots_deal_id" ON "public"."deal_pnl_snapshots" USING "btree" ("deal_id");



CREATE INDEX "ix_deals_commodity" ON "public"."deals" USING "btree" ("commodity");



CREATE INDEX "ix_deals_deal_uuid" ON "public"."deals" USING "btree" ("deal_uuid");



CREATE INDEX "ix_deals_lifecycle_status" ON "public"."deals" USING "btree" ("lifecycle_status");



CREATE INDEX "ix_deals_reference_name" ON "public"."deals" USING "btree" ("reference_name");



CREATE INDEX "ix_deals_status" ON "public"."deals" USING "btree" ("status");



CREATE INDEX "ix_document_monthly_sequences_doc_type_year_month" ON "public"."document_monthly_sequences" USING "btree" ("doc_type", "year_month");



CREATE INDEX "ix_export_jobs_as_of" ON "public"."export_jobs" USING "btree" ("as_of");



CREATE INDEX "ix_export_jobs_export_id" ON "public"."export_jobs" USING "btree" ("export_id");



CREATE INDEX "ix_export_jobs_export_type" ON "public"."export_jobs" USING "btree" ("export_type");



CREATE INDEX "ix_export_jobs_inputs_hash" ON "public"."export_jobs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_export_jobs_requested_by_user_id" ON "public"."export_jobs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_export_jobs_status" ON "public"."export_jobs" USING "btree" ("status");



CREATE INDEX "ix_exposures_source" ON "public"."exposures" USING "btree" ("source_type", "source_id");



CREATE INDEX "ix_finance_pipeline_runs_as_of_date" ON "public"."finance_pipeline_runs" USING "btree" ("as_of_date");



CREATE INDEX "ix_finance_pipeline_runs_inputs_hash" ON "public"."finance_pipeline_runs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_finance_pipeline_runs_pipeline_version" ON "public"."finance_pipeline_runs" USING "btree" ("pipeline_version");



CREATE INDEX "ix_finance_pipeline_runs_requested_by_user_id" ON "public"."finance_pipeline_runs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_finance_pipeline_runs_status" ON "public"."finance_pipeline_runs" USING "btree" ("status");



CREATE INDEX "ix_finance_pipeline_steps_run_id" ON "public"."finance_pipeline_steps" USING "btree" ("run_id");



CREATE INDEX "ix_finance_pipeline_steps_status" ON "public"."finance_pipeline_steps" USING "btree" ("status");



CREATE INDEX "ix_finance_pipeline_steps_step_name" ON "public"."finance_pipeline_steps" USING "btree" ("step_name");



CREATE INDEX "ix_finance_risk_flag_runs_as_of_date" ON "public"."finance_risk_flag_runs" USING "btree" ("as_of_date");



CREATE INDEX "ix_finance_risk_flag_runs_inputs_hash" ON "public"."finance_risk_flag_runs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_finance_risk_flag_runs_requested_by_user_id" ON "public"."finance_risk_flag_runs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_finance_risk_flags_as_of_date" ON "public"."finance_risk_flags" USING "btree" ("as_of_date");



CREATE INDEX "ix_finance_risk_flags_contract_id" ON "public"."finance_risk_flags" USING "btree" ("contract_id");



CREATE INDEX "ix_finance_risk_flags_deal_id" ON "public"."finance_risk_flags" USING "btree" ("deal_id");



CREATE INDEX "ix_finance_risk_flags_flag_code" ON "public"."finance_risk_flags" USING "btree" ("flag_code");



CREATE INDEX "ix_finance_risk_flags_inputs_hash" ON "public"."finance_risk_flags" USING "btree" ("inputs_hash");



CREATE INDEX "ix_finance_risk_flags_run_id" ON "public"."finance_risk_flags" USING "btree" ("run_id");



CREATE INDEX "ix_finance_risk_flags_subject_id" ON "public"."finance_risk_flags" USING "btree" ("subject_id");



CREATE INDEX "ix_finance_risk_flags_subject_type" ON "public"."finance_risk_flags" USING "btree" ("subject_type");



CREATE INDEX "ix_fx_policy_map_created_by_user_id" ON "public"."fx_policy_map" USING "btree" ("created_by_user_id");



CREATE UNIQUE INDEX "ix_fx_policy_map_policy_key" ON "public"."fx_policy_map" USING "btree" ("policy_key");



CREATE INDEX "ix_fx_policy_map_reporting_currency" ON "public"."fx_policy_map" USING "btree" ("reporting_currency");



CREATE INDEX "ix_kyc_checks_owner" ON "public"."kyc_checks" USING "btree" ("owner_id");



CREATE INDEX "ix_kyc_checks_owner_type" ON "public"."kyc_checks" USING "btree" ("owner_type");



CREATE INDEX "ix_kyc_checks_type" ON "public"."kyc_checks" USING "btree" ("check_type");



CREATE INDEX "ix_kyc_documents_owner" ON "public"."kyc_documents" USING "btree" ("owner_id");



CREATE INDEX "ix_mtm_contract_snapshot_runs_as_of_date" ON "public"."mtm_contract_snapshot_runs" USING "btree" ("as_of_date");



CREATE INDEX "ix_mtm_contract_snapshot_runs_inputs_hash" ON "public"."mtm_contract_snapshot_runs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_mtm_contract_snapshot_runs_requested_by_user_id" ON "public"."mtm_contract_snapshot_runs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_mtm_contract_snapshots_as_of_date" ON "public"."mtm_contract_snapshots" USING "btree" ("as_of_date");



CREATE INDEX "ix_mtm_contract_snapshots_contract_id" ON "public"."mtm_contract_snapshots" USING "btree" ("contract_id");



CREATE INDEX "ix_mtm_contract_snapshots_deal_id" ON "public"."mtm_contract_snapshots" USING "btree" ("deal_id");



CREATE INDEX "ix_mtm_contract_snapshots_inputs_hash" ON "public"."mtm_contract_snapshots" USING "btree" ("inputs_hash");



CREATE INDEX "ix_mtm_contract_snapshots_run_id" ON "public"."mtm_contract_snapshots" USING "btree" ("run_id");



CREATE INDEX "ix_mtm_snapshots_object" ON "public"."mtm_snapshots" USING "btree" ("object_type", "object_id");



CREATE INDEX "ix_pnl_contract_realized_contract_id" ON "public"."pnl_contract_realized" USING "btree" ("contract_id");



CREATE INDEX "ix_pnl_contract_realized_deal_id" ON "public"."pnl_contract_realized" USING "btree" ("deal_id");



CREATE INDEX "ix_pnl_contract_realized_inputs_hash" ON "public"."pnl_contract_realized" USING "btree" ("inputs_hash");



CREATE INDEX "ix_pnl_contract_realized_settlement_date" ON "public"."pnl_contract_realized" USING "btree" ("settlement_date");



CREATE INDEX "ix_pnl_contract_snapshots_as_of_date" ON "public"."pnl_contract_snapshots" USING "btree" ("as_of_date");



CREATE INDEX "ix_pnl_contract_snapshots_contract_id" ON "public"."pnl_contract_snapshots" USING "btree" ("contract_id");



CREATE INDEX "ix_pnl_contract_snapshots_deal_id" ON "public"."pnl_contract_snapshots" USING "btree" ("deal_id");



CREATE INDEX "ix_pnl_contract_snapshots_inputs_hash" ON "public"."pnl_contract_snapshots" USING "btree" ("inputs_hash");



CREATE INDEX "ix_pnl_contract_snapshots_run_id" ON "public"."pnl_contract_snapshots" USING "btree" ("run_id");



CREATE INDEX "ix_pnl_snapshot_runs_as_of_date" ON "public"."pnl_snapshot_runs" USING "btree" ("as_of_date");



CREATE INDEX "ix_pnl_snapshot_runs_inputs_hash" ON "public"."pnl_snapshot_runs" USING "btree" ("inputs_hash");



CREATE INDEX "ix_pnl_snapshot_runs_requested_by_user_id" ON "public"."pnl_snapshot_runs" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_purchase_orders_deal_id" ON "public"."purchase_orders" USING "btree" ("deal_id");



CREATE INDEX "ix_rfq_send_attempt_idempotency" ON "public"."rfq_send_attempts" USING "btree" ("rfq_id", "idempotency_key");



CREATE INDEX "ix_rfqs_deal_id" ON "public"."rfqs" USING "btree" ("deal_id");



CREATE INDEX "ix_sales_orders_deal_id" ON "public"."sales_orders" USING "btree" ("deal_id");



CREATE INDEX "ix_suppliers_active" ON "public"."suppliers" USING "btree" ("active");



CREATE INDEX "ix_suppliers_contact_email" ON "public"."suppliers" USING "btree" ("contact_email");



CREATE INDEX "ix_suppliers_contact_phone" ON "public"."suppliers" USING "btree" ("contact_phone");



CREATE INDEX "ix_suppliers_tax_id" ON "public"."suppliers" USING "btree" ("tax_id");



CREATE INDEX "ix_timeline_events_actor_user_id" ON "public"."timeline_events" USING "btree" ("actor_user_id");



CREATE INDEX "ix_timeline_events_audit_log_id" ON "public"."timeline_events" USING "btree" ("audit_log_id");



CREATE INDEX "ix_timeline_events_correlation_id" ON "public"."timeline_events" USING "btree" ("correlation_id");



CREATE INDEX "ix_timeline_events_event_type" ON "public"."timeline_events" USING "btree" ("event_type");



CREATE INDEX "ix_timeline_events_occurred_at" ON "public"."timeline_events" USING "btree" ("occurred_at");



CREATE INDEX "ix_timeline_events_subject_id" ON "public"."timeline_events" USING "btree" ("subject_id");



CREATE INDEX "ix_timeline_events_subject_type" ON "public"."timeline_events" USING "btree" ("subject_type");



CREATE INDEX "ix_timeline_events_supersedes_event_id" ON "public"."timeline_events" USING "btree" ("supersedes_event_id");



CREATE INDEX "ix_timeline_events_visibility" ON "public"."timeline_events" USING "btree" ("visibility");



CREATE UNIQUE INDEX "ix_users_email" ON "public"."users" USING "btree" ("email");



CREATE INDEX "ix_workflow_decisions_decided_by_user_id" ON "public"."workflow_decisions" USING "btree" ("decided_by_user_id");



CREATE INDEX "ix_workflow_decisions_decision" ON "public"."workflow_decisions" USING "btree" ("decision");



CREATE INDEX "ix_workflow_decisions_workflow_request_id" ON "public"."workflow_decisions" USING "btree" ("workflow_request_id");



CREATE INDEX "ix_workflow_requests_action" ON "public"."workflow_requests" USING "btree" ("action");



CREATE INDEX "ix_workflow_requests_correlation_id" ON "public"."workflow_requests" USING "btree" ("correlation_id");



CREATE INDEX "ix_workflow_requests_requested_by_user_id" ON "public"."workflow_requests" USING "btree" ("requested_by_user_id");



CREATE INDEX "ix_workflow_requests_required_role" ON "public"."workflow_requests" USING "btree" ("required_role");



CREATE INDEX "ix_workflow_requests_sla_due_at" ON "public"."workflow_requests" USING "btree" ("sla_due_at");



CREATE INDEX "ix_workflow_requests_status" ON "public"."workflow_requests" USING "btree" ("status");



CREATE INDEX "ix_workflow_requests_subject_id" ON "public"."workflow_requests" USING "btree" ("subject_id");



CREATE INDEX "ix_workflow_requests_subject_type" ON "public"."workflow_requests" USING "btree" ("subject_type");



ALTER TABLE ONLY "public"."cashflow_baseline_items"
    ADD CONSTRAINT "cashflow_baseline_items_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."contracts"("contract_id");



ALTER TABLE ONLY "public"."cashflow_baseline_items"
    ADD CONSTRAINT "cashflow_baseline_items_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."cashflow_baseline_runs"("id");



ALTER TABLE ONLY "public"."cashflow_baseline_runs"
    ADD CONSTRAINT "cashflow_baseline_runs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."contract_exposures"
    ADD CONSTRAINT "contract_exposures_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."contracts"("contract_id");



ALTER TABLE ONLY "public"."contract_exposures"
    ADD CONSTRAINT "contract_exposures_exposure_id_fkey" FOREIGN KEY ("exposure_id") REFERENCES "public"."exposures"("id");



ALTER TABLE ONLY "public"."contracts"
    ADD CONSTRAINT "contracts_counterparty_id_fkey" FOREIGN KEY ("counterparty_id") REFERENCES "public"."counterparties"("id");



ALTER TABLE ONLY "public"."contracts"
    ADD CONSTRAINT "contracts_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."contracts"
    ADD CONSTRAINT "contracts_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."contracts"
    ADD CONSTRAINT "contracts_rfq_id_fkey" FOREIGN KEY ("rfq_id") REFERENCES "public"."rfqs"("id");



ALTER TABLE ONLY "public"."deal_links"
    ADD CONSTRAINT "deal_links_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."deal_pnl_snapshots"
    ADD CONSTRAINT "deal_pnl_snapshots_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."deals"
    ADD CONSTRAINT "deals_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."export_jobs"
    ADD CONSTRAINT "export_jobs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."finance_pipeline_runs"
    ADD CONSTRAINT "finance_pipeline_runs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."finance_pipeline_steps"
    ADD CONSTRAINT "finance_pipeline_steps_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."finance_pipeline_runs"("id");



ALTER TABLE ONLY "public"."finance_risk_flag_runs"
    ADD CONSTRAINT "finance_risk_flag_runs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."finance_risk_flags"
    ADD CONSTRAINT "finance_risk_flags_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."finance_risk_flag_runs"("id");



ALTER TABLE ONLY "public"."fx_policy_map"
    ADD CONSTRAINT "fx_policy_map_created_by_user_id_fkey" FOREIGN KEY ("created_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."hedge_exposures"
    ADD CONSTRAINT "hedge_exposures_exposure_id_fkey" FOREIGN KEY ("exposure_id") REFERENCES "public"."exposures"("id");



ALTER TABLE ONLY "public"."hedge_exposures"
    ADD CONSTRAINT "hedge_exposures_hedge_id_fkey" FOREIGN KEY ("hedge_id") REFERENCES "public"."hedges"("id");



ALTER TABLE ONLY "public"."hedge_tasks"
    ADD CONSTRAINT "hedge_tasks_exposure_id_fkey" FOREIGN KEY ("exposure_id") REFERENCES "public"."exposures"("id");



ALTER TABLE ONLY "public"."hedges"
    ADD CONSTRAINT "hedges_counterparty_id_fkey" FOREIGN KEY ("counterparty_id") REFERENCES "public"."counterparties"("id");



ALTER TABLE ONLY "public"."hedges"
    ADD CONSTRAINT "hedges_so_id_fkey" FOREIGN KEY ("so_id") REFERENCES "public"."sales_orders"("id");



ALTER TABLE ONLY "public"."mtm_contract_snapshot_runs"
    ADD CONSTRAINT "mtm_contract_snapshot_runs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."mtm_contract_snapshots"
    ADD CONSTRAINT "mtm_contract_snapshots_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."contracts"("contract_id");



ALTER TABLE ONLY "public"."mtm_contract_snapshots"
    ADD CONSTRAINT "mtm_contract_snapshots_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."mtm_contract_snapshot_runs"("id");



ALTER TABLE ONLY "public"."pnl_contract_realized"
    ADD CONSTRAINT "pnl_contract_realized_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."contracts"("contract_id");



ALTER TABLE ONLY "public"."pnl_contract_snapshots"
    ADD CONSTRAINT "pnl_contract_snapshots_contract_id_fkey" FOREIGN KEY ("contract_id") REFERENCES "public"."contracts"("contract_id");



ALTER TABLE ONLY "public"."pnl_contract_snapshots"
    ADD CONSTRAINT "pnl_contract_snapshots_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "public"."pnl_snapshot_runs"("id");



ALTER TABLE ONLY "public"."pnl_snapshot_runs"
    ADD CONSTRAINT "pnl_snapshot_runs_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."purchase_orders"
    ADD CONSTRAINT "purchase_orders_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."purchase_orders"
    ADD CONSTRAINT "purchase_orders_supplier_id_fkey" FOREIGN KEY ("supplier_id") REFERENCES "public"."suppliers"("id");



ALTER TABLE ONLY "public"."rfq_invitations"
    ADD CONSTRAINT "rfq_invitations_counterparty_id_fkey" FOREIGN KEY ("counterparty_id") REFERENCES "public"."counterparties"("id");



ALTER TABLE ONLY "public"."rfq_invitations"
    ADD CONSTRAINT "rfq_invitations_rfq_id_fkey" FOREIGN KEY ("rfq_id") REFERENCES "public"."rfqs"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."rfq_quotes"
    ADD CONSTRAINT "rfq_quotes_counterparty_id_fkey" FOREIGN KEY ("counterparty_id") REFERENCES "public"."counterparties"("id");



ALTER TABLE ONLY "public"."rfq_quotes"
    ADD CONSTRAINT "rfq_quotes_rfq_id_fkey" FOREIGN KEY ("rfq_id") REFERENCES "public"."rfqs"("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_decided_by_fkey" FOREIGN KEY ("decided_by") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_hedge_id_fkey" FOREIGN KEY ("hedge_id") REFERENCES "public"."hedges"("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_so_id_fkey" FOREIGN KEY ("so_id") REFERENCES "public"."sales_orders"("id");



ALTER TABLE ONLY "public"."rfqs"
    ADD CONSTRAINT "rfqs_winner_quote_id_fkey" FOREIGN KEY ("winner_quote_id") REFERENCES "public"."rfq_quotes"("id");



ALTER TABLE ONLY "public"."sales_orders"
    ADD CONSTRAINT "sales_orders_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."customers"("id");



ALTER TABLE ONLY "public"."sales_orders"
    ADD CONSTRAINT "sales_orders_deal_id_fkey" FOREIGN KEY ("deal_id") REFERENCES "public"."deals"("id");



ALTER TABLE ONLY "public"."timeline_events"
    ADD CONSTRAINT "timeline_events_actor_user_id_fkey" FOREIGN KEY ("actor_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."timeline_events"
    ADD CONSTRAINT "timeline_events_audit_log_id_fkey" FOREIGN KEY ("audit_log_id") REFERENCES "public"."audit_logs"("id");



ALTER TABLE ONLY "public"."timeline_events"
    ADD CONSTRAINT "timeline_events_supersedes_event_id_fkey" FOREIGN KEY ("supersedes_event_id") REFERENCES "public"."timeline_events"("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_role_id_fkey" FOREIGN KEY ("role_id") REFERENCES "public"."roles"("id");



ALTER TABLE ONLY "public"."workflow_decisions"
    ADD CONSTRAINT "workflow_decisions_decided_by_user_id_fkey" FOREIGN KEY ("decided_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."workflow_decisions"
    ADD CONSTRAINT "workflow_decisions_workflow_request_id_fkey" FOREIGN KEY ("workflow_request_id") REFERENCES "public"."workflow_requests"("id");



ALTER TABLE ONLY "public"."workflow_requests"
    ADD CONSTRAINT "workflow_requests_executed_by_user_id_fkey" FOREIGN KEY ("executed_by_user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."workflow_requests"
    ADD CONSTRAINT "workflow_requests_requested_by_user_id_fkey" FOREIGN KEY ("requested_by_user_id") REFERENCES "public"."users"("id");



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON TABLE "public"."alembic_version" TO "anon";
GRANT ALL ON TABLE "public"."alembic_version" TO "authenticated";
GRANT ALL ON TABLE "public"."alembic_version" TO "service_role";



GRANT ALL ON TABLE "public"."audit_logs" TO "anon";
GRANT ALL ON TABLE "public"."audit_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_logs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."audit_logs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."audit_logs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."audit_logs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cashflow_baseline_items" TO "anon";
GRANT ALL ON TABLE "public"."cashflow_baseline_items" TO "authenticated";
GRANT ALL ON TABLE "public"."cashflow_baseline_items" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cashflow_baseline_items_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cashflow_baseline_items_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cashflow_baseline_items_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."cashflow_baseline_runs" TO "anon";
GRANT ALL ON TABLE "public"."cashflow_baseline_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."cashflow_baseline_runs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."cashflow_baseline_runs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."cashflow_baseline_runs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."cashflow_baseline_runs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."contract_exposures" TO "anon";
GRANT ALL ON TABLE "public"."contract_exposures" TO "authenticated";
GRANT ALL ON TABLE "public"."contract_exposures" TO "service_role";



GRANT ALL ON SEQUENCE "public"."contract_exposures_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."contract_exposures_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."contract_exposures_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."contracts" TO "anon";
GRANT ALL ON TABLE "public"."contracts" TO "authenticated";
GRANT ALL ON TABLE "public"."contracts" TO "service_role";



GRANT ALL ON TABLE "public"."counterparties" TO "anon";
GRANT ALL ON TABLE "public"."counterparties" TO "authenticated";
GRANT ALL ON TABLE "public"."counterparties" TO "service_role";



GRANT ALL ON SEQUENCE "public"."counterparties_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."counterparties_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."counterparties_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."credit_checks" TO "anon";
GRANT ALL ON TABLE "public"."credit_checks" TO "authenticated";
GRANT ALL ON TABLE "public"."credit_checks" TO "service_role";



GRANT ALL ON SEQUENCE "public"."credit_checks_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."credit_checks_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."credit_checks_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."customers" TO "anon";
GRANT ALL ON TABLE "public"."customers" TO "authenticated";
GRANT ALL ON TABLE "public"."customers" TO "service_role";



GRANT ALL ON SEQUENCE "public"."customers_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."customers_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."customers_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."deal_links" TO "anon";
GRANT ALL ON TABLE "public"."deal_links" TO "authenticated";
GRANT ALL ON TABLE "public"."deal_links" TO "service_role";



GRANT ALL ON SEQUENCE "public"."deal_links_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."deal_links_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."deal_links_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."deal_pnl_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."deal_pnl_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."deal_pnl_snapshots" TO "service_role";



GRANT ALL ON SEQUENCE "public"."deal_pnl_snapshots_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."deal_pnl_snapshots_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."deal_pnl_snapshots_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."deals" TO "anon";
GRANT ALL ON TABLE "public"."deals" TO "authenticated";
GRANT ALL ON TABLE "public"."deals" TO "service_role";



GRANT ALL ON SEQUENCE "public"."deals_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."deals_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."deals_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."document_monthly_sequences" TO "anon";
GRANT ALL ON TABLE "public"."document_monthly_sequences" TO "authenticated";
GRANT ALL ON TABLE "public"."document_monthly_sequences" TO "service_role";



GRANT ALL ON SEQUENCE "public"."document_monthly_sequences_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."document_monthly_sequences_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."document_monthly_sequences_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."export_jobs" TO "anon";
GRANT ALL ON TABLE "public"."export_jobs" TO "authenticated";
GRANT ALL ON TABLE "public"."export_jobs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."export_jobs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."export_jobs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."export_jobs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."exposures" TO "anon";
GRANT ALL ON TABLE "public"."exposures" TO "authenticated";
GRANT ALL ON TABLE "public"."exposures" TO "service_role";



GRANT ALL ON SEQUENCE "public"."exposures_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."exposures_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."exposures_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."finance_pipeline_runs" TO "anon";
GRANT ALL ON TABLE "public"."finance_pipeline_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."finance_pipeline_runs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."finance_pipeline_runs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."finance_pipeline_runs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."finance_pipeline_runs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."finance_pipeline_steps" TO "anon";
GRANT ALL ON TABLE "public"."finance_pipeline_steps" TO "authenticated";
GRANT ALL ON TABLE "public"."finance_pipeline_steps" TO "service_role";



GRANT ALL ON SEQUENCE "public"."finance_pipeline_steps_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."finance_pipeline_steps_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."finance_pipeline_steps_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."finance_risk_flag_runs" TO "anon";
GRANT ALL ON TABLE "public"."finance_risk_flag_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."finance_risk_flag_runs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."finance_risk_flag_runs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."finance_risk_flag_runs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."finance_risk_flag_runs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."finance_risk_flags" TO "anon";
GRANT ALL ON TABLE "public"."finance_risk_flags" TO "authenticated";
GRANT ALL ON TABLE "public"."finance_risk_flags" TO "service_role";



GRANT ALL ON SEQUENCE "public"."finance_risk_flags_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."finance_risk_flags_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."finance_risk_flags_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."fx_policy_map" TO "anon";
GRANT ALL ON TABLE "public"."fx_policy_map" TO "authenticated";
GRANT ALL ON TABLE "public"."fx_policy_map" TO "service_role";



GRANT ALL ON SEQUENCE "public"."fx_policy_map_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."fx_policy_map_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."fx_policy_map_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hedge_exposures" TO "anon";
GRANT ALL ON TABLE "public"."hedge_exposures" TO "authenticated";
GRANT ALL ON TABLE "public"."hedge_exposures" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hedge_exposures_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hedge_exposures_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hedge_exposures_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hedge_tasks" TO "anon";
GRANT ALL ON TABLE "public"."hedge_tasks" TO "authenticated";
GRANT ALL ON TABLE "public"."hedge_tasks" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hedge_tasks_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hedge_tasks_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hedge_tasks_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hedge_trades" TO "anon";
GRANT ALL ON TABLE "public"."hedge_trades" TO "authenticated";
GRANT ALL ON TABLE "public"."hedge_trades" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hedge_trades_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hedge_trades_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hedge_trades_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hedges" TO "anon";
GRANT ALL ON TABLE "public"."hedges" TO "authenticated";
GRANT ALL ON TABLE "public"."hedges" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hedges_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hedges_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hedges_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."kyc_checks" TO "anon";
GRANT ALL ON TABLE "public"."kyc_checks" TO "authenticated";
GRANT ALL ON TABLE "public"."kyc_checks" TO "service_role";



GRANT ALL ON SEQUENCE "public"."kyc_checks_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."kyc_checks_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."kyc_checks_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."kyc_documents" TO "anon";
GRANT ALL ON TABLE "public"."kyc_documents" TO "authenticated";
GRANT ALL ON TABLE "public"."kyc_documents" TO "service_role";



GRANT ALL ON SEQUENCE "public"."kyc_documents_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."kyc_documents_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."kyc_documents_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."market_prices" TO "anon";
GRANT ALL ON TABLE "public"."market_prices" TO "authenticated";
GRANT ALL ON TABLE "public"."market_prices" TO "service_role";



GRANT ALL ON SEQUENCE "public"."market_prices_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."market_prices_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."market_prices_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."mtm_contract_snapshot_runs" TO "anon";
GRANT ALL ON TABLE "public"."mtm_contract_snapshot_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."mtm_contract_snapshot_runs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshot_runs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshot_runs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshot_runs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."mtm_contract_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."mtm_contract_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."mtm_contract_snapshots" TO "service_role";



GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshots_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshots_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."mtm_contract_snapshots_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."mtm_records" TO "anon";
GRANT ALL ON TABLE "public"."mtm_records" TO "authenticated";
GRANT ALL ON TABLE "public"."mtm_records" TO "service_role";



GRANT ALL ON SEQUENCE "public"."mtm_records_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."mtm_records_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."mtm_records_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."mtm_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."mtm_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."mtm_snapshots" TO "service_role";



GRANT ALL ON SEQUENCE "public"."mtm_snapshots_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."mtm_snapshots_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."mtm_snapshots_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."pnl_contract_realized" TO "anon";
GRANT ALL ON TABLE "public"."pnl_contract_realized" TO "authenticated";
GRANT ALL ON TABLE "public"."pnl_contract_realized" TO "service_role";



GRANT ALL ON SEQUENCE "public"."pnl_contract_realized_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."pnl_contract_realized_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."pnl_contract_realized_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."pnl_contract_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."pnl_contract_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."pnl_contract_snapshots" TO "service_role";



GRANT ALL ON SEQUENCE "public"."pnl_contract_snapshots_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."pnl_contract_snapshots_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."pnl_contract_snapshots_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."pnl_snapshot_runs" TO "anon";
GRANT ALL ON TABLE "public"."pnl_snapshot_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."pnl_snapshot_runs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."pnl_snapshot_runs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."pnl_snapshot_runs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."pnl_snapshot_runs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."purchase_orders" TO "anon";
GRANT ALL ON TABLE "public"."purchase_orders" TO "authenticated";
GRANT ALL ON TABLE "public"."purchase_orders" TO "service_role";



GRANT ALL ON SEQUENCE "public"."purchase_orders_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."purchase_orders_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."purchase_orders_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."rfq_invitations" TO "anon";
GRANT ALL ON TABLE "public"."rfq_invitations" TO "authenticated";
GRANT ALL ON TABLE "public"."rfq_invitations" TO "service_role";



GRANT ALL ON SEQUENCE "public"."rfq_invitations_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."rfq_invitations_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."rfq_invitations_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."rfq_quotes" TO "anon";
GRANT ALL ON TABLE "public"."rfq_quotes" TO "authenticated";
GRANT ALL ON TABLE "public"."rfq_quotes" TO "service_role";



GRANT ALL ON SEQUENCE "public"."rfq_quotes_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."rfq_quotes_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."rfq_quotes_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."rfq_send_attempts" TO "anon";
GRANT ALL ON TABLE "public"."rfq_send_attempts" TO "authenticated";
GRANT ALL ON TABLE "public"."rfq_send_attempts" TO "service_role";



GRANT ALL ON SEQUENCE "public"."rfq_send_attempts_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."rfq_send_attempts_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."rfq_send_attempts_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."rfqs" TO "anon";
GRANT ALL ON TABLE "public"."rfqs" TO "authenticated";
GRANT ALL ON TABLE "public"."rfqs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."rfqs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."rfqs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."rfqs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."roles" TO "anon";
GRANT ALL ON TABLE "public"."roles" TO "authenticated";
GRANT ALL ON TABLE "public"."roles" TO "service_role";



GRANT ALL ON SEQUENCE "public"."roles_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."roles_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."roles_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."sales_orders" TO "anon";
GRANT ALL ON TABLE "public"."sales_orders" TO "authenticated";
GRANT ALL ON TABLE "public"."sales_orders" TO "service_role";



GRANT ALL ON SEQUENCE "public"."sales_orders_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."sales_orders_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."sales_orders_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."so_po_links" TO "anon";
GRANT ALL ON TABLE "public"."so_po_links" TO "authenticated";
GRANT ALL ON TABLE "public"."so_po_links" TO "service_role";



GRANT ALL ON SEQUENCE "public"."so_po_links_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."so_po_links_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."so_po_links_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."suppliers" TO "anon";
GRANT ALL ON TABLE "public"."suppliers" TO "authenticated";
GRANT ALL ON TABLE "public"."suppliers" TO "service_role";



GRANT ALL ON SEQUENCE "public"."suppliers_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."suppliers_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."suppliers_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."timeline_events" TO "anon";
GRANT ALL ON TABLE "public"."timeline_events" TO "authenticated";
GRANT ALL ON TABLE "public"."timeline_events" TO "service_role";



GRANT ALL ON SEQUENCE "public"."timeline_events_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."timeline_events_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."timeline_events_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";



GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."users_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."warehouse_locations" TO "anon";
GRANT ALL ON TABLE "public"."warehouse_locations" TO "authenticated";
GRANT ALL ON TABLE "public"."warehouse_locations" TO "service_role";



GRANT ALL ON SEQUENCE "public"."warehouse_locations_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."warehouse_locations_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."warehouse_locations_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."workflow_decisions" TO "anon";
GRANT ALL ON TABLE "public"."workflow_decisions" TO "authenticated";
GRANT ALL ON TABLE "public"."workflow_decisions" TO "service_role";



GRANT ALL ON SEQUENCE "public"."workflow_decisions_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."workflow_decisions_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."workflow_decisions_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."workflow_requests" TO "anon";
GRANT ALL ON TABLE "public"."workflow_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."workflow_requests" TO "service_role";



GRANT ALL ON SEQUENCE "public"."workflow_requests_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."workflow_requests_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."workflow_requests_id_seq" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";







