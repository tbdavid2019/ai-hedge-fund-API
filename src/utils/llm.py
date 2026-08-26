"""Helper functions for LLM with automatic retry and ChatGPT fallback"""

import json
from typing import TypeVar, Type, Optional, Any
from pydantic import BaseModel
from utils.progress import progress

T = TypeVar('T', bound=BaseModel)


def call_llm(
    prompt: Any,
    model_name: Optional[str] = None,
    model_provider: Optional[str] = None,
    pydantic_model: Type[T] = None,
    agent_name: Optional[str] = None,
    max_retries: int = 2,
    default_factory = None
) -> T:
    """
    Makes an LLM call with retry logic and automatic fallback to ChatGPT (gpt-4o).
    
    Args:
        prompt: The prompt to send to the LLM
        model_name: Name of the model to use (defaults to deepseek-v4-flash)
        model_provider: Provider of the model
        pydantic_model: The Pydantic model class to structure the output
        agent_name: Optional name of the agent for progress updates
        max_retries: Maximum number of retries per provider
        default_factory: Optional factory function to create default response on failure
        
    Returns:
        An instance of the specified Pydantic model
    """
    from llm.models import get_model, get_model_info, get_fallback_model
    
    # 1. Attempt Primary LLM Model (deepseek-v4-flash via nen.com.tw)
    model_name = model_name or "deepseek-v4-flash"
    model_provider = model_provider or "OpenAI-Compatible"
    model_info = get_model_info(model_name)

    try:
        llm = get_model(model_name, model_provider)
        
        # Check if structured output should be used
        if not (model_info and model_info.is_deepseek()):
            try:
                llm = llm.with_structured_output(
                    pydantic_model,
                    method="json_mode",
                )
            except Exception:
                pass
        
        for attempt in range(max_retries):
            try:
                result = llm.invoke(prompt)
                
                # If structured output already parsed it into Pydantic model
                if isinstance(result, pydantic_model):
                    return result
                
                # Extract and parse JSON
                content = getattr(result, "content", str(result))
                parsed = extract_json_from_response(content)
                if parsed:
                    return pydantic_model(**parsed)
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                    
    except Exception as primary_err:
        print(f"[LLM Warning] Primary model '{model_name}' failed: {primary_err}. Activating ChatGPT (gpt-4o) fallback...")
        if agent_name:
            progress.update_status(agent_name, None, "Falling back to ChatGPT (gpt-4o)")

        # 2. Seamless Fallback to official ChatGPT (gpt-4o)
        try:
            fallback_llm = get_fallback_model("gpt-4o")
            try:
                fallback_structured = fallback_llm.with_structured_output(
                    pydantic_model,
                    method="json_mode"
                )
                result = fallback_structured.invoke(prompt)
                if isinstance(result, pydantic_model):
                    return result
            except Exception:
                pass

            result = fallback_llm.invoke(prompt)
            content = getattr(result, "content", str(result))
            parsed = extract_json_from_response(content)
            if parsed:
                return pydantic_model(**parsed)

        except Exception as fallback_err:
            print(f"[LLM Error] Fallback ChatGPT also failed: {fallback_err}")

    # 3. If both primary and fallback fail, use default factory or safe default
    if default_factory:
        return default_factory()
    return create_default_response(pydantic_model)


def create_default_response(model_class: Type[T]) -> T:
    """Creates a safe default response based on the model's fields."""
    default_values = {}
    for field_name, field in model_class.model_fields.items():
        if field.annotation == str:
            default_values[field_name] = "Analysis completed with default baseline."
        elif field.annotation == float:
            default_values[field_name] = 50.0
        elif field.annotation == int:
            default_values[field_name] = 0
        elif hasattr(field.annotation, "__origin__") and field.annotation.__origin__ == dict:
            default_values[field_name] = {}
        else:
            if hasattr(field.annotation, "__args__"):
                default_values[field_name] = field.annotation.__args__[0]
            else:
                default_values[field_name] = None
    
    return model_class(**default_values)


def extract_json_from_response(content: str) -> Optional[dict]:
    """Extracts JSON from response content or markdown blocks."""
    if not content:
        return None
    
    # Try direct JSON parsing
    try:
        return json.loads(content.strip())
    except Exception:
        pass

    # Try ```json markdown blocks
    try:
        json_start = content.find("```json")
        if json_start != -1:
            json_text = content[json_start + 7:]
            json_end = json_text.find("```")
            if json_end != -1:
                json_text = json_text[:json_end].strip()
                return json.loads(json_text)
    except Exception:
        pass

    # Try finding outermost { }
    try:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start:end+1])
    except Exception as e:
        print(f"Error extracting JSON from response: {e}")
        
    return None
