from counterparty_verification.agents.prompts import (
    EVALUATOR_INSTRUCTIONS,
    MCP_SERVER_INSTRUCTIONS,
    QUESTION_ANSWER_INSTRUCTIONS,
    SYSTEM_GROUNDING,
)


def test_all_prompt_constants_are_loaded() -> None:
    prompts = (
        MCP_SERVER_INSTRUCTIONS,
        SYSTEM_GROUNDING,
        EVALUATOR_INSTRUCTIONS,
        QUESTION_ANSWER_INSTRUCTIONS,
    )

    assert all(prompt.strip() for prompt in prompts)
    assert SYSTEM_GROUNDING in EVALUATOR_INSTRUCTIONS
    assert SYSTEM_GROUNDING in QUESTION_ANSWER_INSTRUCTIONS
