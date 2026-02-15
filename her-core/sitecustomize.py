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
