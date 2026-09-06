import { MOCK_ANALYSIS, MOCK_PREVIEW, MOCK_SOURCE_REPORT, mockChatAnswer } from './mockData';
import type {
  BatchAnalysisResponse,
  ChatMessageResponse,
  CounterpartyPreview,
  SourceReportResponse,
} from './types';

const useMocks = import.meta.env.VITE_USE_MOCKS === 'true';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? 'Не удалось выполнить запрос', response.status);
  }
  return response.json() as Promise<T>;
}

export async function findCounterparty(
  inn: string,
  signal?: AbortSignal,
): Promise<CounterpartyPreview> {
  if (useMocks) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    return { ...MOCK_PREVIEW, inn };
  }
  return request<CounterpartyPreview>(
    `/api/v1/counterparties/${encodeURIComponent(inn)}/preview`,
    { signal },
  );
}

export async function analyzeCounterparties(
  inns: string[],
): Promise<BatchAnalysisResponse> {
  if (useMocks) {
    await new Promise((resolve) => window.setTimeout(resolve, 900));
    const template = MOCK_ANALYSIS.results[0];
    const results = inns.map((inn, index) => {
      const item = structuredClone(template);
      item.inn = inn;
      if (item.analysis) {
        item.analysis.inn = inn;
        item.analysis.analysis_id = `mock-analysis-${index + 1}`;
        if (item.analysis.company_profile) {
          item.analysis.company_profile.inn = inn;
        }
      }
      return item;
    });
    return {
      chat_id: MOCK_ANALYSIS.chat_id,
      comparison: inns.length > 1
        ? {
            summary: 'Компании имеют средний уровень риска. Показатели сформированы только по данным их отчётов.',
            summary_error: null,
            companies: inns.map((inn, index) => ({
              rank: index + 1,
              inn,
              name: `ООО «КОМПАНИЯ ${index + 1}»`,
              risk_level: 'MEDIUM',
              financial_year: 2025,
              revenue: 278000000 - index * 42000000,
              profit: 16100000 - index * 2500000,
              assets: 149000000 - index * 18000000,
              capital: 52000000 - index * 5000000,
              short_term_liabilities: 68000000 + index * 4000000,
              revenue_change_percent: 6.2 - index * 3.1,
              defendant_cases: index,
              active_enforcements: index * 2,
              fns_status: 'OK',
              bankruptcy_status: 'OK',
            })),
          }
        : null,
      results,
    };
  }
  return request<BatchAnalysisResponse>('/api/v1/analyses', {
    method: 'POST',
    body: JSON.stringify({ inns }),
  });
}

export async function getSourceReport(inn: string): Promise<SourceReportResponse> {
  if (useMocks) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    return { inn, report: structuredClone(MOCK_SOURCE_REPORT) };
  }
  return request<SourceReportResponse>(
    `/api/v1/counterparties/${encodeURIComponent(inn)}/report`,
  );
}

export async function sendChatMessage(
  chatId: string,
  message: string,
): Promise<ChatMessageResponse> {
  if (useMocks) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    return mockChatAnswer(message);
  }
  return request<ChatMessageResponse>(`/api/v1/chats/${chatId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export async function clearChat(chatId: string): Promise<void> {
  if (useMocks) {
    return;
  }
  await request(`/api/v1/chats/${chatId}/messages`, { method: 'DELETE' });
}
