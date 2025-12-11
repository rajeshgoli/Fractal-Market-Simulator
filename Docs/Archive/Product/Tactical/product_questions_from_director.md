# Product Questions from Director

**Date:** December 11, 2025
**From:** Director
**To:** Product
**Context:** Process improvement discussion following Dec 11 validation feedback

---

## Background

The Dec 11 interview surfaced a structural limitation: Product cannot directly experience the tool. Product interviews the user about usability, but relies entirely on user articulation to understand fitness-for-purpose issues.

User proposed: "Perhaps we can stand up an MCP server for product agent to try the product."

---

## Question for Product

**Should Product have direct tool access via MCP server?**

If Product could run the harness directly, it could:
- Form independent usability judgments before user burns time on validation
- Identify fit-for-purpose issues through direct experience
- Reduce "expensive oracle" cost by pre-filtering issues
- Validate usability criteria without requiring user articulation

### Technical Scope (Draft)

Minimum capabilities for Product to "try the product":
1. **CLI execution**: Run `python main.py --data <file>` with various options
2. **Screenshot capture**: View matplotlib output at key moments
3. **Keyboard simulation**: Step through bars, pause/resume, navigate
4. **Output parsing**: Read console output for errors, status messages

### Questions for Product to Reason About

1. **Value vs. Cost**: Is the engineering effort to build an MCP server worth the Product capability gain? What's the minimum viable scope?

2. **Trust boundaries**: Should Product have:
   - Read-only + CLI execution only?
   - Ability to modify test data files?
   - Access to git operations?

3. **Workflow integration**: How would Product use this capability?
   - Before user validation sessions (pre-check)?
   - During milestone review (verify usability criteria)?
   - Ad-hoc exploration when interviewing user?

4. **Alternative approaches**: Could Product get similar value from:
   - Architect running the tool and reporting observations?
   - User providing screen recordings?
   - Structured usability checklists in handoffs?

---

## Requested Output

Product to produce `product_mcp_assessment.md` with:
- Recommendation (build / defer / alternative approach)
- If build: minimum viable scope and success criteria
- If defer: what conditions would change the calculus
- Workflow changes needed if capability is added

---

## Handoff

Product to reason about this independently, then document findings for Director review.
