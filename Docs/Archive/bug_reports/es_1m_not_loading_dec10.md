## Investigation Request: ES 1m CSV Load Failure

I’m seeing consistent failures when the CLI attempts to load `ES-1m.csv` (and case variants). This blocks all 1m workflows. The error appears deterministic and reproducible.

### Observed Output

Running:
- `python3 -m src.cli.main list-data`

Produces:
- Multiple failures reading `ES-1m.csv` / `es-1m.csv`
- Error message:  
  `unsupported operand type(s) for -: 'slice' and 'int'`
- Resolution `1m` ends up with **Status: No data available**
- Other resolutions (5m, 1d) load correctly and report valid ranges

### Your Task

Treat this as a **bug investigation + fix**, not a feature request.

Your goals are:

1. **Identify exactly why `ES-1m.csv` fails to load**
   - Find where a `slice - int` operation is occurring.
   - Determine whether this is:
     - A pandas indexing bug
     - An assumption about sorted indices
     - A misuse of slicing when computing date ranges, bar counts, or resampling
     - A schema mismatch specific to 1m files (column order, header, dtype, index type)

2. **Determine whether the bug is data-specific or logic-specific**
   - Confirm whether:
     - The 1m CSV schema differs from 5m / 1d
     - Case sensitivity (`ES-1m.csv` vs `es-1m.csv`) is a contributing factor
     - Duplicate loading attempts are masking the root cause
   - Explicitly rule out red herrings.

3. **Fix the underlying issue**
   - Do not add try/except to suppress the error.
   - Do not special-case “1m” unless strictly unavoidable.
   - The fix should generalize to any high-frequency resolution.

4. **Add one minimal regression check**
   - Either:
     - A small unit test around the failing function, or
     - A deterministic load check that ensures 1m files can be parsed and summarized.
   - This does not need full coverage—just ensure this exact failure cannot silently recur.

5. **Improve the error message if the failure mode is structural**
   - If the bug arises from invalid assumptions (e.g., index type, bar alignment, slicing semantics), make the error actionable rather than cryptic.
   - “unsupported operand type(s)” is not acceptable as a surfaced failure mode.

### Expected Outcome

After the fix:
- `list-data` should successfully report `1m` availability if the file is valid.
- `validate` should no longer fail due to missing 1m data (assuming date ranges overlap).
- There should be no behavioral regressions for 5m / 1d.

### Documentation

Once fixed, briefly document:
- Root cause
- Fix applied
- Why it only affected 1m
- How you verified the resolution

Place this in an appropriate engineer note (small, bug-fix style).
