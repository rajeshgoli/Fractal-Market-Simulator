# Developer Guide

## Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd fractal-market-simulator

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m pytest tests/ -v
```

## Project Structure

```
fractal-market-simulator/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── CLAUDE.md              # AI assistant instructions
├── src/
│   ├── analysis/          # Core analytical pipeline
│   ├── cli/               # Command-line interface
│   ├── data/              # Data loading utilities
│   ├── legacy/            # Historical components
│   ├── logging/           # Event logging system
│   ├── playback/          # Playback control
│   ├── validation/        # Validation infrastructure
│   └── visualization/     # Visualization components
├── tests/                 # Test suite
├── Docs/                  # Documentation
└── test_data/             # Sample data files (not in git)
```

## Development Workflow

### Running the Application

```bash
# Basic visualization
python main.py --data test.csv

# With auto-start and custom speed
python main.py --data market_data.csv --auto-start --speed 2.0

# Show help
python main.py --help
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_scale_calibrator.py -v

# Run with coverage (if pytest-cov installed)
python -m pytest tests/ --cov=src
```

### CLI Commands

```bash
# Data discovery
python3 -m src.cli.main list-data --symbol ES --verbose

# Historical validation
python3 -m src.cli.main validate --symbol ES --resolution 1m \
    --start 2024-10-10 --end 2024-10-11
```

## Dependencies

Core libraries:
- **matplotlib** - Visualization
- **numpy** - Numerical computation
- **pandas** - Data manipulation
- **pytest** - Testing

Install all dependencies from requirements.txt. Do not commit the `venv/` directory.

## Code Standards

- Type hints on all public functions
- Docstrings for classes and non-trivial functions
- Tests for new functionality
- Follow existing patterns in the codebase

## Git Conventions

### What NOT to commit
- `venv/` - Virtual environment (listed in .gitignore)
- `__pycache__/` - Python bytecode
- `.DS_Store` - macOS metadata
- `*.pyc` - Compiled Python files
- Large data files (use test_data/ locally)

### Commit Messages
Use descriptive commit messages that explain what changed and why.

## Troubleshooting

### Virtual Environment Issues
```bash
# Remove and recreate venv if corrupted
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Import Errors
Ensure you've activated the virtual environment:
```bash
source venv/bin/activate
which python  # Should show path inside venv/
```
