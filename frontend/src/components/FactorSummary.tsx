import type { FactorSummaryItem, RiskLevel } from '../types';

const STATUS_DOT: Record<RiskLevel, string> = {
  HIGH: 'bg-[#d52319]',
  MEDIUM: 'bg-[#e59b00]',
  LOW: 'bg-[#2e9b57]',
  UNKNOWN: 'bg-[#a4a4a4]',
};

export function FactorSummary({ items }: { items: FactorSummaryItem[] }) {
  if (items.length === 0) return null;

  return (
    <section className="mt-5">
      <div className="overflow-hidden rounded-2xl border border-[#e7e7e7]">
        <div className="divide-y divide-[#ededed]">
          {items.map((item) => (
            <div
              key={item.chapter}
              className="grid grid-cols-[minmax(0,1fr)_16px] gap-3 bg-white px-4 py-4 md:grid-cols-[170px_20px_minmax(0,1fr)] md:items-start md:gap-3"
            >
              <span className="font-medium text-[#222]">{item.label}</span>
              <div className="flex h-6 items-center justify-center">
                <span
                  aria-label={`Статус: ${item.status}`}
                  className={`h-3 w-3 rounded-full ${STATUS_DOT[item.status]}`}
                />
              </div>
              {item.details.length === 1 ? (
                <p className="col-span-2 text-sm leading-6 text-[#444] md:col-span-1">
                  {item.details[0]}
                </p>
              ) : (
                <ul className="col-span-2 space-y-2 text-sm leading-6 text-[#444] md:col-span-1">
                  {item.details.map((detail) => (
                    <li
                      key={detail}
                      className="relative pl-4 before:absolute before:left-0 before:content-['•']"
                    >
                      {detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
