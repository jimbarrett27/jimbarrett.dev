import logging
import sys
from datetime import datetime
# Configure logging format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    Sets up a logger with consistent formatting.
    
    Args:
        name: Name of the logger (typically __name__ from the calling module)
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # This logger prints through its own handler; don't also pass records up to
    # the root handler from configure_root_logging, or every line appears twice.
    logger.propagate = False
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        # Formatter
        formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
    
    return logger

def configure_root_logging(level=logging.INFO) -> None:
    """Give plain ``logging.getLogger(__name__)`` loggers somewhere to write.

    Without a root handler only warnings and errors from those loggers surface
    (via Python's last-resort handler), so a long-running process's INFO lines --
    "panel refreshed", "pushed ok" -- silently vanish and a quiet journal can't
    tell success from a job that never ran.

    Chatty third-party loggers are held at WARNING: httpx logs every Telegram
    long-poll request at INFO, and those URLs carry the bot token.
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT, stream=sys.stdout)
    for noisy in ("httpx", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_llm_interaction(logger: logging.Logger, template_path: str, params: dict, 
                        response: str, model_name: str, duration_ms: float = None):
    """
    Logs an LLM interaction with all relevant details.
    
    Args:
        logger: Logger instance to use
        template_path: Path to the template used
        params: Parameters passed to the template
        response: Response from the LLM
        model_name: Name of the model used
        duration_ms: Optional duration of the call in milliseconds
    """
    duration_str = f" ({duration_ms:.2f}ms)" if duration_ms else ""
    logger.info(f"LLM Request{duration_str} - Model: {model_name}")
    logger.debug(f"  Template: {template_path}")
    logger.debug(f"  Params: {params}")
    logger.info(f"  Response: {response[:200]}{'...' if len(response) > 200 else ''}")

def log_telegram_message_received(logger: logging.Logger, chat_id: str, 
                                   username: str, text: str):
    """
    Logs a received Telegram message.
    
    Args:
        logger: Logger instance to use
        chat_id: Chat ID where message was received
        username: Username of the sender
        text: Message text
    """
    logger.info(f"📥 Telegram Message Received - Chat: {chat_id}, User: {username}")
    logger.info(f"  Text: {text}")

def log_telegram_message_sent(logger: logging.Logger, chat_id: str, text: str):
    """
    Logs a sent Telegram message.
    
    Args:
        logger: Logger instance to use
        chat_id: Chat ID where message was sent
        text: Message text
    """
    logger.info(f"📤 Telegram Message Sent - Chat: {chat_id}")
    logger.info(f"  Text: {text[:200]}{'...' if len(text) > 200 else ''}")

