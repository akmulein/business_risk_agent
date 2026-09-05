import type { ChapterResult, RiskLevel } from '../types';

interface FactorSpec {
  chapter: string;
  label: string;
}

const FACTOR_SPECS: FactorSpec[] = [
  { chapter: 'reputation', label: 'Критические флаги и налоги' },
  { chapter: 'legal', label: 'Суды и взыскания' },
  { chapter: 'finance', label: 'Финансы' },
  { chapter: 'structure', label: 'Руководство и связи' },
];

const STATUS_DOT: Record<RiskLevel, string> = {
  HIGH: 'bg-[#d52319]',
  MEDIUM: 'bg-[#e59b00]',
  LOW: 'bg-[#2e9b57]',
  UNKNOWN: 'bg-[#a4a4a4]',
};

const RISK_RANK: Record<RiskLevel, number> = {
  UNKNOWN: 0,
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
};

function factorStatus(chapter: ChapterResult): RiskLevel {
  if (chapter.chapter === 'reputation') {
    if (!chapter.data_sufficient || chapter.error) return 'UNKNOWN';
    return chapter.observations.some((observation) =>
      observation.detail.includes('Негативные:'),
    )
      ? 'HIGH'
      : 'LOW';
  }
  if (chapter.factors.length > 0) {
    return chapter.factors.reduce<RiskLevel>(
      (highest, factor) =>
        RISK_RANK[factor.severity] > RISK_RANK[highest]
          ? factor.severity
          : highest,
      'LOW',
    );
  }
  if (chapter.observations.length > 0) return 'MEDIUM';
  if (!chapter.data_sufficient || chapter.error) return 'UNKNOWN';
  return 'LOW';
}

function factorDescription(chapter: ChapterResult) {
  if (chapter.chapter === 'reputation') {
    const negative = chapter.observations.find((observation) =>
      observation.detail.includes('Негативные:'),
    );
    return negative ? negative.detail : chapter.conclusion;
  }
  const first = chapter.factors[0] ?? chapter.observations[0];
  if (!first) return chapter.conclusion;
  const additional = chapter.factors.length + chapter.observations.length - 1;
  return `${first.title}.${additional > 0 ? ` Ещё замечаний: ${additional}.` : ''}`;
}

export function FactorSummary({ chapters }: { chapters: ChapterResult[] }) {
  const chaptersByName = new Map(chapters.map((chapter) => [chapter.chapter, chapter]));
  const rows = FACTOR_SPECS.flatMap((spec) => {
    const chapter = chaptersByName.get(spec.chapter);
    return chapter ? [{ spec, chapter }] : [];
  });

  if (rows.length === 0) return null;

  return (
    <section className="mt-5">
      <div className="overflow-hidden rounded-2xl border border-[#e7e7e7]">
        <div className="divide-y divide-[#ededed]">
          {rows.map(({ spec, chapter }) => {
            const status = factorStatus(chapter);
            return (
              <div
                key={spec.chapter}
                className="grid grid-cols-[minmax(0,1fr)_16px] gap-3 bg-white px-4 py-4 md:grid-cols-[minmax(180px,0.7fr)_24px_minmax(260px,1.3fr)] md:items-start md:gap-4"
              >
                <span className="font-medium text-[#222]">{spec.label}</span>
                <div className="flex h-6 items-center justify-center">
                  <span
                    aria-label={`Статус: ${status}`}
                    className={`h-3 w-3 rounded-full ${STATUS_DOT[status]}`}
                  />
                </div>
                <p className="col-span-2 text-sm leading-6 text-[#444] md:col-span-1">
                  {factorDescription(chapter)}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
