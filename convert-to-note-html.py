"""
Post-process Typora exported HTML.
  1. Restore footnote labels (Q1/Q2 instead of 1/2/3)
  2. Split footnotes into Notes + References sections
  3. Q&A question and answer on separate lines
  4. Footnote labels clickable (jump back to text)
  5. Hover/tap tooltip on footnote references
  6. If Typora exported empty footnotes, rebuild from .md source
  7. Fix overflow, width, padding, font-size conflicts
  8. Merge adjacent footnotes into [1, Q1] format

Usage: python convert-to-note-html.py input.html [output.html]
"""
import sys
import re
import os
import glob


def find_md(html_path):
    """Find the .md source file"""
    md_path = re.sub(r'\.html$', '.md', html_path)
    candidates = [md_path] + glob.glob(os.path.join(os.path.dirname(html_path), '*.md'))
    for c in candidates:
        try:
            with open(c, 'r', encoding='utf-8') as f:
                md = f.read()
            if '[^' in md:
                return md
        except (FileNotFoundError, PermissionError):
            continue
    return None


def parse_fn_defs(md):
    """Extract footnote definitions from markdown"""
    defs = {}
    for m in re.finditer(r'^\[\^(\w+)\]:\s*(.+?)(?=\n\[\^|\n\n|\Z)', md, re.MULTILINE | re.DOTALL):
        content = m.group(2).strip()
        content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
        content = re.sub(r'`([^`]+)`', r'<code>\1</code>', content)
        defs[m.group(1)] = content
    return defs


def parse_fn_refs_from_md(md):
    """Get footnote labels in order of appearance, excluding those inside backticks"""
    # Remove inline code and code blocks first
    clean = re.sub(r'```.*?```', '', md, flags=re.DOTALL)
    clean = re.sub(r'`[^`]+`', '', clean)
    seen = []
    for m in re.finditer(r'\[\^(\w+)\](?!:)', clean):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fix_html(input_path, output_path=None):
    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Clean up any previous convert runs (make idempotent)
    html = re.sub(r'<style id="style-fix">.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<script>\s*document\.addEventListener.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r' data-tooltip="[^"]*"', '', html)

    md = find_md(input_path)
    fn_defs = parse_fn_defs(md) if md else {}
    fn_refs = parse_fn_refs_from_md(md) if md else []
    fn_map = {i + 1: label for i, label in enumerate(fn_refs)}

    # --- 1. Restore footnote labels ---
    if fn_map:
        def fix_inline(m):
            n = int(m.group(1))
            return m.group(0).replace(f'>{n}</a>', f'>{fn_map.get(n, str(n))}</a>')
        html = re.sub(r"<sup class='md-footnote'><a[^>]*>(\d+)</a></sup>", fix_inline, html)

        def fix_count(m):
            n = int(m.group(1))
            return f"<span class='md-fn-count'>{fn_map.get(n, str(n))}</span>"
        html = re.sub(r"<span class='md-fn-count'>(\d+)</span>", fix_count, html)

    # --- 2. Build or rebuild footnotes section ---
    # Find footnotes-area: match from opening tag to the closing </div> that's followed by </div></div> (outer wrappers)
    fn_match = re.search(r"(<div class='footnotes-area'[^>]*>)(.*?)(</div>\s*</div>\s*</div>\s*</body>)", html, re.DOTALL)
    # Always rebuild footnotes from .md source for consistency
    qa, refs = [], []
    if fn_defs and fn_refs:
        for i, label in enumerate(fn_refs):
            content = fn_defs.get(label, '')
            if not content:
                continue
            ref_anchor = f"ref-footnote-{i+1}"
            dfref_anchor = f"dfref-footnote-{i+1}"
            line = f"<div class='footnote-line' id='{dfref_anchor}'><a class='md-fn-count' href='#{ref_anchor}'>{label}</a> {content}</div>"
            if not label.isdigit():
                line = re.sub(r'</strong>\s*', '</strong><br>', line, count=1)
                qa.append(line)
            else:
                refs.append(line)

    if qa or refs:
        new_fn = "<div class='footnotes-area'>"
        if qa:
            new_fn += "\n<h3 class='fn-section-title'>Notes</h3>\n" + "\n".join(qa)
        if refs:
            new_fn += "\n<h3 class='fn-section-title'>References</h3>\n" + "\n".join(refs)
        new_fn += "\n</div>"
        if fn_match:
            # Replace footnotes-area but keep the outer wrapper divs + </body>
            html = html[:fn_match.start()] + new_fn + fn_match.group(3) + html[fn_match.end():]
        else:
            html = html.replace('</div></div>\n</body>', new_fn + '</div></div>\n</body>')

    # --- 3. Merge adjacent footnotes into [1, Q1] format ---
    html, back_map = _merge_fn_groups(html)

    # Fix footnote-line back-links: all in same group should jump to shared anchor
    for dfref_id, shared_anchor in back_map.items():
        html = html.replace(
            f"<a class='md-fn-count' href='#{shared_anchor}'>",
            f"<a class='md-fn-count' href='#{shared_anchor}'>"
        )  # already correct if using ref-footnote-N
        # The footnote-line href should point to the shared anchor
        html = re.sub(
            rf"(<div class='footnote-line' id='{dfref_id}'><a class='md-fn-count') href='#[^']*'",
            rf"\1 href='#{shared_anchor}'",
            html
        )

    # --- 4. Add hover/tap tooltips ---
    if fn_defs:
        html = _add_tooltips(html, fn_defs)

    # --- 5. Inject CSS + JS ---
    html = html.replace('</head>', _get_css_js() + '\n</head>')

    # --- 6. Remove CSS ::before/::after brackets (script adds them in HTML) ---
    html = re.sub(r"sup\.md-footnote::before\s*\{[^}]*\}", '', html)
    html = re.sub(r"sup\.md-footnote::after\s*\{[^}]*\}", '', html)

    # Remove empty paragraphs before footnotes-area
    html = re.sub(r'(<p>\s*&nbsp;\s*</p>\s*)+(<div class=\'footnotes-area\'>)', r'\2', html)

    # --- 7. Fix Typora base CSS conflicts ---
    html = re.sub(r'width:\s*780px\s*!important', 'width: min(780px, 100%) !important', html)
    html = html.replace('font-size: 16px !important', 'font-size: 16px')
    html = html.replace('padding-left: 30px', 'padding-left: 2px')
    html = html.replace('padding-right: 30px', 'padding-right: 2px')
    html = html.replace('padding-left: 20px', 'padding-left: 2px')
    html = html.replace('padding-right: 20px', 'padding-right: 2px')
    html = html.replace('padding-left: 5px', 'padding-left: 2px')
    html = html.replace('padding-right: 5px', 'padding-right: 2px')
    html = re.sub(r'padding:\s*40px\s+\d+px\s*!important', 'padding: 20px 2px !important', html)
    html = html.replace('overflow-x: hidden', 'overflow-x: visible')
    html = html.replace('overflow-x: initial !important', 'overflow-x: visible !important')
    html = re.sub(r'max-width:\s*calc\(100%\s*\+\s*16px\)', 'max-width: 100%', html)
    # Fix white-space: pre-wrap causing extra spaces
    html = html.replace('.typora-export .footnote-line, .typora-export li, .typora-export p { white-space: pre-wrap; }',
                         '.typora-export .footnote-line, .typora-export li, .typora-export p { white-space: normal; }')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Fixed: {output_path}")


def _split_fn_lines(lines):
    """Split footnote lines into Q&A and References"""
    qa, refs = [], []
    for line in lines:
        back = re.search(r"href='#(ref-footnote-\d+)'", line)
        count = re.search(r"<span class='md-fn-count'>(.*?)</span>", line)
        if count and back:
            label = count.group(1)
            line = line.replace(
                f"<span class='md-fn-count'>{label}</span>",
                f"<a class='md-fn-count' href='#{back.group(1)}'>{label}</a>"
            )
        label_text = count.group(1) if count else ''
        if count and not label_text.isdigit():
            line = re.sub(r'</strong><span>\s*', '</strong><br><span>', line, count=1)
            qa.append(line)
        else:
            refs.append(line)
    return qa, refs


def _merge_fn_groups(html):
    """Merge adjacent <sup class='md-footnote'> into [1, Q1] with individual clickable links.
    Returns (html, back_anchor_map) where back_anchor_map = {dfref-footnote-N: shared-anchor-id}
    so all footnote-lines in a group can jump back to the same place."""
    pattern = r"<sup class='md-footnote'><a([^>]*)>(.*?)</a></sup>"
    sups = list(re.finditer(pattern, html))
    back_map = {}  # {dfref-id: shared-anchor-id}

    if not sups:
        return html, back_map

    groups = []
    current = [sups[0]]
    for i in range(1, len(sups)):
        between = html[sups[i-1].end():sups[i].start()]
        if between.strip() == '':
            current.append(sups[i])
        else:
            groups.append(current)
            current = [sups[i]]
    groups.append(current)

    for group in reversed(groups):
        # Use first sup's name as the shared back-anchor
        first_attrs = group[0].group(1)
        name_match = re.search(r"name='([^']*)'", first_attrs)
        shared_name = name_match.group(1) if name_match else ''

        links = []
        for sup in group:
            attrs = sup.group(1)
            label = sup.group(2).strip('[]')
            href_match = re.search(r"href='([^']*)'", attrs)
            href = href_match.group(1) if href_match else ''
            links.append(f"<a href='{href}' class='fn-ref'>{label}</a>")
            # Map this footnote's dfref to the shared anchor
            if href:
                dfref_id = href.replace('#', '')
                back_map[dfref_id] = shared_name

        inner = ', '.join(links)
        merged = f"<sup class='md-footnote'><span id='{shared_name}'></span>[{inner}]</sup>"
        html = html[:group[0].start()] + merged + html[group[-1].end():]
    return html, back_map


def _add_tooltips(html, fn_defs):
    """Add data-tooltip to each fn-ref link"""
    def add_tip(m):
        full = m.group(0)
        if 'data-tooltip' in full:
            return full
        label = m.group(1)
        if label in fn_defs:
            clean = re.sub(r'<[^>]+>', '', fn_defs[label])
            tooltip = clean.replace('"', '&quot;').replace("'", '&#39;')
            return full.replace("<a ", f'<a data-tooltip="{tooltip}" ', 1)
        return full
    return re.sub(r"<a href='[^']*' class='fn-ref'>(\w+)</a>", add_tip, html)


def _get_css_js():
    return """
<style id="style-fix">
a.md-fn-count { color: #333 !important; font-weight: bold !important; text-decoration: none !important; cursor: pointer; }
a.md-fn-count:hover { text-decoration: none !important; }
a.fn-ref { color: #333; font-weight: bold; text-decoration: none; cursor: pointer; }
a.fn-ref:hover { text-decoration: none; }
.fn-section-title { font-size: 1.25em; margin-top: 0.8em; margin-bottom: 0.3em; padding-bottom: 0.2em; border-bottom: 2px solid #333; display: inline-block; color: #333; }
.footnote-line { margin-bottom: 0.8em; font-size: 0.88em; line-height: 1.6; color: #555; }
.footnotes-area { padding-bottom: 0; margin-bottom: 0; margin-top: 1em; }
#write { padding-bottom: 10px !important; }
#fn-tip {
    display: none; position: fixed; z-index: 10000;
    background: #333; color: #fff; padding: 8px 12px; border-radius: 4px;
    font-size: 13px; line-height: 1.6; white-space: normal;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    max-width: min(600px, calc(100vw - 20px));
    width: max-content;
    pointer-events: none;
}
@media screen and (max-width: 820px) {
    html, body { font-size: 14px; }
    body, body.typora-export { padding: 0; }
    .typora-export-content { padding: 0; margin: 0; }
    #write { margin: 0; padding: 5px; width: 100%; box-sizing: border-box; }
    #write > blockquote { margin-left: 0; width: 100%; }
}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {
    var tip = document.createElement('div');
    tip.id = 'fn-tip';
    document.body.appendChild(tip);

    function show(a) {
        var text = a.getAttribute('data-tooltip');
        if (!text) return;
        var wr = document.getElementById('write');
        var wb = wr ? wr.getBoundingClientRect() : {left:0, right:window.innerWidth};
        tip.style.maxWidth = (wb.right - wb.left - 20) + 'px';
        tip.innerHTML = text;
        tip.style.display = 'block';
        var r = a.getBoundingClientRect();
        var tw = tip.offsetWidth, th = tip.offsetHeight;
        var left = r.left + r.width/2 - tw/2;
        if (left < wb.left) left = wb.left;
        if (left + tw > wb.right) left = wb.right - tw;
        var top = r.top - th - 8;
        if (top < 10) top = r.bottom + 8;
        tip.style.left = left + 'px';
        tip.style.top = top + 'px';
    }
    function hide() { tip.style.display = 'none'; }

    // Desktop: hover = tooltip, click = jump to footnote
    // Mobile: tap = tooltip, long press = jump
    if ('ontouchstart' in window) {
        var active = null, longTimer = null;
        document.addEventListener('touchstart', function(e) {
            var a = e.target.closest('a.fn-ref');
            if (a) {
                longTimer = setTimeout(function() {
                    var href = a.getAttribute('href');
                    if (href) window.location.hash = href.replace('#','');
                    longTimer = null;
                }, 500);
            }
        });
        document.addEventListener('touchend', function(e) {
            if (longTimer) {
                clearTimeout(longTimer);
                longTimer = null;
                var a = e.target.closest('a.fn-ref');
                if (a && a.getAttribute('data-tooltip')) {
                    e.preventDefault();
                    if (active === a) { hide(); active = null; }
                    else { show(a); active = a; }
                } else { hide(); active = null; }
            }
        });
        document.addEventListener('touchmove', function() {
            if (longTimer) { clearTimeout(longTimer); longTimer = null; }
        });
    } else {
        document.querySelectorAll('a.fn-ref').forEach(function(a) {
            a.addEventListener('mouseenter', function() { show(a); });
            a.addEventListener('mouseleave', hide);
            a.addEventListener('click', function(e) {
                e.preventDefault();
                hide();
                var href = a.getAttribute('href');
                if (href) window.location.hash = href.replace('#','');
            });
        });
    }
});
</script>
"""


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        fix_html(args[0], args[1] if len(args) > 1 else None)
    else:
        print("Usage: python convert-to-note-html.py input.html [output.html]")
