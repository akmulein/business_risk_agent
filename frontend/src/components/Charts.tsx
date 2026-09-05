import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { VisualizationData } from '../types';

const compactNumber = new Intl.NumberFormat('ru-RU', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

function EmptyChart({ children }: { children: string }) {
  return (
    <div className="flex h-56 items-center justify-center rounded-2xl border border-dashed border-[#d8d8d8] bg-[#fafafa] px-5 text-center text-sm text-[#777]">
      {children}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-[#ededed] bg-white p-4">
      <h4 className="mb-4 font-semibold text-[#222]">{title}</h4>
      {children}
    </section>
  );
}

export function ReportCharts({ data }: { data: VisualizationData }) {
  const profitData = data.financials.filter((item) => item.profit !== null);
  const revenueData = data.financials.filter((item) => item.revenue !== null);
  const balanceData = data.financials.filter(
    (item) => item.assets !== null || item.obligations !== null,
  );
  const legalData = data.legal_dynamics ?? [];

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartCard title="Прибыль">
        {profitData.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={profitData}>
                <CartesianGrid stroke="#ececec" strokeDasharray="4 4" />
                <XAxis dataKey="year" tick={{ fill: '#777', fontSize: 12 }} />
                <YAxis
                  tickFormatter={(value) => compactNumber.format(value)}
                  tick={{ fill: '#777', fontSize: 12 }}
                  width={54}
                />
                <Tooltip
                  formatter={(value) =>
                    typeof value === 'number'
                      ? `${compactNumber.format(value)} ₽`
                      : String(value ?? '')
                  }
                />
                <Line type="monotone" dataKey="profit" name="Прибыль" stroke="#2e9b57" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет данных о прибыли</EmptyChart>
        )}
      </ChartCard>

      <ChartCard title="Выручка">
        {revenueData.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={revenueData}>
                <CartesianGrid stroke="#ececec" strokeDasharray="4 4" />
                <XAxis dataKey="year" tick={{ fill: '#777', fontSize: 12 }} />
                <YAxis
                  tickFormatter={(value) => compactNumber.format(value)}
                  tick={{ fill: '#777', fontSize: 12 }}
                  width={54}
                />
                <Tooltip
                  formatter={(value) =>
                    typeof value === 'number'
                      ? `${compactNumber.format(value)} ₽`
                      : String(value ?? '')
                  }
                />
                <Line type="monotone" dataKey="revenue" name="Выручка" stroke="#111111" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет данных о выручке</EmptyChart>
        )}
      </ChartCard>

      <ChartCard title="Активы и обязательства">
        {balanceData.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={balanceData}>
                <CartesianGrid stroke="#ececec" strokeDasharray="4 4" />
                <XAxis dataKey="year" tick={{ fill: '#777', fontSize: 12 }} />
                <YAxis
                  tickFormatter={(value) => compactNumber.format(value)}
                  tick={{ fill: '#777', fontSize: 12 }}
                  width={54}
                />
                <Tooltip
                  formatter={(value) =>
                    typeof value === 'number'
                      ? `${compactNumber.format(value)} ₽`
                      : String(value ?? '')
                  }
                />
                <Legend />
                <Line type="monotone" dataKey="assets" name="Активы" stroke="#111111" strokeWidth={3} />
                <Line type="monotone" dataKey="obligations" name="Обязательства" stroke="#ef3124" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет данных об активах и обязательствах</EmptyChart>
        )}
      </ChartCard>

      <ChartCard title="Динамика судов и взысканий">
        {legalData.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={legalData}>
                <CartesianGrid stroke="#ececec" strokeDasharray="4 4" />
                <XAxis dataKey="year" tick={{ fill: '#777', fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#777', fontSize: 12 }} width={36} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="courts" name="Суды" stroke="#111111" strokeWidth={3} />
                <Line type="monotone" dataKey="enforcements" name="Исполнительные производства" stroke="#ef3124" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет данных о судах и взысканиях</EmptyChart>
        )}
      </ChartCard>
    </div>
  );
}

export const CHAPTER_TITLES: Record<string, string> = {
  general: 'Статус компании',
  reputation: 'Критические красные флаги и налоги',
  legal: 'Судебные риски',
  finance: 'Финансовое состояние',
  structure: 'Возраст, руководство и связанные лица',
  procurement: 'Госзакупки',
};
