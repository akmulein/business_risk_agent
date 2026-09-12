from typing import Any

from counterparty_verification.domain import ChapterResult


def chapter_context(chapters: list[ChapterResult]) -> list[dict[str, Any]]:
    """Pass tool findings without duplicating their source-evidence values."""
    return [
        {
            "chapter": chapter.chapter,
            "conclusion": chapter.conclusion,
            "observations": [
                {"title": item.title, "detail": item.detail}
                for item in chapter.observations
            ],
            "factors": [
                {
                    "title": item.title,
                    "detail": item.detail,
                    "severity": item.severity.value,
                }
                for item in chapter.factors
            ],
            "data_sufficient": chapter.data_sufficient,
            "error": chapter.error,
        }
        for chapter in chapters
    ]
