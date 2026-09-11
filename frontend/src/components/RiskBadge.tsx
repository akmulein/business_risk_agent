import type { RiskLevel } from '../types';

const RISK_LABELS: Record<RiskLevel, string> = {
  LOW: 'Низкий риск',
  MEDIUM: 'Средний риск',
  HIGH: 'Высокий риск',
  UNKNOWN: 'Нет оценки',
};

export const RISK_STYLES: Record<RiskLevel, { border: string; badge: string; dot: string }> = {
  LOW: {
    border: 'border-l-[#ffffff]',
    badge: 'bg-[#e9f7ef] text-[#14733b]',
    dot: 'bg-[#27a35a]',
  },
  MEDIUM: {
    border: 'border-l-[#ffffff]',
    badge: 'bg-[#fff6d8] text-[#755800]',
    dot: 'bg-[#f2b705]',
  },
  HIGH: {
    border: 'border-l-[#ffffff]',
    badge: 'bg-[#ffebe9] text-[#b5120a]',
    dot: 'bg-[#ef3124]',
  },
  UNKNOWN: {
    border: 'border-l-[#ffffff]',
    badge: 'bg-[#f0f0f0] text-[#616161]',
    dot: 'bg-[#a3a3a3]',
  },
};

export function RiskBadge({ level }: { level: RiskLevel | null | undefined }) {
  const normalized = level ?? 'UNKNOWN';
  const style = RISK_STYLES[normalized];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${style.badge}`}
    >
      <span className={`h-2 w-2 rounded-full ${style.dot}`} />
      {RISK_LABELS[normalized]}
    </span>
  );
}
