import re
from typing import Tuple

# Ordered list of (label, compiled_regex) pairs.
# More specific patterns must come before broader ones.
_PII_PATTERNS: list[Tuple[str, re.Pattern]] = [
    # JWT tokens
    (
        "[JWT_TOKEN]",
        re.compile(r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b"),
    ),
    # API / secret keys in key=value or key: value form
    (
        "[API_KEY]",
        re.compile(
            r"(?i)(api[_\-\s]?key|secret[_\-\s]?key|access[_\-\s]?token|auth[_\-\s]?token)"
            r"[\s:=]+['\"]?([A-Za-z0-9\-_]{16,})['\"]?",
        ),
    ),
    # Passwords in key=value or key: value form
    (
        "[PASSWORD]",
        re.compile(
            r"(?i)(password|passwd|pwd|secret)[\s:=]+['\"]?(\S+)['\"]?",
        ),
    ),
    # Client / customer IDs that look like UUIDs or long identifiers
    (
        "[CLIENT_ID]",
        re.compile(
            r"(?i)(client[_\-\s]?id|customer[_\-\s]?id|account[_\-\s]?id)"
            r"[\s:=]+['\"]?([A-Za-z0-9\-_]{8,})['\"]?",
        ),
    ),
    # Credit card numbers (major formats, with optional separators)
    (
        "[CREDIT_CARD]",
        re.compile(r"\b(?:\d[ \-]?){13,16}\b"),
    ),
    # US Social Security Numbers
    (
        "[SSN]",
        re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    ),
    # Email addresses
    (
        "[EMAIL]",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    # Phone numbers (US and international formats)
    (
        "[PHONE]",
        re.compile(
            r"(?<!\d)(\+?1[\s\-.]?)?"
            r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)"
        ),
    ),
    # IPv4 addresses
    (
        "[IP_ADDRESS]",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
    ),
]


def mask_pii(text: str) -> Tuple[str, list[str]]:
    """
    Replace PII in *text* with placeholder labels.

    Returns:
        masked_text: text with PII replaced
        findings: list of PII types that were detected
    """
    findings: list[str] = []

    for label, pattern in _PII_PATTERNS:
        if pattern.search(text):
            findings.append(label)
            # For patterns with capture groups, replace only the sensitive group
            if pattern.groups:
                # Replace the whole match; the label is self-explanatory
                text = pattern.sub(label, text)
            else:
                text = pattern.sub(label, text)

    return text, findings
