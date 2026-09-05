export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN';

export interface CounterpartyPreview {
  inn: string;
  name: string;
  status: string | null;
  risk_level: RiskLevel | null;
  kpp: string | null;
}

export interface SourceReportResponse {
  inn: string;
  report: Record<string, unknown>;
}

export interface Evidence {
  field: string;
  value: unknown;
}

export interface RiskFactor {
  title: string;
  detail: string;
  severity: RiskLevel;
  evidence: Evidence[];
}

export interface Observation {
  code: string;
  title: string;
  detail: string;
  evidence: Evidence[];
}

export interface ChapterResult {
  chapter: string;
  risk_level: RiskLevel;
  conclusion: string;
  factors: RiskFactor[];
  observations: Observation[];
  evidence: Evidence[];
  data_sufficient: boolean;
  error: string | null;
}

export interface FactorSummaryItem {
  chapter: string;
  label: string;
  status: RiskLevel;
  details: string[];
}

export interface CompanyProfile {
  inn: string;
  kpp: string | null;
  ogrn: string | null;
  short_name: string | null;
  full_name: string | null;
  status: string | null;
  bank_risk_level: RiskLevel | null;
  director_name: string | null;
  director_position: string | null;
  share_capital: number | null;
  staff: string | null;
  founders_count: number;
  registration_date: string | null;
  address: string | null;
  company_size: string | null;
  account_blocking: string | null;
}

export interface FinancialChartPoint {
  year: number;
  revenue: number | null;
  profit: number | null;
  assets: number | null;
  obligations: number | null;
}

export interface LegalChartPoint {
  year: number;
  courts: number;
  enforcements: number;
}

export interface VisualizationData {
  financials: FinancialChartPoint[];
  legal_dynamics: LegalChartPoint[];
}

export interface Analysis {
  analysis_id: string;
  inn: string;
  summary: string;
  risk_level: RiskLevel;
  chapters: ChapterResult[];
  factor_summary: FactorSummaryItem[];
  company_profile: CompanyProfile | null;
  visualization_data: VisualizationData;
}

export interface BatchAnalysisItem {
  inn: string;
  status: 'success' | 'not_found' | 'error';
  analysis: Analysis | null;
  error: string | null;
}

export interface BatchAnalysisResponse {
  chat_id: string | null;
  results: BatchAnalysisItem[];
}

export interface ChatSource {
  inn: string;
  field: string;
  value: unknown;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
}

export interface ChatMessageResponse {
  chat_id: string;
  answer: string;
  sources: ChatSource[];
}
