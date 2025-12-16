"""
Discretization Log I/O

Persistence layer for reading and writing discretization logs.
JSON format for development; Parquet can be added later if needed.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from .schema import (
    DiscretizationConfig,
    DiscretizationLog,
    validate_log,
)
from .discretizer import DiscretizerConfig

logger = logging.getLogger(__name__)


def write_log(log: DiscretizationLog, path: Path) -> None:
    """
    Write discretization log to JSON file.

    Handles nested dataclasses (EffortAnnotation, ShockAnnotation,
    ParentContext, DiscretizationConfig) via recursive to_dict().

    Args:
        log: The DiscretizationLog to write
        path: Destination file path
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = log.to_dict()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_log(path: Path, validate: bool = True, warn_config_diff: bool = True) -> DiscretizationLog:
    """
    Read discretization log from JSON file.

    Reconstructs nested dataclasses from dicts.
    Optionally validates schema on load.

    Args:
        path: Source file path
        validate: If True, run validation after loading
        warn_config_diff: If True, log warning when config differs from defaults

    Returns:
        DiscretizationLog instance

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If validation fails (when validate=True)
    """
    path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    log = DiscretizationLog.from_dict(data)

    # Warn if config differs from current defaults
    if warn_config_diff:
        _check_config_warnings(log)

    # Validate if requested
    if validate:
        errors = validate_log(log)
        if errors:
            raise ValueError(f"Validation failed: {errors}")

    return log


def _check_config_warnings(log: DiscretizationLog) -> None:
    """Log warnings if log config differs from current defaults."""
    defaults = DiscretizerConfig().to_output_config()
    log_config = log.meta.config

    diffs = compare_configs_detail(log_config, defaults)
    if diffs:
        logger.warning(
            "Log was produced with different config than current defaults:\n%s\n"
            "Results may not be comparable to new discretizations.",
            "\n".join(f"  - {d}" for d in diffs)
        )


def compare_configs(log1: DiscretizationLog, log2: DiscretizationLog) -> List[str]:
    """
    Compare configurations between two logs.

    Returns list of differences (empty if identical).
    Useful for corpus comparability checks.

    Args:
        log1: First log to compare
        log2: Second log to compare

    Returns:
        List of difference descriptions

    Example output:
        - "level_set_version differs: v1.0 vs v1.1"
        - "crossing_semantics differs: close_cross vs open_close_cross"
    """
    return compare_configs_detail(log1.meta.config, log2.meta.config)


def compare_configs_detail(config1: DiscretizationConfig, config2: DiscretizationConfig) -> List[str]:
    """
    Compare two DiscretizationConfig instances in detail.

    Args:
        config1: First config
        config2: Second config

    Returns:
        List of difference descriptions
    """
    differences: List[str] = []

    # Level set version
    if config1.level_set_version != config2.level_set_version:
        differences.append(
            f"level_set_version differs: {config1.level_set_version} vs {config2.level_set_version}"
        )

    # Level set contents
    if config1.level_set != config2.level_set:
        differences.append(
            f"level_set differs: {len(config1.level_set)} levels vs {len(config2.level_set)} levels"
        )

    # Crossing semantics
    if config1.crossing_semantics != config2.crossing_semantics:
        differences.append(
            f"crossing_semantics differs: {config1.crossing_semantics} vs {config2.crossing_semantics}"
        )

    # Crossing tolerance
    if abs(config1.crossing_tolerance_pct - config2.crossing_tolerance_pct) > 1e-9:
        differences.append(
            f"crossing_tolerance_pct differs: {config1.crossing_tolerance_pct} vs {config2.crossing_tolerance_pct}"
        )

    # Invalidation thresholds
    if config1.invalidation_thresholds != config2.invalidation_thresholds:
        differences.append(
            f"invalidation_thresholds differs: {config1.invalidation_thresholds} vs {config2.invalidation_thresholds}"
        )

    # Swing detector version
    if config1.swing_detector_version != config2.swing_detector_version:
        differences.append(
            f"swing_detector_version differs: {config1.swing_detector_version} vs {config2.swing_detector_version}"
        )

    # Discretizer version
    if config1.discretizer_version != config2.discretizer_version:
        differences.append(
            f"discretizer_version differs: {config1.discretizer_version} vs {config2.discretizer_version}"
        )

    return differences


def config_compatible(log: DiscretizationLog, expected: DiscretizationConfig) -> bool:
    """
    Check if log was produced with compatible config.

    Used to warn when loading logs produced with different settings.
    Considers configs compatible if level_set and level_set_version match.

    Args:
        log: Log to check
        expected: Expected configuration

    Returns:
        True if configs are compatible, False otherwise
    """
    log_config = log.meta.config

    # Level set version is the primary compatibility check
    if log_config.level_set_version != expected.level_set_version:
        return False

    # Level set contents must match
    if log_config.level_set != expected.level_set:
        return False

    return True


def get_default_config() -> DiscretizationConfig:
    """
    Get the current default DiscretizationConfig.

    Useful for config comparison checks.

    Returns:
        Default configuration as DiscretizationConfig
    """
    return DiscretizerConfig().to_output_config()
