import { useEffect, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Input } from '@alfalab/core-components/input';
import { Plus, Search } from 'lucide-react';

import { ApiError, findCounterparty } from '../api';
import { isValidInn, normalizeInn } from '../inn';
import type { CounterpartyPreview } from '../types';
import { RiskBadge } from './RiskBadge';

interface CompanySearchProps {
  selectedInns: string[];
  disabled?: boolean;
  onAdd: (company: CounterpartyPreview) => void;
}

export function CompanySearch({
  selectedInns,
  disabled,
  onAdd,
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

  return (
    <section className="rounded-3xl border border-[#e7e7e7] bg-white p-5 shadow-[0_12px_36px_rgba(0,0,0,0.06)] md:p-6">
      <div className="mb-4">
        <p className="text-sm font-medium text-[#6b6b6b]">Новая проверка</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-[#111] md:text-3xl">
          Проверка контрагентов
        </h1>
      </div>

      <div className="relative">
        <div className="pointer-events-none absolute top-1/2 left-4 z-10 -translate-y-1/2 text-[#777]">
          <Search size={20} strokeWidth={2} />
        </div>
        <Input
          block
          size={56}
          value={value}
          disabled={disabled || selectedInns.length >= 10}
          placeholder="Введите ИНН компании или ИП"
          onChange={(event) => setValue(normalizeInn(event.target.value))}
          className="search-input"
        />
      </div>

      <div className="mt-2 flex min-h-6 items-center justify-between gap-3 px-1 text-sm">
        <span className={status === 'error' ? 'text-[#c21a10]' : 'text-[#777]'}>
          {status === 'searching'
            ? 'Ищем компанию…'
            : message || `Добавлено ${selectedInns.length} из 10 компаний`}
        </span>
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
