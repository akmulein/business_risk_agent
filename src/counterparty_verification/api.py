import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status

from .agents import EvaluatorAgent, QuestionAnswerAgent, SpecialistAgent
from .domain import (
    AnalysisRequest,
    BatchAnalysisResponse,
    QuestionRequest,
    QuestionResponse,
)
from .mcp_client import HttpMcpAnalysisClient
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
        raise ValueError(
            "REPOSITORY_BACKEND must be one of: mock, postgres, mongo"
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
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
    app.state.analysis_service = analysis_service
    app.state.question_service = question_service
    app.state.settings = config

    def get_analysis_service(request: Request) -> AnalysisService:
        return request.app.state.analysis_service

    def get_question_service(request: Request) -> QuestionService:
        return request.app.state.question_service

    AnalysisDep = Annotated[AnalysisService, Depends(get_analysis_service)]
    QuestionDep = Annotated[QuestionService, Depends(get_question_service)]

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/api/v1/analyses",
        response_model=BatchAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    async def create_analysis(
        payload: AnalysisRequest, service: AnalysisDep
    ) -> BatchAnalysisResponse:
        return await service.analyze_many(payload.inns)

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
