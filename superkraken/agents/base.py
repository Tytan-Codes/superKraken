"""Base agent class with OpenRouter LLM client dispatch and fallback handling."""

import json
import logging
import re
from typing import Any, Dict, Optional, Type, TypeVar
from openai import AsyncOpenAI
from pydantic import BaseModel
from superkraken.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce percentages, enums, and score ranges into valid Pydantic types."""
    d = dict(data)
    if "action" in d and isinstance(d["action"], str):
        act = d["action"].upper().strip()
        if "BUY" in act:
            d["action"] = "BUY"
        elif "SELL" in act:
            d["action"] = "SELL"
        else:
            d["action"] = "HOLD"

    for field in ("confidence", "bull_score", "bear_score", "recommended_position_pct", "position_pct"):
        if field in d:
            val = d[field]
            if isinstance(val, str):
                val = val.replace("%", "").strip()
                try:
                    val = float(val)
                except ValueError:
                    val = 0.5
            if isinstance(val, (int, float)):
                if val > 1.0 and val <= 100.0:
                    val = val / 100.0
                elif val > 100.0:
                    val = 1.0
                d[field] = max(0.0, min(1.0, float(val)))

    for field in ("recommended_leverage", "leverage"):
        if field in d:
            val = d[field]
            if isinstance(val, str):
                val = val.replace("x", "").replace("X", "").strip()
                try:
                    val = float(val)
                except ValueError:
                    val = 1.0
            if isinstance(val, (int, float)):
                d[field] = float(val)

    return d


class BaseAgent:
    """Base class for all trading desk specialized agents."""

    def __init__(self, name: str, default_model: str, system_prompt: str):
        self.name = name
        self.default_model = default_model
        self.system_prompt = system_prompt
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        # Dynamically reload key from .env to guarantee fresh state
        key = settings.openrouter_api_key
        if not key or key.startswith("sk-or-v1-your"):
            from superkraken.config import Settings
            fresh = Settings(_env_file=".env")
            if fresh.openrouter_api_key and not fresh.openrouter_api_key.startswith("sk-or-v1-your"):
                settings.openrouter_api_key = fresh.openrouter_api_key
                key = fresh.openrouter_api_key

        if self._client is None or self._client.api_key != key:
            self._client = AsyncOpenAI(
                api_key=key or "sk-or-v1-missing-key",
                base_url=settings.openrouter_base_url,
                default_headers={
                    "HTTP-Referer": "https://github.com/superkraken",
                    "X-Title": "superKraken Autonomous AI Trading Desk",
                },
            )
        return self._client

    async def call_llm(
        self,
        user_prompt: str,
        model_override: Optional[str] = None,
        temperature: float = 0.3,
        response_model: Optional[Type[T]] = None,
    ) -> Any:
        """Call OpenRouter LLM with model selection, retry, and zero-cost fallback."""
        model = model_override or self.default_model

        # Only fall back to heuristics if the API key is completely missing or placeholder
        if not settings.openrouter_api_key or "your-key-here" in settings.openrouter_api_key:
            from rich import print as rprint
            rprint(f"[bold magenta]⚠️ [{self.name}] No valid OPENROUTER_API_KEY detected. Using [HEURISTIC FALLBACK].[/bold magenta]")
            res = self._heuristic_fallback(user_prompt, response_model)
            if hasattr(res, "model_used"):
                res.model_used = "heuristic-rules"
            return res

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 1. Primary Attempt
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=6000,
                timeout=50.0,
            )
            msg = response.choices[0].message
            content = msg.content or ""
            reasoning = getattr(msg, "reasoning", "") or ""
            
            # Prioritize content if it contains json/text, fallback to reasoning if content is empty
            if response_model is not None:
                if content and "{" in content:
                    raw_text = content
                elif reasoning and "{" in reasoning:
                    raw_text = reasoning
                else:
                    raw_text = content or reasoning
            else:
                raw_text = content or reasoning
                
            if response_model is not None:
                parsed = self._parse_json_response(raw_text, response_model)
                if hasattr(parsed, "is_fallback"):
                    setattr(parsed, "is_fallback", False)
                if hasattr(parsed, "model_used"):
                    setattr(parsed, "model_used", model)
                return parsed
            return raw_text

        except Exception as e_primary:
            from rich import print as rprint
            rprint(f"[bold yellow]⚠️ [{self.name}] Call to {model} failed: {e_primary}. Retrying once...[/bold yellow]")
            
            # 2. Retry Attempt
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=6000,
                    timeout=50.0,
                )
                msg = response.choices[0].message
                content = msg.content or ""
                reasoning = getattr(msg, "reasoning", "") or ""
                if response_model is not None:
                    if content and "{" in content:
                        raw_text = content
                    elif reasoning and "{" in reasoning:
                        raw_text = reasoning
                    else:
                        raw_text = content or reasoning
                else:
                    raw_text = content or reasoning

                if response_model is not None:
                    parsed = self._parse_json_response(raw_text, response_model)
                    if hasattr(parsed, "is_fallback"):
                        setattr(parsed, "is_fallback", False)
                    if hasattr(parsed, "model_used"):
                        setattr(parsed, "model_used", model)
                    return parsed
                return raw_text

            except Exception as e_retry:
                fallback_model = settings.model_fallback
                rprint(f"[bold yellow]⚠️ [{self.name}] Retry for {model} failed: {e_retry}. Falling back to {fallback_model}...[/bold yellow]")
                
                # 3. Fallback Model Attempt (e.g. deepseek-v4-flash-latest:free)
                try:
                    response = await self.client.chat.completions.create(
                        model=fallback_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=4000,
                        timeout=30.0,
                    )
                    msg = response.choices[0].message
                    content = msg.content or ""
                    reasoning = getattr(msg, "reasoning", "") or ""
                    if response_model is not None:
                        raw_text = content if "{" in content else (reasoning if "{" in reasoning else content or reasoning)
                    else:
                        raw_text = content or reasoning

                    if response_model is not None:
                        parsed = self._parse_json_response(raw_text, response_model)
                        if hasattr(parsed, "is_fallback"):
                            setattr(parsed, "is_fallback", False)
                        if hasattr(parsed, "model_used"):
                            setattr(parsed, "model_used", fallback_model)
                        return parsed
                    return raw_text

                except Exception as e_fallback:
                    rprint(f"[bold red]❌ [{self.name}] Fallback {fallback_model} failed: {e_fallback}. Engaging [HEURISTIC FALLBACK].[/bold red]")
                    res = self._heuristic_fallback(user_prompt, response_model)
                    if hasattr(res, "model_used"):
                        res.model_used = "heuristic-rules"
                    return res



    def _parse_json_response(self, text: str, schema: Type[T]) -> T:
        """Extract and parse structured JSON from model output."""
        cleaned = text.strip()
        # Remove thinking blocks if present
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()
        if "<think>" in cleaned and "</think>" not in cleaned:
            cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()

        # 1. Try json_repair directly on the cleaned text
        try:
            import json_repair
            repaired = json_repair.loads(cleaned)
            if isinstance(repaired, dict):
                return schema.model_validate(_sanitize_dict(repaired))
        except Exception:
            pass

        # 2. Try markdown json block (greedy to outermost closing brace)
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", cleaned)
        if json_match:
            candidate = json_match.group(1).strip()
        else:
            # Find outermost curly braces
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                candidate = cleaned[start_idx : end_idx + 1].strip()
            else:
                candidate = cleaned

        try:
            data = json.loads(candidate)
            return schema.model_validate(_sanitize_dict(data))
        except Exception:
            try:
                import json_repair
                repaired = json_repair.loads(candidate)
                if isinstance(repaired, dict):
                    return schema.model_validate(_sanitize_dict(repaired))
            except Exception:
                pass
            logger.warning(f"[{self.name}] JSON parse failed on: '{candidate[:200]}...'")
            return self._heuristic_fallback(text, schema)

    def _heuristic_fallback(self, context: str, schema: Optional[Type[T]]) -> Any:
        """Subclasses override this to provide deterministic heuristic fallback."""
        if schema is None:
            return f"[HEURISTIC FALLBACK] {self.name} heuristic assessment based on inputs"
        try:
            obj = schema.model_validate({})
            if hasattr(obj, "is_fallback"):
                setattr(obj, "is_fallback", True)
            return obj
        except Exception:
            raise NotImplementedError(f"Heuristic fallback must be implemented for {self.name} with {schema}")
