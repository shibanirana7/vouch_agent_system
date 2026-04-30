"""
LLM factory — returns a Gemini model (default), HuggingFace pipeline, or Ollama ChatModel
depending on the LLM_BACKEND setting.
"""
from functools import lru_cache
from langchain_core.language_models import BaseChatModel
from ..config import settings


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    if settings.llm_backend == "gemini":
        return _load_gemini()
    if settings.llm_backend == "huggingface":
        return _load_huggingface()
    return _load_ollama()


def _load_gemini() -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
        max_retries=4,
    )


def _load_huggingface() -> BaseChatModel:
    import os
    from transformers import pipeline as hf_pipeline
    from langchain_huggingface import HuggingFacePipeline

    os.environ["HUGGINGFACE_TOKEN"] = settings.hf_token
    pipe = hf_pipeline(
        task="text-generation",
        model=settings.hf_model,
        device_map="auto",
        dtype="auto",
        max_new_tokens=1024,
    )
    return HuggingFacePipeline(pipeline=pipe)


def _load_ollama() -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.7,
    )
