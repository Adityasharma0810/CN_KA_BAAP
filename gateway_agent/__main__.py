"""Gateway agent console entry point.

Usage:
    python -m gateway_agent
or after pip install:  experience-budget-agent
"""

from __future__ import annotations

import asyncio

from gateway_agent.core.agent import main

if __name__ == "__main__":
    asyncio.run(main())
