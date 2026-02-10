import os

from langchain_openai import ChatOpenAI


def build_llm() -> ChatOpenAI:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://ollama:11434")).rstrip("/")
        return ChatOpenAI(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            openai_api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
            openai_api_base=f"{base_url}/v1",
        )
    if provider == "groq":
        return ChatOpenAI(
            model=os.getenv("GROQ_MODEL", "llama3-70b-8192"),
            openai_api_key=os.getenv("GROQ_API_KEY"),
            openai_api_base=os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
        )
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
