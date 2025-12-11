#!/usr/bin/env python3
"""
Market Data Visualization Harness - Main Entry Point

This is the primary entry point for the market data visualization harness.
It provides an integrated environment combining:
- Multi-scale swing detection and state management
- Real-time 4-panel visualization with Fibonacci levels
- Interactive playback controls with auto-pause
- Comprehensive event logging with filtering and export

Usage:
    python main.py --data test.csv
    python main.py --data test.csv --session analysis_001
    python main.py --data test.csv --auto-start --speed 2.0

Author: Generated for Market Simulator Project
"""

if __name__ == "__main__":
    from src.visualization_harness.harness import main
    main()