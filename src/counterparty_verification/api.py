import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status

from .agents import EvaluatorAgent, QuestionAnswerAgent, SpecialistAgent
from .domain import (
    AnalysisRequest,
    AnalysisResponse,
    QuestionRequest,
    QuestionResponse,
)
from .mcp_client import HttpMcpAnalysisClient
from .repositories import JsonCounterpartyRepository, PostgresCounterpartyRepository
from .services import (
    AnalysisService,
    AnalysisSessionNotFoundError,
    CounterpartyNotFoundError,
    InMemorySessionStore,
    QuestionService,
    UpstreamServiceError,
)
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
    )

    repository = (
        PostgresCounterpartyRepository(config.database_url)
        if config.repository_backend == "postgres"
        else JsonCounterpartyRepository(config.mock_data_path)
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
        response_model=AnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    async def create_analysis(
        payload: AnalysisRequest, service: AnalysisDep
    ) -> AnalysisResponse:
        try:
            return await service.analyze(payload.inn)
        except CounterpartyNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Контрагент с таким ИНН не найден"
            ) from error
        except TimeoutError as error:
            raise HTTPException(
                status_code=503, detail="Превышено время анализа"
            ) from error
        except UpstreamServiceError as error:
            raise HTTPException(
                status_code=502, detail="Ошибка сервиса языковой модели"
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
