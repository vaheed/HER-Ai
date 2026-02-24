from __future__ import annotations


def requires_explicit_approval(tool_name: str, irreversible: bool) -> bool:
    """Gate tool calls that are irreversible or privileged."""

    sensitive_tools = {"filesystem_delete", "external_payment", "account_change"}
    return irreversible or tool_name in sensitive_tools
