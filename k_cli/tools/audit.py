"""audit.py - Multi-model independent audit and verification consensus engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from k_cli.core.llm_driver import LLMDriver
from k_cli.git.verifier import Verifier, VerificationResult


@dataclass
class AuditCandidate:
    model: str
    code: str
    verification: VerificationResult

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "code": self.code,
            "verification": self.verification.to_dict(),
        }


@dataclass
class AuditSummary:
    task: str
    language: str
    candidates: List[AuditCandidate] = field(default_factory=list)
    consensus_reached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "language": self.language,
            "consensus_reached": self.consensus_reached,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def run_audit(
    task: str,
    models: Optional[List[str]] = None,
    language: str = "python",
    mock: bool = True,
) -> AuditSummary:
    """Run multi-model audit across selected models and evaluate consensus."""
    models = models or ["qwen2.5-coder:1.5b", "gemini-2.0-flash"]
    verifier = Verifier()

    candidates: List[AuditCandidate] = []
    passing_count = 0

    for model_name in models:
        driver = LLMDriver(model_name=model_name, mock_mode=mock)
        prompt = f"Implement the following task in {language}:\n{task}"
        generated_code = driver.generate(prompt=prompt)
        verification_res = verifier.verify(generated_code, language=language)

        if verification_res.success:
            passing_count += 1

        candidates.append(
            AuditCandidate(
                model=model_name,
                code=generated_code,
                verification=verification_res,
            )
        )

    # Consensus threshold: at least 2 passing candidates (or all if <2 total)
    consensus_reached = passing_count >= min(2, len(models))

    return AuditSummary(
        task=task,
        language=language,
        candidates=candidates,
        consensus_reached=consensus_reached,
    )
