"""
devguard/bob_executor.py — BobExecutor interface and implementations.

Defines the abstract BobExecutor contract and three concrete backends:

  MockBobExecutor
    ---------------
    Applies a pre-written diff from fixtures/bob_mock_response.json.
    Always available — no external dependencies or API keys.
    This is the reliable demo path.

  WatsonxLLMExecutor
    ------------------
    Sends the BobTask prompt to IBM watsonx.ai as a plain LLM call.
    Requires WATSONX_API_KEY and WATSONX_PROJECT_ID in .env.
    Parses the response into a BobResponse.

  WatsonxAgentExecutor
    --------------------
    Stub only.  Marked NotImplemented until the IBM Bob Agents API
    endpoint is confirmed.  Raises NotImplementedError if called.

The executor is selected by the BOB_BACKEND environment variable:
  BOB_BACKEND=mock             → MockBobExecutor
  BOB_BACKEND=watsonx_llm      → WatsonxLLMExecutor
  BOB_BACKEND=watsonx_agent    → WatsonxAgentExecutor (raises NotImplementedError)

All executors implement the same interface:
  execute(task: BobTask) -> BobResponse

BobResponse:
  intent_summary    — what Bob says it did (natural language)
  proposed_diff     — unified diff of the change
  files_modified    — list of file paths Bob claims to have changed
  raw               — the raw response from Bob (string or dict)
  executor_backend  — which backend produced this response
  executed_at       — ISO-8601 UTC timestamp
"""

from __future__ import annotations

import json
import os
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devguard.bob_task import BobTask


# ---------------------------------------------------------------------------
# BobResponse
# ---------------------------------------------------------------------------

@dataclass
class BobResponse:
    """The structured response from Bob after executing a maintenance task."""

    intent_summary: str          # What Bob says it did
    proposed_diff: str           # Unified diff of the change
    files_modified: list[str]    # File paths Bob claims to have changed
    raw: str                     # Raw response text / JSON from Bob
    executor_backend: str        # "mock" | "watsonx_llm" | "watsonx_agent"
    executed_at: str             # ISO-8601 UTC

    def to_dict(self) -> dict:
        return {
            "intent_summary": self.intent_summary,
            "proposed_diff": self.proposed_diff,
            "files_modified": self.files_modified,
            "raw": self.raw,
            "executor_backend": self.executor_backend,
            "executed_at": self.executed_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class BobExecutor(ABC):
    """Abstract base class for all Bob execution backends.

    Every backend must implement execute() with the same signature.
    The rest of the DEVGUARD pipeline never interacts with a backend
    directly — only through this interface.
    """

    @abstractmethod
    def execute(self, task: BobTask) -> BobResponse:
        """Execute the maintenance task and return Bob's response.

        Args:
            task: The BobTask assembled by build_bob_task().

        Returns:
            A BobResponse describing what Bob did.
        """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable name of this backend."""


# ---------------------------------------------------------------------------
# MockBobExecutor
# ---------------------------------------------------------------------------

# The controlled-failure diff: Enterprise discount correctly updated to 0.15,
# but Loyalty discount ALSO accidentally changed to 0.15.
# This is written inline rather than in a separate fixture file so the
# executor is fully self-contained for the hackathon demo.
_MOCK_DIFF_BAD = """\
--- a/sample_app/customers.py
+++ b/sample_app/customers.py
@@ -31,3 +31,3 @@
-NEW_CUSTOMER_DISCOUNT: float = 0.05          # 5%  — new customer benefit
-LOYALTY_DISCOUNT: float = 0.10               # 10% — loyalty programme rate
-ENTERPRISE_DISCOUNT: float = 0.10            # 10% — enterprise contract rate (initial)
+NEW_CUSTOMER_DISCOUNT: float = 0.05          # 5%  — new customer benefit
+LOYALTY_DISCOUNT: float = 0.15               # 15% — loyalty programme rate
+ENTERPRISE_DISCOUNT: float = 0.15            # 15% — enterprise contract rate (updated)
"""

# The correct diff: ONLY ENTERPRISE_DISCOUNT changes.
_MOCK_DIFF_GOOD = """\
--- a/sample_app/customers.py
+++ b/sample_app/customers.py
@@ -33,1 +33,1 @@
-ENTERPRISE_DISCOUNT: float = 0.10            # 10% — enterprise contract rate (initial)
+ENTERPRISE_DISCOUNT: float = 0.15            # 15% — enterprise contract rate (updated)
"""


class MockBobExecutor(BobExecutor):
    """Returns a pre-written mock Bob response.

    Supports two scenarios controlled by the `scenario` parameter:
      "failure"  (default) — the bad diff that also changes LOYALTY_DISCOUNT.
                             This is what DEVGUARD is designed to catch.
      "success"            — the correct diff that only changes ENTERPRISE_DISCOUNT.

    No external dependencies.  Always works offline.
    """

    def __init__(self, scenario: str = "failure") -> None:
        if scenario not in ("failure", "success"):
            raise ValueError(f"Unknown scenario: {scenario!r}. Use 'failure' or 'success'.")
        self.scenario = scenario

    @property
    def backend_name(self) -> str:
        return "mock"

    def execute(self, task: BobTask) -> BobResponse:
        allowed = task.allowed_scope
        symbol = allowed["symbol"]
        from_val = allowed["from_value"]
        to_val = allowed["to_value"]
        target_file = task.file_context.get("relative_path", allowed["file"])

        if self.scenario == "success":
            diff = _MOCK_DIFF_GOOD
            intent = (
                f"Updated {symbol} from {from_val} to {to_val} in {target_file}. "
                f"Only the enterprise discount constant was changed. "
                f"LOYALTY_DISCOUNT and NEW_CUSTOMER_DISCOUNT were not touched."
            )
        else:  # failure
            diff = _MOCK_DIFF_BAD
            intent = (
                f"Updated the enterprise discount rate from {from_val} to {to_val}. "
                f"Also updated the loyalty programme rate to match the new tier pricing policy."
            )

        return BobResponse(
            intent_summary=intent,
            proposed_diff=diff,
            files_modified=[target_file],
            raw=json.dumps({
                "scenario": self.scenario,
                "intent": intent,
                "diff": diff,
            }),
            executor_backend=self.backend_name,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# WatsonxLLMExecutor
# ---------------------------------------------------------------------------

class WatsonxLLMExecutor(BobExecutor):
    """Sends the BobTask prompt to IBM watsonx.ai as a plain LLM call.

    Requires environment variables:
      WATSONX_API_KEY     — IBM Cloud API key
      WATSONX_PROJECT_ID  — watsonx.ai project ID
      WATSONX_URL         — watsonx.ai endpoint URL
                            (default: https://us-south.ml.cloud.ibm.com)

    The LLM is instructed to act as a precise coding agent.
    The full BobTask prompt is sent as the user message.
    The response is parsed to extract the diff and intent.

    Raises:
        EnvironmentError: if required env vars are missing.
        ImportError:      if ibm-watsonx-ai is not installed.
    """

    MODEL_ID = "ibm/granite-3-8b-instruct"

    def __init__(self) -> None:
        self._api_key = os.environ.get("WATSONX_API_KEY")
        self._project_id = os.environ.get("WATSONX_PROJECT_ID")
        self._url = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

    @property
    def backend_name(self) -> str:
        return "watsonx_llm"

    def is_configured(self) -> bool:
        """Return True if the required environment variables are set."""
        return bool(self._api_key and self._project_id)

    def execute(self, task: BobTask) -> BobResponse:
        if not self.is_configured():
            raise EnvironmentError(
                "WatsonxLLMExecutor requires WATSONX_API_KEY and WATSONX_PROJECT_ID. "
                "Set these in your .env file or use BOB_BACKEND=mock for offline use."
            )

        try:
            from ibm_watsonx_ai import APIClient, Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as exc:
            raise ImportError(
                "ibm-watsonx-ai is not installed. "
                "Run: pip install ibm-watsonx-ai"
            ) from exc

        credentials = Credentials(url=self._url, api_key=self._api_key)
        client = APIClient(credentials)
        model = ModelInference(
            model_id=self.MODEL_ID,
            api_client=client,
            project_id=self._project_id,
            params={
                "max_new_tokens": 1024,
                "temperature": 0.0,   # deterministic
                "stop_sequences": ["---END---"],
            },
        )

        system_prompt = (
            "You are a precise software engineering agent. "
            "You make exactly one targeted code change as instructed. "
            "You do not refactor, rename, or modify anything beyond the stated scope. "
            "After making the change, you output:\n"
            "INTENT: <one sentence describing what you changed>\n"
            "DIFF:\n<unified diff of the change>\n"
            "---END---"
        )

        full_prompt = f"{system_prompt}\n\n{task.bob_prompt}"
        raw = model.generate_text(prompt=full_prompt)

        intent, diff = _parse_watsonx_response(raw)

        return BobResponse(
            intent_summary=intent,
            proposed_diff=diff,
            files_modified=[task.allowed_scope["file"]],
            raw=raw,
            executor_backend=self.backend_name,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )


def _parse_watsonx_response(raw: str) -> tuple[str, str]:
    """Extract intent and diff from a watsonx response string."""
    intent = ""
    diff = ""
    lines = raw.splitlines()
    in_diff = False
    diff_lines: list[str] = []

    for line in lines:
        if line.startswith("INTENT:"):
            intent = line[len("INTENT:"):].strip()
        elif line.strip() == "DIFF:":
            in_diff = True
        elif in_diff:
            if line.strip() == "---END---":
                break
            diff_lines.append(line)

    diff = "\n".join(diff_lines).strip()

    if not intent:
        intent = "(no intent summary provided by model)"
    if not diff:
        diff = "(no diff provided by model)"

    return intent, diff


# ---------------------------------------------------------------------------
# WatsonxAgentExecutor (stub)
# ---------------------------------------------------------------------------

class WatsonxAgentExecutor(BobExecutor):
    """Stub for the IBM Bob Agents API.

    This executor will be implemented once the IBM Bob Agents API endpoint
    and SDK integration method are confirmed.  Until then it raises
    NotImplementedError to make the unavailability explicit.

    Planned integration:
      - Uses the IBM Bob Agent API to submit the BobTask as a structured task.
      - Bob runs as a tool-calling agent with access to the project files.
      - Response includes the actual applied diff and test results.
    """

    @property
    def backend_name(self) -> str:
        return "watsonx_agent"

    def execute(self, task: BobTask) -> BobResponse:
        raise NotImplementedError(
            "WatsonxAgentExecutor is not yet implemented. "
            "The IBM Bob Agents API integration is pending confirmation of the "
            "correct SDK method and endpoint. "
            "Use BOB_BACKEND=mock for offline demo, or "
            "BOB_BACKEND=watsonx_llm for a live LLM-based execution."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_executor(backend: Optional[str] = None, scenario: str = "failure") -> BobExecutor:
    """Return the appropriate BobExecutor based on the BOB_BACKEND env var.

    Args:
        backend:  Override the BOB_BACKEND env var. If None, reads from env.
                  Values: "mock" | "watsonx_llm" | "watsonx_agent"
        scenario: For MockBobExecutor only — "failure" (default) or "success".

    Returns:
        A BobExecutor instance.

    Raises:
        ValueError: if an unknown backend name is given.
    """
    name = (backend or os.environ.get("BOB_BACKEND", "mock")).lower().strip()

    if name == "mock":
        return MockBobExecutor(scenario=scenario)
    if name == "watsonx_llm":
        return WatsonxLLMExecutor()
    if name == "watsonx_agent":
        return WatsonxAgentExecutor()

    raise ValueError(
        f"Unknown BOB_BACKEND: {name!r}. "
        f"Valid values: 'mock', 'watsonx_llm', 'watsonx_agent'."
    )
