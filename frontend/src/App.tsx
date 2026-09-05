import { useMemo, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Bot, Building2, CheckCircle2, ShieldCheck } from 'lucide-react';

import { analyzeCounterparties } from './api';
import { ChatSidebar } from './components/ChatSidebar';
import { CompanySearch } from './components/CompanySearch';
import { ReportCard } from './components/ReportCard';
import type {
  BatchAnalysisItem,
  BatchAnalysisResponse,
  CounterpartyPreview,
} from './types';

export default function App() {
  const [selected, setSelected] = useState<CounterpartyPreview[]>([]);
  const [response, setResponse] = useState<BatchAnalysisResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const [isMobileChatOpen, setIsMobileChatOpen] = useState(false);

  const resultsByInn = useMemo(
    () =>
      new Map<string, BatchAnalysisItem>(
        (response?.results ?? []).map((item) => [item.inn, item]),
      ),
    [response],
  );

  const invalidateAnalysis = () => {
    setResponse(null);
    setAnalysisError('');
  };

  const addCompany = (company: CounterpartyPreview) => {
    if (selected.length >= 10 || selected.some((item) => item.inn === company.inn)) {
      return;
    }
    setSelected((current) => [...current, company]);
    invalidateAnalysis();
  };

  const removeCompany = (inn: string) => {
    setSelected((current) => current.filter((item) => item.inn !== inn));
    invalidateAnalysis();
  };

  const runAnalysis = async () => {
    if (!selected.length || isAnalyzing) return;
    setAnalysisError('');
    setResponse(null);
    setIsAnalyzing(true);
    try {
      const result = await analyzeCounterparties(selected.map((item) => item.inn));
      setResponse(result);
    } catch (error) {
      setAnalysisError(
        error instanceof Error ? error.message : 'Не удалось выполнить проверку',
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const successfulCompanyCount =
    response?.results.filter((item) => item.status === 'success').length ?? 0;

  return (
    <main className="h-screen overflow-hidden bg-[#f3f3f3] text-[#111]">
      <div className="grid h-full min-h-0 lg:grid-cols-[minmax(0,3fr)_minmax(320px,1fr)]">
        <section className="min-h-0 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1440px] space-y-5 p-4 md:p-6 lg:p-8">
            <header className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#ef3124] font-bold text-white shadow-sm">
                  A
                </span>
                <div>
                  <p className="font-semibold text-[#111]">Контрагент AI</p>
                  <p className="text-xs text-[#777]">Проверка на основе банковского отчёта</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsMobileChatOpen(true)}
                className="flex items-center gap-2 rounded-full bg-[#111] px-4 py-2 text-sm font-medium text-white lg:hidden"
              >
                <Bot size={17} />
                Чат
              </button>
            </header>

            <CompanySearch
              selectedInns={selected.map((item) => item.inn)}
              disabled={isAnalyzing}
              onAdd={addCompany}
            />

            {selected.length > 0 && (
              <section className="flex flex-col gap-4 rounded-3xl bg-[#111] p-5 text-white shadow-lg sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={18} className="text-[#ef3124]" />
                    <p className="font-semibold">Выбрано компаний: {selected.length}</p>
                  </div>
                  <p className="mt-1 text-sm text-white/60">
                    Отчёты сформируются одним запросом и попадут в общий чат.
                  </p>
                </div>
                <Button
                  view="primary"
                  size={48}
                  disabled={isAnalyzing}
                  onClick={() => void runAnalysis()}
                >
                  {isAnalyzing
                    ? 'Формируем полный отчёт…'
                    : 'Проверить ' +
                      selected.length +
                      ' ' +
                      (selected.length === 1 ? 'компанию' : 'компании')}
                </Button>
              </section>
            )}

            {analysisError && (
              <div className="rounded-2xl border border-[#f1b9b5] bg-[#fff0ef] p-4 text-sm text-[#a71b13]">
                {analysisError}
              </div>
            )}

            {selected.length === 0 ? (
              <section className="flex min-h-72 flex-col items-center justify-center rounded-3xl border border-dashed border-[#d3d3d3] bg-white px-6 text-center">
                <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#f1f1f1] text-[#666]">
                  <Building2 size={28} />
                </span>
                <h2 className="mt-5 text-xl font-semibold">Добавьте первую компанию</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-[#777]">
                  Введите корректный ИНН выше. Мы найдём карточку в базе, после чего
                  её можно добавить в общую проверку.
                </p>
              </section>
            ) : (
              <section className="space-y-5 pb-8">
                {selected.map((company) => (
                  <ReportCard
                    key={company.inn}
                    preview={company}
                    result={resultsByInn.get(company.inn)}
                    analyzing={isAnalyzing}
                    onRemove={() => removeCompany(company.inn)}
                  />
                ))}
              </section>
            )}

            <footer className="flex items-center gap-2 pb-4 text-xs text-[#888]">
              <ShieldCheck size={14} />
              Решение не пересчитывает банковский уровень риска
            </footer>
          </div>
        </section>

        <div className="hidden min-h-0 border-l border-[#dedede] lg:block">
          <ChatSidebar
            chatId={response?.chat_id ?? null}
            companyCount={successfulCompanyCount}
          />
        </div>
      </div>

      {isMobileChatOpen && (
        <div className="fixed inset-0 z-50 bg-black/35 lg:hidden">
          <div className="absolute inset-y-0 right-0 w-full max-w-md shadow-2xl">
            <ChatSidebar
              chatId={response?.chat_id ?? null}
              companyCount={successfulCompanyCount}
              onClose={() => setIsMobileChatOpen(false)}
            />
          </div>
        </div>
      )}
    </main>
  );
}
