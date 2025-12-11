# CLI Data Availability Enhancements

**Engineer:** Claude Code  
**Date:** 2025-12-10  
**Type:** Usability Fix  
**Status:** Complete

## Context

Users attempting to run historical validation commands consistently encountered blocking errors indicating that requested date ranges did not overlap with available data. The CLI provided no mechanism to discover what data was actually available, forcing users to manually inspect filesystem contents to determine valid `--start/--end` parameters. This created a poor user experience where even informed users could not effectively use the validation system without trial-and-error.

## Change Summary

**Added new CLI command:**
- `list-data` command (with aliases `describe`, `inspect`) to display comprehensive data availability summaries
- Shows available resolutions, date ranges, file counts, and total bars for any symbol
- Optional `--verbose` flag provides per-file details including specific date ranges and bar counts

**Enhanced error messaging:**
- Validation failures due to date mismatch now display specific available date ranges
- Error messages include exact CLI commands to get detailed data information
- Timestamps displayed in human-readable format with UTC timezone

**Improved verbose logging:**
- `validate --verbose` now shows which data files were loaded during validation
- Displays file-specific date ranges and bar counts before date filtering
- Reports filtered data range and final bar count after processing

## Behavior Before vs After

**Before:** Validation command fails with generic message "Requested range ... does not overlap with available data ranges" - user has no way to determine valid ranges.

**After:** Validation failure provides specific available date ranges (e.g., "Available data spans: 2024-10-09 22:00 UTC to 2025-12-05 21:55 UTC") and suggests exact command to get detailed information (`python3 -m src.cli.main list-data --symbol ES --resolution 1m --verbose`).

## Scope and Intent

This change strictly improves debuggability and discoverability of available data. It does not modify:
- Validation logic or algorithms
- Data loading behavior or file discovery patterns  
- Data sources or file formats
- Core harness functionality

The enhancement is focused on surface-level usability and information transparency, not comprehensive data management capabilities.

## Verification

Verified across multiple scenarios:
- Failing validation commands now display specific available date ranges and helpful guidance
- New `list-data` command successfully shows data availability for multiple resolutions (1m, 5m, 1d)
- Verbose output provides detailed per-file information including date ranges and bar counts
- Alias commands (`describe`, `inspect`) function identically to primary command
- Enhanced error messages guide users to appropriate discovery commands

Testing confirmed that users can now determine valid date ranges through a single discovery command rather than filesystem inspection or trial-and-error validation attempts.

## Follow-Ups

Non-blocking enhancements that could be considered in future iterations:
- Auto-suggestion of valid date ranges when validation fails due to date mismatch
- Caching of data summaries for improved performance during repeated discovery operations
- Integration with validation workflow to pre-validate date ranges before attempting full data loading
- Rich formatting options for data summaries (JSON, CSV export for programmatic use)

These improvements provide immediate resolution of the reported usability issue while maintaining focus on core validation functionality.