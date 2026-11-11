"""Preview-only routing checks; no paid calls or credentials."""
import json
from types import SimpleNamespace
from unittest.mock import Mock


def test_luna_uses_responses_api_with_no_storage(monkeypatch, isolated_app):
    from game import classify_question
    monkeypatch.setenv("USE_API", "true")
    monkeypatch.setenv("DARK_STORIES_MODERATOR_MODEL", "gpt-6-luna")
    create = Mock(return_value=SimpleNamespace(output_text=json.dumps({
        "kind": "question", "label": "Yes", "short_explanation": "",
        "fact_indices": [0],
    })))
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))
    observed = []
    assert classify_question("Are they two fish?", "private context", fake_client,
                             observe_origin=observed.append) == ("Yes", "", [0])
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["store"] is False
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert observed == ["ai_tool"]


def test_default_model_remains_gpt_4_1_mini(monkeypatch, isolated_app):
    from game import classify_question
    monkeypatch.setenv("USE_API", "true")
    monkeypatch.delenv("DARK_STORIES_MODERATOR_MODEL", raising=False)
    args = {"kind": "question", "label": "No", "short_explanation": "",
            "fact_indices": []}
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(args)))]))])
    create = Mock(return_value=completion)
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert classify_question("Question?", "prompt", fake_client) == ("No", "", [])
    assert create.call_args.kwargs["model"] == "gpt-4.1-mini"
