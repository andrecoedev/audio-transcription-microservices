"""Provider-neutral v1 contract; safe to import in the HTTP runtime."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Evidence(StrictModel):
    segment_order: int = Field(ge=0, description="Índice do segmento que sustenta semanticamente a afirmação, não apenas uma menção próxima.")
    quote: str = Field(min_length=1, max_length=2000, description="Trecho literal que justifica a informação; presença literal não prova suporte semântico.")


class SupportedItem(StrictModel):
    description: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(min_length=1, max_length=20, description="Segmentos que, juntos, sustentam a afirmação e os campos preenchidos; incluir contexto necessário.")


class ActionItem(SupportedItem):
    assignee: str | None = Field(max_length=255, description="Responsável explicitamente vinculado a esta tarefa; null em conflito, ruído, sugestão ou atribuição ambígua. Nome citado/speaker não é atribuição.")
    due_date: str | None = Field(max_length=255, description="Expressão literal de prazo explicitamente vinculada a esta tarefa; null para conflito, ruído ou associação incerta. Tempo de outro evento não é prazo.")


class IntelligenceResult(StrictModel):
    schema_version: Literal["1"]
    summary: str = Field(min_length=1, max_length=8000, description="Resumo fiel; não reintroduzir campos incertos nem enumerar valores descartados como responsáveis ou prazos candidatos.")
    topics: list[SupportedItem] = Field(max_length=100)
    decisions: list[SupportedItem] = Field(max_length=100, description="Somente decisões efetivamente tomadas com suporte explícito; omitir sugestões, possibilidades ou decisões incertas.")
    action_items: list[ActionItem] = Field(max_length=100, description="Somente tarefas confirmadas; omitir sugestões ou compromissos sem suporte. Campos opcionais incertos devem ser null.")
    open_questions: list[SupportedItem] = Field(max_length=100)


def validate_grounding(result: IntelligenceResult, segments: list[dict], speakers: list[dict]) -> None:
    """Check literal references, not semantic truth; never silently repair facts."""
    identities = {value for speaker in speakers for value in (speaker["id"], speaker.get("display_name")) if value}
    for item in [*result.topics, *result.decisions, *result.action_items, *result.open_questions]:
        quotes = []
        for reference in item.evidence:
            if reference.segment_order >= len(segments):
                raise ValueError("Unknown segment reference")
            if reference.quote not in segments[reference.segment_order]["text"]:
                raise ValueError("Evidence quote is absent from transcript")
            quotes.append(reference.quote)
        if isinstance(item, ActionItem):
            if item.due_date is not None and not any(item.due_date in quote for quote in quotes):
                raise ValueError("Deadline is not explicit in evidence")
            if item.assignee is not None:
                cited_ids = {segments[ref.segment_order].get("speaker") for ref in item.evidence}
                cited_names = {value for speaker in speakers if speaker["id"] in cited_ids for value in (speaker["id"], speaker.get("display_name")) if value}
                if not any(item.assignee in quote for quote in quotes) and not (item.assignee in identities and item.assignee in cited_names):
                    raise ValueError("Assignee is not identified in evidence")
