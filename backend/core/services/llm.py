"""
LLM API interface for making calls to various language models.

This module provides a unified interface for making API calls to different LLM providers
using LiteLLM with simplified error handling and clean parameter management.
"""

from typing import Union, Dict, Any, Optional, AsyncGenerator, List
import os
import asyncio
import copy
import litellm
from litellm.router import Router
from litellm.files.main import ModelResponse
from core.utils.logger import logger
from core.utils.config import config
from core.agentpress.error_processor import ErrorProcessor
from core.observability.local_collector import local_collector
from core.utils.token_counter import TokenCounter
import time

# Configure LiteLLM
# os.environ['LITELLM_LOG'] = 'DEBUG'
# litellm.set_verbose = True  # Enable verbose logging
litellm.modify_params = True
litellm.drop_params = True

# Enable additional debug logging
# import logging
# litellm_logger = logging.getLogger("LiteLLM")
# litellm_logger.setLevel(logging.DEBUG)

# Constants
MAX_RETRIES = 3
# Fallback when vision API is not configured or call fails (same concept as browser: use vision API)
PLACEHOLDER_NO_VISION = "[Image omitted - vision API not configured or unavailable]"
provider_router = None


def _get_vision_api_config() -> Optional[Dict[str, Any]]:
    """Return vision API config (same as browser/Stagehand: VISION_API_KEY, VISION_API_ENDPOINT, VISION_MODEL_ID)."""
    api_key = getattr(config, "VISION_API_KEY", None) or getattr(config, "GEMINI_API_KEY", None)
    if not api_key:
        return None
    endpoint = getattr(config, "VISION_API_ENDPOINT", None)
    model_id = getattr(config, "VISION_MODEL_ID", None) or "gpt-4o-mini"
    return {"api_key": api_key, "api_base": endpoint, "model_id": model_id}


async def _describe_image_with_vision_api(image_url: str) -> str:
    """Call the same vision API used by browser (VISION_*) to get a short text description of the image."""
    cfg = _get_vision_api_config()
    if not cfg or not cfg.get("api_key"):
        return PLACEHOLDER_NO_VISION
    try:
        # OpenAI-compatible vision call: same pattern as LiteLLM custom endpoint
        model = f"openai/{cfg['model_id']}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image briefly in one or two sentences."},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        response = await litellm.acompletion(
            model=model,
            api_key=cfg["api_key"],
            api_base=cfg.get("api_base"),
            messages=messages,
            max_tokens=300,
        )
        if response and response.choices and len(response.choices) > 0:
            content = getattr(response.choices[0].message, "content", None) or ""
            return (content or "").strip() or PLACEHOLDER_NO_VISION
    except Exception as e:
        logger.warning(f"Vision API description failed: {e}")
    return PLACEHOLDER_NO_VISION


async def _replace_images_with_vision_descriptions(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For each message with image_url parts, call vision API and replace with text (same API as browser)."""
    out = []
    for msg in messages:
        msg = copy.deepcopy(msg)
        content = msg.get("content")
        if isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url") or ""
                    desc = await _describe_image_with_vision_api(url)
                    new_parts.append({"type": "text", "text": f"[Image description: {desc}]"})
                else:
                    new_parts.append(part)
            msg["content"] = new_parts
        out.append(msg)
    return out


class LLMError(Exception):
    """Exception for LLM-related errors."""
    pass

def setup_api_keys() -> None:
    """Set up API keys from environment variables."""
    if not config:
        logger.warning("Config not loaded - skipping API key setup")
        return
        
    providers = [
        "OPENAI",
        "ANTHROPIC",
        "GROQ",
        "OPENROUTER",
        "XAI",
        "MORPH",
        "GEMINI",
        "OPENAI_COMPATIBLE",
    ]
    
    for provider in providers:
        try:
            key = getattr(config, f"{provider}_API_KEY", None)
            if key:
                # logger.debug(f"API key set for provider: {provider}")
                pass
            else:
                #logger.debug(f"No API key found for provider: {provider} (this is normal if not using this provider)")
                continue
        except AttributeError as e:
            #logger.debug(f"Could not access {provider}_API_KEY: {e}")
            continue

    # Set up OpenRouter API base if not already set
    if hasattr(config, 'OPENROUTER_API_KEY') and hasattr(config, 'OPENROUTER_API_BASE'):
        if config.OPENROUTER_API_KEY and config.OPENROUTER_API_BASE:
            os.environ["OPENROUTER_API_BASE"] = config.OPENROUTER_API_BASE
            logger.debug(f"Set OPENROUTER_API_BASE to {config.OPENROUTER_API_BASE}")

    # Set up AWS Bedrock bearer token authentication
    if hasattr(config, 'AWS_BEARER_TOKEN_BEDROCK'):
        bedrock_token = config.AWS_BEARER_TOKEN_BEDROCK
        if bedrock_token:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = bedrock_token
            logger.debug("AWS Bedrock bearer token configured")
        else:
            logger.debug("AWS_BEARER_TOKEN_BEDROCK not configured - Bedrock models will not be available")

def setup_provider_router(openai_compatible_api_key: str = None, openai_compatible_api_base: str = None):
    global provider_router
    
    # Get config values safely
    config_openai_key = getattr(config, 'OPENAI_COMPATIBLE_API_KEY', None) if config else None
    config_openai_base = getattr(config, 'OPENAI_COMPATIBLE_API_BASE', None) if config else None
    
    model_list = [
        {
            "model_name": "openai-compatible/*", # support OpenAI-Compatible LLM provider
            "litellm_params": {
                "model": "openai/*",
                "api_key": openai_compatible_api_key or config_openai_key,
                "api_base": openai_compatible_api_base or config_openai_base,
            },
        },
        {
            "model_name": "*", # supported LLM provider by LiteLLM
            "litellm_params": {
                "model": "*",
            },
        },
    ]
    
    # Build fallbacks from registry
    # Disabled by user request: force fallbacks to be empty
    fallbacks = []
    
    provider_router = Router(
        model_list=model_list,
        retry_after=15,
        fallbacks=fallbacks,
    )
    
    logger.info(f"Configured LiteLLM Router with {len(fallbacks)} fallback rules")

def _configure_openai_compatible(params: Dict[str, Any], model_name: str, api_key: Optional[str], api_base: Optional[str]) -> None:
    """Configure OpenAI-compatible provider setup."""
    if not model_name.startswith("openai-compatible/"):
        return
    
    # Get config values safely
    config_openai_key = getattr(config, 'OPENAI_COMPATIBLE_API_KEY', None) if config else None
    config_openai_base = getattr(config, 'OPENAI_COMPATIBLE_API_BASE', None) if config else None
    
    # Check if have required config either from parameters or environment
    if (not api_key and not config_openai_key) or (
        not api_base and not config_openai_base
    ):
        raise LLMError(
            "OPENAI_COMPATIBLE_API_KEY and OPENAI_COMPATIBLE_API_BASE is required for openai-compatible models. If just updated the environment variables, wait a few minutes or restart the service to ensure they are loaded."
        )
    
    setup_provider_router(api_key, api_base)
    logger.debug(f"Configured OpenAI-compatible provider with custom API base")

def _add_tools_config(params: Dict[str, Any], tools: Optional[List[Dict[str, Any]]], tool_choice: str) -> None:
    """Add tools configuration to parameters."""
    if tools is None:
        return
    
    params.update({
        "tools": tools,
        "tool_choice": tool_choice
    })
    # logger.debug(f"Added {len(tools)} tools to API parameters")


async def make_llm_api_call(
    messages: List[Dict[str, Any]],
    model_name: str,
    response_format: Optional[Any] = None,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = True,  # Always stream for better UX
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    token_breakdown: Optional[Dict[str, int]] = None,
) -> Union[Dict[str, Any], AsyncGenerator, ModelResponse]:
    """Make an API call to a language model using LiteLLM."""
    logger.info(f"Making LLM API call to model: {model_name} with {len(messages)} messages")
    
    # Prepare parameters using centralized model configuration
    from core.ai_models import model_manager
    resolved_model_name = model_manager.resolve_model_id(model_name)
    # logger.debug(f"Model resolution: '{model_name}' -> '{resolved_model_name}'")
    
    # Only pass headers/extra_headers if they are not None to avoid overriding model config
    override_params = {
        "messages": messages,
        "temperature": temperature,
        "response_format": response_format,
        "top_p": top_p,
        "stream": stream,
        "api_key": api_key,
        "api_base": api_base
    }
    
    # Only add headers if they are provided (not None)
    if headers is not None:
        override_params["headers"] = headers
    if extra_headers is not None:
        override_params["extra_headers"] = extra_headers
    
    # append the prefix for resolved_model_name "openai/gpt-5-nano-2025-08-07"
    if resolved_model_name.startswith("openai/"):
        resolved_model_name = f"openrouter/openai/gpt-5-nano"
    
    params = model_manager.get_litellm_params(resolved_model_name, **override_params)

    # If model does not support vision, use same vision API as browser (VISION_*) to describe images and inject text
    model = model_manager.get_model(resolved_model_name)
    if model is not None and not getattr(model, "supports_vision", True):
        if params.get("messages"):
            params["messages"] = await _replace_images_with_vision_descriptions(params["messages"])
            logger.info(f"Replaced image content with vision API descriptions for non-vision model: {resolved_model_name}")

    logger.debug(f"Parameters from model_manager.get_litellm_params: {params}")
    
    if model_id:
        params["model_id"] = model_id
    
    if stream:
        params["stream_options"] = {"include_usage": True}
    
    # Apply additional configurations that aren't in the model config yet
    _configure_openai_compatible(params, model_name, api_key, api_base)
    _add_tools_config(params, tools, tool_choice)

    start_time = time.time()
    thread_id = "unknown" # Need to pass this locally if possible, but messages usually don't have it directly.
    # Try to extract thread_id from logs context or pass it explicitly?
    # For now, let's keep it simple.

    try:
        # Log the complete parameters being sent to LiteLLM
        # logger.debug(f"Calling LiteLLM acompletion for {resolved_model_name}")
        # logger.debug(f"Complete LiteLLM parameters: {params}")
        
        # # Save parameters to txt file for debugging
        # import json
        # import os
        # from datetime import datetime
        
        # debug_dir = "debug_logs"
        # os.makedirs(debug_dir, exist_ok=True)
        
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # filename = f"{debug_dir}/llm_params_{timestamp}.txt"
        
        # with open(filename, 'w') as f:
        #     f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        #     f.write(f"Model Name: {model_name}\n")
        #     f.write(f"Resolved Model Name: {resolved_model_name}\n")
        #     f.write(f"Parameters:\n{json.dumps(params, indent=2, default=str)}\n")
        
        # logger.debug(f"LiteLLM parameters saved to: {filename}")
        
        response = await provider_router.acompletion(**params)

        duration = (time.time() - start_time) * 1000

        # For streaming responses, we need to handle errors that occur during iteration
        if hasattr(response, '__aiter__') and stream:
            return _wrap_streaming_response(response, model_name, duration, token_breakdown)

        # Log non-streaming response
        usage = getattr(response, 'usage', None)
        prompt_tokens = 0
        completion_tokens = 0
        if usage:
            prompt_tokens = getattr(usage, 'prompt_tokens', 0)
            completion_tokens = getattr(usage, 'completion_tokens', 0)
        
        # Fallback to calculated breakdown for prompt tokens if usage is missing
        if prompt_tokens == 0 and token_breakdown:
            prompt_tokens = sum(token_breakdown.values())

        local_collector.log_llm_call(
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration,
            thread_id="unknown", # We can improve this later
            success=True,
            token_breakdown=token_breakdown
        )

        return response

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        
        # Fallback to calculated breakdown for prompt tokens
        prompt_tokens = 0
        if token_breakdown:
            prompt_tokens = sum(token_breakdown.values())
            
        local_collector.log_llm_call(
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            duration_ms=duration,
            thread_id="unknown",
            success=False,
            token_breakdown=token_breakdown
        )
        # Use ErrorProcessor to handle the error consistently
        processed_error = ErrorProcessor.process_llm_error(e, context={"model": model_name})
        ErrorProcessor.log_error(processed_error)
        raise LLMError(processed_error.message)

async def _wrap_streaming_response(response, model_name: str, initial_duration_ms: float, token_breakdown: Optional[Dict[str, int]] = None) -> AsyncGenerator:
    """Wrap streaming response to handle errors during iteration."""
    start_time = time.time()
    prompt_tokens = 0
    completion_tokens = 0

    # Flag to prevent duplicate logging in finally block if exception occurs
    logged = False
    accumulated_content = []
    try:
        async for chunk in response:
            # Try to capture usage from chunk if available (usually in the last chunk)
            if hasattr(chunk, 'usage') and chunk.usage:
                prompt_tokens = getattr(chunk.usage, 'prompt_tokens', 0)
                completion_tokens = getattr(chunk.usage, 'completion_tokens', 0)

            # Capture content for fallback token counting
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    accumulated_content.append(delta.content)

            yield chunk

    except Exception as e:
        logged = True
        total_duration = initial_duration_ms + (time.time() - start_time) * 1000
        
        # Fallback to calculated breakdown for prompt tokens if usage is missing
        if prompt_tokens == 0 and token_breakdown:
            prompt_tokens = sum(token_breakdown.values())
            
        local_collector.log_llm_call(
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=total_duration,
            thread_id="unknown",
            success=False,
            token_breakdown=token_breakdown
        )
        # Convert streaming errors to processed errors
        processed_error = ErrorProcessor.process_llm_error(e)
        ErrorProcessor.log_error(processed_error)
        raise LLMError(processed_error.message)
    finally:
        if not logged:
            # Fallback to calculated breakdown for prompt tokens if usage is missing
            if prompt_tokens == 0 and token_breakdown:
                prompt_tokens = sum(token_breakdown.values())

            # Fallback to estimated completion tokens if usage is missing
            if completion_tokens == 0 and accumulated_content:
                full_content = "".join(accumulated_content)
                counter = TokenCounter(model=model_name)
                completion_tokens = counter.count_tokens(full_content)

            # Log after stream completes (or is interrupted)
            total_duration = initial_duration_ms + (time.time() - start_time) * 1000
            local_collector.log_llm_call(
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=total_duration,
                thread_id="unknown",
                success=True,
                token_breakdown=token_breakdown
            )

setup_api_keys()
setup_provider_router()


if __name__ == "__main__":
    from litellm import completion
    import os

    setup_api_keys()

    response = completion(
        model="bedrock/anthropic.claude-sonnet-4-20250115-v1:0",
        messages=[{"role": "user", "content": "Hello! Testing 1M context window."}],
        max_tokens=100,
        extra_headers={
            "anthropic-beta": "context-1m-2025-08-07"  # 👈 Enable 1M context
        }
    )

