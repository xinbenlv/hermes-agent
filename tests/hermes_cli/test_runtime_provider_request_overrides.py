import hermes_cli.runtime_provider as runtime_provider


def test_resolve_runtime_provider_attaches_model_extra_body_request_overrides(monkeypatch):
    monkeypatch.setattr(
        runtime_provider,
        "load_config",
        lambda: {
            "model": {
                "provider": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "extra_body": {
                    "transforms": ["middle-out"],
                    "provider": {"ignore": ["deepinfra"]},
                },
            }
        },
    )
    monkeypatch.setattr(runtime_provider, "load_pool", lambda provider: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)

    runtime = runtime_provider.resolve_runtime_provider(requested="openrouter")

    assert runtime["provider"] == "openrouter"
    assert runtime["request_overrides"] == {
        "extra_body": {
            "transforms": ["middle-out"],
            "provider": {"ignore": ["deepinfra"]},
        }
    }
