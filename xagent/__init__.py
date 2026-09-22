"""xagent: a from-scratch, teaching-oriented code agent.

Reading order for a newcomer:

    messages.py            -- what a conversation *is*
    backends/base.py       -- what "talking to a model" *looks like*
    backends/openai_compat.py -- how that is actually done over HTTP
    agent.py               -- the loop that ties them together
    cli.py                 -- wiring for humans
"""

__version__ = "0.1.0"
