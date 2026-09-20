from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from gcp_util.secrets import get_openrouter_api_key
from util.logging_util import setup_logger, log_llm_interaction
import time

logger = setup_logger(__name__)

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


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

    llm = ChatOpenAI(
        model=model_name,
        openai_api_key=get_openrouter_api_key(),
        openai_api_base="https://openrouter.ai/api/v1",
    )

    with open(template_path, "r") as f:
        template_content = f.read()

    prompt = PromptTemplate.from_template(template_content, template_format="jinja2")
    chain = prompt | llm

    response = chain.invoke(params)
    response_content = response.content

    duration_ms = (time.time() - start_time) * 1000
    log_llm_interaction(logger, template_path, params, response_content, model_name, duration_ms)

    return response_content
