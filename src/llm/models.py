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
        display_name="[nen.com.tw] deepseek-v4-flash (Primary Default)",
        model_name="deepseek-v4-flash",
        provider=ModelProvider.OPENAI_COMPATIBLE
    ),

    # OpenAI Models
    LLMModel(
        display_name="[openai] gpt-4o (Fallback)",
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

    # Gemini Models
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
        display_name="[groq] deepseek-r1 70b",
        model_name="deepseek-r1-distill-llama-70b",
        provider=ModelProvider.GROQ
    ),
    LLMModel(
        display_name="[groq] llama-3.3 70b",
        model_name="llama-3.3-70b-versatile",
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
    Defaults to Primary Model (deepseek-v4-flash via https://nen.com.tw/v1/).
    """
    if not model_name:
        model_name = os.getenv("DEFAULT_MODEL", "deepseek-v4-flash")
    
    # Auto-detect provider if model matches known signatures
    if isinstance(model_provider, str):
        try:
            model_provider = ModelProvider(model_provider)
        except Exception:
            pass

    if model_name == "deepseek-v4-flash" or (model_provider == ModelProvider.OPENAI_COMPATIBLE and "nen" in os.getenv("OPENAI_BASE_URL", "https://nen.com.tw/v1")):
        api_key = os.getenv("PRIMARY_API_KEY") or os.getenv("NEN_API_KEY") or os.getenv("OPENAI_API_KEY", "your_primary_api_key_here")
        base_url = os.getenv("PRIMARY_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://nen.com.tw/v1")
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
        # If base_url is nen.com.tw but model is gpt-4o, use official openai base url
        if base_url and "nen.com.tw" in base_url and model_name.startswith("gpt-"):
            base_url = "https://api.openai.com/v1"
            
        if base_url:
            return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)
        return ChatOpenAI(model=model_name, api_key=api_key)

    elif model_provider == ModelProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key not found. Please set ANTHROPIC_API_KEY in .env file.")
        return ChatAnthropic(model=model_name, api_key=api_key)

    elif model_provider == ModelProvider.GEMINI:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found. Please set GEMINI_API_KEY in .env file.")
        
        return ChatOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            model=model_name
        )

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
        api_key = os.getenv("PRIMARY_API_KEY") or os.getenv("CUSTOM_API_KEY") or os.getenv("OPENAI_API_KEY", "your_primary_api_key_here")
        base_url = os.getenv("PRIMARY_BASE_URL") or os.getenv("CUSTOM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://nen.com.tw/v1")
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name
        )

    # Fallback to OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(f"Unknown provider {model_provider} and no OPENAI_API_KEY found.")
    return ChatOpenAI(model=model_name, api_key=api_key)


def get_fallback_model(fallback_model_name: Optional[str] = None) -> Any:
    """Get fallback model instance with custom fallback URL and model support"""
    fallback_model_name = fallback_model_name or os.getenv("FALLBACK_MODEL", "gemini-2.5-flash")
    base_url = os.getenv("FALLBACK_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    api_key = os.getenv("FALLBACK_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Fallback API key not found.")
    return ChatOpenAI(
        model=fallback_model_name,
        api_key=api_key,
        base_url=base_url
    )