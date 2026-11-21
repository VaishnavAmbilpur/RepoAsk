import time
from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler

class RepoAskCallbackHandler(BaseCallbackHandler):
    """Observability handler tracking LLM latency, token usage, and retrieval events."""
    def __init__(self):
        super().__init__()
        self.start_times: Dict[str, float] = {}

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self.start_times["llm"] = time.time()
        model_name = serialized.get("name", "OpenRouter-LLM")
        print(f"[Observability] 🚀 LLM request started ({model_name})")

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        elapsed = time.time() - self.start_times.get("llm", time.time())
        token_usage = getattr(response, "llm_output", {}) or {}
        usage = token_usage.get("token_usage", {})
        print(f"[Observability] ✅ LLM response completed in {elapsed:.2f}s | Tokens: {usage}")

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        print(f"[Observability] ❌ LLM Error: {error}")

