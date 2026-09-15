import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

from app.agents.chat import (
    ChatModelNotConfiguredError,
    ReportChatAgent,
)
from app.agents.comparison import ComparisonAgent
from app.agents.evaluator import EvaluatorAgent
from app.agents.question_answer import QuestionAnswerAgent
from app.analysis.presentation import (
    build_counterparty_preview,
    sanitize_source_report,
)
from app.analysis.service import (
    AnalysisService,
    UpstreamServiceError,
)
from app.analysis.timing import analysis_trace, timed
from app.chat.models import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from app.chat.questions import (
    AnalysisSessionNotFoundError,
    QuestionService,
)
from app.chat.service import ChatService, ChatUpstreamServiceError
from app.domain import (
    AnalysisRequest,
    BatchAnalysisResponse,
    CounterpartyPreview,
    QuestionRequest,
    QuestionResponse,
    SourceReportResponse,
    validate_inn,
)
from app.mcp.client import HttpMcpAnalysisClient
from app.settings import Settings, get_settings
from app.storage.interfaces import (
    ChatSessionNotFoundError,
    CounterpartyRepository,
)
from app.storage.mongo import MongoCounterpartyRepository
from app.storage.sessions import (
    InMemoryChatSessionStore,
    InMemorySessionStore,
    MongoChatSessionStore,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def create_app(
    settings: Settings | None = None,
    *,
    repository: CounterpartyRepository | None = None,
) -> FastAPI:
    config = settings or get_settings()

    if repository is None:
        repository = MongoCounterpartyRepository(
            config.mongodb_url,
            config.mongodb_database,
            config.mongodb_collection,
            source_collection=config.mongodb_source_collection,
        )
    if isinstance(repository, MongoCounterpartyRepository):
        chat_store = MongoChatSessionStore(
            repository.client[config.mongodb_database][config.mongodb_chat_collection],
            config.session_ttl_seconds,
        )
    else:
        chat_store = InMemoryChatSessionStore(config.session_ttl_seconds)

    mcp_client = HttpMcpAnalysisClient(config.mcp_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await chat_store.ensure_indexes()
        yield
        close = getattr(repository, "close", None)
        if close is not None:
            await close()
        await mcp_client.aclose()

    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    sessions = InMemorySessionStore(config.session_ttl_seconds)
    analysis_service = AnalysisService(
        repository=repository,
        tools=mcp_client,
        evaluator=EvaluatorAgent(config),
        sessions=sessions,
        comparison_agent=ComparisonAgent(config),
        chapter_concurrency=config.batch_chapter_concurrency,
        llm_concurrency=config.batch_llm_concurrency,
    )
    question_service = QuestionService(
        sessions,
        QuestionAnswerAgent(config),
    )
    chat_service = ChatService(
        repository=repository,
        store=chat_store,
        agent=ReportChatAgent(config),
        history_limit=config.chat_history_limit,
    )
    app.state.analysis_service = analysis_service
    app.state.question_service = question_service
    app.state.settings = config
    app.state.chat_service = chat_service

    def get_analysis_service(request: Request) -> AnalysisService:
        return request.app.state.analysis_service

    def get_question_service(request: Request) -> QuestionService:
        return request.app.state.question_service

    def get_chat_service(request: Request) -> ChatService:
        return request.app.state.chat_service

    AnalysisDep = Annotated[AnalysisService, Depends(get_analysis_service)]
    QuestionDep = Annotated[QuestionService, Depends(get_question_service)]

    ChatDep = Annotated[ChatService, Depends(get_chat_service)]

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get(
        "/api/v1/counterparties/{inn}/preview",
        response_model=CounterpartyPreview,
        tags=["counterparties"],
    )
    async def counterparty_preview(inn: str) -> CounterpartyPreview:
        try:
            normalized_inn = validate_inn(inn.strip())
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        card = await repository.get_by_inn(normalized_inn)
        if card is None:
            raise HTTPException(status_code=404, detail="Контрагент не найден")
        return build_counterparty_preview(card)

    @app.get(
        "/api/v1/counterparties/{inn}/report",
        response_model=SourceReportResponse,
        tags=["counterparties"],
    )
    async def source_report(inn: str) -> SourceReportResponse:
        try:
            normalized_inn = validate_inn(inn.strip())
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        report = await repository.get_source_report_by_inn(normalized_inn)
        if report is None:
            raise HTTPException(status_code=404, detail="Исходный отчёт не найден")
        return SourceReportResponse(
            inn=normalized_inn,
            report=sanitize_source_report(report),
        )

    @app.post(
        "/api/v1/analyses",
        response_model=BatchAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    async def create_analysis(
        payload: AnalysisRequest,
        http_response: Response,
        service: AnalysisDep,
        chat: ChatDep,
    ) -> BatchAnalysisResponse:
        with analysis_trace(payload.inns) as trace_id:
            http_response.headers["X-Analysis-Trace-Id"] = trace_id
            response = await service.analyze_many(payload.inns)
            with timed("chat_save"):
                response.chat_id = await chat.create_for_analysis(response)
            return response

    @app.post(
        "/api/v1/chats/{chat_id}/messages",
        response_model=ChatMessageResponse,
        tags=["chat"],
    )
    async def send_chat_message(
        chat_id: str,
        payload: ChatMessageRequest,
        service: ChatDep,
    ) -> ChatMessageResponse:
        try:
            return await service.answer(chat_id, payload.message)
        except ChatSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Чат не найден или срок сессии истёк",
            ) from error
        except ChatModelNotConfiguredError as error:
            raise HTTPException(
                status_code=503,
                detail="OPENROUTER_API_KEY не настроен",
            ) from error
        except ChatUpstreamServiceError as error:
            raise HTTPException(
                status_code=502,
                detail="Ошибка сервиса языковой модели",
            ) from error

    @app.get(
        "/api/v1/chats/{chat_id}/messages",
        response_model=ChatHistoryResponse,
        tags=["chat"],
    )
    async def get_chat_messages(
        chat_id: str,
        service: ChatDep,
    ) -> ChatHistoryResponse:
        try:
            return await service.history(chat_id)
        except ChatSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Чат не найден или срок сессии истёк",
            ) from error

    @app.delete(
        "/api/v1/chats/{chat_id}/messages",
        response_model=ChatHistoryResponse,
        tags=["chat"],
    )
    async def clear_chat_messages(
        chat_id: str,
        service: ChatDep,
    ) -> ChatHistoryResponse:
        try:
            return await service.clear_history(chat_id)
        except ChatSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Чат не найден или срок сессии истёк",
            ) from error

    @app.post(
        "/api/v1/analyses/{analysis_id}/questions",
        response_model=QuestionResponse,
        tags=["analysis"],
    )
    async def ask_question(
        analysis_id: str, payload: QuestionRequest, service: QuestionDep
    ) -> QuestionResponse:
        try:
            return await service.answer(analysis_id, payload.question)
        except AnalysisSessionNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Анализ не найден или срок сессии истёк",
            ) from error
        except UpstreamServiceError as error:
            raise HTTPException(
                status_code=502, detail="Ошибка сервиса языковой модели"
            ) from error

    return app


app = create_app()
