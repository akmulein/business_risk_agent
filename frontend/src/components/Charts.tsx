import {
  Bar,
  BarChart,
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
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartCard title="Выручка и прибыль">
        {data.financials.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <LineChart data={data.financials}>
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
                <Line type="monotone" dataKey="revenue" name="Выручка" stroke="#ef3124" strokeWidth={3} />
                <Line type="monotone" dataKey="profit" name="Прибыль" stroke="#111111" strokeWidth={3} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет финансовых данных для графика</EmptyChart>
        )}
      </ChartCard>

      <ChartCard title="Активы">
        {data.financials.length ? (
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <BarChart data={data.financials}>
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
                <Bar dataKey="assets" name="Активы" fill="#252525" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart>В отчёте нет данных об активах</EmptyChart>
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
