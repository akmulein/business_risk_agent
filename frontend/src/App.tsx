import { useMemo, useState } from 'react';
import { Building2 } from 'lucide-react';

import { analyzeCounterparties } from './api';
import { ChatSidebar } from './components/ChatSidebar';
import { CompanySearch } from './components/CompanySearch';
import { ComparisonDashboard } from './components/ComparisonDashboard';
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

  const displayedCompanies = useMemo(() => {
    if (!response?.comparison) return selected;
    const ranks = new Map(
      response.comparison.companies.map((company) => [company.inn, company.rank]),
    );
    return [...selected].sort(
      (left, right) =>
        (ranks.get(left.inn) ?? Number.POSITIVE_INFINITY) -
        (ranks.get(right.inn) ?? Number.POSITIVE_INFINITY),
    );
  }, [response?.comparison, selected]);

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
            <CompanySearch
              selectedInns={selected.map((item) => item.inn)}
              disabled={isAnalyzing}
              onAdd={addCompany}
              onRunAnalysis={() => void runAnalysis()}
              onOpenMobileChat={() => setIsMobileChatOpen(true)}
            />

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
                {response?.comparison && (
                  <ComparisonDashboard comparison={response.comparison} />
                )}
                {response?.comparison && (
                  <h2 className="pt-2 text-lg font-semibold text-[#222]">
                    Отчёты по компаниям
                  </h2>
                )}
                {displayedCompanies.map((company) => (
                  <ReportCard
                    key={company.inn}
                    preview={company}
                    result={resultsByInn.get(company.inn)}
                    analyzing={isAnalyzing}
                    collapsedByDefault={Boolean(response?.comparison)}
                    onRemove={() => removeCompany(company.inn)}
                  />
                ))}
              </section>
            )}
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
