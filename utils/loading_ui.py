# ===========================================================
# utils/loading_ui.py
# Reusable, theme-matched loading animations for the whole app.
#
# Provides:
#   - themed_loader(message)   -> use in place of st.spinner(...)
#   - show_splash_screen()     -> full-page splash shown once per session
#   - show_page_transition()   -> short loader shown right after login,
#                                 before the dashboard renders
# ===========================================================

import time
import contextlib
import streamlit as st

_SPINNER_CSS = "<style>@keyframes ml_spin { to { transform: rotate(360deg); } } .ml-loader-row { display: flex; align-items: center; gap: 0.7rem; padding: 0.35rem 0; } .ml-loader-ring { width: 20px; height: 20px; flex-shrink: 0; border: 3px solid rgba(52,211,153,0.18); border-top-color: #34d399; border-radius: 50%; animation: ml_spin 0.7s linear infinite; } .ml-loader-text { font-family: 'DM Mono', monospace, sans-serif; font-size: 0.85rem; color: #34d399; letter-spacing: 0.3px; } .ml-splash-wrap { height: 65vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.1rem; } .ml-splash-ring { width: 46px; height: 46px; border: 4px solid rgba(52,211,153,0.18); border-top-color: #34d399; border-radius: 50%; animation: ml_spin 0.8s linear infinite; } .ml-splash-title { font-family: 'Sora', sans-serif; font-weight: 700; font-size: 1.3rem; color: #e6f2ec; letter-spacing: -0.3px; } .ml-splash-sub { font-family: 'DM Mono', monospace, sans-serif; font-size: 0.78rem; color: #8fb5a2; letter-spacing: 0.4px; }</style>"


def _render_html(html: str):
    """Render raw HTML reliably. Prefer st.html (no markdown parsing at
    all); fall back to st.markdown with unsafe_allow_html on older
    Streamlit versions that don't have st.html yet."""
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


@contextlib.contextmanager
def themed_loader(message: str = "Loading..."):
    """
    Drop-in replacement for `with st.spinner("..."):`.
    Shows a small inline ring + message that matches the app theme,
    and clears itself automatically when the block finishes.

    Usage:
        with themed_loader("Saving profile..."):
            save_candidate_profile(uid, payload)
    """
    placeholder = st.empty()
    with placeholder:
        html = (
            _SPINNER_CSS
            + '<div class="ml-loader-row">'
            + '<div class="ml-loader-ring"></div>'
            + f'<span class="ml-loader-text">{message}</span>'
            + '</div>'
        )
        _render_html(html)
    try:
        yield
    finally:
        placeholder.empty()


def show_splash_screen(app_name: str = "InterviewAI", min_seconds: float = 1.1):
    """
    Full-page splash animation shown once, the very first time the app
    is opened in a browser session.
    """
    if st.session_state.get("_app_booted"):
        return
    st.session_state._app_booted = True

    placeholder = st.empty()
    with placeholder:
        html = (
            _SPINNER_CSS
            + '<div class="ml-splash-wrap">'
            + '<div class="ml-splash-ring"></div>'
            + f'<div class="ml-splash-title">{app_name}</div>'
            + '<div class="ml-splash-sub">// booting up your workspace</div>'
            + '</div>'
        )
        _render_html(html)
    time.sleep(min_seconds)
    placeholder.empty()


def show_page_transition(message: str = "Loading your dashboard...", seconds: float = 0.9):
    """
    Short themed loader shown right after a successful login/register,
    before the dashboard is rendered.
    """
    placeholder = st.empty()
    with placeholder:
        html = (
            _SPINNER_CSS
            + '<div class="ml-splash-wrap" style="height:40vh;">'
            + '<div class="ml-splash-ring"></div>'
            + f'<div class="ml-loader-text" style="font-size:0.9rem;">{message}</div>'
            + '</div>'
        )
        _render_html(html)
    time.sleep(seconds)
    placeholder.empty()