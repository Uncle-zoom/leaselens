"""Structured outputs for the LeaseLens agent team (PydanticAI)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["hidden gem", "fine", "think twice"]


class BlockVerdict(BaseModel):
    verdict: Verdict
    reasons: list[str] = Field(min_length=3, max_length=3, description="Exactly three one-sentence reasons, each citing a fact.")
    summary: str = Field(description="One sentence a renter could read aloud.")


class LandlordReport(BaseModel):
    plain_english: str = Field(description="Short paragraph on what the owner, registry and other-parcel records show.")
    observations: list[str] = Field(max_length=4, description="Two to four neutral one-sentence observations.")
    questions: list[str] = Field(min_length=3, max_length=3, description="Exactly three questions to ask the landlord.")


class EmailDraft(BaseModel):
    purpose: Literal["ask_questions", "negotiate"]
    tone: Literal["friendly", "firm"] = "friendly"
    subject: str
    body: str
    facts_cited: list[str] = Field(description="Facts used, copied exactly from the data.")


class RankedAddress(BaseModel):
    address: str
    rank: int = Field(ge=1)
    headline: str
    strengths: list[str] = Field(max_length=3)
    trade_offs: list[str] = Field(max_length=3)


class Recommendation(BaseModel):
    ranking: list[RankedAddress]
    overall: str
    key_tradeoffs: str


class ChatAnswer(BaseModel):
    answer: str
    known: bool = Field(description="False when the data does not contain the answer.")
    sources: list[str] = Field(default_factory=list, description="Data sections used.")
