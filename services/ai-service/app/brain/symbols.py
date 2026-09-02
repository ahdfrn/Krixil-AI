"""Real symbol extraction for Project Brain (PRD §13's "Symbol Index"). Python is accurate — real
stdlib `ast` parsing, real line numbers. JS/TS/JSX/TSX is a real but deliberately narrow
regex heuristic (no new parser dependency), single-line detection only: it finds a real
declaration line, but doesn't know where the function/class actually ends without a real parser,
so it never claims an end_line for those. Every other language just isn't parsed — no symbols
found there, not a fabricated zero-effort "supported" claim.
"""

import ast
import re
from dataclasses import dataclass

_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".md": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
}


def guess_language(path: str) -> str | None:
    for ext, language in _LANGUAGE_BY_EXTENSION.items():
        if path.endswith(ext):
            return language
    return None


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str  # "function" | "class"
    start_line: int
    end_line: int | None  # None when the real end can't be determined (JS/TS heuristic)


def _extract_python_symbols(content: str) -> list[Symbol]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # A real file that doesn't parse (a template, a fragment, a genuine syntax error) —
        # no symbols found, not a crash, not a guess.
        return []
    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            symbols.append(
                Symbol(
                    name=node.name,
                    kind="function",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                Symbol(
                    name=node.name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                )
            )
    return symbols


_JS_TS_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)"
)
_JS_TS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)")
_JS_TS_ARROW_CONST_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>"
)


def _extract_js_ts_symbols(content: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern, kind in (
            (_JS_TS_FUNCTION_RE, "function"),
            (_JS_TS_CLASS_RE, "class"),
            (_JS_TS_ARROW_CONST_RE, "function"),
        ):
            match = pattern.match(line)
            if match:
                symbols.append(
                    Symbol(name=match.group(1), kind=kind, start_line=line_number, end_line=None)
                )
                break
    return symbols


def extract_symbols(path: str, content: str) -> list[Symbol]:
    language = guess_language(path)
    if language == "python":
        return _extract_python_symbols(content)
    if language in ("javascript", "typescript"):
        return _extract_js_ts_symbols(content)
    return []
