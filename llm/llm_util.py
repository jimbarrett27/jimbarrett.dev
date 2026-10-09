import base64

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from gcp_util.secrets import get_openrouter_api_key
from util.logging_util import setup_logger, log_llm_interaction
import time

logger = setup_logger(__name__)

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


def _openrouter_llm(model_name: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        openai_api_key=get_openrouter_api_key(),
        openai_api_base="https://openrouter.ai/api/v1",
    )


def get_llm_response(template_path: str, params: dict, model_name: str = DEFAULT_MODEL) -> str:
    """
    Generates a response from the LLM via OpenRouter based on a Jinja2 template file and parameters.

    Args:
        template_path: The absolute path to the Jinja2 template file.
        params: A dictionary of parameters to populate the template.
        model_name: The OpenRouter model to use.

    Returns:
        The string response from the LLM.
    """
    start_time = time.time()

    llm = _openrouter_llm(model_name)

    with open(template_path, "r") as f:
        template_content = f.read()

    prompt = PromptTemplate.from_template(template_content, template_format="jinja2")
    chain = prompt | llm

    response = chain.invoke(params)
    response_content = response.content

    duration_ms = (time.time() - start_time) * 1000
    log_llm_interaction(logger, template_path, params, response_content, model_name, duration_ms)

    return response_content


def get_vision_response(template_path: str, params: dict, images: list[tuple[bytes, str]],
                        model_name: str = DEFAULT_MODEL) -> str:
    """
    Like :func:`get_llm_response`, but sends images alongside the rendered prompt.

    Args:
        template_path: The absolute path to the Jinja2 template file.
        params: A dictionary of parameters to populate the template.
        images: ``(bytes, mime_type)`` pairs, sent in order after the prompt text.
        model_name: The OpenRouter model to use; it must accept image input.

    Returns:
        The string response from the LLM.
    """
    start_time = time.time()

    with open(template_path, "r") as f:
        template_content = f.read()
    text = PromptTemplate.from_template(template_content, template_format="jinja2").format(**params)

    content = [{"type": "text", "text": text}]
    for data, mime in images:
        encoded = base64.b64encode(data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

    response_content = _openrouter_llm(model_name).invoke([HumanMessage(content=content)]).content

    duration_ms = (time.time() - start_time) * 1000
    log_llm_interaction(logger, template_path, {**params, "images": len(images)},
                        response_content, model_name, duration_ms)

    return response_content
