CREATE TABLE IF NOT EXISTS company_reports (
    report_id UUID PRIMARY KEY,
    report_date TIMESTAMPTZ NOT NULL,
    inn TEXT NOT NULL,
    ogrn TEXT,
    short_name TEXT,
    full_name TEXT,
    risk_level TEXT CHECK (risk_level IS NULL OR risk_level IN ('LOW','MEDIUM','HIGH','UNKNOWN')),
    zsk_risk_level TEXT CHECK (zsk_risk_level IS NULL OR zsk_risk_level IN ('GREEN','YELLOW','RED')),
    kpp TEXT,
    okpo TEXT,
    address TEXT,
    email TEXT,
    website TEXT,
    company_size TEXT,
    staff TEXT,
    registration_date TIMESTAMPTZ,
    years_from_registration SMALLINT,
    status TEXT,
    status_reason TEXT,
    status_date TIMESTAMPTZ,
    share_capital NUMERIC,
    branches_count INTEGER,
    raw_report_json JSONB NOT NULL,
    CONSTRAINT uq_company_reports_report_inn UNIQUE (report_id, inn),
    CONSTRAINT uq_company_reports_snapshot UNIQUE (inn, report_date)
);

CREATE TABLE IF NOT EXISTS structure_items (
    id BIGSERIAL PRIMARY KEY,
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    subject_inn TEXT,
    item_type TEXT NOT NULL CHECK (item_type IN (
        'activity','branch','director','founder','phone',
        'related_company','related_parent_organization','tax_system'
    )),
    item_index INTEGER NOT NULL,
    name TEXT,
    related_inn TEXT,
    related_ogrn TEXT,
    role TEXT,
    position TEXT,
    code TEXT,
    description TEXT,
    share NUMERIC,
    amount NUMERIC,
    date_from TIMESTAMPTZ,
    active BOOLEAN,
    registration_date TIMESTAMPTZ,
    address TEXT,
    phone_type TEXT,
    phone_code TEXT,
    phone_number TEXT,
    auth_person_name TEXT,
    auth_person_position TEXT,
    details_json JSONB,
    CONSTRAINT fk_structure_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS financial_reports (
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    year SMALLINT NOT NULL,
    proceeds NUMERIC,
    profit NUMERIC,
    total_assets NUMERIC,
    current_assets_total NUMERIC,
    stocks NUMERIC,
    receivables NUMERIC,
    bankroll NUMERIC,
    uncurrent_assets_total NUMERIC,
    fixed_assets NUMERIC,
    total_liabilities NUMERIC,
    capitals NUMERIC,
    long_term_duties_total NUMERIC,
    long_term_duties_others NUMERIC,
    short_term_liabilities_total NUMERIC,
    borrowed_funds NUMERIC,
    accounts_payable NUMERIC,
    sustainability NUMERIC,
    solvency NUMERIC,
    profitability NUMERIC,
    PRIMARY KEY (report_id, year),
    CONSTRAINT fk_financial_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS risk_factors (
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    sign TEXT NOT NULL CHECK (sign IN ('positive','negative')),
    item_index INTEGER NOT NULL,
    code TEXT,
    name TEXT,
    chapter TEXT,
    PRIMARY KEY (report_id, sign, item_index),
    CONSTRAINT fk_risk_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS arbitration (
    id BIGSERIAL PRIMARY KEY,
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('yearly','status')),
    year SMALLINT,
    role TEXT NOT NULL CHECK (role IN ('all','plaintiff','defendant')),
    case_status TEXT NOT NULL CHECK (case_status IN ('all','finished','appealed','pending')),
    case_count INTEGER,
    amount NUMERIC,
    CONSTRAINT fk_arbitration_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS legal_events (
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('execution','inspection','license')),
    item_index INTEGER NOT NULL,
    external_id TEXT,
    event_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    active BOOLEAN,
    status TEXT,
    amount NUMERIC,
    title TEXT,
    authority TEXT,
    form TEXT,
    details_json JSONB,
    PRIMARY KEY (report_id, event_type, item_index),
    CONSTRAINT fk_legal_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS procurements (
    report_id UUID NOT NULL,
    company_inn TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    year SMALLINT,
    federal_law_code TEXT,
    tender_admitted_count INTEGER,
    tender_winner_count INTEGER,
    contract_signed_count INTEGER,
    contract_signed_amount NUMERIC,
    PRIMARY KEY (report_id, item_index),
    CONSTRAINT fk_procurement_report_company
        FOREIGN KEY (report_id, company_inn)
        REFERENCES company_reports (report_id, inn)
        ON DELETE CASCADE
);

-- Indexes tailored to the six tools / common filters.
CREATE INDEX IF NOT EXISTS idx_company_reports_inn
    ON company_reports (inn);
CREATE INDEX IF NOT EXISTS idx_company_reports_risk
    ON company_reports (risk_level, zsk_risk_level);

CREATE INDEX IF NOT EXISTS idx_structure_company_type
    ON structure_items (company_inn, item_type);
CREATE INDEX IF NOT EXISTS idx_structure_related_inn
    ON structure_items (related_inn)
    WHERE related_inn IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_financial_company_year
    ON financial_reports (company_inn, year DESC);

CREATE INDEX IF NOT EXISTS idx_risk_company_sign
    ON risk_factors (company_inn, sign);
CREATE INDEX IF NOT EXISTS idx_risk_company_chapter
    ON risk_factors (company_inn, chapter);

CREATE INDEX IF NOT EXISTS idx_arbitration_company
    ON arbitration (company_inn, source, role, case_status);
CREATE INDEX IF NOT EXISTS idx_arbitration_company_year
    ON arbitration (company_inn, year DESC)
    WHERE year IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_company_type
    ON legal_events (company_inn, event_type);
CREATE INDEX IF NOT EXISTS idx_legal_execution_active
    ON legal_events (company_inn, active)
    WHERE event_type = 'execution';
CREATE INDEX IF NOT EXISTS idx_legal_event_date
    ON legal_events (company_inn, event_type, event_date DESC);

CREATE INDEX IF NOT EXISTS idx_procurements_company_year
    ON procurements (company_inn, year DESC);
