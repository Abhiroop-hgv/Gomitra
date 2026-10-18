"""Assemble router/static/index.html from the original design file (CSS + embedded images) plus the new app code."""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1]
L = open(src, encoding="utf-8").read().split("\n")
assert L[97].strip() == "</style>" and L[102].startswith("const IMG ="), "design file layout changed"
css = open(os.path.join(here, "extra.css"), encoding="utf-8").read()
js = open(os.path.join(here, "strings.js"), encoding="utf-8").read() + "\n" + open(os.path.join(here, "app.js"), encoding="utf-8").read()
out = L[:97] + [css] + L[97:102] + [L[102], js, "</script>", "</body>", "</html>"]
os.makedirs(os.path.join(here, "..", "router", "static"), exist_ok=True)
open(os.path.join(here, "..", "router", "static", "index.html"), "w", encoding="utf-8").write("\n".join(out))
print("ok", sum(len(x) for x in out) // 1024, "KB")
