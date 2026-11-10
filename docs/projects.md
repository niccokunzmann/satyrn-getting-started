# The Satyrn projects

This project is one of several around Satyrn, a local-first coding assistant.

| Repository | What it is |
| --- | --- |
| [satyrn-agent](https://github.com/satyrn-ai/satyrn-agent) | `satyrn_agent` Python package and ds4 patch series (dense Qwen on Metal, DFlash speculative decoding). The engine behind [`satyrn-codegen`](satyrn-engine.md). |
| ds4-py | Python bindings for the ds4 C engine: sessions, chat templates, tool-call parsing. satyrn-agent pins the version it uses. |
| [satyrn-models](https://github.com/satyrn-ai/satyrn-models) | Fine-tuning pipeline (datasets, Unsloth trainer); exports 4-bit GGUF models that Ollama can serve, and so this project can use them. |
| [satyrn-evals-collector](https://github.com/satyrn-ai/satyrn-evals-collector) | Community reports on coding agents with local models. |
| [satyrn-website](https://github.com/satyrn-ai/satyrn-website), [satyrn-zen](https://github.com/satyrn-ai/satyrn-zen), [team-compass](https://github.com/satyrn-ai/team-compass) | Documentation sites. |
