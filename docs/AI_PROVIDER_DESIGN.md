# AI provider design

Agents use `AIProvider`, defined in `app/core/contracts.py`. Its current portable capability is `generate(request) -> AIResponse`; streaming, embeddings, tool calls, and structured-output enforcement are explicit future additions rather than provider-specific leakage.

## Resolution order

`AI_PROVIDER` selects `anthropic`, `openai`, `freemodel`, or `local`. If it is unset, `ProviderManager` infers `freemodel` when `ANTHROPIC_BASE_URL` or `ANTHROPIC_AUTH_TOKEN` is present, then falls back to `openai` when `OPENAI_API_KEY` exists. Otherwise the application uses an unavailable provider that fails clearly at call time.

`freemodel` is an Anthropic-compatible adapter configuration, not a separate agent API. This supports Freebuff endpoints such as `ANTHROPIC_BASE_URL=https://cc.freemodel.dev`.

## Security and extension rules

- Providers read environment configuration via `Settings`; never read environment variables inside agents.
- Do not persist auth tokens, raw prompts containing secrets, or full provider responses by default.
- Each concrete adapter lives in `app/providers/` and implements the same contract.
- Add a provider SDK only when implementing that adapter; Phase 1 ships no networked adapter calls.
