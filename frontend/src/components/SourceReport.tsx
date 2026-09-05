import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

const FIELD_LABELS: Record<string, string> = {
  reportDate: 'Дата отчёта',
  baseInfo: 'Основные сведения',
  foundersInfo: 'Учредители и руководство',
  kindsOfActivityInfo: 'Виды деятельности',
  arbitrationCases: 'Арбитражные дела по годам',
  phones: 'Телефоны',
  status: 'Статус компании',
  finReports: 'Финансовая отчётность',
  taxSystem: 'Система налогообложения',
  relatedCompanies: 'Связанные организации',
  zskRiskLevel: 'Уровень риска ЗСК',
  reputationalRisks: 'Репутационные факторы',
  arbitrationByStatus: 'Арбитражные дела по статусам',
  executionProceedings: 'Исполнительные производства',
  procurements: 'Государственные закупки',
  inspections: 'Проверки',
  coefficient: 'Финансовые коэффициенты',
  inn: 'ИНН',
  kpp: 'КПП',
  ogrn: 'ОГРН',
  okpo: 'ОКПО',
  shortName: 'Краткое наименование',
  fullName: 'Полное наименование',
  registrationInfo: 'Регистрационные сведения',
  registrationDate: 'Дата регистрации',
  yearsFromRegistration: 'Возраст компании, лет',
  riskLevel: 'Уровень риска',
  address: 'Адрес',
  email: 'Электронная почта',
  website: 'Сайт',
  companySize: 'Размер компании',
  reasonName: 'Причина статуса',
  date: 'Дата',
  dateFrom: 'Дата начала',
  startDate: 'Дата начала',
  endDate: 'Дата окончания',
  issueDate: 'Дата выдачи',
  cofounders: 'Учредители',
  authPerson: 'Руководитель',
  authPersonName: 'ФИО руководителя',
  authPersonPosition: 'Должность руководителя',
  positionName: 'Должность',
  positionDate: 'Дата назначения',
  parentOrganizations: 'Головные организации',
  parentDate: 'Дата возникновения связи',
  shareCapital: 'Уставный капитал, ₽',
  share: 'Доля, %',
  amount: 'Сумма, ₽',
  name: 'Наименование',
  active: 'Действующий',
  mainKindOfActivity: 'Основной вид деятельности',
  otherKindsOfActivity: 'Дополнительные виды деятельности',
  code: 'Код',
  description: 'Описание',
  branchesInfo: 'Филиалы',
  branchesCount: 'Количество филиалов',
  branches: 'Список филиалов',
  phoneCode: 'Код телефона',
  phoneNumber: 'Номер телефона',
  phoneType: 'Тип телефона',
  year: 'Год',
  common: 'Основные показатели',
  proceeds: 'Выручка, ₽',
  profit: 'Прибыль, ₽',
  assets: 'Активы',
  totalAssets: 'Активы всего, ₽',
  currentAssets: 'Оборотные активы',
  uncurrentAssets: 'Внеоборотные активы',
  fixedAssets: 'Основные средства, ₽',
  stocks: 'Запасы, ₽',
  receivables: 'Дебиторская задолженность, ₽',
  bankroll: 'Денежные средства, ₽',
  total: 'Всего, ₽',
  liabilities: 'Пассивы',
  totalLiabilities: 'Пассивы всего, ₽',
  capitals: 'Капитал и резервы, ₽',
  longTermDuties: 'Долгосрочные обязательства',
  shortTermLiabilities: 'Краткосрочные обязательства',
  borrowedFunds: 'Заёмные средства, ₽',
  accountsPayable: 'Кредиторская задолженность, ₽',
  others: 'Прочее, ₽',
  sustainability: 'Финансовая устойчивость',
  solvency: 'Платёжеспособность',
  profitability: 'Рентабельность',
  negative: 'Негативные факторы',
  positive: 'Позитивные факторы',
  chapter: 'Раздел',
  plaintiffArbitration: 'Дела в качестве истца',
  defandantArbitration: 'Дела в качестве ответчика',
  plaintiffArbitrationPending: 'Открытые дела истца',
  plaintiffArbitrationFinished: 'Завершённые дела истца',
  plaintiffArbitrationAppealed: 'Обжалованные дела истца',
  defandantArbitrationPending: 'Открытые дела ответчика',
  defandantArbitrationFinished: 'Завершённые дела ответчика',
  defandantArbitrationAppealed: 'Обжалованные дела ответчика',
  plaintiffCount: 'Количество дел истца',
  plaintiffAmount: 'Сумма требований истца, ₽',
  defendantCount: 'Количество дел ответчика',
  defendantAmount: 'Сумма требований к ответчику, ₽',
  commonCount: 'Общее количество дел',
  commonAmount: 'Общая сумма, ₽',
  ppCount: 'Открытые дела истца, количество',
  ppAmount: 'Открытые дела истца, сумма, ₽',
  pfCount: 'Завершённые дела истца, количество',
  pfAmount: 'Завершённые дела истца, сумма, ₽',
  paCount: 'Обжалованные дела истца, количество',
  paAmount: 'Обжалованные дела истца, сумма, ₽',
  dpCount: 'Открытые дела ответчика, количество',
  dpAmount: 'Открытые дела ответчика, сумма, ₽',
  dfCount: 'Завершённые дела ответчика, количество',
  dfAmount: 'Завершённые дела ответчика, сумма, ₽',
  daCount: 'Обжалованные дела ответчика, количество',
  daAmount: 'Обжалованные дела ответчика, сумма, ₽',
  erpId: 'Идентификатор в реестре',
  authorityName: 'Орган',
  form: 'Форма',
  licenses: 'Лицензии',
  number: 'Номер',
  issuingAuthority: 'Орган, выдавший документ',
  procurementsYear: 'Год закупок',
  federalLawCode: 'Федеральный закон',
  tenderWinnerCnt: 'Побед в закупках',
  contractSignedCnt: 'Заключено контрактов',
  contractSignedAmt: 'Сумма контрактов, ₽',
  inspectionStatus: 'Статус проверки',
  type: 'Тип',
};

const VALUE_LABELS: Record<string, string> = {
  CURRENT: 'Действующая',
  ACTIVE: 'Действующий',
  LOW: 'Низкий',
  MEDIUM: 'Средний',
  HIGH: 'Высокий',
  UNKNOWN: 'Не определён',
  GREEN: 'Зелёный',
  YELLOW: 'Жёлтый',
  RED: 'Красный',
  InspectionsViolationNotDetected: 'Нарушений не выявлено',
};

const YEAR_FIELDS = new Set(['year', 'procurementsYear', 'yearsFromRegistration']);
const MONEY_FIELDS = new Set([
  'amount',
  'shareCapital',
  'proceeds',
  'profit',
  'totalAssets',
  'fixedAssets',
  'stocks',
  'receivables',
  'bankroll',
  'totalLiabilities',
  'capitals',
  'borrowedFunds',
  'accountsPayable',
  'commonAmount',
  'plaintiffAmount',
  'defendantAmount',
  'ppAmount',
  'pfAmount',
  'paAmount',
  'dpAmount',
  'dfAmount',
  'daAmount',
  'contractSignedAmt',
]);

// Report is split into at most this many collapsible sections; any field
// not explicitly grouped below falls back into the first section so the
// limit always holds.
const GROUPS: { title: string; keys: string[] }[] = [
  { title: 'Основные сведения', keys: ['baseInfo', 'reportDate', 'status', 'phones', 'taxSystem', 'branchesInfo'] },
  { title: 'Учредители и руководство', keys: ['foundersInfo', 'relatedCompanies'] },
  { title: 'Деятельность и разрешения', keys: ['kindsOfActivityInfo', 'licenses', 'procurements', 'inspections'] },
  { title: 'Финансы', keys: ['finReports', 'coefficient'] },
  {
    title: 'Юридические и репутационные риски',
    keys: ['arbitrationCases', 'arbitrationByStatus', 'executionProceedings', 'reputationalRisks'],
  },
];

// Shown on the main card already — dropped from the full report.
const EXCLUDED_KEYS = new Set(['zskRiskLevel']);

const ARRAY_ROW_LIMIT = 15;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  if (isRecord(value)) return Object.keys(value).length === 0;
  return false;
}

function labelFor(key: string) {
  return (
    FIELD_LABELS[key] ??
    key
      .replace(/([a-zа-яё])([A-ZА-ЯЁ])/g, '$1 $2')
      .replace(/_/g, ' ')
      .replace(/^./, (letter) => letter.toUpperCase())
  );
}

function formatScalar(value: unknown, fieldKey?: string): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (typeof value === 'number') {
    return YEAR_FIELDS.has(fieldKey ?? '') ? String(value) : numberFormatter.format(value);
  }
  const text = String(value);
  if (VALUE_LABELS[text]) return VALUE_LABELS[text];
  if (MONEY_FIELDS.has(fieldKey ?? '') && /^-?\d+(?:\.\d+)?$/.test(text)) {
    return numberFormatter.format(Number(text));
  }
  if (/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(text)) {
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) return date.toLocaleDateString('ru-RU');
  }
  return text;
}

const numberFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 2,
});

/** Recursively pulls nested-object fields up to the top level (arrays are left as-is). */
function flattenLeaves(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (isRecord(value)) {
      Object.assign(out, flattenLeaves(value));
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Splits an object into flat scalar pairs and named arrays found anywhere in its tree. */
function splitObject(obj: Record<string, unknown>): {
  scalars: [string, unknown][];
  arrays: [string, unknown[]][];
} {
  const scalars: [string, unknown][] = [];
  const arrays: [string, unknown[]][] = [];
  const walk = (o: Record<string, unknown>) => {
    for (const [key, value] of Object.entries(o)) {
      if (Array.isArray(value)) {
        if (value.length) arrays.push([key, value]);
      } else if (isRecord(value)) {
        walk(value);
      } else if (value !== null && value !== undefined && value !== '') {
        scalars.push([key, value]);
      }
    }
  };
  walk(obj);
  return { scalars, arrays };
}

/** One-line representation of a value for use inside a table cell. */
function formatCell(value: unknown, key?: string): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) {
    if (!value.length) return '—';
    if (value.every((item) => !isRecord(item) && !Array.isArray(item))) {
      return value.map((item) => formatScalar(item, key)).join(', ');
    }
    return `${value.length} зап.`;
  }
  if (isRecord(value)) {
    const flat = flattenLeaves(value);
    const parts = Object.entries(flat)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${labelFor(k)}: ${formatScalar(v, k)}`);
    return parts.length ? parts.join('; ') : '—';
  }
  return formatScalar(value, key);
}

function ScalarTable({ rows }: { rows: [string, unknown][] }) {
  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
      {rows.map(([key, value]) => (
        <div key={key} className="flex gap-1.5">
          <span className="shrink-0 text-[#999]">{labelFor(key)}:</span>
          <span className="min-w-0 break-words text-[#222]">{formatScalar(value, key)}</span>
        </div>
      ))}
    </div>
  );
}

function ArrayTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? rows : rows.slice(0, ARRAY_ROW_LIMIT);
  return (
    <div className="overflow-x-auto rounded-lg border border-[#ececec]">
      <table className="w-full min-w-[420px] border-collapse text-xs">
        <thead>
          <tr className="bg-[#fafafa]">
            {columns.map((column) => (
              <th
                key={column}
                className="whitespace-nowrap border-b border-[#ececec] px-2 py-1 text-left font-medium text-[#888]"
              >
                {labelFor(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={index} className="border-b border-[#f3f3f3] last:border-0">
              {columns.map((column) => (
                <td key={column} className="px-2 py-1 align-top text-[#222]">
                  {formatCell(row[column], column)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > ARRAY_ROW_LIMIT && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="w-full border-t border-[#ececec] bg-[#fafafa] py-1 text-[11px] text-[#666] hover:text-[#111]"
        >
          {expanded ? 'Свернуть' : `Показать все (${rows.length})`}
        </button>
      )}
    </div>
  );
}

function ValueArray({ items, fieldKey }: { items: unknown[]; fieldKey?: string }) {
  if (!items.length) return <span className="text-xs text-[#999]">—</span>;
  const allScalar = items.every((item) => !isRecord(item) && !Array.isArray(item));
  if (allScalar) {
    return (
      <p className="break-words text-xs text-[#222]">
        {items.map((item) => formatScalar(item, fieldKey)).join(', ')}
      </p>
    );
  }
  const rows = items.map((item) => (isRecord(item) ? flattenLeaves(item) : { значение: item }));
  const columns: string[] = [];
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!columns.includes(key)) columns.push(key);
    });
  });
  return <ArrayTable columns={columns} rows={rows} />;
}

function FieldBlock({ label, value }: { label: string; value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length) return null;
    return (
      <div className="mb-2.5 last:mb-0">
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#999]">{label}</p>
        <ValueArray items={value} />
      </div>
    );
  }
  if (isRecord(value)) {
    const { scalars, arrays } = splitObject(value);
    if (!scalars.length && !arrays.length) return null;
    return (
      <div className="mb-2.5 last:mb-0">
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#999]">{label}</p>
        {scalars.length > 0 && <ScalarTable rows={scalars} />}
        {arrays.map(([key, items]) => (
          <div key={key} className={scalars.length > 0 ? 'mt-1.5' : undefined}>
            <p className="mb-1 text-[11px] text-[#999]">{labelFor(key)}</p>
            <ValueArray items={items} fieldKey={key} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="mb-1 flex gap-1.5 text-xs last:mb-0">
      <span className="shrink-0 text-[#999]">{label}:</span>
      <span className="min-w-0 break-words text-[#222]">{formatScalar(value)}</span>
    </div>
  );
}

interface SourceReportProps {
  report: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
}

export function SourceReport({ report, loading, error }: SourceReportProps) {
  return (
    <div className="border-t border-[#ededed] px-5 py-6 md:px-6">
      <h3 className="mb-4 text-lg font-semibold text-[#111]">Полный отчёт</h3>

      {loading && (
        <div className="space-y-3">
          <div className="h-16 animate-pulse rounded-2xl bg-[#f1f1f1]" />
          <div className="h-28 animate-pulse rounded-2xl bg-[#f1f1f1]" />
        </div>
      )}

      {error && <p className="rounded-xl bg-[#fff0ef] p-4 text-sm text-[#9d1811]">{error}</p>}

      {report &&
        (() => {
          const knownKeys = new Set(GROUPS.flatMap((group) => group.keys));
          const leftoverKeys = Object.keys(report).filter(
            (key) => !knownKeys.has(key) && !EXCLUDED_KEYS.has(key),
          );
          const groups = GROUPS.map((group, index) =>
            index === 0 ? { ...group, keys: [...group.keys, ...leftoverKeys] } : group,
          );

          return (
            <div className="space-y-2">
              {groups.map((group) => {
                const fields = group.keys.filter(
                  (key) => key in report && !isEmptyValue(report[key]),
                );
                if (!fields.length) return null;
                return (
                  <details key={group.title} open className="group rounded-xl border border-[#e8e8e8] bg-white">
                    <summary className="flex cursor-pointer list-none items-center gap-2 px-3.5 py-2.5 text-sm font-semibold text-[#222]">
                      <ChevronDown size={15} className="shrink-0 transition-transform group-open:rotate-180" />
                      {group.title}
                    </summary>
                    <div className="border-t border-[#ededed] px-3.5 py-2.5">
                      {fields.map((key) => (
                        <FieldBlock key={key} label={labelFor(key)} value={report[key]} />
                      ))}
                    </div>
                  </details>
                );
              })}
            </div>
          );
        })()}
    </div>
  );
}
