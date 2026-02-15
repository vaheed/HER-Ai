"""Interpreter startup customizations for production log hygiene.

Python imports ``sitecustomize`` automatically when present on ``sys.path``.
"""

import warnings

# CrewAI 0.28.x still mixes some Pydantic V1/V2 models internally.
# Keep this specific, known warning out of runtime logs while retaining
# all other warnings.
warnings.filterwarnings(
    "ignore",
    message=r"Mixing V1 models and V2 models.*CrewAgentExecutor.*",
    category=UserWarning,
    module=r"pydantic\._internal\._generate_schema",
)

# langchain-openai 0.0.x still calls ``dict()`` on Pydantic models in a few
# response adapters. Keep this specific warning out of runtime logs until
# upstream migration to ``model_dump()`` is fully complete.
warnings.filterwarnings(
    "ignore",
    message=r"The `dict` method is deprecated; use `model_dump` instead.*",
    category=DeprecationWarning,
    module=r"langchain_openai\.chat_models\.base",
)
