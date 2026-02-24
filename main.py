from __future__ import annotations

import uvicorn

from her.config.settings import get_settings


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("her.interfaces.api.main:app", host=settings.api_host, port=settings.api_port, reload=False)
