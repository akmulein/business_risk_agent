import { useEffect, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Input } from '@alfalab/core-components/input';
import { Bot, Plus, Search } from 'lucide-react';

import { ApiError, findCounterparty } from '../api';
import { isValidInn, normalizeInn } from '../inn';
import type { CounterpartyPreview } from '../types';
import { AlfaLogo } from './AlfaLogo';
import { RiskBadge } from './RiskBadge';

interface CompanySearchProps {
  selectedInns: string[];
  disabled?: boolean;
  onAdd: (company: CounterpartyPreview) => void;
  onRunAnalysis: () => void;
  onOpenMobileChat: () => void;
}

export function CompanySearch({
  selectedInns,
  disabled,
  onAdd,
  onRunAnalysis,
  onOpenMobileChat,
}: CompanySearchProps) {
  const [value, setValue] = useState('');
  const [preview, setPreview] = useState<CounterpartyPreview | null>(null);
  const [status, setStatus] = useState<'idle' | 'searching' | 'found' | 'error'>('idle');
  const [message, setMessage] = useState('');

  useEffect(() => {
    setPreview(null);
    setMessage('');
    if (!value) {
      setStatus('idle');
      return;
    }
    if (selectedInns.length >= 10) {
      setStatus('idle');
      setMessage('Максимум 10 ИНН');
      return;
    }
    if (!isValidInn(value)) {
      setStatus('idle');
      if (value.length === 10 || value.length === 12) {
        setMessage('Проверьте контрольные цифры ИНН');
      }
      return;
    }
    if (selectedInns.includes(value)) {
      setStatus('idle');
      setMessage('Компания уже добавлена');
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setStatus('searching');
      try {
        const company = await findCounterparty(value, controller.signal);
        setPreview(company);
        setStatus('found');
      } catch (error) {
        if (controller.signal.aborted) return;
        setStatus('error');
        setMessage(
          error instanceof ApiError && error.status === 404
            ? 'Компания с таким ИНН не найдена'
            : error instanceof Error
              ? error.message
              : 'Не удалось найти компанию',
        );
      }
    }, 450);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [selectedInns, value]);

  const addCompany = () => {
    if (!preview) return;
    onAdd(preview);
    setValue('');
    setPreview(null);
    setStatus('idle');
  };

  const companyWord =
    selectedInns.length === 1
      ? 'компанию'
      : selectedInns.length >= 2 && selectedInns.length <= 4
        ? 'компании'
        : 'компаний';

  return (
    <section className="surface-shadow rounded-3xl border border-[#e7e7e7] bg-white p-5 md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <AlfaLogo />
          <h1 className="text-2xl font-semibold tracking-[-0.03em] text-[#111] md:text-3xl">
            Проверка контрагентов
          </h1>
        </div>
        <button
          type="button"
          onClick={onOpenMobileChat}
          className="flex items-center gap-2 rounded-full bg-[#111] px-4 py-2 text-sm font-medium text-white lg:hidden"
        >
          <Bot size={17} />
          Чат
        </button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <div className="relative">
            <div className="pointer-events-none absolute top-1/2 left-4 z-10 -translate-y-1/2 text-[#777]">
              <Search size={20} strokeWidth={2} />
            </div>
            <Input
              block
              size={56}
              value={value}
              disabled={disabled}
              placeholder="Введите ИНН компании или ИП"
              onChange={(event) => setValue(normalizeInn(event.target.value))}
              className="search-input"
            />
          </div>

          {(status === 'searching' || message) && (
            <div className="mt-2 px-1 text-sm">
              <span className={status === 'error' ? 'text-[#c21a10]' : 'text-[#777]'}>
                {status === 'searching' ? 'Ищем компанию…' : message}
              </span>
            </div>
          )}
        </div>

        {selectedInns.length > 0 && (
          <button
            type="button"
            disabled={disabled}
            onClick={onRunAnalysis}
            aria-label={disabled ? 'Анализ отчета...' : undefined}
            className={`h-14 min-w-56 overflow-hidden rounded-xl px-6 text-sm font-semibold text-white transition ${
              disabled
                ? 'analysis-button-loading cursor-wait'
                : 'bg-[#111] hover:bg-[#292929] active:scale-[0.99]'
            }`}
          >
            {!disabled && `Проверить ${selectedInns.length} ${companyWord}`}
          </button>
        )}
      </div>

      {preview && status === 'found' && (
        <div className="mt-3 flex flex-col gap-4 rounded-2xl bg-[#f5f5f5] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate font-semibold text-[#111]">{preview.name}</p>
              <RiskBadge level={preview.risk_level} />
            </div>
            <p className="mt-1 text-sm text-[#777]">
              ИНН {preview.inn}
              {preview.kpp ? ` · КПП ${preview.kpp}` : ''}
            </p>
          </div>
          <Button view="primary" size={40} onClick={addCompany}>
            <span className="inline-flex items-center gap-2">
              <Plus size={16} />
              Добавить
            </span>
          </Button>
        </div>
      )}
    </section>
  );
}
