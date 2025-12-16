"""CSV export utilities.

Provides common functions for CSV field escaping and formatting.
"""


def escape_csv_field(value: str) -> str:
    """
    Escape special characters in a CSV field.

    Replaces:
    - Commas with semicolons (to avoid field delimiter conflicts)
    - Newlines with spaces (to keep single-line format)

    Args:
        value: The string value to escape

    Returns:
        Escaped string safe for CSV inclusion
    """
    if value is None:
        return ""
    return value.replace(",", ";").replace("\n", " ")
