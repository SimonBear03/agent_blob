"""
Model configuration and context window limits.

This module provides model metadata including context window limits.
Context windows are based on OpenAI's official documentation.
"""
import os

# Default context window limits by model
# Source: https://platform.openai.com/docs/models
DEFAULT_MODEL_LIMITS = {
    # GPT-4o models
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o-2024-11-20": 128000,
    "gpt-4o-2024-08-06": 128000,
    "gpt-4o-2024-05-13": 128000,
    "gpt-4o-mini-2024-07-18": 128000,
    
    # GPT-4 models
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-2024-04-09": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    
    # GPT-3.5 models
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-0125": 16385,
}


def get_model_context_limit(model_name: str) -> int:
    """
    Get the context window limit for a given model.
    
    First checks environment variable CONTEXT_WINDOW_LIMIT for override.
    Then checks DEFAULT_MODEL_LIMITS.
    Falls back to 128000 if model is unknown.
    
    Args:
        model_name: Name of the model (e.g., "gpt-4o-mini")
    
    Returns:
        Context window limit in tokens
    """
    # Allow environment variable override
    env_limit = os.getenv("CONTEXT_WINDOW_LIMIT")
    if env_limit:
        try:
            return int(env_limit)
        except ValueError:
            pass
    
    # Check known models
    return DEFAULT_MODEL_LIMITS.get(model_name, 128000)


def get_current_model() -> str:
    """
    Get the current model name from environment.
    
    Returns:
        Model name (defaults to "gpt-4o")
    """
    return os.getenv("MODEL_NAME", "gpt-4o")
