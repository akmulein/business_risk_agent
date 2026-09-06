import { useEffect, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  Trash2,
} from 'lucide-react';

import type {
  BatchAnalysisItem,
  CounterpartyPreview,
  RiskLevel,
} from '../types';
import { getSourceReport } from '../api';
import { ReportCharts } from './Charts';
import { FactorSummary } from './FactorSummary';
import { RISK_STYLES, RiskBadge } from './RiskBadge';
import { SourceReport } from './SourceReport';

interface ReportCardProps {
  preview: CounterpartyPreview;
  result?: BatchAnalysisItem;
  analyzing: boolean;
  collapsedByDefault: boolean;
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

export function ReportCard({
  preview,
  result,
  analyzing,
  collapsedByDefault,
  onRemove,
}: ReportCardProps) {
  const [isDetailsOpen, setIsDetailsOpen] = useState(!collapsedByDefault);
  const [isOpen, setIsOpen] = useState(false);
  const [sourceReport, setSourceReport] = useState<Record<string, unknown> | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const analysis = result?.analysis;
  const profile = analysis?.company_profile;
  const riskLevel: RiskLevel =
    profile?.bank_risk_level ?? preview.risk_level ?? 'UNKNOWN';
  const style = RISK_STYLES[riskLevel];

  useEffect(() => {
    setIsDetailsOpen(!collapsedByDefault);
  }, [collapsedByDefault, analysis?.analysis_id]);

  const director = profile?.director_name
    ? [profile.director_position, profile.director_name].filter(Boolean).join(' ')
    : null;
  const region = extractRegion(profile?.address);
  const companyAge = formatCompanyAge(profile?.registration_date);
  const companyStatus = formatCompanyStatus(profile?.status ?? preview.status);

  const toggleSourceReport = async () => {
    if (isOpen) {
      setIsOpen(false);
      return;
    }
    setIsOpen(true);
    if (sourceReport || reportLoading) return;
    setReportLoading(true);
    setReportError(null);
    try {
      const response = await getSourceReport(preview.inn);
      setSourceReport(response.report);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Не удалось загрузить полный отчёт');
    } finally {
      setReportLoading(false);
    }
  };

  return (
    <article
      className={`surface-shadow overflow-hidden rounded-3xl border border-[#e6e6e6] border-l-4 bg-white ${style.border}`}
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
            {analysis && profile && collapsedByDefault && (
              <button
                type="button"
                onClick={() => setIsDetailsOpen((current) => !current)}
                aria-expanded={isDetailsOpen}
                className="inline-flex items-center gap-1 rounded-full px-3 py-2 text-xs font-medium text-[#555] transition hover:bg-[#f2f2f2] hover:text-[#111]"
              >
                {isDetailsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                {isDetailsOpen ? 'Свернуть' : 'Развернуть отчёт'}
              </button>
            )}
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

        {isDetailsOpen && analyzing && !result && (
          <div className="mt-5 flex items-center gap-3 text-sm text-[#777]">
            <span className="shrink-0">Анализ отчета...</span>
            <span className="analysis-progress-track" aria-hidden="true">
              <span className="analysis-progress-value" />
            </span>
          </div>
        )}

        {isDetailsOpen && !analyzing && !result && (
          <div className="mt-5 rounded-2xl border border-dashed border-[#d7d7d7] bg-[#fafafa] px-4 py-5 text-sm text-[#666]">
            Компания добавлена. Запустите общую проверку выбранных контрагентов.
          </div>
        )}

        {isDetailsOpen && result && result.status !== 'success' && (
          <div className="mt-5 rounded-2xl bg-[#fff0ef] p-4 text-sm text-[#9d1811]">
            {result.error || 'Не удалось сформировать отчёт'}
          </div>
        )}

        {isDetailsOpen && analysis && profile && (
          <>
            <section className="mt-5 rounded-2xl bg-[#f2f5f9] p-5">
              <div className="flex items-center gap-2 text-[#333]">
                <Sparkles size={19} className="text-[#ef3124]" />
                <h3 className="font-semibold">Анализ контрагента</h3>
              </div>
              <p className="mt-3 whitespace-pre-line leading-7 text-[#303030]">
                {analysis.summary}
              </p>
            </section>

            <FactorSummary items={analysis.factor_summary ?? []} />

            <div className="mt-5">
              <ReportCharts
                data={analysis.visualization_data ?? { financials: [], legal_dynamics: [] }}
              />
            </div>

            <div className="mt-5">
              <Button view="primary" size={48} onClick={() => void toggleSourceReport()}>
                {isOpen ? 'Свернуть полный отчёт' : 'Открыть полный отчёт'}
              </Button>
            </div>
          </>
        )}
      </div>

      {analysis && profile && isOpen && (
        <SourceReport report={sourceReport} loading={reportLoading} error={reportError} />
      )}
    </article>
  );
}
