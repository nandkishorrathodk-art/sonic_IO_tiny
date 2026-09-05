"""
SONIC-REDA — Semantic Code Graph & AST Taint Analysis Engine
============================================================
Parses codebases into an Abstract Syntax Tree (AST) graph, extracts symbols,
builds cross-function call-graphs, detects entry points and sensitive sinks,
and computes reachability (source-to-sink taint paths).

Enables deep, multi-month codebase auditing on complex repositories without
relying on shallow string search or context-window saturation.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class SymbolType(StrEnum):
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    MODULE = "module"


class SinkCategory(StrEnum):
    SQL = "sql"
    COMMAND_EXEC = "command_exec"
    FILE_IO = "file_io"
    DESERIALIZATION = "deserialization"
    CRYPTO = "crypto"
    AUTH_DECISION = "auth_decision"
    NETWORK_EGRESS = "network_egress"
    UNKNOWN = "unknown"


# Standard known sinks across common frameworks & standard libraries
KNOWN_SINKS: dict[str, tuple[SinkCategory, list[str]]] = {
    "sql": (
        SinkCategory.SQL,
        [
            "execute",
            "executemany",
            "raw_sql",
            "raw",
            "cursor.execute",
            "session.execute",
            "db.execute",
        ],
    ),
    "command_exec": (
        SinkCategory.COMMAND_EXEC,
        [
            "system",
            "popen",
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_output",
            "exec",
            "eval",
            "spawn",
        ],
    ),
    "file_io": (
        SinkCategory.FILE_IO,
        [
            "open",
            "remove",
            "unlink",
            "rmdir",
            "shutil.rmtree",
            "os.remove",
            "os.unlink",
        ],
    ),
    "deserialization": (
        SinkCategory.DESERIALIZATION,
        [
            "pickle.loads",
            "pickle.load",
            "yaml.load",
            "yaml.unsafe_load",
            "marshal.loads",
        ],
    ),
    "auth_decision": (
        SinkCategory.AUTH_DECISION,
        [
            "verify=False",
            "authenticate",
            "authorize",
            "check_permission",
            "set_password",
        ],
    ),
}

KNOWN_SANITIZERS = [
    "sanitize",
    "validate",
    "escape",
    "clean",
    "is_safe",
    "check_scope",
    "is_target_allowed",
    "require_operator",
    "require_admin",
    "verify_token",
    "quote",
]


@dataclass
class CodeSymbol:
    """A symbol (function, method, class) extracted from AST."""

    id: str
    name: str
    file_path: str
    symbol_type: SymbolType
    line_start: int
    line_end: int
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    is_entry_point: bool = False
    is_sink: bool = False
    sink_category: SinkCategory | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallEdge:
    """Directed edge representing a caller invoking a callee."""

    caller_id: str
    callee_name: str
    callee_id: str | None = None
    line_number: int = 0


@dataclass
class DataFlowPath:
    """Source-to-sink reachability path across the call graph."""

    entry_point: CodeSymbol
    sink: CodeSymbol
    call_chain: list[str]
    has_sanitizer: bool
    sanitizers_found: list[str]
    risk_score: float
    rationale: str


class _ASTSymbolVisitor(ast.NodeVisitor):
    """Walks Python AST to discover symbols, calls, entry points, and sinks."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.symbols: list[CodeSymbol] = []
        self.calls: list[CallEdge] = []
        self._current_class: str | None = None
        self._current_symbol: CodeSymbol | None = None

    def _get_call_name(self, node: ast.AST) -> str:
        """Extract callable name from AST Call node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._get_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Extract decorator name."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_decorator_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""

    def _classify_entry_point(self, name: str, decorators: list[str]) -> bool:
        """Check if a function acts as an external entry point (e.g. web route, CLI)."""
        route_patterns = ("route", "get", "post", "put", "delete", "patch", "api", "endpoint")
        for dec in decorators:
            dec_lower = dec.lower()
            if any(p in dec_lower for p in route_patterns):
                return True
        if name.startswith(("handle_", "on_", "endpoint_", "api_")):
            return True
        return False

    def _classify_sink(self, calls: list[str]) -> tuple[bool, SinkCategory | None]:
        """Check if the function directly invokes any sensitive sink."""
        for call in calls:
            for cat, sink_patterns in KNOWN_SINKS.values():
                for pat in sink_patterns:
                    if pat in call:
                        return True, cat
        return False, None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prev_class = self._current_class
        self._current_class = node.name
        class_id = f"{self.file_path}::{node.name}"
        class_symbol = CodeSymbol(
            id=class_id,
            name=node.name,
            file_path=self.file_path,
            symbol_type=SymbolType.CLASS,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=ast.get_docstring(node),
        )
        self.symbols.append(class_symbol)
        self.generic_visit(node)
        self._current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        func_name = node.name
        if self._current_class:
            full_name = f"{self._current_class}.{func_name}"
            sym_type = SymbolType.METHOD
        else:
            full_name = func_name
            sym_type = SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION

        sym_id = f"{self.file_path}::{full_name}"
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        parameters = [a.arg for a in node.args.args]

        sym = CodeSymbol(
            id=sym_id,
            name=full_name,
            file_path=self.file_path,
            symbol_type=sym_type,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=ast.get_docstring(node),
            decorators=decorators,
            parameters=parameters,
            is_entry_point=self._classify_entry_point(full_name, decorators),
        )

        prev_sym = self._current_symbol
        self._current_symbol = sym

        # Collect calls within this function body
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                cname = self._get_call_name(child.func)
                if cname:
                    sym.calls.append(cname)
                    self.calls.append(
                        CallEdge(
                            caller_id=sym_id,
                            callee_name=cname,
                            line_number=getattr(child, "lineno", node.lineno),
                        )
                    )

        is_sink, category = self._classify_sink(sym.calls)
        sym.is_sink = is_sink
        sym.sink_category = category

        self.symbols.append(sym)
        self._current_symbol = prev_sym


class CodeGraph:
    """
    In-memory semantic graph representing multi-file codebase structure.
    Indexes symbols, builds cross-file call graphs, and identifies reachability paths.
    """

    def __init__(self):
        self.symbols: dict[str, CodeSymbol] = {}
        self.name_to_symbol_ids: dict[str, list[str]] = defaultdict(list)
        self.caller_to_callees: dict[str, list[str]] = defaultdict(list)
        self.callee_to_callers: dict[str, list[str]] = defaultdict(list)
        self.call_edges: list[CallEdge] = []
        self.files_indexed: set[str] = set()

    def index_source(self, file_path: str, source_code: str) -> bool:
        """Parse source code into AST and integrate into code graph."""
        try:
            tree = ast.parse(source_code, filename=file_path)
        except Exception as e:
            logger.warning("ast_parse_failed", file=file_path, error=str(e))
            return False

        visitor = _ASTSymbolVisitor(file_path=file_path)
        visitor.visit(tree)

        # Register symbols
        for sym in visitor.symbols:
            self.symbols[sym.id] = sym
            self.name_to_symbol_ids[sym.name].append(sym.id)
            # Also register by simple name if method
            if "." in sym.name:
                simple_name = sym.name.split(".")[-1]
                self.name_to_symbol_ids[simple_name].append(sym.id)

        # Store edges
        for edge in visitor.calls:
            self.call_edges.append(edge)

        self.files_indexed.add(file_path)
        self._resolve_edges()
        return True

    def index_file(self, file_path: str) -> bool:
        """Read and index a single file from disk."""
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.index_source(file_path, content)
        except Exception as e:
            logger.warning("file_index_failed", file=file_path, error=str(e))
            return False

    def index_directory(
        self,
        root_dir: str,
        extensions: tuple[str, ...] = (".py",),
        exclude_dirs: tuple[str, ...] = (".git", "__pycache__", "venv", ".venv", "node_modules", "dist", "build"),
    ) -> int:
        """Recursively index all matching source files in a directory tree."""
        count = 0
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file.endswith(extensions):
                    path = os.path.join(root, file)
                    if self.index_file(path):
                        count += 1
        self._resolve_edges()
        return count

    def _resolve_edges(self) -> None:
        """Resolve callee names to symbol IDs across indexed files."""
        self.caller_to_callees.clear()
        self.callee_to_callers.clear()

        for edge in self.call_edges:
            callee_ids = self.name_to_symbol_ids.get(edge.callee_name, [])
            if callee_ids:
                edge.callee_id = callee_ids[0]
                self.caller_to_callees[edge.caller_id].append(edge.callee_id)
                self.callee_to_callers[edge.callee_id].append(edge.caller_id)

    def find_entry_points(self) -> list[CodeSymbol]:
        """Return all discovered entry points."""
        return [sym for sym in self.symbols.values() if sym.is_entry_point]

    def find_sinks(self, category: SinkCategory | None = None) -> list[CodeSymbol]:
        """Return all discovered sinks, optionally filtered by category."""
        return [
            sym
            for sym in self.symbols.values()
            if sym.is_sink and (category is None or sym.sink_category == category)
        ]

    def trace_paths_to_sinks(self, max_depth: int = 6) -> list[DataFlowPath]:
        """
        Compute reachability paths from all entry points to sensitive sinks.
        Detects if any sanitizer or validation boundary exists along the path.
        """
        entry_points = self.find_entry_points()
        sinks = {sym.id: sym for sym in self.find_sinks()}
        paths: list[DataFlowPath] = []

        for ep in entry_points:
            visited = set()
            queue: list[tuple[str, list[str]]] = [(ep.id, [ep.id])]

            while queue:
                current_id, current_chain = queue.pop(0)
                if len(current_chain) > max_depth:
                    continue

                # Check if current node is a sink
                if current_id in sinks and current_id != ep.id:
                    sink_sym = sinks[current_id]
                    sanitizers = self._find_sanitizers_in_chain(current_chain)
                    has_san = len(sanitizers) > 0

                    # Unsanitized paths carry high risk score
                    risk = 0.9 if not has_san else 0.25
                    rationale = (
                        f"Direct unvalidated reachability from entry point '{ep.name}' "
                        f"to {sink_sym.sink_category.value if sink_sym.sink_category else 'sensitive'} sink '{sink_sym.name}'."
                        if not has_san
                        else f"Sanitizer(s) [{', '.join(sanitizers)}] detected along call chain."
                    )

                    paths.append(
                        DataFlowPath(
                            entry_point=ep,
                            sink=sink_sym,
                            call_chain=current_chain,
                            has_sanitizer=has_san,
                            sanitizers_found=sanitizers,
                            risk_score=risk,
                            rationale=rationale,
                        )
                    )

                # Expand successors
                for next_id in self.caller_to_callees.get(current_id, []):
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, current_chain + [next_id]))

        # Sort descending by risk score
        paths.sort(key=lambda p: p.risk_score, reverse=True)
        return paths

    def _find_sanitizers_in_chain(self, chain: list[str]) -> list[str]:
        """Scan function names and calls along the chain for known sanitizers."""
        sanitizers = []
        for sym_id in chain:
            sym = self.symbols.get(sym_id)
            if not sym:
                continue
            name_lower = sym.name.lower()
            for s in KNOWN_SANITIZERS:
                if s in name_lower:
                    sanitizers.append(sym.name)
            for call in sym.calls:
                call_lower = call.lower()
                for s in KNOWN_SANITIZERS:
                    if s in call_lower:
                        sanitizers.append(call)
        return list(set(sanitizers))

    def summary(self) -> dict[str, Any]:
        """Generate high-level architectural metrics."""
        entry_points = self.find_entry_points()
        sinks = self.find_sinks()
        paths = self.trace_paths_to_sinks()
        unvalidated = [p for p in paths if not p.has_sanitizer]

        return {
            "files_indexed": len(self.files_indexed),
            "symbols_total": len(self.symbols),
            "call_edges": len(self.call_edges),
            "entry_points": len(entry_points),
            "sinks": len(sinks),
            "reachability_paths": len(paths),
            "unvalidated_paths": len(unvalidated),
            "top_unvalidated": [
                {
                    "entry_point": p.entry_point.name,
                    "sink": p.sink.name,
                    "sink_category": p.sink.sink_category.value if p.sink.sink_category else "unknown",
                    "risk_score": p.risk_score,
                }
                for p in unvalidated[:5]
            ],
        }

