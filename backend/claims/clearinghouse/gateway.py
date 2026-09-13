"""The one door to the clearinghouse (D1).

VendorGateway is the only code that imports the vendor module. It turns
the vendor's two exceptions into explicit outcomes so callers must handle
"maybe recorded" as a value rather than forgetting to catch it.

FakeGateway mirrors the vendor's recording rules for tests: a Registered
outcome records, a Rejected one does not, and an Unknown one records
unless told otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Registered:
    submission_id: str


@dataclass(frozen=True)
class Rejected:
    """The clearinghouse said no. Nothing was recorded. Safe to retry."""

    reason: str


@dataclass(frozen=True)
class Unknown:
    """No answer in time. The submission MAY have been recorded. Never
    retry blind: look up first."""

    reason: str


Outcome = Registered | Rejected | Unknown


class Gateway(Protocol):
    def register(self, reference: str, amount: str) -> Outcome: ...

    def lookup(self, reference: str) -> list[str]: ...


class VendorGateway:
    """Imports the vendor module lazily so the rest of the app never needs
    it on the path."""

    def register(self, reference: str, amount: str) -> Outcome:
        import clearinghouse

        try:
            return Registered(clearinghouse.submit(reference, amount))
        except clearinghouse.ClearinghouseError as exc:
            return Rejected(str(exc))
        except clearinghouse.ClearinghouseTimeout as exc:
            return Unknown(str(exc))

    def lookup(self, reference: str) -> list[str]:
        import clearinghouse

        return clearinghouse.lookup(reference)


class FakeGateway:
    def __init__(self, outcomes: list[Outcome] | tuple[Outcome, ...] = (), record_on_unknown: bool = True):
        self.outcomes = list(outcomes)
        self.record_on_unknown = record_on_unknown
        self.records: dict[str, list[str]] = {}
        self.register_calls: list[tuple[str, str]] = []
        self.lookup_calls: list[str] = []

    def register(self, reference: str, amount: str) -> Outcome:
        self.register_calls.append((reference, amount))
        n = len(self.register_calls)
        outcome = self.outcomes.pop(0) if self.outcomes else Registered(f"CH-FAKE{n:04d}")
        if isinstance(outcome, Registered):
            self.records.setdefault(reference, []).append(outcome.submission_id)
        elif isinstance(outcome, Unknown) and self.record_on_unknown:
            self.records.setdefault(reference, []).append(f"CH-LOST{n:04d}")
        return outcome

    def lookup(self, reference: str) -> list[str]:
        self.lookup_calls.append(reference)
        return list(self.records.get(reference, []))
