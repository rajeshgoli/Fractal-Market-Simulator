# Interview Command

Use the interview skill to conduct an in-depth spec interview.

## Arguments

$ARGUMENTS = the spec name or path (e.g., "reference layer spec" or "Docs/Working/proposal.md")

## Instructions

1. Locate the spec file (check `Docs/Working/` if path not given)
2. Read the spec thoroughly
3. Use `AskUserQuestion` tool for in-depth interviews:
   - Technical implementation choices
   - UI/UX tradeoffs
   - Concerns and edge cases
   - Non-obvious questions only
4. Be thorough — multiple rounds expected, exhaust the design space
5. Continue until user confirms complete
6. Update the spec with findings

Operate as polymath — bring product, architecture, and engineering perspectives.
