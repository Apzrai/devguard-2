"""
devguard/verifier.py — Behavioral Verifier.

Verifies that a proposed Bob change preserves protected behavior and correctly
implements the requested change by:

  1. Creating a working copy of the LegacyShop source (never the canonical sample_app).
  2. Applying the proposed diff (or a direct file patch) to the working copy.
  3. Running the existing deterministic pytest suite against the working copy.
  4. Capturing actual test results — pass, fail, error counts and identities.
  5. Determining whether:
       a. The requested behavior changed correctly.
       b. Protected behaviors were preserved (no protected tests failed).
       c. No unexpected changes occurred.

No LLM is called.  All verdicts are derived from actual pytest output.

Output schema:
{
  "verification_id": str,
  "verified_at": str,
  "contract_id": str,
  "working_copy": str,                  # path to the temporary working copy
  "patch_applied": bool,
  "tests_run": int,
  "tests_passed": int,
  "tests_failed": int,
  "tests_errored": int,
  "failed_test_ids": [str],             # pytest node IDs of failed tests
  "protected_tests_failed": [str],      # subset that are protected anchors
  "requested_behavior_correct": bool,   # requested symbol changed to correct value
  "protected_behavior_preserved": bool, # no protected test failures
  "unexpected_changes": [str],          # symbols changed that are not in allowed scope
  "contract_satisfied": bool,           # all criteria met
  "status": "PASSED" | "FAILED" | "ERROR",
  "summary": str,
}
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devguard.contract import BehavioralContract
from devguard.bob_executor import BobResponse
from devguard.drift_detector import DriftResult


# ---------------------------------------------------------------------------
# Working copy management
# ---------------------------------------------------------------------------

def _create_working_copy(source_root: Path) -> Path:
    """Copy the source project into a fresh temporary directory.

    Args:
        source_root: The canonical source project root (never modified).

    Returns:
        Path to the working copy root.
    """
    tmp = Path(tempfile.mkdtemp(prefix="devguard_wc_"))
    dest = tmp / source_root.name
    shutil.copytree(str(source_root), str(dest))
    return dest


def cleanup_working_copy(working_copy: Path) -> None:
    """Remove the working copy directory tree.

    Args:
        working_copy: Path returned by _create_working_copy().
                      The parent tmpdir is also removed.
    """
    parent = working_copy.parent
    if parent.exists() and "devguard_wc_" in parent.name:
        shutil.rmtree(str(parent), ignore_errors=True)


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def _apply_patch_to_working_copy(
    working_copy: Path,
    target_filename: str,
    symbol: str,
    new_value: str,
) -> bool:
    """Apply a targeted symbol value change to the working copy.

    This is a simple, reliable line-level patch that replaces the assignment
    of `symbol` in `target_filename` with the new value.  It handles both
    annotated and plain assignment forms.

    Args:
        working_copy:    Path to the working copy root.
        target_filename: Basename of the file to patch (e.g. "customers.py").
        symbol:          The constant name to update (e.g. "LOYALTY_DISCOUNT").
        new_value:       The new value string (e.g. "0.15").

    Returns:
        True if the symbol was found and replaced, False otherwise.
    """
    # Find the file in the working copy
    candidates = list(working_copy.rglob(target_filename))
    if not candidates:
        return False
    target = candidates[0]
    content = target.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    new_lines = []
    replaced = False
    # Pattern: optional leading spaces, SYMBOL: type = VALUE  or  SYMBOL = VALUE
    pattern = re.compile(
        r'^(\s*' + re.escape(symbol) + r'\s*(?::\s*\S+\s*)?)=\s*[^\s#]+'
    )
    for line in lines:
        m = pattern.match(line)
        if m:
            # Preserve the comment if any
            comment_match = re.search(r'(#.*)$', line)
            comment = "  " + comment_match.group(1) if comment_match else ""
            prefix = m.group(1)
            new_lines.append(f"{prefix}= {new_value}{comment}\n")
            replaced = True
        else:
            new_lines.append(line)
    if replaced:
        target.write_text("".join(new_lines), encoding="utf-8")
    return replaced


def apply_diff_to_working_copy(
    working_copy: Path,
    target_filename: str,
    changes: list[dict],
) -> bool:
    """Apply a set of symbol changes (from diff analysis) to the working copy.

    Args:
        working_copy:    Path to the working copy root.
        target_filename: The source file to patch.
        changes:         List of {symbol, to_value} dicts from drift_detector.

    Returns:
        True if all changes were applied successfully.
    """
    all_ok = True
    for ch in changes:
        sym = ch.get("symbol")
        new_val = ch.get("to_value")
        if sym and new_val:
            ok = _apply_patch_to_working_copy(working_copy, target_filename, sym, new_val)
            if not ok:
                all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Pytest runner
# ---------------------------------------------------------------------------

# Matches pytest's short-test-summary line for failures/errors
_SUMMARY_RE = re.compile(
    r'=+\s+(?:(\d+) failed)?(?:,?\s*)?(?:(\d+) error(?:s)?)?(?:,?\s*)?(?:(\d+) passed)?'
    r'|(\d+) passed(?:,\s*(\d+) failed)?(?:,\s*(\d+) error(?:s)?)?'
)


def _run_pytest(working_copy: Path, project_workspace: Path) -> dict:
    """Run the sample_app test suite against the working copy.

    We run pytest with the working copy injected into sys.path so that
    `sample_app` imports resolve to the working copy, not the canonical one.

    Args:
        working_copy:       Path to the working copy (contains sample_app/).
        project_workspace:  Workspace root (contains pytest.ini).

    Returns:
        A dict with keys:
          returncode, stdout, stderr,
          tests_run, tests_passed, tests_failed, tests_errored,
          failed_test_ids
    """
    # The working copy contains a copy of sample_app.
    # We run pytest with --rootdir pointing at the working copy,
    # and set PYTHONPATH so imports pick up the working copy's sample_app.
    test_dir = working_copy / "tests"
    if not test_dir.exists():
        # Working copy is the sample_app dir itself
        test_dir = working_copy

    import os
    env = os.environ.copy()
    # Prepend the working copy's parent to PYTHONPATH so
    # `import sample_app` resolves to the working copy
    wp_parent = str(working_copy.parent)
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = wp_parent + (os.pathsep + existing_path if existing_path else "")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_dir), "-v", "--tb=no"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )

    stdout = result.stdout + result.stderr
    failed_ids: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED "):
            failed_ids.append(stripped[len("FAILED "):].strip())

    # Parse the final summary line, e.g.:
    #   "5 failed, 121 passed in 1.23s"  or  "126 passed in 0.98s"
    tests_passed = 0
    tests_failed = 0
    tests_errored = 0
    # Look for the terminal summary line (contains " passed" and optionally " failed")
    _SHORT_SUMMARY = re.compile(
        r'(?:(\d+) failed,?\s*)?(\d+) passed(?:,\s*(\d+) error)?'
    )
    for line in reversed(stdout.splitlines()):
        m = _SHORT_SUMMARY.search(line)
        if m and "passed" in line:
            tests_failed = int(m.group(1) or 0)
            tests_passed = int(m.group(2) or 0)
            tests_errored = int(m.group(3) or 0)
            break

    tests_run = tests_passed + tests_failed + tests_errored

    return {
        "returncode": result.returncode,
        "stdout": stdout,
        "tests_run": tests_run,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "tests_errored": tests_errored,
        "failed_test_ids": failed_ids,
    }


# ---------------------------------------------------------------------------
# Protected test detection — baseline comparison
# ---------------------------------------------------------------------------

def _get_baseline_failures(source_root: Path, contract: BehavioralContract) -> set[str]:
    """Apply ONLY the allowed change and return the test function names that fail.

    This baseline captures tests that legitimately fail because the intended
    symbol was updated (e.g. tests that hardcode the old Enterprise value).
    Any failure in the candidate run absent from this baseline is a genuine
    protected-behavior violation.

    Args:
        source_root: Canonical source project root (never modified).
        contract:    Behavioral contract supplying the allowed change.

    Returns:
        Set of test function names (last ``::`` segment of the node ID)
        that fail after applying the allowed change alone.
    """
    allowed = contract.allowed_change
    wc = _create_working_copy(source_root)
    try:
        _apply_patch_to_working_copy(
            wc, allowed["file"], allowed["symbol"], allowed["to_value"]
        )
        run = _run_pytest(wc, source_root.parent)
        return {tid.split("::")[-1] for tid in run["failed_test_ids"]}
    finally:
        cleanup_working_copy(wc)


def _identify_protected_failures(
    candidate_failed_ids: list[str],
    baseline_failed_fns: set[str],
) -> list[str]:
    """Return failures in the candidate run that are absent from the baseline.

    Args:
        candidate_failed_ids: Full pytest node IDs from the proposed-diff run.
        baseline_failed_fns:  Function names that fail after the allowed-only change.

    Returns:
        Candidate failures whose function name is NOT in the baseline — these
        are caused by something beyond the allowed change and represent genuine
        protected-behavior violations.
    """
    return [
        tid for tid in candidate_failed_ids
        if tid.split("::")[-1] not in baseline_failed_fns
    ]


# ---------------------------------------------------------------------------
# Symbol value check in working copy
# ---------------------------------------------------------------------------

def _read_symbol_value(working_copy: Path, filename: str, symbol: str) -> str | None:
    """Read the current value of a symbol from the working copy.

    Args:
        working_copy: Path to the working copy root.
        filename:     Basename of the file.
        symbol:       The constant name.

    Returns:
        The value as a string, or None if not found.
    """
    candidates = list(working_copy.rglob(filename))
    if not candidates:
        return None
    content = candidates[0].read_text(encoding="utf-8")
    pattern = re.compile(
        r'^\s*' + re.escape(symbol) + r'\s*(?::\s*\S+\s*)?\s*=\s*([^\s#\n]+)',
        re.MULTILINE,
    )
    m = pattern.search(content)
    if m:
        return m.group(1).rstrip(",;")
    return None


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

class VerificationResult:
    """The result of a behavioral verification run."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    @property
    def contract_satisfied(self) -> bool:
        return self._data["contract_satisfied"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def protected_behavior_preserved(self) -> bool:
        return self._data["protected_behavior_preserved"]

    @property
    def requested_behavior_correct(self) -> bool:
        return self._data["requested_behavior_correct"]

    @property
    def tests_failed(self) -> int:
        return self._data["tests_failed"]

    @property
    def failed_test_ids(self) -> list[str]:
        return self._data["failed_test_ids"]

    @property
    def protected_tests_failed(self) -> list[str]:
        return self._data["protected_tests_failed"]

    @property
    def summary(self) -> str:
        return self._data["summary"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify(
    contract: BehavioralContract,
    response: BobResponse,
    drift: DriftResult,
    source_root: Path,
    *,
    cleanup: bool = True,
) -> VerificationResult:
    """Verify a proposed change against the behavioral contract.

    Creates a working copy of source_root, applies all changes from the
    proposed diff, runs the test suite, and reports whether the contract
    is satisfied.

    Args:
        contract:    The behavioral contract for the maintenance request.
        response:    Bob's proposed change (contains the diff).
        drift:       The DriftResult from detect_drift() for this response.
        source_root: Path to the canonical source project (e.g. sample_app/).
                     This directory is NEVER modified.
        cleanup:     If True (default), remove the working copy when done.

    Returns:
        A VerificationResult with actual test results and verdicts.
    """
    verification_id = str(uuid.uuid4())
    verified_at = datetime.now(timezone.utc).isoformat()
    allowed = contract.allowed_change

    # Step 1: Create working copy
    working_copy = _create_working_copy(source_root)
    working_copy_str = str(working_copy)

    try:
        # Step 2: Apply ALL changes from the drift analysis
        # (both intended and unintended — we want to test what Bob actually proposed)
        all_changes = drift.intended_changes + drift.unintended_changes
        patch_applied = apply_diff_to_working_copy(
            working_copy,
            allowed["file"],
            all_changes,
        )

        # Step 3: Run the test suite against the working copy
        workspace_root = source_root.parent
        run_result = _run_pytest(working_copy, workspace_root)

        failed_test_ids = run_result["failed_test_ids"]

        # Step 4: Run baseline (allowed-only change) to learn which failures are expected
        baseline_failed_fns = _get_baseline_failures(source_root, contract)

        # Step 5: Genuine protected-behavior failures = candidate failures
        # whose function name is NOT in the baseline set
        protected_failures = _identify_protected_failures(
            failed_test_ids, baseline_failed_fns
        )

        # Step 6: Check requested behavior
        actual_value = _read_symbol_value(working_copy, allowed["file"], allowed["symbol"])
        requested_behavior_correct = (
            actual_value is not None
            and allowed["to_value"] in actual_value
        )

        # Step 7: Protected behavior preserved = no failures beyond the baseline
        protected_behavior_preserved = len(protected_failures) == 0

        # Step 8: Unexpected changes = unintended symbols in diff
        unexpected_changes = [
            uch["symbol"] for uch in drift.unintended_changes
        ]

        # Step 9: Net extra failures (beyond what the allowed change explains)
        net_failed = len(protected_failures)

        # Step 10: Contract satisfied?
        contract_satisfied = (
            patch_applied
            and requested_behavior_correct
            and protected_behavior_preserved
            and len(unexpected_changes) == 0
        )

        if net_failed > 0 or not requested_behavior_correct:
            status = "FAILED"
        else:
            status = "PASSED"

        # Build summary
        if contract_satisfied:
            summary = (
                f"Verification PASSED.\n"
                f"  Requested behavior changed correctly: "
                f"{allowed['symbol']} = {actual_value} ✓\n"
                f"  Protected behavior preserved ✓\n"
                f"  Tests: {run_result['tests_passed']} passed, "
                f"{run_result['tests_failed']} failed ✓\n"
                f"  Unexpected changes: none ✓\n"
                f"  Contract satisfied ✓"
            )
        else:
            lines = ["Verification FAILED."]
            if not requested_behavior_correct:
                lines.append(
                    f"  Requested behavior NOT correct: "
                    f"{allowed['symbol']} = {actual_value!r} "
                    f"(expected {allowed['to_value']!r})"
                )
            if not protected_behavior_preserved:
                lines.append(
                    f"  Protected behavior VIOLATED: "
                    f"{len(protected_failures)} protected test(s) failed:"
                )
                for pf in protected_failures:
                    lines.append(f"    - {pf}")
            if unexpected_changes:
                lines.append(
                    f"  Unexpected changes: {', '.join(unexpected_changes)}"
                )
            if run_result["tests_failed"] > 0:
                lines.append(
                    f"  Tests: {run_result['tests_passed']} passed, "
                    f"{run_result['tests_failed']} failed"
                )
                for fid in failed_test_ids[:10]:
                    lines.append(f"    FAILED: {fid}")
            summary = "\n".join(lines)

    except Exception as exc:  # pragma: no cover
        status = "ERROR"
        contract_satisfied = False
        requested_behavior_correct = False
        protected_behavior_preserved = False
        unexpected_changes = []
        failed_test_ids = []
        protected_failures = []
        patch_applied = False
        run_result = {
            "tests_run": 0, "tests_passed": 0,
            "tests_failed": 0, "tests_errored": 0,
        }
        summary = f"Verification ERROR: {exc}"

    finally:
        if cleanup:
            cleanup_working_copy(working_copy)

    return VerificationResult({
        "verification_id": verification_id,
        "verified_at": verified_at,
        "contract_id": contract.contract_id,
        "working_copy": working_copy_str,
        "patch_applied": patch_applied,
        "tests_run": run_result["tests_run"],
        "tests_passed": run_result["tests_passed"],
        "tests_failed": run_result["tests_failed"],
        "tests_errored": run_result["tests_errored"],
        "failed_test_ids": failed_test_ids,
        "protected_tests_failed": protected_failures,
        "requested_behavior_correct": requested_behavior_correct,
        "protected_behavior_preserved": protected_behavior_preserved,
        "unexpected_changes": unexpected_changes,
        "contract_satisfied": contract_satisfied,
        "status": status,
        "summary": summary,
    })
