import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

from .agents import EvaluatorAgent, QuestionAnswerAgent, SpecialistAgent
from .chat_agent import ChatModelNotConfiguredError, ReportChatAgent
from .chat_models import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from .chat_service import (
    ChatService,
    ChatSessionNotFoundError,
    ChatUpstreamServiceError,
    InMemoryChatSessionStore,
    MongoChatSessionStore,
)
from .domain import (
    AnalysisRequest,
    BatchAnalysisResponse,
    CounterpartyPreview,
    QuestionRequest,
    QuestionResponse,
    validate_inn,
)
from .mcp_client import HttpMcpAnalysisClient
from .presentation import build_counterparty_preview
from .repositories import (
    JsonCounterpartyRepository,
    MongoCounterpartyRepository,
    PostgresCounterpartyRepository,
)
from .services import (
    AnalysisService,
    AnalysisSessionNotFoundError,
    InMemorySessionStore,
    QuestionService,
    UpstreamServiceError,
)
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    if config.repository_backend == "postgres":
        repository = PostgresCounterpartyRepository(config.database_url)
    elif config.repository_backend == "mongo":
        repository = MongoCounterpartyRepository(
            config.mongodb_url,
            config.mongodb_database,
            config.mongodb_collection,
        )
    elif config.repository_backend == "mock":
        repository = JsonCounterpartyRepository(config.mock_data_path)
    else:
        raise ValueError("REPOSITORY_BACKEND must be one of: mock, postgres, mongo")
    if isinstance(repository, MongoCounterpartyRepository):
        chat_store = MongoChatSessionStore(
            repository.client[config.mongodb_database][config.mongodb_chat_collection],
            config.session_ttl_seconds,
        )
    else:
        chat_store = InMemoryChatSessionStore(config.session_ttl_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await chat_store.ensure_indexes()
        yield
        close = getattr(repository, "close", None)
        if close is not None:
            await close()

    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    sessions = InMemorySessionStore(config.session_ttl_seconds)
    analysis_service = AnalysisService(
        repository=repository,
        tools=HttpMcpAnalysisClient(
            config.mcp_url, timeout_seconds=config.mcp_timeout_seconds
        ),
        specialist=SpecialistAgent(config),
        evaluator=EvaluatorAgent(config),
        sessions=sessions,
        timeout_seconds=config.analysis_timeout_seconds,
    )
    question_service = QuestionService(
        sessions,
        QuestionAnswerAgent(config),
        timeout_seconds=config.analysis_timeout_seconds,
    )
    chat_service = ChatService(
        repository=repository,
        store=chat_store,
        agent=ReportChatAgent(config),
        timeout_seconds=config.chat_timeout_seconds,
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

    @app.post(
        "/api/v1/analyses",
        response_model=BatchAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    async def create_analysis(
        payload: AnalysisRequest,
        service: AnalysisDep,
        chat: ChatDep,
    ) -> BatchAnalysisResponse:
        response = await service.analyze_many(payload.inns)
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
        except asyncio.TimeoutError as error:
            raise HTTPException(
                status_code=503,
                detail="Превышено время ответа",
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
        except asyncio.TimeoutError as error:
            raise HTTPException(
                status_code=503, detail="Превышено время ответа"
            ) from error
        except UpstreamServiceError as error:
            raise HTTPException(
                status_code=502, detail="Ошибка сервиса языковой модели"
            ) from error

    return app


app = create_app()
