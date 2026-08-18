"""Visual design for the OmniCare assistant.

Direction: "the policy desk". Insurance runs on documents -- clauses, ledgers,
filed paperwork -- so the interface is paper and ink rather than chat-app chrome.

Three typefaces, each carrying a distinct kind of speech:

  Inter Tight    the assistant talking to you
  Spectral       the policy document being quoted -- the source text literally
                 speaks in a different voice from the assistant
  IBM Plex Mono  identifiers and machine facts: CLM-9015, POL-1092, tool names

Colour is disciplined on purpose. Oxblood (`--seal`) is reserved for refusals and
denials and appears nowhere else, so a refusal reads as a stamped decision rather
than as red-for-error.
"""

FONTS = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter+Tight:wght@400;500;600;700"
    "&family=Spectral:ital,wght@0,400;0,500;1,400"
    "&family=IBM+Plex+Mono:wght@400;500"
    "&display=swap"
)

CSS = f"""
<style>
@import url('{FONTS}');

:root {{
  --ink:      #14201F;   /* ledger ink: near-black with a green cast */
  --ink-60:   #5A6663;
  --ink-40:   #8B9491;
  --paper:    #F7F4ED;   /* warm document stock */
  --surface:  #FFFDF8;
  --clause:   #F1EDE1;   /* tinted paper, for quoted policy text */
  --rule:     #DFD8C8;
  --teal:     #1F5C55;   /* the institution */
  --teal-dim: #E4EDEA;
  --seal:     #A6402E;   /* stamped refusal. Used for nothing else. */
  --seal-dim: #F6E7E2;
  --amber:    #9C6B1F;   /* pending */
  --amber-dim:#F6EDDC;
  --moss:     #3F6B3A;   /* approved */
  --moss-dim: #E7EFE2;
}}

/* ---- Streamlit chrome ------------------------------------------------- */
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], footer {{ display: none !important; }}
/* Heading anchor links -- the little chain icon beside the wordmark. */
.stMarkdown a[href^="#"] svg, h1 a, h2 a, h3 a {{ display: none !important; }}
[data-testid="stAppViewContainer"] {{ background: var(--paper); }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.6rem; max-width: 47rem; }}

/* Set on containers and let it inherit -- deliberately NOT a universal `*` rule.
   Streamlit draws its chevrons and glyphs with a Material Symbols ligature font,
   and a `*` selector overrides that, so every icon renders as its own name in
   text ("keyboard_arrow_right"). Icon spans keep their own font-family here. */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {{
  font-family: 'Inter Tight', system-ui, -apple-system, sans-serif;
}}
[data-testid="stAppViewContainer"] button,
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] select,
[data-testid="stMarkdownContainer"] {{
  font-family: 'Inter Tight', system-ui, -apple-system, sans-serif;
}}

/* ---- Sidebar ---------------------------------------------------------- */
[data-testid="stSidebar"] {{
  background: var(--surface);
  border-right: 1px solid var(--rule);
}}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .6rem; }}

.wordmark {{
  display: flex; align-items: baseline; gap: .5rem;
  font-family: 'Spectral', Georgia, serif;
  font-size: 1.32rem; font-weight: 500; letter-spacing: -.015em;
  color: var(--ink); margin: .1rem 0 .1rem;
}}
.wordmark .mark {{
  width: .58rem; height: .58rem; border-radius: 50%;
  background: var(--teal); flex: none; transform: translateY(-.12rem);
}}
.wordmark-sub {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: .61rem; letter-spacing: .14em; text-transform: uppercase;
  color: var(--ink-40); margin: 0 0 1.1rem 1.08rem;
}}

.eyebrow {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: .6rem; letter-spacing: .15em; text-transform: uppercase;
  color: var(--ink-40); margin: 1.1rem 0 .45rem;
  display: flex; align-items: center; gap: .5rem;
}}
.eyebrow::after {{
  content: ""; flex: 1; height: 1px; background: var(--rule);
}}

.holder {{
  border: 1px solid var(--rule); border-left: 2px solid var(--teal);
  background: var(--paper); padding: .6rem .7rem; border-radius: 2px;
}}
.holder-name {{ font-weight: 600; font-size: .9rem; color: var(--ink); }}
.holder-policies {{
  font-family: 'IBM Plex Mono', monospace; font-size: .69rem;
  color: var(--ink-60); margin-top: .2rem; letter-spacing: .01em;
}}

.pill {{
  display: inline-flex; align-items: center; gap: .38rem;
  font-family: 'IBM Plex Mono', monospace; font-size: .66rem;
  letter-spacing: .04em; padding: .2rem .5rem; border-radius: 2px;
}}
.pill .dot {{ width: .42rem; height: .42rem; border-radius: 50%; }}
.pill.ok   {{ background: var(--moss-dim); color: var(--moss); }}
.pill.ok .dot   {{ background: var(--moss); }}
.pill.down {{ background: var(--seal-dim); color: var(--seal); }}
.pill.down .dot {{ background: var(--seal); }}

/* ---- Empty state ------------------------------------------------------ */
.lede {{
  font-family: 'Spectral', Georgia, serif;
  font-size: 2.15rem; line-height: 1.16; font-weight: 400;
  letter-spacing: -.02em; color: var(--ink); margin: .2rem 0 .5rem;
}}
.lede em {{ font-style: italic; color: var(--teal); }}
.lede-sub {{
  font-size: .93rem; color: var(--ink-60); line-height: 1.55;
  max-width: 32rem; margin-bottom: 1.9rem;
}}

/* Starter buttons, grouped by the three things this assistant can actually do. */
[data-testid="stMainBlockContainer"] .stButton > button {{
  width: 100%; text-align: left; justify-content: flex-start;
  background: var(--surface); border: 1px solid var(--rule);
  border-radius: 2px; color: var(--ink); font-size: .845rem;
  font-weight: 400; padding: .6rem .75rem; line-height: 1.35;
  transition: border-color .14s ease, background .14s ease, transform .14s ease;
}}
/* Streamlit centres the label inside the button; a list of questions scans far
   better flush left. */
[data-testid="stMainBlockContainer"] .stButton > button > div,
[data-testid="stMainBlockContainer"] .stButton > button p {{
  text-align: left; width: 100%;
}}
[data-testid="stMainBlockContainer"] .stButton > button:hover {{
  border-color: var(--teal); background: var(--teal-dim);
  transform: translateX(2px); color: var(--ink);
}}
[data-testid="stMainBlockContainer"] .stButton > button:focus-visible {{
  outline: 2px solid var(--teal); outline-offset: 2px;
}}

/* ---- Messages --------------------------------------------------------- */
[data-testid="stChatMessage"] {{
  background: transparent; padding: .1rem 0 1.15rem; gap: 0;
}}
[data-testid="stChatMessage"] p {{ font-size: .95rem; line-height: 1.62; }}
/* Stock avatars are icon bubbles and fight the typographic direction. Each turn
   is labelled in mono micro-caps instead -- the same voice as the clause refs.
   Prefix match: the testids are stChatMessageAvatarUser / ...Assistant. */
[data-testid^="stChatMessageAvatar"] {{ display: none !important; }}

.speaker {{
  font-family: 'IBM Plex Mono', monospace; font-size: .6rem;
  letter-spacing: .15em; text-transform: uppercase;
  color: var(--ink-40); margin-bottom: .35rem;
}}
.speaker.them {{ color: var(--teal); }}

/* ---- The signature: a clause pulled from the policy ------------------- */
.clause {{
  border-left: 2px solid var(--seal);
  background: var(--clause);
  padding: .62rem .85rem .68rem;
  margin: .1rem 0 .45rem;
  border-radius: 0 2px 2px 0;
}}
.clause-ref {{
  font-family: 'IBM Plex Mono', monospace; font-size: .585rem;
  letter-spacing: .13em; text-transform: uppercase;
  color: var(--seal); margin-bottom: .28rem;
}}
.clause-text {{
  font-family: 'Spectral', Georgia, serif; font-size: .935rem;
  line-height: 1.5; color: var(--ink); font-style: italic;
}}
.cited {{
  font-family: 'IBM Plex Mono', monospace; font-size: .6rem;
  letter-spacing: .13em; text-transform: uppercase; color: var(--ink-40);
  margin: .85rem 0 .4rem; display: flex; align-items: center; gap: .5rem;
}}
.cited::after {{ content: ""; flex: 1; height: 1px; background: var(--rule); }}

/* ---- Tool trace (diagnostic, stays quiet) ----------------------------- */
[data-testid="stExpander"] {{
  border: 1px solid var(--rule); border-radius: 2px;
  background: var(--surface); margin-top: .3rem;
}}
/* Target the label, not the summary, so the chevron keeps its icon font. */
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
[data-testid="stExpander"] summary p {{
  font-family: 'IBM Plex Mono', monospace !important; font-size: .655rem;
  letter-spacing: .1em; text-transform: uppercase; color: var(--ink-60);
}}
[data-testid="stExpander"] summary:hover {{ color: var(--teal); }}
.trace-row {{
  font-family: 'IBM Plex Mono', monospace; font-size: .72rem;
  color: var(--ink); padding: .2rem 0;
}}
.trace-args {{
  font-family: 'IBM Plex Mono', monospace; font-size: .69rem;
  color: var(--ink-60); word-break: break-word; padding-bottom: .35rem;
}}
/* Scoped `*` (no icons live in here) so paragraph breaks in the tool output
   don't pick up the body face and render at a different size. */
.trace-out, .trace-out * {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: .7rem; color: var(--ink-60); line-height: 1.55;
}}
.trace-out {{
  border-left: 1px solid var(--rule); padding: .05rem 0 .05rem .55rem;
  margin-bottom: .5rem; white-space: pre-wrap;
}}

/* ---- Notices ---------------------------------------------------------- */
.notice {{
  border: 1px solid var(--rule); border-left: 2px solid var(--amber);
  background: var(--amber-dim); padding: .6rem .8rem; border-radius: 0 2px 2px 0;
  font-size: .875rem; color: var(--ink); line-height: 1.5;
}}
.notice.seal {{ border-left-color: var(--seal); background: var(--seal-dim); }}

/* ---- Composer --------------------------------------------------------- */
[data-testid="stChatInput"] {{
  border: 1px solid var(--rule); border-radius: 2px; background: var(--surface);
}}
[data-testid="stChatInput"]:focus-within {{ border-color: var(--teal); }}
[data-testid="stBottomBlockContainer"] {{ background: var(--paper); }}

@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; }}
}}
</style>
"""
