"""
Post-process Typora exported HTML.
  1. Restore footnote labels (Q1/Q2 instead of 1/2/3)
  2. Split footnotes into Notes + References sections
  3. Q&A question and answer on separate lines
  4. Footnote labels clickable (jump back to text)
  5. Fix overflow clipping on images

Usage: python fix-export.py input.html [output.html]
  If output.html is omitted, overwrites input.html in-place.
"""
import sys
import re


def fix_html(input_path, output_path=None):
    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # --- 1. Restore footnote labels from .md ---
    md_path = re.sub(r'\.html$', '.md', input_path)
    fn_map = {}
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            md = f.read()
        seen = []
        for m in re.finditer(r'\[\^(\w+)\]', md):
            if m.group(1) not in seen:
                seen.append(m.group(1))
        fn_map = {i + 1: label for i, label in enumerate(seen)}
    except FileNotFoundError:
        pass

    if fn_map:
        def fix_inline(m):
            n = int(m.group(1))
            return m.group(0).replace(f'>{n}</a>', f'>{fn_map.get(n, str(n))}</a>')
        html = re.sub(r"<sup class='md-footnote'><a[^>]*>(\d+)</a></sup>", fix_inline, html)

        def fix_count(m):
            n = int(m.group(1))
            return f"<span class='md-fn-count'>{fn_map.get(n, str(n))}</span>"
        html = re.sub(r"<span class='md-fn-count'>(\d+)</span>", fix_count, html)

    # --- 2. Split footnotes into Notes + References ---
    fn_match = re.search(r"<div class='footnotes-area'[^>]*>(.*?)</div>\s*</div>", html, re.DOTALL)
    if fn_match:
        lines = re.findall(r"<div class='footnote-line'>.*?</div>", fn_match.group(1), re.DOTALL)
        qa, refs = [], []
        for line in lines:
            # Make label a clickable link
            back = re.search(r"href='#(ref-footnote-\d+)'", line)
            count = re.search(r"<span class='md-fn-count'>(.*?)</span>", line)
            if count and back:
                label = count.group(1)
                line = line.replace(
                    f"<span class='md-fn-count'>{label}</span>",
                    f"<a class='md-fn-count' href='#{back.group(1)}'>{label}</a>"
                )
            is_qa = count and count.group(1).startswith('Q')
            if is_qa:
                line = re.sub(r'</strong><span>\s*', '</strong><br><span>', line, count=1)
                qa.append(line)
            else:
                refs.append(line)

        new_fn = "<div class='footnotes-area'>"
        if qa:
            new_fn += "\n<h3 class='fn-section-title'>Notes</h3>\n" + "\n".join(qa)
        if refs:
            new_fn += "\n<h3 class='fn-section-title'>References</h3>\n" + "\n".join(refs)
        new_fn += "\n</div></div>"
        html = html[:fn_match.start()] + new_fn + html[fn_match.end():]

    # --- 3. Inject minimal CSS ---
    css = """
<style id="style-fix">
a.md-fn-count { color: #333 !important; font-weight: bold !important; text-decoration: none !important; cursor: pointer; }
a.md-fn-count:hover { text-decoration: underline !important; }
.fn-section-title { font-size: 1.25em; margin-top: 1.5em; margin-bottom: 0.5em; padding-bottom: 0.2em; border-bottom: 2px solid #333; display: inline-block; color: #333; }
@media screen and (max-width: 820px) {
    html, body { font-size: 14px; }
    body, body.typora-export { padding: 0; }
    .typora-export-content { padding: 0; margin: 0; }
    #write { margin: 0; padding: 5px; width: 100%; box-sizing: border-box; }
    #write > blockquote { margin-left: 0; width: 100%; }
}
</style>
"""
    # Also directly fix inline styles that CSS can't override
    # Remove all width: 780px !important from #write rules
    html = re.sub(r'width:\s*780px\s*!important', 'width: min(780px, 100%) !important', html)
    # Remove !important from font-size so media query can override
    html = html.replace('font-size: 16px !important', 'font-size: 16px')
    # Fix padding: reduce to 2px
    html = html.replace('padding-left: 30px', 'padding-left: 2px')
    html = html.replace('padding-right: 30px', 'padding-right: 2px')
    html = html.replace('padding-left: 20px', 'padding-left: 2px')
    html = html.replace('padding-right: 20px', 'padding-right: 2px')
    html = html.replace('padding-left: 5px', 'padding-left: 2px')
    html = html.replace('padding-right: 5px', 'padding-right: 2px')
    html = re.sub(r'padding:\s*40px\s+\d+px\s*!important', 'padding: 20px 2px !important', html)
    # Fix body overflow
    html = html.replace('overflow-x: hidden', 'overflow-x: visible')
    html = html.replace('overflow-x: initial !important', 'overflow-x: visible !important')
    # Fix image/figure clipping
    html = re.sub(r'max-width:\s*calc\(100%\s*\+\s*16px\)', 'max-width: 100%', html)
    html = html.replace('</head>', css + '\n</head>')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Fixed: {output_path}")


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        fix_html(args[0], args[1] if len(args) > 1 else None)
    else:
        print("Usage: python fix-export.py input.html [output.html]")
