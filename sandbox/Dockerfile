FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
    && npm config set update-notifier false \
    && npm config set fund false \
    && rm -rf /var/lib/apt/lists/*

# Pre-warm a minimal useful MCP toolkit (free, no API keys)
RUN npm install -g \
      @modelcontextprotocol/server-filesystem \
      @modelcontextprotocol/server-fetch \
      @modelcontextprotocol/server-memory \
      @modelcontextprotocol/server-sequential-thinking \
      @modelcontextprotocol/server-sqlite

RUN useradd -m -s /bin/bash sandbox \
    && mkdir -p /workspace /home/sandbox/.config/her \
    && chown -R sandbox:sandbox /workspace /home/sandbox/.config

COPY config/mcp_servers.local.yaml /home/sandbox/.config/her/mcp_servers.local.yaml
RUN chown sandbox:sandbox /home/sandbox/.config/her/mcp_servers.local.yaml

USER sandbox
WORKDIR /workspace

CMD ["bash", "-lc", "tail -f /dev/null"]
