"""String escaping and decoding helpers for PO files."""

from __future__ import annotations


class PoStringCodec:
    """Handle PO string escaping and decoding."""

    @staticmethod
    def decode(value: str) -> str:
        """Decode PO escape sequences.

        Args:
            value: Encoded PO string payload without surrounding quotes.

        Returns:
            Decoded text.
        """

        if "\\" not in value:
            return value
        replacements = [
            ("\\\\", "\\"),
            ("\\n", "\n"),
            ("\\t", "\t"),
            ("\\r", "\r"),
            ('\\"', '"'),
            ("\\'", "'"),
            ("\\u2028", "\u2028"),
            ("\\u2029", "\u2029"),
        ]
        for old, new in replacements:
            value = value.replace(old, new)
        return value

    @staticmethod
    def escape(value: str) -> str:
        """Escape a string for PO serialization.

        Args:
            value: Plain text value.

        Returns:
            Escaped PO string payload without surrounding quotes.
        """

        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
