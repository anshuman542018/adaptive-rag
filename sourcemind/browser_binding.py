"""Read the OAuth browser nonce via a component, including on Cloud proxies."""
from pathlib import Path
import streamlit.components.v1 as components

_binding = components.declare_component("oauth_browser_binding", path=str(Path(__file__).with_suffix("")))


def browser_binding(mode: str, nonce: str = "", key: str = "oauth_binding"):
    return _binding(mode=mode, nonce=nonce, key=key, default=None)
