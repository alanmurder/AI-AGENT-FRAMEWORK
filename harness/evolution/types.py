"""Evolution system type definitions."""

from pydantic import BaseModel


class ThreeAgentResult(BaseModel):
    passed: bool
    skill_content: str
    skill_spec: str
    evaluation: str
    rounds: int
    suggestions: list[str] = []


class EvolutionCheckResult(BaseModel):
    needs_evolution: bool
    reason: str = ""
    suggested_skill_name: str = ""


class GEPACandidate(BaseModel):
    variant_id: str
    content: str
    score: float
    criteria_scores: dict[str, float] = {}


class GEPAResult(BaseModel):
    optimized: bool
    original_score: float
    best_candidate: GEPACandidate | None = None
    candidates_count: int = 0