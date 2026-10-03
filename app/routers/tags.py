"""Section names shown as groups in the Swagger UI (/docs)."""

SUBMIT = "Submit trades"
READ = "Read trades"
SCHEDULER = "Scheduler"
SYSTEM = "System"

OPENAPI_TAGS = [
    {
        "name": SUBMIT,
        "description": "Send trades to the store. Applies rules R1 (lower version), "
        "R2 (same version replaces) and R3 (past maturity).",
    },
    {
        "name": READ,
        "description": "Read stored trades and their version history. "
        "The `expired` flag is derived from the maturity date at read time.",
    },
    {
        "name": SCHEDULER,
        "description": "Status of the background job that marks matured trades as expired (R4).",
    },
    {
        "name": SYSTEM,
        "description": "Operational endpoints.",
    },
]