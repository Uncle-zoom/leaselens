"""The whole look of LeaseLens in one place: colour tokens, the contrast pairs they must satisfy, and all CSS.

Light is the default; dark follows the visitor's system setting (prefers-color-scheme).
tests/test_design.py computes the contrast ratio of every pair in CONTRAST_PAIRS for both themes.
"""
from __future__ import annotations

FONT_STACK = "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

TOKENS = {
    "light": {
        "bg": "#F5F5F7", "card": "#FFFFFF", "text": "#1D1D1F", "text2": "#6E6E73",
        "accent": "#0071E3",          # fills: buttons, selected states (white text on it)
        "accent_text": "#0066CC",     # blue used as TEXT or a thin line (links); #0071E3 is only 4.3:1 on #F5F5F7
        "on_accent": "#FFFFFF",
        "green": "#1F7A38",           # the brief's #248A3D is 4.40:1 on white (just under AA 4.5), so it is darkened
        "orange": "#B25000", "red": "#D70015", "on_status": "#FFFFFF",
        "related": "#0B7285", "owner_marker": "#5856D6",
        "focus": "#0071E3", "control_border": "#7C7C80", "hairline": "rgba(0,0,0,0.06)",
        "shadow": "0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.04)",
    },
    "dark": {
        "bg": "#000000", "card": "#1C1C1E", "text": "#F5F5F7", "text2": "#A1A1A6",
        "accent": "#0071E3", "accent_text": "#4DA3FF", "on_accent": "#FFFFFF",
        "green": "#30D158", "orange": "#FF9F0A", "red": "#FF6961", "on_status": "#000000",
        "related": "#5AC8D8", "owner_marker": "#9A98FF",
        "focus": "#4DA3FF", "control_border": "#8E8E93", "hairline": "rgba(255,255,255,0.10)",
        "shadow": "0 1px 2px rgba(0,0,0,0.5)",
    },
}

# (what it is, foreground token, background token, minimum ratio). 4.5 = normal text, 3.0 = large text and UI parts.
CONTRAST_PAIRS = [
    ("body text on page", "text", "bg", 4.5), ("body text on card", "text", "card", 4.5),
    ("secondary text on page", "text2", "bg", 4.5), ("secondary text on card", "text2", "card", 4.5),
    ("link text on page", "accent_text", "bg", 4.5), ("link text on card", "accent_text", "card", 4.5),
    ("button label on accent fill", "on_accent", "accent", 4.5),
    ("green status text on card", "green", "card", 4.5), ("green status text on page", "green", "bg", 4.5),
    ("orange status text on card", "orange", "card", 4.5), ("orange status text on page", "orange", "bg", 4.5),
    ("red status text on card", "red", "card", 4.5), ("red status text on page", "red", "bg", 4.5),
    ("map glyph on green marker", "on_status", "green", 4.5), ("map glyph on orange marker", "on_status", "orange", 4.5),
    ("map glyph on red marker", "on_status", "red", 4.5),
    ("map glyph on related-company marker", "on_status", "related", 4.5), ("map glyph on owner marker", "on_status", "owner_marker", 4.5),
    ("related-company marker against card", "related", "card", 3.0), ("owner marker against card", "owner_marker", "card", 3.0),
    ("focus ring on card", "focus", "card", 3.0), ("focus ring on page", "focus", "bg", 3.0),
    ("input border on card", "control_border", "card", 3.0), ("input border on page", "control_border", "bg", 3.0),
    ("accent fill against card (button edge)", "accent", "card", 3.0),
]


def _vars(t: dict) -> str:
    return "".join(f"--{k.replace('_', '-')}:{v};" for k, v in t.items())


def css() -> str:
    L, D = TOKENS["light"], TOKENS["dark"]
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {{ {_vars(L)} --radius:16px; }}
@media (prefers-color-scheme: dark) {{ :root {{ {_vars(D)} }} }}

html, body, [data-testid="stAppViewContainer"], .stApp {{ font-family:{FONT_STACK}; background:var(--bg); color:var(--text);
  font-size:1.0625rem; line-height:1.5; }}
[data-testid="stHeader"] {{ background:transparent; }}
.stDeployButton, [data-testid="stToolbar"] [data-testid="stAppDeployButton"] {{ display:none; }}
.block-container {{ max-width:1120px; padding:2.2rem 1.25rem 4rem; }}
@media (max-width: 900px) {{ .ll-card {{ min-height:0; }} }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp summary, .stApp td, .stApp th, .stApp caption,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"] {{ font-family:{FONT_STACK} !important; }}
h1, h2, h3 {{ font-family:{FONT_STACK}; font-weight:600; letter-spacing:-0.02em; color:var(--text); line-height:1.15; border:0 !important; }}
a, a:visited {{ color:var(--accent-text); }}
.ll-num, .ll-score, td.num, .ll-tabular {{ font-variant-numeric: tabular-nums; }}

/* focus: always visible, for mouse-free use */
*:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible, a:focus-visible,
[role="button"]:focus-visible, [role="tab"]:focus-visible {{ outline:3px solid var(--focus) !important; outline-offset:2px !important; border-radius:8px; }}
.ll-skip {{ position:absolute; left:-9999px; top:0; background:var(--card); color:var(--accent-text); padding:.6rem 1rem; border-radius:8px; z-index:9999; }}
.ll-skip:focus {{ left:1rem; top:1rem; }}
.ll-sr {{ position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }}

/* hero */
.ll-hero {{ text-align:center; padding:2.2rem 0 1.2rem; animation: llfade .18s ease-out; }}
.ll-hero h1 {{ font-size:clamp(2rem, 5.2vw, 3.4rem); margin:0 auto .6rem; max-width:22ch; }}
.ll-hero p {{ color:var(--text2); font-size:1.2rem; margin:0 auto; max-width:40ch; }}
.ll-brand {{ font-weight:600; letter-spacing:-0.01em; color:var(--text2); text-align:center; margin-bottom:.4rem; }}
.ll-brand b {{ color:var(--accent-text); }}

/* cards */
.ll-card {{ background:var(--card); border:1px solid var(--hairline); border-radius:var(--radius); box-shadow:{L['shadow']};
  padding:1.25rem 1.4rem; animation: llfade .18s ease-out; min-height:26.5rem; margin-bottom:.7rem; }}
@media (prefers-color-scheme: dark) {{ .ll-card {{ box-shadow:{D['shadow']}; }} }}
.ll-card h2, .ll-card h3 {{ margin:.1rem 0 .3rem; font-size:1.2rem; }}
.ll-addr {{ font-size:1.15rem; font-weight:600; letter-spacing:-0.01em; margin:0 0 .5rem; }}
.ll-muted {{ color:var(--text2); }}
.ll-pill {{ display:inline-flex; align-items:center; gap:.45rem; font-weight:600; font-size:1rem; padding:.3rem .8rem; border-radius:999px;
  background:var(--card); border:2px solid currentColor; }}
.ll-pill svg {{ width:1.15em; height:1.15em; flex:none; }}
.ll-tone-great {{ color:var(--green); }} .ll-tone-good {{ color:var(--accent-text); }} .ll-tone-warn {{ color:var(--orange); }}
.ll-tone-bad {{ color:var(--red); }} .ll-tone-neutral {{ color:var(--text2); }}
.ll-note-line {{ font-size:.9rem; margin:.1rem 0 .4rem; line-height:1.4; }}
.ll-score {{ display:flex; align-items:baseline; gap:.4rem; margin:.7rem 0 .2rem; }}
.ll-score strong {{ font-size:3rem; font-weight:600; letter-spacing:-0.03em; line-height:1; }}
.ll-score span {{ color:var(--text2); }}
.ll-meter {{ height:6px; border-radius:99px; background:var(--hairline); overflow:hidden; margin:.2rem 0 .9rem; }}
.ll-meter i {{ display:block; height:100%; background:var(--accent); border-radius:99px; }}
.ll-facts {{ list-style:none; padding:0; margin:0 0 .4rem; display:grid; gap:.45rem; }}
.ll-facts li {{ display:flex; gap:.6rem; align-items:flex-start; }}
.ll-facts svg, .ll-ico {{ width:1.2em; height:1.2em; flex:none; margin-top:.2em; color:var(--text2); }}
.ll-answer {{ font-size:1.25rem; line-height:1.4; font-weight:500; letter-spacing:-0.01em; margin:.2rem 0 .6rem; }}
.ll-note {{ border-left:3px solid var(--accent); padding:.55rem .9rem; background:var(--card); border-radius:8px; color:var(--text); }}

/* step indicator */
.ll-steps {{ list-style:none; display:flex; flex-wrap:wrap; gap:.6rem 1.4rem; padding:0; margin:.5rem 0 1rem; justify-content:center; }}
.ll-steps li {{ display:flex; align-items:center; gap:.5rem; color:var(--text2); }}
.ll-steps li[aria-current="step"] {{ color:var(--text); font-weight:600; }}
.ll-steps .dot {{ width:1.5rem; height:1.5rem; border-radius:50%; border:2px solid var(--control-border); display:inline-flex; align-items:center; justify-content:center; flex:none; }}
.ll-steps .done .dot {{ background:var(--green); border-color:var(--green); color:var(--on-status); }}
.ll-steps .now .dot {{ border-color:var(--accent); border-top-color:transparent; animation: llspin .9s linear infinite; }}
.ll-steps .dot svg {{ width:.9rem; height:.9rem; }}
.ll-load {{ display:flex; align-items:center; gap:.6rem; color:var(--text2); }}
.ll-spin {{ width:1rem; height:1rem; border:3px solid var(--hairline); border-top-color:var(--accent); border-radius:50%; animation: llspin .9s linear infinite; flex:none; }}

/* map legend (drawn under the map, with the same shapes as the markers) */
.ll-legend {{ list-style:none; display:flex; flex-wrap:wrap; gap:.5rem 1.3rem; padding:0; margin:.6rem 0 0; font-size:.92rem; color:var(--text2); }}
.ll-legend li {{ display:flex; align-items:center; gap:.5rem; }}
.ll-legend .lg {{ width:1.5rem; height:1.5rem; display:inline-flex; align-items:center; justify-content:center; color:var(--on-status); flex:none; }}
.ll-legend .lg svg {{ width:.95rem; height:.95rem; }}
.ll-legend .am {{ background:var(--green); border-radius:50%; }} .ll-legend .sq {{ background:var(--red); border-radius:5px; }}
.ll-legend .tri {{ background:var(--orange); clip-path:polygon(50% 0, 100% 100%, 0 100%); align-items:flex-end; padding-bottom:2px; }}
.ll-legend .dia {{ background:var(--red); transform:rotate(45deg); border-radius:3px; width:1.25rem; height:1.25rem; }}
.ll-legend .dia svg {{ transform:rotate(-45deg); width:.8rem; height:.8rem; }}
.ll-legend .ow {{ background:var(--owner-marker); border-radius:6px; }} .ll-legend .rel {{ background:var(--related); clip-path:polygon(25% 5%, 75% 5%, 100% 50%, 75% 95%, 25% 95%, 0 50%); }} .ll-legend .pin {{ background:var(--accent); border-radius:50%; }}
.ll-legend .ring {{ width:1.6rem; border-top:2px dashed var(--accent-text); height:0; }}

/* ownership trail */
.ll-chain {{ list-style:none; margin:.4rem 0 1rem; padding:0; display:grid; gap:.6rem; }}
.ll-chain li {{ display:grid; grid-template-columns:2rem 1fr; gap:.2rem .8rem; background:var(--card); border:1px solid var(--hairline); border-radius:12px; padding:.7rem .9rem; }}
.ll-chain .n {{ width:2rem; height:2rem; border-radius:50%; background:var(--accent); color:var(--on-accent); display:flex; align-items:center; justify-content:center; font-weight:600; grid-column:1; grid-row:1 / span 3; align-self:start; }}
.ll-chain .lab {{ color:var(--text2); font-size:.9rem; grid-column:2; }}
.ll-chain .val {{ font-size:1.1rem; font-weight:600; grid-column:2; }}
.ll-chain .how {{ grid-column:2; color:var(--text2); font-size:.9rem; }}

/* html tables */
.ll-table {{ width:100%; border-collapse:collapse; font-size:.98rem; }}
.ll-table caption {{ text-align:left; color:var(--text2); padding-bottom:.4rem; }}
.ll-table th, .ll-table td {{ text-align:left; padding:.6rem .7rem; border-bottom:1px solid var(--hairline); vertical-align:top; }}
.ll-table th {{ font-weight:600; color:var(--text); }}
.ll-table td.num {{ text-align:right; }}
.ll-win {{ display:inline-flex; gap:.3rem; align-items:center; color:var(--green); font-weight:600; }}
.ll-win svg {{ width:1.1em; height:1.1em; }}
.ll-cell {{ display:flex; justify-content:flex-end; align-items:center; gap:.55rem; }}
.ll-tablewrap {{ overflow-x:auto; }}

/* Streamlit widgets in the same language */
.stButton > button, [data-testid="stFormSubmitButton"] > button {{ border-radius:980px; font-weight:500; padding:.55rem 1.3rem; min-height:2.75rem;
  border:1px solid var(--control-border); background:var(--card); color:var(--text); transition: background-color .15s ease; }}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {{ background:var(--accent) !important; color:var(--on-accent) !important; border-color:var(--accent) !important; }}
[class*="st-key-chip"] button {{ min-height:2.75rem; font-size:.95rem; padding:.4rem 1rem; }}
[data-baseweb="input"], [data-baseweb="base-input"], .stTextInput input {{ border-radius:12px !important; font-size:1.05rem; }}
[data-baseweb="input"] {{ border:1px solid var(--control-border) !important; background:var(--card) !important; }}
.stTextInput label p, .stSlider label p, .stSelectSlider label p {{ font-weight:500; color:var(--text) !important; }}
[data-testid="stExpander"] {{ background:var(--card); border:1px solid var(--hairline) !important; border-radius:12px; box-shadow:none; }}
[data-testid="stExpander"] summary p {{ font-weight:500; }}
[data-testid="stSidebar"] {{ background:var(--card); }}
[data-testid="stSidebar"] .block-container {{ padding-top:1rem; }}
.stAlert {{ border-radius:12px; }}
iframe {{ max-width:100%; border:0; border-radius:12px; }}

@keyframes llfade {{ from {{ opacity:0; transform:translateY(4px); }} to {{ opacity:1; transform:none; }} }}
@keyframes llspin {{ to {{ transform:rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation:none !important; transition:none !important; scroll-behavior:auto !important; }}
  .ll-steps .now .dot, .ll-spin {{ border-top-color:var(--accent); }}
}}
@media (max-width: 640px) {{ .block-container {{ padding:1.2rem .9rem 3rem; }} .ll-score strong {{ font-size:2.5rem; }} }}
</style>"""
