"""
Main entry point for the Market Structure Analyzer Server.

Usage:
    python -m src.replay_server.main
    python -m src.replay_server.main --port 8080
"""

import argparse
import logging

import uvicorn

from .api import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Market Structure Analyzer - View market structure as it forms"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on (default: 8000)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Market Structure Analyzer")
    print(f"{'='*60}")
    print("The app will prompt for file selection in the browser.")
    print()
    print(f"Server:         http://{args.host}:{args.port}/replay")
    print(f"{'='*60}")
    print("\nOpen the URL above in your browser.\n")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
