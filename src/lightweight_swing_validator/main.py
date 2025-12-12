"""
Main entry point for the lightweight swing validator.

Usage:
    python -m src.lightweight_swing_validator.main --data test_data/test.csv
    python -m src.lightweight_swing_validator.main --data test_data/es-1m.csv --port 8080
"""

import argparse
import logging
import sys

import uvicorn

from .api import app, init_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Lightweight Swing Validator - Human-in-the-loop swing detection validation"
    )
    parser.add_argument(
        "--data",
        required=True,
        help="Path to OHLC CSV data file"
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
        "--storage-dir",
        default="validation_results",
        help="Directory for storing validation results"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    # Initialize the application
    try:
        init_app(
            data_file=args.data,
            storage_dir=args.storage_dir,
            seed=args.seed
        )
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Print startup message
    print(f"\n{'='*60}")
    print("Lightweight Swing Validator")
    print(f"{'='*60}")
    print(f"Data file: {args.data}")
    print(f"Server:    http://{args.host}:{args.port}")
    print(f"Storage:   {args.storage_dir}/")
    print(f"{'='*60}")
    print("\nOpen the URL above in your browser to start validating.\n")

    # Run the server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
