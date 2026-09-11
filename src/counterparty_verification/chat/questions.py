from __future__ import annotations

from counterparty_verification.agents.question_answer import QuestionAnswerAgent
from counterparty_verification.analysis.service import UpstreamServiceError
from counterparty_verification.domain import (
    QuestionResponse,
)
from counterparty_verification.storage.sessions import InMemorySessionStore


class AnalysisSessionNotFoundError(LookupError):
    pass


class QuestionService:
    def __init__(
        self,
        sessions: InMemorySessionStore,
        agent: QuestionAnswerAgent,
    ) -> None:
        self.sessions = sessions
        self.agent = agent

    async def answer(self, analysis_id: str, question: str) -> QuestionResponse:
        session = await self.sessions.get(analysis_id)
        if session is None:
            raise AnalysisSessionNotFoundError(analysis_id)
        try:
            answer = await self.agent.answer(
                question, session.card, session.response.chapters
            )
        except Exception as error:
            raise UpstreamServiceError("Question agent failed") from error
        return QuestionResponse(analysis_id=analysis_id, answer=answer)
