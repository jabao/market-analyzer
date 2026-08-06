"""Streamlit wrapper for a minimal Plaid Link custom component."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent / "plaid_link_frontend"
_plaid_link = components.declare_component("plaid_link", path=str(_COMPONENT_DIR))


def plaid_link_button(
    link_token: str | None,
    *,
    label: str = "Connect Robinhood",
    auto_open: bool = False,
    popup_mode: bool = True,
    prepare_mode: bool = False,
    popup_id: str | None = None,
    launch_id: str | None = None,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Render a Plaid Link button and return the component result."""
    return _plaid_link(
        linkToken=link_token or "",
        buttonLabel=label,
        autoOpen=auto_open,
        popupMode=popup_mode,
        prepareMode=prepare_mode,
        popupId=popup_id,
        launchId=launch_id,
        default=None,
        key=key,
    )
