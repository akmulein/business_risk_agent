from typing import Any

from counterparty_verification.domain import ChapterResult, RiskLevel

# The model can only repeat what it is given, so no raw enum value is ever
# passed to a summarizer -- every status reaches it already spelled out.
SEVERITY_LABELS = {
    RiskLevel.LOW: "низкая",
    RiskLevel.MEDIUM: "средняя",
    RiskLevel.HIGH: "высокая",
    RiskLevel.UNKNOWN: "не определена",
}


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
                    "severity": SEVERITY_LABELS[item.severity],
                }
                for item in chapter.factors
            ],
            "data_sufficient": chapter.data_sufficient,
            "error": chapter.error,
        }
        for chapter in chapters
    ]
