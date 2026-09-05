import { useState, type ReactNode } from 'react';
import { Button } from '@alfalab/core-components/button';
import {
  AlertTriangle,
  Building2,
  CalendarDays,
  ChevronDown,
  CircleDollarSign,
  FileText,
  Landmark,
  MapPin,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
  UsersRound,
} from 'lucide-react';

import type {
  Analysis,
  BatchAnalysisItem,
  CounterpartyPreview,
  Evidence,
  RiskLevel,
} from '../types';
import { CHAPTER_TITLES, ReportCharts } from './Charts';
import { RISK_STYLES, RiskBadge } from './RiskBadge';

interface ReportCardProps {
  preview: CounterpartyPreview;
  result?: BatchAnalysisItem;
  analyzing: boolean;
  onRemove: () => void;
}

const money = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

function formatDate(value: string | null | undefined) {
  if (!value) return 'Нет данных';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('ru-RU').format(date);
}

function valueOrFallback(value: ReactNode) {
  return value === null || value === undefined || value === '' ? 'Нет данных' : value;
}

function Fact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[24px_minmax(0,1fr)] gap-3 rounded-2xl bg-[#f7f7f7] p-4">
      <div className="mt-0.5 text-[#777]">{icon}</div>
      <div className="min-w-0">
        <dt className="text-xs leading-4 text-[#858585]">{label}</dt>
        <dd className="mt-1 break-words text-sm font-medium leading-5 text-[#222]">
          {valueOrFallback(value)}
        </dd>
      </div>
    </div>
  );
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

function FullReport({ analysis }: { analysis: Analysis }) {
  return (
    <div className="space-y-5 border-t border-[#ededed] px-5 py-6 md:px-6">
      <ReportCharts
        data={analysis.visualization_data ?? { financials: [], procurements: [] }}
        chapters={analysis.chapters}
      />

      <section>
        <h3 className="mb-3 text-lg font-semibold text-[#111]">Разделы проверки</h3>
        <div className="space-y-3">
          {analysis.chapters.map((chapter) => (
            <details
              key={chapter.chapter}
              className="group overflow-hidden rounded-2xl border border-[#e5e5e5] bg-white"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <ChevronDown
                    size={18}
                    className="shrink-0 transition-transform group-open:rotate-180"
                  />
                  <span className="font-semibold text-[#222]">
                    {CHAPTER_TITLES[chapter.chapter] ?? chapter.chapter}
                  </span>
                </div>
                <RiskBadge level={chapter.risk_level} />
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
                    <h4 className="text-sm font-semibold text-[#333]">Требует внимания</h4>
                    {chapter.observations.map((observation) => (
                      <div key={observation.code} className="rounded-xl bg-[#fff8df] p-3">
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

  return (
    <article
      className={`overflow-hidden rounded-3xl border border-[#e6e6e6] border-l-4 bg-white shadow-[0_12px_36px_rgba(0,0,0,0.06)] ${style.border}`}
    >
      <div className="p-5 md:p-6">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-[#111]">
                {profile?.short_name || preview.name}
              </h2>
              <RiskBadge level={riskLevel} />
            </div>
            <p className="mt-1 text-sm text-[#777]">
              ИНН {preview.inn}
              {profile?.kpp || preview.kpp ? ` · КПП ${profile?.kpp || preview.kpp}` : ''}
            </p>
          </div>
          <button
            type="button"
            disabled={analyzing}
            onClick={onRemove}
            aria-label="Удалить компанию из проверки"
            className="rounded-full p-2 text-[#777] transition hover:bg-[#f2f2f2] hover:text-[#111] disabled:opacity-40"
          >
            <Trash2 size={18} />
          </button>
        </header>

        {analyzing && !result && (
          <div className="mt-5 space-y-3">
            <div className="h-16 animate-pulse rounded-2xl bg-[#f1f1f1]" />
            <div className="h-28 animate-pulse rounded-2xl bg-[#f1f1f1]" />
            <p className="text-sm text-[#777]">Агенты анализируют полный отчёт…</p>
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
            <dl className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <Fact
                icon={<Building2 size={18} />}
                label="Полное юридическое наименование"
                value={profile.full_name}
              />
              <Fact
                icon={<UserRound size={18} />}
                label="Руководитель"
                value={director}
              />
              <Fact
                icon={<FileText size={18} />}
                label="ИНН / КПП"
                value={[profile.inn, profile.kpp].filter(Boolean).join(' / ')}
              />
              <Fact
                icon={<CircleDollarSign size={18} />}
                label="Уставный капитал"
                value={profile.share_capital === null ? null : money.format(profile.share_capital)}
              />
              <Fact
                icon={<UsersRound size={18} />}
                label="Численность персонала"
                value={profile.staff}
              />
              <Fact
                icon={<UsersRound size={18} />}
                label="Количество учредителей"
                value={profile.founders_count}
              />
              <Fact
                icon={<CalendarDays size={18} />}
                label="Дата регистрации"
                value={formatDate(profile.registration_date)}
              />
              <Fact
                icon={<ShieldCheck size={18} />}
                label="Блокировка банковских счетов"
                value={profile.account_blocking}
              />
              <Fact
                icon={<Landmark size={18} />}
                label="Реестр МСП"
                value={profile.company_size}
              />
              <Fact
                icon={<MapPin size={18} />}
                label="Юридический адрес"
                value={profile.address}
              />
            </dl>

            <section className="mt-5 rounded-2xl border border-[#e1e6ed] bg-[#f2f5f9] p-5">
              <div className="flex items-center gap-2 text-[#333]">
                <Sparkles size={19} className="text-[#ef3124]" />
                <h3 className="font-semibold">AI-вердикт по контрагенту</h3>
              </div>
              <p className="mt-3 whitespace-pre-line leading-7 text-[#303030]">
                {analysis.summary}
              </p>
            </section>

            <div className="mt-5">
              <Button view="primary" size={48} onClick={() => setIsOpen((value) => !value)}>
                {isOpen ? 'Свернуть полный отчёт' : 'Открыть полный отчёт'}
              </Button>
            </div>
          </>
        )}
      </div>

      {analysis && isOpen && <FullReport analysis={analysis} />}
    </article>
  );
}
