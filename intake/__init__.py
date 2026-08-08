"""Six-field intake: what the user says, and everything resolved around it."""

from intake.premise import Advisory, check
from intake.resolve import Resolution, resolve
from intake.spec import ContractSpec, DealSpec

__all__ = [
    "Advisory",
    "ContractSpec",
    "DealSpec",
    "Resolution",
    "check",
    "resolve",
]
