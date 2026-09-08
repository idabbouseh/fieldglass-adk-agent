try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is a convenience, not a requirement
    pass

from . import agent  # noqa: E402,F401  (ADK discovers root_agent here)
