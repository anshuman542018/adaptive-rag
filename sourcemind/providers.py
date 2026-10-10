"""Bounded provider calls with safe diagnostics and model-access recovery."""
import json
import logging

LOG = logging.getLogger("sourcemind")


class ModelServiceError(RuntimeError):
    def __init__(self, category):
        self.category = category
        messages = {
            "authentication": "The answer service rejected its credentials. The app owner must check the service configuration.",
            "model_access": "The configured answer models are unavailable to this account. The app owner must check model access.",
            "rate_limit": "The answer service reached its rate limit. Please try again shortly.",
            "invalid_response": "The answer service returned an unreadable response. Please retry.",
            "unavailable": "The answer service is unavailable. Please try again shortly.",
        }
        super().__init__(messages.get(category, messages["unavailable"]))


def run_model(api_key, model_id, system, payload, fallback="openai/gpt-oss-20b", client_factory=None):
    if not api_key:
        raise ModelServiceError("authentication")
    if client_factory is None:
        from groq import Groq
        client_factory = Groq
    client = client_factory(api_key=api_key, timeout=45, max_retries=1)
    models = list(dict.fromkeys([model_id, fallback])) if fallback else [model_id]
    for index, selected in enumerate(models):
        try:
            response = client.chat.completions.create(model=selected, temperature=0,
                response_format={"type":"json_object"}, max_tokens=3000,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":json.dumps(payload,ensure_ascii=False)}])
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as exc:
            raise ModelServiceError("invalid_response") from exc
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            # Never log provider exception bodies: they can echo input/keys.
            safe_status = status if type(status) is int else None
            LOG.warning("Model call failed (%s, HTTP %s)", type(exc).__name__, safe_status)
            code = getattr(exc, "code", None)
            body = getattr(exc, "body", None)
            if not code and isinstance(body, dict):
                error = body.get("error", body)
                code = error.get("code") if isinstance(error,dict) else None
            model_access = status == 404 or code in {"model_not_found","model_decommissioned","model_permission_denied","model_not_allowed"}
            if model_access and index+1 < len(models):
                LOG.warning("Trying configured fallback model after model access failure")
                continue
            category = "authentication" if status == 401 else "rate_limit" if status == 429 else "model_access" if model_access or status == 403 else "unavailable"
            raise ModelServiceError(category) from exc
