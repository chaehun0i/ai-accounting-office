from dataclasses import dataclass


@dataclass(frozen=True)
class Sheet:
    index: int
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Workbook:
    sheets: tuple[Sheet, ...]
    encoding: str
