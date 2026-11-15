from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# LLM_SERVER_ADDRESS = "127.0.0.1:8080"
LLM_SERVER_ADDRESS = "http://debian-server:8080"

GRAMMAR_DIR = REPO_ROOT / "llm/grammars"
