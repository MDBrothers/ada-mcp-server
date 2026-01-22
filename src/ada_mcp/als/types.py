"""LSP type definitions and dataclasses for ALS communication."""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class DiagnosticSeverity(IntEnum):
    """LSP diagnostic severity levels."""

    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class SymbolKind(IntEnum):
    """LSP symbol kinds."""

    FILE = 1
    MODULE = 2
    NAMESPACE = 3
    PACKAGE = 4
    CLASS = 5
    METHOD = 6
    PROPERTY = 7
    FIELD = 8
    CONSTRUCTOR = 9
    ENUM = 10
    INTERFACE = 11
    FUNCTION = 12
    VARIABLE = 13
    CONSTANT = 14
    STRING = 15
    NUMBER = 16
    BOOLEAN = 17
    ARRAY = 18
    OBJECT = 19
    KEY = 20
    NULL = 21
    ENUM_MEMBER = 22
    STRUCT = 23
    EVENT = 24
    OPERATOR = 25
    TYPE_PARAMETER = 26


@dataclass
class Position:
    """LSP position (0-based line and character)."""

    line: int
    character: int

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "Position":
        return cls(line=data["line"], character=data["character"])


@dataclass
class Range:
    """LSP range with start and end positions."""

    start: Position
    end: Position

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Range":
        return cls(start=Position.from_dict(data["start"]), end=Position.from_dict(data["end"]))


@dataclass
class Location:
    """LSP location (URI + range)."""

    uri: str
    range: Range

    def to_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "range": self.range.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Location":
        return cls(uri=data["uri"], range=Range.from_dict(data["range"]))


@dataclass
class Diagnostic:
    """LSP diagnostic (error, warning, etc.)."""

    range: Range
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    code: str | None = None
    source: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Diagnostic":
        return cls(
            range=Range.from_dict(data["range"]),
            message=data["message"],
            severity=DiagnosticSeverity(data.get("severity", 1)),
            code=data.get("code"),
            source=data.get("source"),
        )


@dataclass
class DocumentSymbol:
    """LSP document symbol."""

    name: str
    kind: SymbolKind
    range: Range
    selection_range: Range
    detail: str | None = None
    children: list["DocumentSymbol"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentSymbol":
        children = [cls.from_dict(c) for c in data.get("children", [])]
        return cls(
            name=data["name"],
            kind=SymbolKind(data["kind"]),
            range=Range.from_dict(data["range"]),
            selection_range=Range.from_dict(data["selectionRange"]),
            detail=data.get("detail"),
            children=children,
        )


@dataclass
class SymbolInformation:
    """LSP workspace symbol information."""

    name: str
    kind: SymbolKind
    location: Location
    container_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolInformation":
        return cls(
            name=data["name"],
            kind=SymbolKind(data["kind"]),
            location=Location.from_dict(data["location"]),
            container_name=data.get("containerName"),
        )


@dataclass
class CompletionItem:
    """LSP completion item."""

    label: str
    kind: int | None = None
    detail: str | None = None
    documentation: str | None = None
    insert_text: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionItem":
        doc = data.get("documentation")
        if isinstance(doc, dict):
            doc = doc.get("value", str(doc))
        return cls(
            label=data["label"],
            kind=data.get("kind"),
            detail=data.get("detail"),
            documentation=doc,
            insert_text=data.get("insertText"),
        )


@dataclass
class Hover:
    """LSP hover result."""

    contents: str
    range: Range | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hover":
        contents = data.get("contents", "")
        if isinstance(contents, dict):
            contents = contents.get("value", str(contents))
        elif isinstance(contents, list):
            # Handle MarkedString[]
            parts = []
            for item in contents:
                if isinstance(item, dict):
                    parts.append(item.get("value", str(item)))
                else:
                    parts.append(str(item))
            contents = "\n".join(parts)

        range_data = data.get("range")
        return cls(contents=contents, range=Range.from_dict(range_data) if range_data else None)


@dataclass
class TextDocumentIdentifier:
    """LSP text document identifier."""

    uri: str

    def to_dict(self) -> dict[str, str]:
        return {"uri": self.uri}


@dataclass
class TextDocumentPositionParams:
    """LSP text document position parameters."""

    text_document: TextDocumentIdentifier
    position: Position

    def to_dict(self) -> dict[str, Any]:
        return {"textDocument": self.text_document.to_dict(), "position": self.position.to_dict()}
