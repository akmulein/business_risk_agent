import { useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import {
  AlertTriangle,
  ChevronDown,
  Sparkles,
  Trash2,
} from 'lucide-react';

import type {
  Analysis,
  BatchAnalysisItem,
  CounterpartyPreview,
  Evidence,
  RiskLevel,
} from '../types';
import { CHAPTER_TITLES, ReportCharts } from './Charts';
import { FactorSummary } from './FactorSummary';
import { RISK_STYLES, RiskBadge } from './RiskBadge';

interface ReportCardProps {
  preview: CounterpartyPreview;
  result?: BatchAnalysisItem;
  analyzing: boolean;
  companyCount: number;
  onRemove: () => void;
}

function formatCompanyStatus(value: string | null | undefined) {
  const status = value?.trim().toUpperCase();
  if (!status) return 'Статус не указан';
  if (['CURRENT', 'ACTIVE', 'ДЕЙСТВУЮЩАЯ', 'ДЕЙСТВУЮЩИЙ'].includes(status)) {
    return 'Действующая';
  }
  if (status.includes('BANKRUPT') || status.includes('БАНКРОТ')) return 'Банкротство';
  if (status.includes('REORGAN') || status.includes('РЕОРГАН')) return 'Реорганизация';
  if (status.includes('LIQUID') || status.includes('ЛИКВИД')) return 'Ликвидация';
  return value ?? 'Статус не указан';
}

function yearWord(years: number) {
  const lastTwo = years % 100;
  const last = years % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return 'лет';
  if (last === 1) return 'год';
  if (last >= 2 && last <= 4) return 'года';
  return 'лет';
}

function formatCompanyAge(value: string | null | undefined) {
  if (!value) return null;
  const registrationDate = new Date(value);
  if (Number.isNaN(registrationDate.getTime())) return null;
  const now = new Date();
  let years = now.getFullYear() - registrationDate.getFullYear();
  const anniversaryPassed =
    now.getMonth() > registrationDate.getMonth() ||
    (now.getMonth() === registrationDate.getMonth() &&
      now.getDate() >= registrationDate.getDate());
  if (!anniversaryPassed) years -= 1;
  return years > 0
    ? `зарегистрирована ${years} ${yearWord(years)} назад`
    : 'зарегистрирована менее года назад';
}

function extractRegion(address: string | null | undefined) {
  if (!address) return 'Регион не указан';
  const region = address
    .split(',')
    .map((part) => part.trim())
    .find((part) =>
      /(республика|область|край|автоном|москва|санкт-петербург|севастополь)/i.test(
        part,
      ),
    );
  return region || 'Регион не указан';
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (!evidence.length) {
    return <p className="text-sm text-[#777]">Дополнительные поля не указаны.</p>;
  }
  return (
    <dl className="space-y-2">
      {evidence.map((item, index) => (
        <div
          key={`${item.field}-${index}`}
          className="grid gap-1 rounded-xl bg-white px-3 py-2 text-xs sm:grid-cols-[minmax(160px,0.8fr)_1.2fr]"
        >
          <dt className="break-all text-[#777]">{item.field}</dt>
          <dd className="break-words font-medium text-[#222]">
            {typeof item.value === 'object'
              ? JSON.stringify(item.value, null, 2)
              : String(item.value ?? '—')}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const REPORT_SECTION_ORDER = ['general', 'reputation', 'legal', 'finance', 'structure'];

function FullReport({ analysis }: { analysis: Analysis }) {
  const chapters = analysis.chapters
    .filter((chapter) => chapter.chapter !== 'procurement')
    .sort((left, right) => {
      const leftIndex = REPORT_SECTION_ORDER.indexOf(left.chapter);
      const rightIndex = REPORT_SECTION_ORDER.indexOf(right.chapter);
      return (leftIndex < 0 ? Number.MAX_SAFE_INTEGER : leftIndex) -
        (rightIndex < 0 ? Number.MAX_SAFE_INTEGER : rightIndex);
    });

  return (
    <div className="space-y-5 border-t border-[#ededed] px-5 py-6 md:px-6">
      <section>
        <h3 className="mb-3 text-lg font-semibold text-[#111]">Подробности проверки</h3>
        <div className="space-y-3">
          {chapters.map((chapter) => (
            <details
              key={chapter.chapter}
              className="group overflow-hidden rounded-2xl border border-[#e5e5e5] bg-white"
            >
              <summary className="flex cursor-pointer list-none items-center gap-4 px-4 py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <ChevronDown
                    size={18}
                    className="shrink-0 transition-transform group-open:rotate-180"
                  />
                  <span className="font-semibold text-[#222]">
                    {CHAPTER_TITLES[chapter.chapter] ?? chapter.chapter}
                  </span>
                </div>
              </summary>

              <div className="space-y-4 border-t border-[#ededed] bg-[#fafafa] px-4 py-4">
                <p className="leading-6 text-[#333]">{chapter.conclusion}</p>

                {chapter.factors.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-[#333]">Факторы риска</h4>
                    {chapter.factors.map((factor, index) => (
                      <div key={index} className="rounded-xl bg-[#fff0ef] p-3">
                        <div className="flex items-center gap-2">
                          <AlertTriangle size={16} className="text-[#d52319]" />
                          <p className="text-sm font-semibold text-[#9d1811]">{factor.title}</p>
                        </div>
                        <p className="mt-1 text-sm leading-5 text-[#4a4a4a]">{factor.detail}</p>
                      </div>
                    ))}
                  </div>
                )}

                {chapter.observations.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-[#333]">
                      {chapter.chapter === 'reputation'
                        ? 'Факторы отчёта'
                        : 'Требует внимания'}
                    </h4>
                    {chapter.observations.map((observation) => (
                      <div
                        key={observation.code}
                        className={`rounded-xl p-3 ${
                          chapter.chapter === 'reputation'
                            ? 'bg-[#f3f3f3]'
                            : 'bg-[#fff8df]'
                        }`}
                      >
                        <p className="text-sm font-semibold text-[#6c5300]">
                          {observation.title}
                        </p>
                        <p className="mt-1 text-sm leading-5 text-[#4a4a4a]">
                          {observation.detail}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                <details className="rounded-xl border border-[#dedede] bg-[#f3f3f3]">
                  <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-[#444]">
                    Показать исходные данные
                  </summary>
                  <div className="border-t border-[#dedede] p-3">
                    <EvidenceList
                      evidence={[
                        ...chapter.evidence,
                        ...chapter.factors.flatMap((item) => item.evidence),
                        ...chapter.observations.flatMap((item) => item.evidence),
                      ]}
                    />
                  </div>
                </details>
              </div>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ReportCard({
  preview,
  result,
  analyzing,
  companyCount,
  onRemove,
}: ReportCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const analysis = result?.analysis;
  const profile = analysis?.company_profile;
  const riskLevel: RiskLevel =
    profile?.bank_risk_level ?? preview.risk_level ?? 'UNKNOWN';
  const style = RISK_STYLES[riskLevel];

  const director = profile?.director_name
    ? [profile.director_position, profile.director_name].filter(Boolean).join(' ')
    : null;
  const region = extractRegion(profile?.address);
  const companyAge = formatCompanyAge(profile?.registration_date);
  const companyStatus = formatCompanyStatus(profile?.status ?? preview.status);

  return (
    <article
      className={`overflow-hidden rounded-3xl border border-[#e6e6e6] border-l-4 bg-white shadow-[0_12px_36px_rgba(0,0,0,0.06)] ${style.border}`}
    >
      <div className="p-5 md:p-6">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold uppercase tracking-[-0.02em] text-[#111]">
              {profile?.short_name || preview.name}
            </h2>
            <p className="mt-1 text-xs uppercase leading-5 text-[#777] sm:text-sm">
              ИНН {preview.inn}
              {profile
                ? ` · ${region}`
                : preview.kpp
                  ? ` · КПП ${preview.kpp}`
                  : ''}
              {director ? ` · ${director}` : ''}
            </p>
            {profile && (
              <p className="mt-2 text-sm text-[#555]">
                {companyStatus}
                {companyAge ? ` · ${companyAge}` : ''}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <RiskBadge level={riskLevel} />
            <button
              type="button"
              disabled={analyzing}
              onClick={onRemove}
              aria-label="Удалить компанию из проверки"
              className="rounded-full p-2 text-[#777] transition hover:bg-[#f2f2f2] hover:text-[#111] disabled:opacity-40"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </header>

        {analyzing && !result && (
          <div className="mt-5 space-y-3">
            <div className="h-16 animate-pulse rounded-2xl bg-[#f1f1f1]" />
            <div className="h-28 animate-pulse rounded-2xl bg-[#f1f1f1]" />
            <p className="text-sm text-[#777]">Анализ отчета...</p>
          </div>
        )}

        {!analyzing && !result && (
          <div className="mt-5 rounded-2xl border border-dashed border-[#d7d7d7] bg-[#fafafa] px-4 py-5 text-sm text-[#666]">
            Компания добавлена. Запустите общую проверку выбранных контрагентов.
          </div>
        )}

        {result && result.status !== 'success' && (
          <div className="mt-5 rounded-2xl bg-[#fff0ef] p-4 text-sm text-[#9d1811]">
            {result.error || 'Не удалось сформировать отчёт'}
          </div>
        )}

        {analysis && profile && (
          <>
            <FactorSummary chapters={analysis.chapters} />

            <section className="mt-5 rounded-2xl bg-[#f2f5f9] p-5">
              <div className="flex items-center gap-2 text-[#333]">
                <Sparkles size={19} className="text-[#ef3124]" />
                <h3 className="font-semibold">
                  {companyCount === 1 ? 'Анализ контрагента' : 'Анализ контрагентов'}
                </h3>
              </div>
              <p className="mt-3 whitespace-pre-line leading-7 text-[#303030]">
                {analysis.summary}
              </p>
            </section>

            <div className="mt-5">
              <ReportCharts
                data={analysis.visualization_data ?? { financials: [], procurements: [] }}
              />
            </div>

            <div className="mt-5">
              <Button view="primary" size={48} onClick={() => setIsOpen((value) => !value)}>
                {isOpen ? 'Свернуть полный отчёт' : 'Открыть полный отчёт'}
              </Button>
            </div>
          </>
        )}
      </div>

      {analysis && profile && isOpen && (
        <FullReport analysis={analysis} />
      )}
    </article>
  );
}
