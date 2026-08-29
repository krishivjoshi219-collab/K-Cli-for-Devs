"""Provider-aware prompt scaffolding used by K-CLI commands."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    strengths: str
    response_contract: str


PROFILES = {
    "gemini": ModelProfile("Gemini", "large-context analysis and implementation", "State assumptions, then emit one implementation."),
    "claude": ModelProfile("Claude", "careful design, refactoring, and review", "Prefer a small, reviewable diff with explicit trade-offs."),
    "openai": ModelProfile("OpenAI-compatible", "tool-oriented coding and concise execution", "Work from repository evidence and keep the final answer concise."),
    "deepseek": ModelProfile("DeepSeek", "reasoning-heavy algorithmic and coding tasks", "Check edge cases and return executable code."),
    "ollama": ModelProfile("Local model", "focused local code generation", "Use short context, concrete constraints, and one self-contained answer."),
    "default": ModelProfile("Generic model", "general software engineering", "Return a minimal, testable implementation."),
}


def resolve_profile(model_name: str) -> ModelProfile:
    name = (model_name or "").lower()
    for key, profile in PROFILES.items():
        if key != "default" and key in name:
            return profile
    return PROFILES["ollama"] if ":" in name else PROFILES["default"]


def enhance_prompt(task: str, model_name: str, language: str = "python") -> str:
    """Add a short provider-specific execution contract without changing user intent."""
    profile = resolve_profile(model_name)
    return (
        f"You are using {profile.name}. Your strength for this task is {profile.strengths}.\n"
        f"Target language: {language}. {profile.response_contract}\n"
        "Respect existing APIs, avoid unrelated rewrites, and make acceptance criteria observable.\n\n"
        f"Task: {task}"
    )
