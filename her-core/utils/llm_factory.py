import os

from langchain_openai import ChatOpenAI


def build_llm() -> ChatOpenAI:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "groq":
        return ChatOpenAI(
            model=os.getenv("GROQ_MODEL", "llama3-70b-8192"),
            openai_api_key=os.getenv("GROQ_API_KEY"),
            openai_api_base=os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
        )
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
