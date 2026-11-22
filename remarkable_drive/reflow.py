"""arXiv's HTML rendering → a PDF sized for the reMarkable.

A4 two-column papers shrink to ~6.5pt text on the tablet, so for arXiv papers we
print arXiv's own HTML (LaTeXML output) in headless Chromium instead: a 157×210mm
page at 11pt with a wider left margin, because the tablet's menu covers the left
edge. The result has a real text layer, which the annotation pipeline needs.

LaTeXML quirks the page script works around:

- **tcolorbox prompt boxes** arrive as an SVG whose ``foreignObject`` holds a
  fixed-width minipage; the SVG clips whatever is past its edge. They are pulled
  out into a plain bordered ``div`` so the text wraps. Real diagrams are left alone.
- **Listings** are a span per token with fixed white-space rules; each becomes a
  ``<pre>`` of its text.
- **Wide tables** first get wrapping cells, then are zoomed down until they fit.
  Wide equations are zoomed too.

Needs Chromium for Playwright on the server (the same install mermaid uses):

    uv run playwright install chromium-headless-shell
"""

from typing import Optional

from playwright.sync_api import sync_playwright

from util.logging_util import setup_logger

logger = setup_logger(__name__)

PAGE_MM = (157, 210)        # the reMarkable 2's screen, portrait
MARGIN_MM = (8, 7, 8, 14)   # top, right, bottom, left
FONT_PT = 11
TIMEOUT_MS = 120_000
# Print area width in CSS px (96/in): lay the page out at the width it will print at.
VIEWPORT_PX = round((PAGE_MM[0] - MARGIN_MM[1] - MARGIN_MM[3]) / 25.4 * 96)

CSS = """
@page { size: %(w)smm %(h)smm; margin: %(mt)smm %(mr)smm %(mb)smm %(ml)smm; }
header, nav, footer, .ltx_page_header, .ltx_page_footer, #header, .arxiv-watermark,
#license-tr, .ltx_role_affiliation, .package-alerts, button, .ar5iv-footer,
.ltx_TOC, #openForm, .html-header-message { display: none !important; }
html, body { background: white !important; }
/* arXiv sizes the article in rem, so the base size has to live on <html>. */
html { font-size: %(pt)spt !important; }
body, .ltx_page_main, .ltx_page_content, .ltx_document {
  max-width: none !important; margin: 0 !important; padding: 0 !important; width: auto !important; }
body { font-family: "Charter", "Georgia", serif !important; font-size: 1rem !important;
       line-height: 1.35 !important; color: black !important; }
.ltx_para, p { text-align: left; hyphens: auto; }
.ltx_title_document { font-size: 1.5em !important; }
.ltx_figure img, .ltx_figure svg, img.ltx_graphics {
  max-width: 100%% !important; height: auto !important; }
figure, .ltx_figure, .ltx_table, .ltx_equation, .ltx_equationgroup, table {
  break-inside: avoid; }
.ltx_tabular { font-size: 0.85em !important; }
.ltx_tabular td, .ltx_tabular th, .ltx_tabular span[style*="font-size"] { font-size: inherit !important; }
/* LaTeX parboxes come through as fixed pt widths that can exceed the page. */
.ltx_tabular [style*="width"] { width: auto !important; max-width: 100%%; }
h1, h2, h3, h4, h5, h6, .ltx_title { break-after: avoid; }
/* arXiv stacks a 24px para margin on a 16px <p> margin. */
.ltx_para { margin: 0 0 0.6em 0 !important; }
.ltx_para > p, .ltx_p { margin: 0 !important; }
/* Lists: a hanging bullet instead of text sliding left. */
.ltx_itemize, .ltx_enumerate { padding-left: 0 !important; margin: 0 0 0.6em 0 !important; }
.ltx_item { display: block !important; position: relative; padding-left: 1.2em !important; margin: 0 0 0.3em 0 !important; }
.ltx_item > .ltx_tag_item, .ltx_item > .ltx_tag_enumerate { position: absolute; left: 0; }
/* Listings, rebuilt as <pre class="lst"> by the page script. */
pre.lst { white-space: pre-wrap; overflow-wrap: break-word; font-size: 0.8rem; line-height: 1.3;
  margin: 0; font-family: "DejaVu Sans Mono", monospace; }
/* A prompt box can run for pages; let it (and its float) split rather than jump whole. */
.unboxed, figure:has(.unboxed), .ltx_float:has(.unboxed) { break-inside: auto !important; }
.ltx_listing_data { display: none !important; }
.unboxed { border: 1px solid #888; padding: 0.4em 0.6em; margin: 0 0 0.8em 0; }
.unboxed .ltx_foreignobject_container, .unboxed .ltx_foreignobject_content, .unboxed .ltx_minipage {
  display: block !important; width: auto !important; height: auto !important; }
/* Print stylesheets append (href) after links. */
a::after { content: none !important; }
/* References: plain stacked entries rather than a two-column grid. */
.ltx_biblist { display: block !important; padding: 0 !important; }
.ltx_bibitem { display: block !important; margin: 0 0 0.5em 0 !important; font-size: 0.9em; }
.ltx_bibitem > .ltx_tag_bibitem { display: inline !important; font-weight: bold; margin-right: 0.4em; }
.ltx_bibitem > .ltx_bibblock { display: inline !important; }
table { max-width: 100%% !important; }
math[display=block], .ltx_equation { max-width: 100%%; overflow: hidden; }
""" % dict(w=PAGE_MM[0], h=PAGE_MM[1], mt=MARGIN_MM[0], mr=MARGIN_MM[1], mb=MARGIN_MM[2],
           ml=MARGIN_MM[3], pt=FONT_PT)

FIX_LAYOUT = """() => {
  const w = document.body.clientWidth;
  for (const svg of document.querySelectorAll('svg')) {
    const fos = [...svg.querySelectorAll('foreignObject')];
    if (!fos.some(fo => fo.querySelector('.ltx_listing, .ltx_minipage'))) continue;
    const box = document.createElement('div');
    box.className = 'unboxed';
    for (const fo of fos) for (const c of [...fo.childNodes]) box.appendChild(c);
    const holder = svg.parentElement;
    svg.replaceWith(box);
    // The wrapper is an inline-block that would grow to the longest unwrapped line.
    if (holder && holder.classList.contains('ltx_inline-block')) {
      holder.style.display = 'block'; holder.style.width = 'auto';
    }
  }
  for (const lst of document.querySelectorAll('.ltx_listing')) {
    const lines = [...lst.querySelectorAll('.ltx_listingline')].map(l => l.textContent);
    if (!lines.length) continue;
    const pre = document.createElement('pre');
    pre.className = 'lst';
    pre.textContent = lines.join('\\n');
    lst.replaceWith(pre);
  }
  for (const el of document.querySelectorAll('.unboxed [style*="width"]')) {
    el.style.width = 'auto'; el.style.maxWidth = '100%';
  }
  const top = [...document.querySelectorAll('.ltx_tabular')]
    .filter(t => !t.parentElement.closest('.ltx_tabular'));
  for (const el of top) {
    if (el.getBoundingClientRect().width > w) {
      for (const c of el.querySelectorAll('td, th')) c.style.whiteSpace = 'normal';
    }
  }
  const wide = [...document.querySelectorAll('table.ltx_equation, table.ltx_equationgroup')].concat(top);
  for (const el of wide) {
    el.style.maxWidth = 'none';  // measure at natural width, not squeezed by max-width
    const natural = Math.max(el.scrollWidth, el.getBoundingClientRect().width);
    if (natural > w) el.style.zoom = (w / natural) * 0.99;
    // Zoom re-lays the table out (text reflows), so check and tighten.
    for (let i = 0; i < 4; i++) {
      const now = el.getBoundingClientRect().width;
      if (now <= w) break;
      el.style.zoom = parseFloat(el.style.zoom || 1) * (w / now) * 0.99;
    }
  }
}"""


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{arxiv_id}"


def render(url: str) -> Optional[bytes]:
    """The LaTeXML page at ``url`` as a tablet-sized PDF.

    None when there is no such page (a 4xx, or a page that isn't LaTeXML output:
    arXiv has no HTML for papers whose source didn't convert). Timeouts and browser
    failures raise.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": VIEWPORT_PX, "height": 800})
            page.set_default_timeout(TIMEOUT_MS)
            response = page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
            if response is not None and response.status >= 400:
                logger.info("no HTML at %s (%s)", url, response.status)
                return None
            if page.locator(".ltx_document").count() == 0:
                logger.info("%s isn't a LaTeXML document", url)
                return None
            page.emulate_media(media="print")
            page.add_style_tag(content=CSS)
            page.evaluate(FIX_LAYOUT)
            return page.pdf(prefer_css_page_size=True, print_background=False)
        finally:
            browser.close()
