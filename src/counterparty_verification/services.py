from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .agents import EvaluatorAgent, QuestionAnswerAgent, SpecialistAgent
from .domain import (
    BatchAnalysisItem,
    BatchAnalysisResponse,
    BatchAnalysisStatus,
    AnalysisResponse,
    ChapterResult,
    CounterpartyCard,
    QuestionResponse,
    RiskLevel,
)
from .mcp_client import AnalysisToolClient
from .presentation import build_company_profile, build_visualization_data
from .repositories import CounterpartyRepository

TOOL_NAMES = (
    "analyze_general",
    "analyze_structure",
    "analyze_legal",
    "analyze_reputation",
    "analyze_finance",
    "analyze_procurement",
)
BATCH_ANALYSIS_CONCURRENCY = 3


class CounterpartyNotFoundError(LookupError):
    pass


class AnalysisSessionNotFoundError(LookupError):
    pass


class UpstreamServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class AnalysisSession:
    card: CounterpartyCard
    response: AnalysisResponse
    expires_at: datetime


class InMemorySessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[str, AnalysisSession] = {}
        self._lock = asyncio.Lock()

    async def put(
        self, card: CounterpartyCard, response: AnalysisResponse
    ) -> AnalysisSession:
        session = AnalysisSession(
            card=card,
            response=response,
            expires_at=datetime.now(UTC) + self.ttl,
        )
        async with self._lock:
            self._sessions[response.analysis_id] = session
        return session

    async def get(self, analysis_id: str) -> AnalysisSession | None:
        async with self._lock:
            session = self._sessions.get(analysis_id)
            if session and session.expires_at > datetime.now(UTC):
                return session
            self._sessions.pop(analysis_id, None)
        return None


class AnalysisService:
    def __init__(
        self,
        repository: CounterpartyRepository,
        tools: AnalysisToolClient,
        specialist: SpecialistAgent,
        evaluator: EvaluatorAgent,
        sessions: InMemorySessionStore,
        timeout_seconds: float,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.specialist = specialist
        self.evaluator = evaluator
        self.sessions = sessions
        self.timeout_seconds = timeout_seconds

    async def analyze(self, inn: str) -> AnalysisResponse:
        card = await self.repository.get_by_inn(inn)
        if card is None:
            raise CounterpartyNotFoundError(inn)
        return await self._analyze_card(inn, card)

    async def analyze_many(self, inns: list[str]) -> BatchAnalysisResponse:
        cards = await self.repository.get_many_by_inns(inns)
        cards_by_inn = {card.company_reports.inn: card for card in cards}
        semaphore = asyncio.Semaphore(BATCH_ANALYSIS_CONCURRENCY)

        async def analyze_one(inn: str) -> BatchAnalysisItem:
            card = cards_by_inn.get(inn)
            if card is None:
                return BatchAnalysisItem(
                    inn=inn,
                    status=BatchAnalysisStatus.NOT_FOUND,
                    error="Контрагент с таким ИНН не найден",
                )
            async with semaphore:
                try:
                    analysis = await self._analyze_card(inn, card)
                except TimeoutError:
                    return BatchAnalysisItem(
                        inn=inn,
                        status=BatchAnalysisStatus.ERROR,
                        error="Превышено время анализа",
                    )
                except UpstreamServiceError:
                    return BatchAnalysisItem(
                        inn=inn,
                        status=BatchAnalysisStatus.ERROR,
                        error="Ошибка сервиса языковой модели",
                    )
            return BatchAnalysisItem(
                inn=inn,
                status=BatchAnalysisStatus.SUCCESS,
                analysis=analysis,
            )

        results = await asyncio.gather(*(analyze_one(inn) for inn in inns))
        return BatchAnalysisResponse(results=list(results))

    async def _analyze_card(
        self, inn: str, card: CounterpartyCard
    ) -> AnalysisResponse:
        async with asyncio.timeout(self.timeout_seconds):
            chapters = await asyncio.gather(
                *(self._run_chapter(name, card) for name in TOOL_NAMES)
            )
            try:
                summary = await self.evaluator.summarize(chapters)
            except Exception as error:
                raise UpstreamServiceError("Evaluator failed") from error
        response = AnalysisResponse(
            analysis_id=str(uuid4()),
            inn=inn,
            summary=summary.summary,
            risk_level=summary.risk_level,
            chapters=chapters,
            company_profile=build_company_profile(card),
            visualization_data=build_visualization_data(card),
        )
        await self.sessions.put(card, response)
        return response

    async def _run_chapter(
        self, tool_name: str, card: CounterpartyCard
    ) -> ChapterResult:
        chapter_name = tool_name.removeprefix("analyze_")
        try:
            chapter = await self.tools.call(tool_name, card)
            return await self.specialist.enrich(chapter)
        except Exception as error:
            return ChapterResult(
                chapter=chapter_name,
                risk_level=RiskLevel.UNKNOWN,
                conclusion=f"Раздел {chapter_name} временно недоступен.",
                data_sufficient=False,
                error=type(error).__name__,
            )


class QuestionService:
    def __init__(
        self,
        sessions: InMemorySessionStore,
        agent: QuestionAnswerAgent,
        timeout_seconds: float = 30,
    ) -> None:
        self.sessions = sessions
        self.agent = agent
        self.timeout_seconds = timeout_seconds

    async def answer(self, analysis_id: str, question: str) -> QuestionResponse:
        session = await self.sessions.get(analysis_id)
        if session is None:
            raise AnalysisSessionNotFoundError(analysis_id)
        async with asyncio.timeout(self.timeout_seconds):
            try:
                answer = await self.agent.answer(
                    question, session.card, session.response.chapters
                )
            except Exception as error:
                raise UpstreamServiceError("Question agent failed") from error
        return QuestionResponse(analysis_id=analysis_id, answer=answer)
