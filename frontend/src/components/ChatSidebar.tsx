import { useEffect, useRef, useState } from 'react';
import { Button } from '@alfalab/core-components/button';
import { Textarea } from '@alfalab/core-components/textarea';
import { Bot, RotateCcw, Send, Sparkles, X } from 'lucide-react';

import { clearChat, sendChatMessage } from '../api';
import type { ChatMessage } from '../types';

const PRESETS = [
  'С кем судилась компания в 2024?',
  'Есть ли налоговые задолженности?',
  'Динамика выручки за 3 года',
  'Кто конечный бенефициар?',
];

interface ChatSidebarProps {
  chatId: string | null;
  companyCount: number;
  onClose?: () => void;
}

export function ChatSidebar({ chatId, companyCount, onClose }: ChatSidebarProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [value, setValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([]);
    setError('');
  }, [chatId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [isSending, messages]);

  const submit = async (text: string) => {
    const message = text.trim();
    if (!chatId || !message || isSending) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message,
    };
    setMessages((current) => [...current, userMessage]);
    setValue('');
    setError('');
    setIsSending(true);
    try {
      const response = await sendChatMessage(chatId, message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
        },
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Не удалось получить ответ ассистента',
      );
    } finally {
      setIsSending(false);
    }
  };

  const handleClear = async () => {
    if (!chatId || isSending) return;
    setError('');
    try {
      await clearChat(chatId);
      setMessages([]);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : 'Не удалось очистить чат',
      );
    }
  };

  return (
    <aside className="flex h-full min-h-0 flex-col bg-white">
      <header className="flex items-center justify-between gap-3 border-b border-[#e8e8e8] px-4 py-4 lg:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#111] text-white">
            <Bot size={20} />
          </span>
          <div className="min-w-0">
            <h2 className="font-semibold text-[#111]">AI-Ассистент</h2>
            <p className="truncate text-xs text-[#7a7a7a]">
              {chatId ? 'Отчётов в контексте: ' + companyCount : 'Сначала запустите проверку'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={!chatId || messages.length === 0 || isSending}
            onClick={handleClear}
            title="Очистить историю"
            className="rounded-full p-2 text-[#6b6b6b] transition hover:bg-[#f2f2f2] hover:text-[#111] disabled:cursor-not-allowed disabled:opacity-30"
          >
            <RotateCcw size={18} />
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Закрыть чат"
              className="rounded-full p-2 text-[#6b6b6b] transition hover:bg-[#f2f2f2] lg:hidden"
            >
              <X size={20} />
            </button>
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        {!chatId && (
          <div className="flex h-full min-h-56 flex-col items-center justify-center text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#f2f2f2] text-[#777]">
              <Sparkles size={24} />
            </span>
            <p className="mt-4 font-medium text-[#333]">Чат появится после анализа</p>
            <p className="mt-1 max-w-64 text-sm leading-5 text-[#858585]">
              Добавьте компании и запустите общую проверку.
            </p>
          </div>
        )}

        {chatId && messages.length === 0 && (
          <div className="rounded-2xl bg-[#f5f5f5] p-4 text-sm leading-5 text-[#555]">
            Я отвечаю только по данным выбранных отчётов. Можно уточнить финансовые
            показатели, руководителей, судебные события или сравнить компании.
          </div>
        )}

        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={['flex', message.role === 'user' ? 'justify-end' : 'justify-start'].join(' ')}
            >
              <div
                className={[
                  'max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-5',
                  message.role === 'user'
                    ? 'rounded-br-md bg-[#111] text-white'
                    : 'rounded-bl-md bg-[#f1f1f1] text-[#222]',
                ].join(' ')}
              >
                <p className="whitespace-pre-line">{message.content}</p>
                {message.sources && message.sources.length > 0 && (
                  <details className="mt-2 border-t border-black/10 pt-2 text-xs">
                    <summary className="cursor-pointer text-[#666]">
                      Показать исходные данные
                    </summary>
                    <div className="mt-2 space-y-2">
                      {message.sources.map((source, index) => (
                        <div key={source.field + '-' + index} className="break-words">
                          <span className="font-medium">ИНН {source.inn}</span>
                          <br />
                          <span className="text-[#777]">{source.field}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-2xl rounded-bl-md bg-[#f1f1f1] px-4 py-3 text-sm text-[#666]">
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#777] [animation-delay:-0.2s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#777] [animation-delay:-0.1s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-[#777]" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <footer className="border-t border-[#e8e8e8] p-4">
        {error && <p className="mb-2 text-xs text-[#c21a10]">{error}</p>}
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1 lg:flex-wrap">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              disabled={!chatId || isSending}
              onClick={() => void submit(preset)}
              className="shrink-0 rounded-full border border-[#d9d9d9] bg-white px-3 py-2 text-left text-xs text-[#444] transition hover:border-[#999] hover:bg-[#f7f7f7] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {preset}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-2">
          <Textarea
            block
            minRows={1}
            maxRows={5}
            value={value}
            disabled={!chatId || isSending}
            placeholder="Задайте вопрос по отчётам"
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void submit(value);
              }
            }}
          />
          <Button
            view="primary"
            size={48}
            disabled={!chatId || !value.trim() || isSending}
            onClick={() => void submit(value)}
            aria-label="Отправить сообщение"
          >
            <Send size={18} />
          </Button>
        </div>
      </footer>
    </aside>
  );
}
