import os

from crewai import LLM


def build_llm() -> LLM:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "groq":
        return LLM(
            provider="groq",
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama3-70b-8192",
        )
    return LLM(
        provider="openai",
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4-turbo-preview",
    )
