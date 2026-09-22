"""Model transport implementations.

Everything in this package is replaceable: the agent only depends on the
`Backend` protocol in `base.py`.
"""

from .base import Backend, BackendError, ModelParams, StreamEvent
from .mock import MockBackend
from .openai_compat import OpenAICompatBackend

__all__ = [
    "Backend",
    "BackendError",
    "MockBackend",
    "ModelParams",
    "OpenAICompatBackend",
    "StreamEvent",
]
