import { useMemo, useState } from 'react';
import {
  ArrowDown,
  CircleCheck,
  Minus,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type {
  BatchComparison,
  ComparisonCompany,
  RiskLevel,
  VerificationStatus,
} from '../types';

type FinanceMetric = 'revenue' | 'profit' | 'assets' | 'capital';

const METRICS: { key: FinanceMetric; label: string }[] = [
  { key: 'revenue', label: 'Выручка' },
  { key: 'profit', label: 'Прибыль' },
  { key: 'assets', label: 'Активы' },
  { key: 'capital', label: 'Капитал' },
];

const money = new Intl.NumberFormat('ru-RU', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

const exactMoney = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
});

const RISK_DOTS: Record<RiskLevel, { color: string; label: string }> = {
  LOW: { color: 'bg-[#27a35a]', label: 'Низкий риск' },
  MEDIUM: { color: 'bg-[#f2b705]', label: 'Средний риск' },
  HIGH: { color: 'bg-[#ef3124]', label: 'Высокий риск' },
  UNKNOWN: { color: 'bg-[#a3a3a3]', label: 'Нет оценки' },
};

function formatMoney(value: number | null) {
  return value === null ? '—' : `${money.format(value)} ₽`;
}

function formatPercent(value: number | null) {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toLocaleString('ru-RU')}%`;
}

function RiskDot({ level }: { level: RiskLevel }) {
  const risk = RISK_DOTS[level];
  return (
    <span
      className="flex justify-center"
      title={risk.label}
      aria-label={risk.label}
    >
      <span className={`h-3 w-3 rounded-full ${risk.color}`} />
    </span>
  );
}

function NumericValue({
  value,
  children,
}: {
  value: number | null;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex items-center justify-end gap-1">
      {value !== null && value < 0 && (
        <ArrowDown size={13} strokeWidth={1.5} className="text-[#d52218]" />
      )}
      {children}
    </span>
  );
}

function StatusIcon({ status }: { status: VerificationStatus }) {
  if (status === 'OK') {
    return (
      <span title="Признаков риска в отчёте нет" aria-label="Признаков риска в отчёте нет">
        <CircleCheck size={19} className="text-[#219653]" />
      </span>
    );
  }
  if (status === 'ISSUE') {
    return (
      <span title="В отчёте есть замечание" aria-label="В отчёте есть замечание">
        <TriangleAlert size={19} className="text-[#d69200]" />
      </span>
    );
  }
  return (
    <span title="Нет данных" aria-label="Нет данных">
      <Minus size={19} className="text-[#999]" />
    </span>
  );
}

function ChartEmpty({ children }: { children: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-2xl bg-[#fafafa] px-4 text-center text-sm text-[#777]">
      {children}
    </div>
  );
}

function shortName(company: ComparisonCompany) {
  return company.name.length > 24
    ? `${company.name.slice(0, 22)}…`
    : company.name;
}

export function ComparisonDashboard({ comparison }: { comparison: BatchComparison }) {
  const [metric, setMetric] = useState<FinanceMetric>('revenue');
  const financeData = useMemo(
    () =>
      comparison.companies
        .filter((company) => company[metric] !== null)
        .map((company) => ({
          name: shortName(company),
          value: company[metric],
        })),
    [comparison.companies, metric],
  );
  const legalData = useMemo(
    () =>
      comparison.companies
        .filter(
          (company) =>
            company.defendant_cases !== null || company.active_enforcements !== null,
        )
        .map((company) => ({
          name: shortName(company),
          courts: company.defendant_cases,
          enforcements: company.active_enforcements,
        })),
    [comparison.companies],
  );
  const chartHeight = Math.max(260, comparison.companies.length * 48 + 80);

  return (
    <section className="space-y-5">
      <section className="surface-shadow rounded-3xl bg-[#eef2f6] p-5 md:p-6">
        <div className="flex items-center gap-2 text-[#333]">
          <Sparkles size={19} className="text-[#ef3124]" />
          <h2 className="font-semibold">Анализ контрагентов</h2>
        </div>
        {comparison.summary ? (
          <p className="mt-3 leading-7 text-[#303030]">{comparison.summary}</p>
        ) : (
          <p className="mt-3 text-sm text-[#777]">
            {comparison.summary_error || 'Сравнительный анализ временно недоступен'}
          </p>
        )}
      </section>

      <section className="surface-shadow overflow-hidden rounded-3xl border border-[#e6e6e6] bg-white">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[850px] border-collapse text-left text-sm">
            <thead className="bg-[#f6f6f6] text-xs uppercase tracking-wide text-[#777]">
              <tr>
                <th className="px-5 py-4 font-medium">Контрагент</th>
                <th className="px-4 py-4 font-medium">Риск</th>
                <th className="px-4 py-4 text-right font-medium">Выручка</th>
                <th className="px-4 py-4 text-right font-medium">Прибыль</th>
                <th className="px-4 py-4 text-right font-medium">Суды ответчика</th>
                <th className="px-4 py-4 text-right font-medium">Действующие ИП</th>
                <th className="px-4 py-4 text-center font-medium">ФНС</th>
                <th className="px-4 py-4 text-center font-medium">Банкротство</th>
              </tr>
            </thead>
            <tbody>
              {comparison.companies.map((company) => (
                <tr key={company.inn} className="border-t border-[#ededed]">
                  <td className="px-5 py-4">
                    <span className="font-semibold text-[#222]">{company.name}</span>
                    <span className="mt-1 block text-xs text-[#777]">ИНН {company.inn}</span>
                  </td>
                  <td className="px-4 py-4"><RiskDot level={company.risk_level} /></td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.revenue}>{formatMoney(company.revenue)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.profit}>{formatMoney(company.profit)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">{company.defendant_cases ?? '—'}</td>
                  <td className="px-4 py-4 text-right tabular-nums">{company.active_enforcements ?? '—'}</td>
                  <td className="px-4 py-4"><span className="flex justify-center"><StatusIcon status={company.fns_status} /></span></td>
                  <td className="px-4 py-4"><span className="flex justify-center"><StatusIcon status={company.bankruptcy_status} /></span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="surface-shadow rounded-3xl border border-[#e6e6e6] bg-white p-5">
          <h3 className="font-semibold text-[#222]">Сравнение финансов</h3>
          <div className="mt-4 flex flex-wrap gap-2">
            {METRICS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setMetric(item.key)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  metric === item.key
                    ? 'bg-[#111] text-white'
                    : 'bg-[#ededed] text-[#555] hover:bg-[#dedede]'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-[#888]">Последний доступный отчётный год</p>
          {financeData.length ? (
            <div className="mt-2 w-full" style={{ height: chartHeight }}>
              <ResponsiveContainer>
                <BarChart data={financeData} layout="vertical" margin={{ left: 8, right: 18 }}>
                  <CartesianGrid stroke="#ececec" strokeDasharray="4 4" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money.format(value)} tick={{ fill: '#777', fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={126} tick={{ fill: '#555', fontSize: 11 }} />
                  <ReferenceLine x={0} stroke="#999" />
                  <Tooltip formatter={(value) => typeof value === 'number' ? `${exactMoney.format(value)} ₽` : '—'} />
                  <Bar dataKey="value" name={METRICS.find((item) => item.key === metric)?.label} fill="#111111" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4"><ChartEmpty>В отчётах нет данных по выбранному показателю</ChartEmpty></div>
          )}
        </section>

        <section className="surface-shadow rounded-3xl border border-[#e6e6e6] bg-white p-5">
          <h3 className="font-semibold text-[#222]">Суды и взыскания</h3>
          <p className="mt-3 text-xs text-[#888]">Текущие дела ответчика и действующие исполнительные производства</p>
          {legalData.length ? (
            <div className="mt-2 w-full" style={{ height: chartHeight }}>
              <ResponsiveContainer>
                <BarChart data={legalData} layout="vertical" margin={{ left: 8, right: 18 }}>
                  <CartesianGrid stroke="#ececec" strokeDasharray="4 4" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fill: '#777', fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={126} tick={{ fill: '#555', fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="courts" name="Суды ответчика" fill="#111111" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="enforcements" name="Действующие ИП" fill="#ef3124" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-4"><ChartEmpty>В отчётах нет сопоставимых данных о судах и взысканиях</ChartEmpty></div>
          )}
        </section>
      </div>

      <section className="surface-shadow overflow-hidden rounded-3xl border border-[#e6e6e6] bg-white">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] border-collapse text-left text-sm">
            <thead className="bg-[#f6f6f6] text-xs uppercase tracking-wide text-[#777]">
              <tr>
                <th className="px-5 py-4 font-medium">Контрагент</th>
                <th className="px-4 py-4 text-right font-medium">Активы</th>
                <th className="px-4 py-4 text-right font-medium">Капитал</th>
                <th className="px-4 py-4 text-right font-medium">Краткосрочные обязательства</th>
                <th className="px-4 py-4 text-right font-medium">Прибыль</th>
                <th className="px-4 py-4 text-right font-medium">Динамика выручки</th>
              </tr>
            </thead>
            <tbody>
              {comparison.companies.map((company) => (
                <tr key={company.inn} className="border-t border-[#ededed]">
                  <td className="px-5 py-4 font-semibold text-[#222]">{company.name}</td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.assets}>{formatMoney(company.assets)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.capital}>{formatMoney(company.capital)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.short_term_liabilities}>{formatMoney(company.short_term_liabilities)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.profit}>{formatMoney(company.profit)}</NumericValue>
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums">
                    <NumericValue value={company.revenue_change_percent}>{formatPercent(company.revenue_change_percent)}</NumericValue>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
