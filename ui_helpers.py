"""Small HTML snippets for the page (kept out of app.py so they can be tested)."""
from __future__ import annotations

import html
import json

VERDICT_STYLE = {"hidden gem": ("💎", "Hidden gem", "#1faa59"), "fine": ("🙂", "Fine", "#e0a800"),
                 "think twice": ("⚠️", "Think twice", "#e5484d")}


def verdict_badge(verdict: str, summary: str = "") -> str:
    icon, label, color = VERDICT_STYLE.get(verdict, ("•", verdict, "#888"))
    return (f'<div class="ll-verdict" style="border-color:{color}"><span class="ll-pill" style="background:{color}">{icon} {label}</span>'
            f'<span class="ll-verdict-text">{html.escape(summary)}</span></div>')


def loading_html(message: str) -> str:
    return f'<div class="ll-load"><span class="ll-spin"></span><span>{html.escape(message)}</span></div>'


def copy_button_html(text: str, label: str = "📋 Copy email") -> str:
    """A button that copies `text` to the clipboard (with a fallback for iframes that block the clipboard API)."""
    payload = json.dumps(text).replace("</", "<\\/")
    return f"""<style>
  :root {{ color-scheme: light dark; --btn:#0071E3; --btnt:#FFFFFF; --ok:#1F7A38; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --ok:#30D158; }} }}
  body {{ margin:0; font-family:Inter, -apple-system, 'SF Pro Text', 'Segoe UI', sans-serif; }}
  button {{ background:var(--btn); color:var(--btnt); border:0; border-radius:980px; padding:.65rem 1.3rem; font:500 15px/1.2 inherit;
           font-family:inherit; cursor:pointer; min-height:44px; }}
  button:focus-visible {{ outline:3px solid #4DA3FF; outline-offset:2px; }}
  [role=status] {{ margin-left:.7rem; color:var(--ok); font:600 14px inherit; font-family:inherit; }}
</style>
<button id="cp" type="button">{html.escape(label)}</button><span id="st" role="status" aria-live="polite"></span>
<script>
const text = {payload};
const b = document.getElementById("cp"), st = document.getElementById("st");
b.onclick = async () => {{
  try {{ await navigator.clipboard.writeText(text); }}
  catch (e) {{ const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }}
  st.textContent = "Copied to the clipboard"; setTimeout(() => st.textContent = "", 2500);
}};
</script>"""


HOW_IT_WORKS = [("1", "Add up to three addresses", "Type them in the sidebar, or switch on Demo mode."),
                ("2", "See the block and the landlord", "Walking times, noise, street reports and public ownership records, side by side."),
                ("3", "Let the AI team weigh it up", "A ranked pick, questions to ask, and a draft email you send yourself.")]


def how_it_works_html() -> str:
    cards = "".join(f'<div class="ll-step"><span class="ll-num">{n}</span><div><b>{html.escape(t)}</b><br>'
                    f'<span>{html.escape(d)}</span></div></div>' for n, t, d in HOW_IT_WORKS)
    return f'<div class="ll-steps">{cards}</div>'


def embed_html(html_text: str, height: int) -> None:
    """Embed an HTML snippet in an iframe of FIXED height (st.iframe on current Streamlit, components.html on older ones)."""
    import streamlit as st
    if hasattr(st, "iframe"):
        st.iframe(html_text, height=max(int(height), 1))
    else:  # pragma: no cover - older Streamlit
        import streamlit.components.v1 as components
        components.html(html_text, height=height, scrolling=False)


def show_map(m, height: int = 420) -> None:
    """Draw a folium map with an explicit pixel height. st_folium sized itself from its content and rendered at height 0
    inside tabs that were not the active tab when the page loaded; a fixed-height iframe renders in every tab."""
    embed_html(m.get_root().render(), height)
