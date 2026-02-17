FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        git \
        ca-certificates \
        curl \
        wget \
        jq \
        git \
        nmap \
        whois \
        net-tools \
        iproute2 \
        openssl \
        iputils-ping \
        dnsutils \
        netcat-openbsd \
        traceroute \
        procps \
        tree \
        vim-tiny \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# Pre-warm a minimal useful MCP toolkit (free, no API keys)
RUN npm install -g \
      @modelcontextprotocol/server-filesystem \
      mcp-fetch-server \
      @modelcontextprotocol/server-memory \
      @modelcontextprotocol/server-sequential-thinking \
      @modelcontextprotocol/server-pdf

RUN useradd -m -s /bin/bash sandbox \
    && mkdir -p /workspace /home/sandbox/.config/her \
    && chown -R sandbox:sandbox /workspace /home/sandbox/.config

COPY config/mcp_servers.local.yaml /home/sandbox/.config/her/mcp_servers.local.yaml
RUN chown sandbox:sandbox /home/sandbox/.config/her/mcp_servers.local.yaml
COPY sandbox/check_pentest_tools.sh /usr/local/bin/check_pentest_tools
RUN chmod +x /usr/local/bin/check_pentest_tools

USER sandbox
WORKDIR /workspace

CMD ["bash", "-lc", "echo \"[sandbox] Ready: container=$(hostname) user=$(whoami) workspace=/workspace\"; tail -f /dev/null"]
