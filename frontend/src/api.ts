import { MOCK_ANALYSIS, MOCK_PREVIEW, mockChatAnswer } from './mockData';
import type {
  BatchAnalysisResponse,
  ChatMessageResponse,
  CounterpartyPreview,
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
    return {
      chat_id: MOCK_ANALYSIS.chat_id,
      results: inns.map((inn, index) => {
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
      }),
    };
  }
  return request<BatchAnalysisResponse>('/api/v1/analyses', {
    method: 'POST',
    body: JSON.stringify({ inns }),
  });
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
