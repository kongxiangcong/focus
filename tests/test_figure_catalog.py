import tempfile
import unittest
from pathlib import Path
from host.core_bridge import CoreBridge
from host.figure_catalog import source_figures


class FigureCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.temp.name) / 'sources/demo-paper/parser-bundle'
        self.bundle.mkdir(parents=True)
        (self.bundle/'images').mkdir()
        for name in ('one.png', 'two.png', 'table.png', 'equation.png', 'literal.png', 'a b.png'):
            (self.bundle/'images'/name).write_bytes(b'fixture')

    def tearDown(self):
        self.temp.cleanup()

    def test_orders_markdown_and_html_including_unread_and_multiline_captions(self):
        markdown = '![one](images/one.png)\n\nFigure 1. Complete caption\ncontinued second line.\n\n<figure><img src="images/two.png"><figcaption>Figure 2. HTML caption.</figcaption></figure>\n\n![same](./images/one.png)'
        figures = list(source_figures(self.bundle, markdown))
        self.assertEqual([Path(f['path']).name for f in figures], ['one.png', 'two.png'])
        self.assertEqual(figures[0]['caption'], 'Figure 1. Complete caption\ncontinued second line.')
        self.assertEqual(figures[1]['caption'], 'Figure 2. HTML caption.')

    def test_omits_tables_formulas_code_external_and_unsafe_paths(self):
        markdown = '<table><tr><td><img src="images/table.png"></td></tr></table>\n\n<img class="equation" src="images/equation.png">\n\n| Table |\n| --- |\n| ![tab](images/table.png) |\n\n```html\n<img src="images/literal.png">\n```\n\n![bad](../../secret.png)\n![external](https://example.org/one.png)\n![ok](images/a%20b.png)'
        self.assertEqual([Path(f['path']).name for f in source_figures(self.bundle, markdown)], ['a b.png'])

    def test_bridge_cache_tracks_content_and_preserves_bundle_bytes(self):
        content = self.bundle/'content.md'
        content.write_text('![one](images/one.png)\nFigure 1. First')
        bridge = CoreBridge(Path(self.temp.name))
        before = {str(p):p.read_bytes() for p in self.bundle.rglob('*') if p.is_file()}
        self.assertEqual(bridge.figure_catalog('demo-paper')[0]['src'], '/reader/assets/demo-paper/images/one.png')
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.bundle.rglob('*') if p.is_file()})
        content.write_text('<figure><img src="images/two.png"><figcaption>Figure 2. New</figcaption></figure>')
        self.assertEqual(bridge.figure_catalog('demo-paper')[0]['caption'], 'Figure 2. New')

    def test_rasterized_tables_and_equations_are_not_gallery_figures(self):
        markdown = '![data](images/table.png)\nTable 2. Raster table.\n\n![Equation 1](images/equation.png)'
        self.assertEqual(list(source_figures(self.bundle, markdown)), [])


if __name__ == '__main__':
    unittest.main()
