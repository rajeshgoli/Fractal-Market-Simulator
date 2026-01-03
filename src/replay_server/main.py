"""
Main entry point for the Market Structure Analyzer Server.

Usage:
    python -m src.replay_server.main --data-dir ./test_data
    python -m src.replay_server.main --data-dir ./test_data --port 8080
"""

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from .api import app, set_data_dir

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
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory containing data files (required)"
    )

    args = parser.parse_args()

    # Validate data directory
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        return 1
    if not data_dir.is_dir():
        print(f"Error: Not a directory: {data_dir}")
        return 1

    # Set data directory for the API
    set_data_dir(str(data_dir.resolve()))

    # Check if running in multi-tenant mode
    multi_tenant = os.environ.get("MULTI_TENANT", "").lower() in ("true", "1", "yes")

    print(f"\n{'='*60}")
    print("Market Structure Analyzer")
    print(f"{'='*60}")
    if multi_tenant:
        print("Mode:           Multi-tenant (file picker disabled)")
    else:
        print("Mode:           Local (file picker enabled)")
    print(f"Data directory: {data_dir.resolve()}")
    print(f"Server:         http://{args.host}:{args.port}/")
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
