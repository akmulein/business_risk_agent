import type {
  BatchAnalysisResponse,
  ChatMessageResponse,
  CounterpartyPreview,
} from './types';

export const MOCK_PREVIEW: CounterpartyPreview = {
  inn: '7325145393',
  name: 'ООО «ЗЕБРЕЙНС»',
  status: 'CURRENT',
  risk_level: 'MEDIUM',
  kpp: '732501001',
};

export const MOCK_SOURCE_REPORT: Record<string, unknown> = {
  reportDate: '2025-12-31',
  baseInfo: {
    inn: '7325145393',
    kpp: '732501001',
    ogrn: '1167325059000',
    shortName: 'ООО «ЗЕБРЕЙНС»',
    fullName: 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ЗЕБРЕЙНС»',
    address: 'г. Ульяновск',
    riskLevel: 'MEDIUM',
    registrationInfo: {
      registrationDate: '2016-05-10',
      yearsFromRegistration: 9,
    },
  },
  status: { status: 'CURRENT' },
  foundersInfo: {
    shareCapital: 10000,
    authPerson: {
      name: 'ЗАЙНЕЕВ РАМИЛЬ РИНАТОВИЧ',
      positionName: 'ГЕНЕРАЛЬНЫЙ ДИРЕКТОР',
    },
  },
  finReports: [
    { common: { year: 2025, proceeds: 278000000, profit: 16100000 } },
  ],
};

export const MOCK_ANALYSIS: BatchAnalysisResponse = {
  chat_id: 'mock-chat',
  results: [
    {
      inn: '7325145393',
      status: 'success',
      error: null,
      analysis: {
        analysis_id: 'mock-analysis',
        inn: '7325145393',
        risk_level: 'MEDIUM',
        summary:
          'Компания ведёт деятельность более восьми лет и сохраняет действующий статус. Финансовые показатели демонстрируют рост выручки, однако в последнем периоде увеличилась долговая нагрузка. Существенных юридических ограничений в доступных данных не обнаружено.',
        factor_summary: [
          {
            chapter: 'reputation',
            label: 'Критические флаги',
            status: 'LOW',
            details: ['Критических факторов в отчёте не указано.'],
          },
          {
            chapter: 'legal',
            label: 'Суды и взыскания',
            status: 'LOW',
            details: ['Существенных юридических ограничений не обнаружено.'],
          },
          {
            chapter: 'finance',
            label: 'Финансы',
            status: 'MEDIUM',
            details: ['В последнем периоде увеличилась долговая нагрузка.'],
          },
          {
            chapter: 'structure',
            label: 'Руководство',
            status: 'LOW',
            details: ['Руководитель и состав учредителей определены.'],
          },
        ],
        company_profile: {
          inn: '7325145393',
          kpp: '732501001',
          ogrn: '1167325059000',
          short_name: 'ООО «ЗЕБРЕЙНС»',
          full_name: 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ЗЕБРЕЙНС»',
          status: 'CURRENT',
          bank_risk_level: 'MEDIUM',
          director_name: 'ЗАЙНЕЕВ РАМИЛЬ РИНАТОВИЧ',
          director_position: 'ГЕНЕРАЛЬНЫЙ ДИРЕКТОР',
          share_capital: 10000,
          staff: '196',
          founders_count: 7,
          registration_date: '2016-05-10',
          address: 'г. Ульяновск',
          company_size: 'Среднее предприятие',
          account_blocking: 'Нет сведений о приостановке операций',
        },
        visualization_data: {
          financials: [
            { year: 2023, revenue: 184000000, profit: 14200000, assets: 96000000, obligations: 51000000 },
            { year: 2024, revenue: 231000000, profit: 18800000, assets: 121000000, obligations: 68000000 },
            { year: 2025, revenue: 278000000, profit: 16100000, assets: 149000000, obligations: 97000000 },
          ],
          legal_dynamics: [
            { year: 2023, courts: 2, enforcements: 1 },
            { year: 2024, courts: 4, enforcements: 2 },
            { year: 2025, courts: 3, enforcements: 5 },
          ],
        },
        chapters: [
          {
            chapter: 'general',
            risk_level: 'LOW',
            conclusion: 'Компания зарегистрирована и имеет действующий статус.',
            factors: [],
            observations: [],
            evidence: [
              { field: 'company_reports.status', value: 'CURRENT' },
              { field: 'company_reports.registration_date', value: '2016-05-10' },
            ],
            data_sufficient: true,
            error: null,
          },
          {
            chapter: 'structure',
            risk_level: 'LOW',
            conclusion: 'Руководитель и состав учредителей определены.',
            factors: [],
            observations: [],
            evidence: [{ field: 'structure_items.director', value: 'ЗАЙНЕЕВ РАМИЛЬ РИНАТОВИЧ' }],
            data_sufficient: true,
            error: null,
          },
          {
            chapter: 'legal',
            risk_level: 'LOW',
            conclusion: 'Существенных юридических ограничений не обнаружено.',
            factors: [],
            observations: [],
            evidence: [],
            data_sufficient: true,
            error: null,
          },
          {
            chapter: 'reputation',
            risk_level: 'LOW',
            conclusion: 'Негативных репутационных факторов не выявлено.',
            factors: [],
            observations: [],
            evidence: [],
            data_sufficient: true,
            error: null,
          },
          {
            chapter: 'finance',
            risk_level: 'MEDIUM',
            conclusion: 'Выручка растёт, долговая нагрузка требует внимания.',
            factors: [],
            observations: [
              {
                code: 'leverage',
                title: 'Рост обязательств',
                detail: 'Обязательства выросли быстрее активов в последнем отчётном периоде.',
                evidence: [
                  { field: 'financial_reports[2].total_liabilities', value: 97000000 },
                ],
              },
            ],
            evidence: [],
            data_sufficient: true,
            error: null,
          },
          {
            chapter: 'procurement',
            risk_level: 'LOW',
            conclusion: 'Компания регулярно участвует в закупках и заключает контракты.',
            factors: [],
            observations: [],
            evidence: [],
            data_sufficient: true,
            error: null,
          },
        ],
      },
    },
  ],
};

export function mockChatAnswer(message: string): ChatMessageResponse {
  return {
    chat_id: 'mock-chat',
    answer: message.toLowerCase().includes('выруч')
      ? 'Выручка выросла с 184 млн ₽ в 2023 году до 278 млн ₽ в 2025 году.'
      : 'По доступным данным существенных дополнительных рисков не обнаружено.',
    sources: [
      {
        inn: '7325145393',
        field: 'financial_reports',
        value: 'Данные отчётности за 2023–2025 годы',
      },
    ],
  };
}
