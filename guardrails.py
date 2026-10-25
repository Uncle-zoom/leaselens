"""Guardrails that live in code, not in prompts: untrusted-text filter, fact check, spending caps."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from pydantic import BaseModel

# ------------------------------------------------------------------ untrusted text
REMOVED = "[text removed: it looked like an instruction]"
_INJECTION = [re.compile(p, re.I) for p in [
    r"\b(ignore|disregard|forget|override|bypass|skip)\b.{0,40}\b(instruction|rule|prompt|guideline|polic|previous|above|earlier|prior)",
    r"\b(system|developer|assistant)\s*(prompt|message|:)",
    r"\b(you are|you're)\s+(now|a|an|no longer)\b",
    r"\b(act|behave|respond|answer|reply)\s+(as|like|with|only|exactly)\b",
    r"\bnew\s+(instruction|task|role|rule)s?\b",
    r"\bpretend\b|\bjailbreak\b|\bdeveloper mode\b",
    r"\b(rate|score|rank|grade|give|mark|call)\b.{0,30}(\b10\s*/\s*10\b|\b5\s*stars?\b|\bperfect\b|\bhidden gem\b|\bbest\b|\btop\b)",
    r"\b\d+\s*/\s*10\b",
    r"\bdo not (tell|mention|reveal|say|show)\b",
    r"\b(reveal|print|repeat|output)\b.{0,30}\b(prompt|instruction|key|secret|password)",
    r"<\s*/?\s*(system|assistant|user|data|instructions?)\b|<\|",
    r"\bplease (always|never|only)\b",
    r"\bfrom now on\b",
]]
_TAGS = re.compile(r"<[^>]{0,200}>|`{3}.*?`{3}|[\x00-\x08\x0b-\x1f\x7f]", re.S)
_SENT = re.compile(r"(?<=[.!?;])\s+|\n+")


def sanitize(text: str | None, max_len: int = 240) -> tuple[str, bool]:
    """Make public- or user-written text safe to show a model as DATA.

    Sentences that look like instructions are replaced by a marker; markup, code fences and control
    characters are stripped; length is capped. Returns (clean_text, was_anything_removed).
    """
    if not text:
        return "", False
    flagged = False
    kept = []
    for sent in _SENT.split(_TAGS.sub(" ", str(text))):
        sent = sent.strip()
        if not sent:
            continue
        if any(p.search(sent) for p in _INJECTION):
            flagged = True
            if not kept or kept[-1] != REMOVED:
                kept.append(REMOVED)
        else:
            kept.append(sent)
    out = " ".join(kept)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > max_len:
        out = out[: max_len - 1].rstrip() + "…"
    return out, flagged


# ------------------------------------------------------------------ fact check
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'’.\-]*")
_PLACEHOLDER = re.compile(r"\[[^\]]*\]")
# capitalised words that are fine without being in the data: greetings, sentence openers, generic words
_STOP = {w.lower() for w in """
I I'm I'd I'll I've We Our Us You Your The This That These Those It Its Is Are Was Were Be Do Does Did Has Have Had
A An And Or But If In On At For To Of By With From As So Not No Yes What Which Who Whom Whose When Where How Why
Hello Hi Hey Dear Thanks Thank Best Regards Sincerely Cheers Please Could Would Can Should Will May Might Must
Ask Check Also However Because Since While Although Overall First Second Third Finally Next Then Here There Both
Walking Walk Minutes Street Avenue Noise Quiet Landlord Owner Parcel Parcels Registry Business Records Record Data
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August
September October November December LeaseLens LLC LP Inc Corp Co Ltd CT NY MA
Connecticut Hidden Gem Fine Think Twice Groceries Grocery Gym Transit Park Parks Bus Train Subway Station Pharmacy
Nightclubs Nightclub Bars Bar Pubs Pub Hospital Hospitals Fire Rail Line Lines Score Scores Overall Rank
Exact Normalized Same Mailing Address Name High Medium Low Confidence Match Matched Reports Report Street-level
Limit Priorities Priority Draft Subject Body Question Questions Facts Fact
""".split()}


def _num_key(s: str) -> str:
    return s.replace(",", "").rstrip(".")


def numbers_in(text: str) -> set[str]:
    return {_num_key(m) for m in _NUM.findall(text)}


def allowed_numbers(facts_text: str, extra: tuple[int, ...] = ()) -> set[str]:
    """Every number in the facts, plus the whole-number roundings of decimals (7.5 -> 7, 8)."""
    out = numbers_in(facts_text)
    for n in list(out):
        if "." in n:
            f = float(n)
            out |= {str(int(f)), str(round(f)), str(int(f) + 1)}
            out.add(n.rstrip("0").rstrip("."))
    out |= {str(x) for x in extra}
    return out


def _words(text: str) -> set[str]:
    text = text.replace("\u2019", "'")
    return {t.lower().strip(".'’-") for t in _TOKEN.findall(text)}


@dataclass
class FactIndex:
    numbers: set[str]
    words: set[str]

    @classmethod
    def build(cls, facts_text: str, extra_numbers: tuple[int, ...] = ()) -> "FactIndex":
        return cls(allowed_numbers(facts_text, extra_numbers), _words(facts_text))


def unsupported(sentence: str, idx: FactIndex) -> list[str]:
    """Numbers and capitalised names in `sentence` that are not in the facts."""
    s = _PLACEHOLDER.sub(" ", sentence.replace("\u2019", "'"))
    s = re.sub(r"(^|\n)\s*\d{1,2}[.)]\s+", r"\1", s)        # a list marker ("1. Rent: ...") is not a claim about the data
    bad = [n for n in (_num_key(m) for m in _NUM.findall(s)) if n not in idx.numbers]
    tokens = list(_TOKEN.finditer(s))
    for pos, m in enumerate(tokens):
        t = m.group(0)
        core = t.strip(".'’-")
        if not core or not core[0].isupper() or core.lower() in _STOP or core.lower() in idx.words:
            continue
        if any(ch.isdigit() for ch in core) and _num_key(core) in idx.numbers:
            continue
        before = s[:m.start()].rstrip()
        if pos == 0 or before.endswith((":", ";", "(", "-", "–", "—")) or re.fullmatch(r".*\b\d+\.", before.split("\n")[-1]):
            continue          # the first word of a sentence, or of a list item ("Rent: Whether ..."), is capitalised anyway
        bad.append(core)
    return bad


@dataclass
class Removal:
    field: str
    text: str
    unsupported: list[str]

    def to_dict(self) -> dict:
        return {"field": self.field, "text": self.text, "unsupported": self.unsupported}


def check_text(text: str, idx: FactIndex, field_name: str = "text") -> tuple[str, list[Removal]]:
    """Drop every sentence that contains a number or name that is not in the facts."""
    keep, removed = [], []
    for line in re.split(r"(\n)", text):
        if line == "\n":
            keep.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        for part in parts:
            if not part.strip():
                continue
            bad = unsupported(part, idx)
            if bad:
                removed.append(Removal(field_name, part.strip(), bad))
            else:
                keep.append(part.strip() + " ")
    return "".join(keep).strip(), removed


def fact_check(obj: BaseModel, idx: FactIndex, skip: tuple[str, ...] = (), _prefix: str = "") -> tuple[BaseModel, list[Removal]]:
    """Walk a structured output; remove unsupported sentences/items. Enums, ints and bools are left alone.

    Returns a copy (model_copy skips validation, so lists may end up shorter than the schema asked for) and
    the list of removals to show in the "removed by fact check" note.
    """
    updates, removed = {}, []
    for name, value in obj:
        path = f"{_prefix}{name}"
        if name in skip:
            continue
        if isinstance(value, str):
            new, rem = check_text(value, idx, path)
            updates[name] = new
            removed += rem
        elif isinstance(value, BaseModel):
            updates[name], rem = fact_check(value, idx, skip, path + ".")
            removed += rem
        elif isinstance(value, list):
            items = []
            for k, item in enumerate(value):
                if isinstance(item, str):
                    new, rem = check_text(item, idx, f"{path}[{k}]")
                    if rem:                      # an item with any unsupported sentence is dropped whole
                        removed.append(Removal(f"{path}[{k}]", item, sorted({u for r in rem for u in r.unsupported})))
                    else:
                        items.append(new)
                elif isinstance(item, BaseModel):
                    new, rem = fact_check(item, idx, skip, f"{path}[{k}].")
                    items.append(new)
                    removed += rem
                else:
                    items.append(item)
            updates[name] = items
    return obj.model_copy(update=updates), removed


# ------------------------------------------------------------------ wording rule (CLAUDE.md)
# Never in any output: claims of control or secrecy, or the labels we refuse to use. Ownership links are only ever "linked to".
BANNED_EVERYWHERE = [re.compile(p, re.I) for p in (
    r"\bslum\w*", r"\bshadow landlord", r"\bsecret(ly)?\b", r"\bcontrols\b", r"\bcontrolled by\b", r"\bcontrolling\b",
    r"\bscam\w*", r"\bfraud\w*", r"\bpredator\w*", r"\bshady\b", r"\bnegligent\b")]
# Extra rules for email drafts: factual and polite, no threats and no legal claims.
BANNED_IN_EMAILS = [re.compile(p, re.I) for p in (
    r"\bsue\b", r"\bsuing\b", r"\blawsuit\w*", r"\blegal action\b", r"\battorney\w*", r"\blawyer\w*", r"\billegal\w*", r"\bunlawful\w*",
    r"\bviolat(e|es|ed|ion|ions)\b", r"\bthreat\w*", r"\bor else\b", r"\bi will report\b", r"\bwe will report\b", r"\bdemand(s|ed)?\b",
    r"\bultimatum\b", r"\bin court\b", r"\bcomplaint to\b")]


def banned_in(text: str, patterns=BANNED_EVERYWHERE) -> list[str]:
    return sorted({m.group(0).lower() for rx in patterns for m in rx.finditer(text or "")})


def wording_filter(obj: BaseModel, patterns=BANNED_EVERYWHERE, skip: tuple[str, ...] = (), _prefix: str = "") -> tuple[BaseModel, list[Removal]]:
    """Remove every sentence or list item that contains banned wording. Same shape as fact_check; reasons read "banned wording: ..."."""
    updates, removed = {}, []
    for name, value in obj:
        path = f"{_prefix}{name}"
        if name in skip:
            continue
        if isinstance(value, str):
            lines_out = []
            for line in value.split("\n"):
                keep = []
                # split sentences after a letter or bracket, not after a list number ("1. Rent: ...")
                for part in re.split(r"(?<=[A-Za-z\)\"'])(?<=[.!?])\s+|(?<=[A-Za-z\)\"'][.!?])\s+", line):
                    bad = banned_in(part, patterns)
                    if bad:
                        removed.append(Removal(path, part.strip(), [f"banned wording: {b}" for b in bad]))
                    elif part.strip():
                        keep.append(part.strip())
                lines_out.append(" ".join(keep))
            updates[name] = "\n".join(lines_out)
        elif isinstance(value, BaseModel):
            updates[name], rem = wording_filter(value, patterns, skip, path + ".")
            removed += rem
        elif isinstance(value, list):
            items = []
            for k, item in enumerate(value):
                if isinstance(item, str):
                    bad = banned_in(item, patterns)
                    if bad:
                        removed.append(Removal(f"{path}[{k}]", item, [f"banned wording: {b}" for b in bad]))
                    else:
                        items.append(item)
                elif isinstance(item, BaseModel):
                    new, rem = wording_filter(item, patterns, skip, f"{path}[{k}].")
                    items.append(new)
                    removed += rem
                else:
                    items.append(item)
            updates[name] = items
    return obj.model_copy(update=updates), removed


# ------------------------------------------------------------------ caps
class BudgetExceeded(RuntimeError):
    """Raised before a model call that would break a cap. The message is safe to show the user."""


@dataclass
class Budget:
    """Caps on model requests, tokens and dollars. `name` is how the cap is described to the user."""
    name: str = "this run"
    max_requests: int = 40
    max_tokens: int = 150_000
    max_usd: float = 0.15
    requests: int = 0
    tokens: int = 0
    usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def reserve(self) -> None:
        """Check the caps AND count one request, atomically. Used before every model call so that agents running in
        parallel cannot all slip past the request cap together."""
        with self._lock:
            self._check_locked()
            self.requests += 1

    def release(self) -> None:
        with self._lock:
            self.requests = max(0, self.requests - 1)

    def check(self) -> None:
        with self._lock:
            self._check_locked()

    def _check_locked(self) -> None:
        if self.requests >= self.max_requests:
            raise BudgetExceeded(f"AI request limit reached for {self.name} ({self.max_requests} requests). "
                                 "Nothing more was sent to the model. Your data and earlier answers are unchanged.")
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded(f"AI token limit reached for {self.name} ({self.max_tokens:,} tokens). "
                                 "Nothing more was sent to the model.")
        if self.usd >= self.max_usd:
            raise BudgetExceeded(f"AI spending limit reached for {self.name} (${self.max_usd:.2f}). "
                                 "Nothing more was sent to the model.")

    def add(self, requests: int, tokens: int, usd: float) -> None:
        with self._lock:
            self.requests += requests
            self.tokens += tokens
            self.usd += usd

    def requests_left(self) -> int:
        return max(0, self.max_requests - self.requests)

    def tokens_left(self) -> int:
        return max(0, self.max_tokens - self.tokens)
