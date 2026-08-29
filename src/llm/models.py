import os
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from enum import Enum
from pydantic import BaseModel
from typing import Tuple, Optional, Any


class ModelProvider(str, Enum):
    """Enum for supported LLM providers"""
    OPENAI = "OpenAI"
    GROQ = "Groq"
    ANTHROPIC = "Anthropic"
    GEMINI = "Gemini"
    DEEPSEEK = "DeepSeek"
    OPENAI_COMPATIBLE = "OpenAI-Compatible"


class LLMModel(BaseModel):
    """Represents an LLM model configuration"""
    display_name: str
    model_name: str
    provider: ModelProvider

    def to_choice_tuple(self) -> Tuple[str, str, str]:
        """Convert to format needed for questionary choices"""
        return (self.display_name, self.model_name, self.provider.value)
    
    def is_deepseek(self) -> bool:
        """Check if the model is a DeepSeek model"""
        return "deepseek" in self.model_name.lower()


# Define available models
AVAILABLE_MODELS = [
    # Primary default model
    LLMModel(
        display_name="[gemini] models/gemini-flash-latest (Primary Default)",
        model_name="models/gemini-flash-latest",
        provider=ModelProvider.GEMINI
    ),
    LLMModel(
        display_name="[gemini] gemini-flash-latest",
        model_name="gemini-flash-latest",
        provider=ModelProvider.GEMINI
    ),
    LLMModel(
        display_name="[gemini] gemini-2.0-flash",
        model_name="gemini-2.0-flash",
        provider=ModelProvider.GEMINI
    ),
    LLMModel(
        display_name="[gemini] gemini-2.0-pro-exp",
        model_name="gemini-2.0-pro-exp-02-05",
        provider=ModelProvider.GEMINI
    ),
    LLMModel(
        display_name="[gemini] gemini-1.5-pro",
        model_name="gemini-1.5-pro",
        provider=ModelProvider.GEMINI
    ),

    # OpenAI Models
    LLMModel(
        display_name="[openai] gpt-4o",
        model_name="gpt-4o",
        provider=ModelProvider.OPENAI
    ),
    LLMModel(
        display_name="[openai] gpt-4o-mini",
        model_name="gpt-4o-mini",
        provider=ModelProvider.OPENAI
    ),
    LLMModel(
        display_name="[openai] o3-mini",
        model_name="o3-mini",
        provider=ModelProvider.OPENAI
    ),
    LLMModel(
        display_name="[openai] o1",
        model_name="o1",
        provider=ModelProvider.OPENAI
    ),
    LLMModel(
        display_name="[openai] gpt-4.5-preview",
        model_name="gpt-4.5-preview",
        provider=ModelProvider.OPENAI
    ),

    # Anthropic Models
    LLMModel(
        display_name="[anthropic] claude-3.7-sonnet",
        model_name="claude-3-7-sonnet-latest",
        provider=ModelProvider.ANTHROPIC
    ),
    LLMModel(
        display_name="[anthropic] claude-3.5-sonnet",
        model_name="claude-3-5-sonnet-latest",
        provider=ModelProvider.ANTHROPIC
    ),
    LLMModel(
        display_name="[anthropic] claude-3.5-haiku",
        model_name="claude-3-5-haiku-latest",
        provider=ModelProvider.ANTHROPIC
    ),

    # DeepSeek Native
    LLMModel(
        display_name="[deepseek] deepseek-chat (V3)",
        model_name="deepseek-chat",
        provider=ModelProvider.DEEPSEEK
    ),
    LLMModel(
        display_name="[deepseek] deepseek-reasoner (R1)",
        model_name="deepseek-reasoner",
        provider=ModelProvider.DEEPSEEK
    ),

    # Groq Models
    LLMModel(
        display_name="[groq] openai/gpt-oss-120b",
        model_name="openai/gpt-oss-120b",
        provider=ModelProvider.GROQ
    ),
    LLMModel(
        display_name="[groq] openai/gpt-oss-20b",
        model_name="openai/gpt-oss-20b",
        provider=ModelProvider.GROQ
    ),
]

# Create LLM_ORDER in the format expected by the UI
LLM_ORDER = [model.to_choice_tuple() for model in AVAILABLE_MODELS]


def get_model_info(model_name: str) -> Optional[LLMModel]:
    """Get model information by model_name"""
    return next((model for model in AVAILABLE_MODELS if model.model_name == model_name), None)


def get_model(model_name: str = None, model_provider: ModelProvider = None) -> Any:
    """
    Instantiate Chat LLM model.
    Defaults to Primary Model (models/gemini-flash-latest via Gemini).
    """
    if not model_name:
        model_name = os.getenv("DEFAULT_MODEL", "models/gemini-flash-latest")
    
    # Auto-detect provider if model matches known signatures
    if isinstance(model_provider, str):
        try:
            model_provider = ModelProvider(model_provider)
        except Exception:
            pass

    if model_provider == ModelProvider.GEMINI or "gemini" in model_name.lower():
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("FALLBACK_API_KEY") or "your_gemini_api_key_here"
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.2
        )

    if model_provider == ModelProvider.GROQ:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Groq API key not found. Please set GROQ_API_KEY in .env file.")
        return ChatGroq(model=model_name, api_key=api_key)

    elif model_provider == ModelProvider.OPENAI:
        api_key = os.getenv("FALLBACK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in .env file.")
        
        base_url = os.getenv("FALLBACK_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        if base_url:
            return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)
        return ChatOpenAI(model=model_name, api_key=api_key)

    elif model_provider == ModelProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key not found. Please set ANTHROPIC_API_KEY in .env file.")
        return ChatAnthropic(model=model_name, api_key=api_key)

    elif model_provider == ModelProvider.DEEPSEEK:
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("DeepSeek API key not found. Please set DEEPSEEK_API_KEY in .env file.")
        return ChatOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            model=model_name
        )

    elif model_provider == ModelProvider.OPENAI_COMPATIBLE:
        api_key = os.getenv("PRIMARY_API_KEY") or os.getenv("CUSTOM_API_KEY") or os.getenv("GEMINI_API_KEY") or "your_gemini_api_key_here"
        base_url = os.getenv("PRIMARY_BASE_URL") or os.getenv("CUSTOM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai/"
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name
        )

    # Fallback
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("FALLBACK_API_KEY") or os.getenv("OPENAI_API_KEY") or "your_gemini_api_key_here"
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)


def get_fallback_model(fallback_model_name: Optional[str] = None) -> Any:
    """Get fallback model instance with custom fallback URL and model support"""
    fallback_model_name = fallback_model_name or os.getenv("FALLBACK_MODEL", "models/gemini-flash-latest")
    base_url = os.getenv("FALLBACK_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    api_key = os.getenv("FALLBACK_API_KEY") or os.getenv("GEMINI_API_KEY") or "your_gemini_api_key_here"
    return ChatOpenAI(
        model=fallback_model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.2
    )