"""
devguard/understand.py — Project Understanding step.

Reads the target project's source tree using Python AST and static analysis.
Produces a structured Understanding record describing every source file,
its top-level symbols, and all test functions found in the test suite.

No LLM is called here.  Every finding is labelled with the provenance tag
OBSERVED (directly read from source) or DOCUMENTED (read from markdown docs).

Output schema (as a plain Python dict / JSON-serialisable):
{
  "project_root": str,
  "analyzed_at": str,           # ISO-8601 UTC
  "source_files": [FileRecord],
  "test_files": [TestFileRecord],
  "doc_files": [DocFileRecord],
  "constants": [ConstantRecord],
  "provenance": "OBSERVED"
}
"""

from __future__ import annotations

import ast
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") and path.suffix == ".py"


def _is_source_file(path: Path) -> bool:
    return (
        path.suffix == ".py"
        and not _is_test_file(path)
        and path.name != "__init__.py"
        and path.name != "__main__.py"
    )


def _parse_module_symbols(path: Path) -> dict:
    """Parse a Python source file and extract top-level symbols.

    Returns a dict with:
        classes:   list of class names
        functions: list of top-level function names
        constants: list of {name, value_repr, lineno} for module-level assignments
                   where the value is a numeric or string literal
        imports:   list of imported module names (top-level only)
        docstring: module docstring or None
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return {
            "classes": [], "functions": [], "constants": [],
            "imports": [], "docstring": None,
            "parse_error": str(exc),
        }

    classes = []
    functions = []
    constants = []
    imports = []
    docstring = ast.get_docstring(tree)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            else:
                module = node.module or ""
                imports.append(module)
        elif isinstance(node, ast.Assign):
            # Capture simple module-level constant assignments (e.g. LOYALTY_DISCOUNT = 0.10)
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    # Only capture literals (numbers, strings, booleans)
                    value_repr = _literal_repr(node.value)
                    if value_repr is not None:
                        constants.append({
                            "name": target.id,
                            "value_repr": value_repr,
                            "lineno": node.lineno,
                            "provenance": "OBSERVED",
                        })
        elif isinstance(node, ast.AnnAssign):
            # Capture annotated assignments: LOYALTY_DISCOUNT: float = 0.10
            if (
                isinstance(node.target, ast.Name)
                and node.target.id.isupper()
                and node.value is not None
            ):
                value_repr = _literal_repr(node.value)
                if value_repr is not None:
                    constants.append({
                        "name": node.target.id,
                        "value_repr": value_repr,
                        "lineno": node.lineno,
                        "provenance": "OBSERVED",
                    })

    return {
        "classes": classes,
        "functions": functions,
        "constants": constants,
        "imports": imports,
        "docstring": docstring,
    }


def _literal_repr(node: ast.expr) -> str | None:
    """Return a string representation of a literal AST node, or None."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal_repr(node.operand)
        if inner is not None:
            return f"-{inner}"
    return None


def _parse_test_functions(path: Path) -> list[dict]:
    """Return all test function names and their docstrings from a test file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                results.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "docstring": ast.get_docstring(node),
                })
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ProjectUnderstanding:
    """Holds the complete static understanding of a project."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    # Convenience accessors
    @property
    def source_files(self) -> list[dict]:
        return self._data["source_files"]

    @property
    def test_files(self) -> list[dict]:
        return self._data["test_files"]

    @property
    def constants(self) -> list[dict]:
        return self._data["constants"]

    @property
    def doc_files(self) -> list[dict]:
        return self._data["doc_files"]

    def get_constants_by_file(self, filename: str) -> list[dict]:
        """Return all constants found in a specific source file (basename match)."""
        return [
            c for c in self._data["constants"]
            if os.path.basename(c["source_file"]) == filename
        ]

    def get_source_file(self, filename: str) -> dict | None:
        """Return the FileRecord for a given basename, or None."""
        for sf in self._data["source_files"]:
            if os.path.basename(sf["path"]) == filename:
                return sf
        return None

    def get_tests_for_file(self, filename: str) -> list[str]:
        """Return test function names from test files whose name matches test_<filename>."""
        stem = Path(filename).stem                 # e.g. "customers"
        target = f"test_{stem}.py"
        for tf in self._data["test_files"]:
            if os.path.basename(tf["path"]) == target:
                return [t["name"] for t in tf.get("test_functions", [])]
        return []


def understand(project_root: str | Path) -> ProjectUnderstanding:
    """Analyse a project directory and return a ProjectUnderstanding.

    Walks the project root, parsing all Python source files and test files,
    and reading any Markdown documentation.

    Args:
        project_root: Path to the project root (e.g. "sample_app/").

    Returns:
        A ProjectUnderstanding instance with fully populated data.
    """
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {root}")

    source_files: list[dict] = []
    test_files: list[dict] = []
    doc_files: list[dict] = []
    all_constants: list[dict] = []

    # Walk all .py and .md files
    for py_path in sorted(root.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in py_path.parts:
            continue

        relative = str(py_path.relative_to(root))
        sha = _sha256(py_path)
        line_count = len(py_path.read_text(encoding="utf-8").splitlines())

        if _is_test_file(py_path):
            test_fns = _parse_test_functions(py_path)
            test_files.append({
                "path": relative,
                "sha256": sha,
                "line_count": line_count,
                "test_functions": test_fns,
                "test_count": len(test_fns),
                "provenance": "OBSERVED",
            })
        elif _is_source_file(py_path):
            symbols = _parse_module_symbols(py_path)
            record: dict[str, Any] = {
                "path": relative,
                "sha256": sha,
                "line_count": line_count,
                "classes": symbols["classes"],
                "functions": symbols["functions"],
                "imports": symbols["imports"],
                "docstring": symbols["docstring"],
                "provenance": "OBSERVED",
            }
            source_files.append(record)
            # Attach source_file path to each constant then hoist to top-level list
            for c in symbols["constants"]:
                c["source_file"] = relative
                all_constants.append(c)

    for md_path in sorted(root.rglob("*.md")):
        if "__pycache__" in md_path.parts:
            continue
        relative = str(md_path.relative_to(root))
        content = md_path.read_text(encoding="utf-8")
        sha = hashlib.sha256(md_path.read_bytes()).hexdigest()
        doc_files.append({
            "path": relative,
            "sha256": sha,
            "line_count": len(content.splitlines()),
            "char_count": len(content),
            "provenance": "DOCUMENTED",
        })

    return ProjectUnderstanding({
        "project_root": str(root),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "source_files": source_files,
        "test_files": test_files,
        "doc_files": doc_files,
        "constants": all_constants,
        "provenance": "OBSERVED",
    })
