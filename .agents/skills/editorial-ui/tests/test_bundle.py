"""Unit regressions for deterministic assets and conservative offline checks."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from build_starters import outputs
from check_offline import inspect_text
from validate_skill import contrast, validate

class BundleTests(unittest.TestCase):
    def test_generated_assets_match(self):
        for path, content in outputs().items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_text(encoding='utf-8'), content)

    def test_generation_is_deterministic(self):
        self.assertEqual(outputs(), outputs())

    def test_bundle_profile(self):
        errors, ratios = validate()
        self.assertEqual(errors, [])
        self.assertEqual(len(ratios), 22)

    def test_contrast_reference_black_white(self):
        self.assertAlmostEqual(contrast('#000000','#ffffff'),21.0)

    def test_contrast_same_color(self):
        self.assertAlmostEqual(contrast('#ababab','#ababab'),1.0)

    def test_invalid_contrast_color(self):
        with self.assertRaises(ValueError):
            contrast('red','#ffffff')

    def test_each_starter_is_offline_preflight_clean(self):
        for path in (ROOT/'assets/starters').glob('*.html'):
            with self.subTest(path=path.name):
                self.assertEqual(inspect_text(path.read_text(encoding='utf-8')).findings, [])

class OfflineTests(unittest.TestCase):
    pass

CASES = {
 'inline_plain': ('<style>body{color:#333}</style><p>正文</p><script>let a=1;</script>',False),
 'cdn_script': ('<script src="https://example.com/a.js"></script>',True),
 'relative_script': ('<script src="./a.js"></script>',True),
 'protocol_relative': ('<img src="//example.com/a.png">',True),
 'local_image': ('<img src="a.png">',True),
 'inline_image': ('<img src="data:image/png;base64,abcd">',False),
 'inline_svg_reference': ('<svg><use href="#symbol"></use></svg>',False),
 'external_svg_reference': ('<svg><use href="icons.svg#symbol"></use></svg>',True),
 'stylesheet_link': ('<link rel="stylesheet" href="theme.css">',True),
 'preconnect': ('<link rel="preconnect" href="https://fonts.example">',True),
 'css_url': ('<style>.a{background:url(https://example.com/a.png)}</style>',True),
 'css_inline_url': ('<style>.a{background:url(data:image/png;base64,abcd)}</style>',False),
 'css_quoted_import': ('<style>@import "theme.css";</style>',True),
 'css_url_import': ('<style>@import url("theme.css");</style>',True),
 'font_binary': ('<style>@font-face{font-family:x;src:url(data:font/woff;base64,abcd)}</style>',True),
 'fetch_computed': ('<script>fetch(base + suffix);</script>',True),
 'websocket': ('<script>new WebSocket(endpoint);</script>',True),
 'sendbeacon': ('<script>navigator.sendBeacon(url,data);</script>',True),
 'dynamic_import': ('<script>import("./x.js");</script>',True),
 'static_import': ('<script type="module">import x from "./x.js";</script>',True),
 'worker': ('<script>new Worker("x.js");</script>',True),
 'serviceworker': ('<script>navigator.serviceWorker.register("x.js");</script>',True),
 'eval_review': ('<script>eval(code);</script>',True),
 'base_url': ('<base href="https://example.com">',True),
 'refresh': ('<meta http-equiv="refresh" content="1;url=https://example.com">',True),
 'form_action': ('<form action="https://example.com/send"></form>',True),
 'form_no_action': ('<form id="local"></form>',False),
 'user_link': ('<a href="https://example.com">Source</a>',False),
 'javascript_link': ('<a href="javascript:alert(1)">bad</a>',True),
 'ping_link': ('<a href="#x" ping="https://example.com">ping</a>',True),
 'srcset_review': ('<img srcset="a.png 1x, b.png 2x">',True),
 'srcdoc_recursion': ('<iframe srcdoc="&lt;img src=&quot;https://example.com/x&quot;&gt;"></iframe>',True),
 'json_not_code': ('<script type="application/json">{"text":"fetch(a)"}</script>',False),
 'inline_handler': ('<button onclick="fetch(url)">run</button>',True),
 'inline_style': ('<div style="background:url(a.png)"></div>',True),
 'dynamic_src': ('<script>img.src="https://example.com/x";</script>',True),
 'attribute_src': ('<script>img.setAttribute("src", base);</script>',True),
}
for name, (html, should_flag) in CASES.items():
    def test(self, source=html, expected=should_flag):
        self.assertEqual(bool(inspect_text(source).findings), expected)
    setattr(OfflineTests, 'test_'+name, test)

if __name__ == '__main__':
    unittest.main()
