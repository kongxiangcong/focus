"""Execution structure and link integrity, independent of editorial phrasing."""
import re
import sys
import tempfile
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from validate_skill import markdown_link_errors

class WorkflowTests(unittest.TestCase):
    def test_six_ordered_workflow_steps(self):
        text = (ROOT/'SKILL.md').read_text()
        self.assertEqual(re.findall(r'^### (\d+)\.', text, re.M), list('123456'))
        steps = re.split(r'^### \d+\.', text, flags=re.M)[1:]
        self.assertTrue(all('**Done:**' in step for step in steps))

    def test_mode_routes_are_explicit(self):
        text = (ROOT/'SKILL.md').read_text()
        rows = [line.split('|')[1].strip() for line in text.split('## Workflow', 1)[0].splitlines() if line.startswith('|')]
        for mode in ('Review', 'Standalone', 'Integrate + preserve', 'Integrate + redesign'):
            self.assertEqual(rows.count(mode), 1)

    def test_reference_table_has_conditions_and_existing_targets(self):
        text = (ROOT/'SKILL.md').read_text()
        table = text.split('## Rules to consult during implementation', 1)[1]
        rows = [line for line in table.splitlines() if line.startswith('|') and '](' in line]
        self.assertGreaterEqual(len(rows), 8)
        for row in rows:
            cells = row.split('|')[1:-1]
            self.assertEqual(len(cells), 3)
            self.assertTrue(all(cell.strip() for cell in cells))

    def test_brief_is_shared_by_workflow_redesign_and_delivery(self):
        for file in ['SKILL.md', 'references/product-redesign.md', 'references/delivery-template.md']:
            self.assertIn('brief-schema.md)', (ROOT/file).read_text())

    def test_local_links_and_anchors_resolve(self):
        self.assertEqual(markdown_link_errors(ROOT), [])

    def test_link_checker_catches_missing_target_anchor_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'a.md').write_text('[valid](b.md#good-heading) [missing](no.md) [bad anchor](b.md#bad) [escape](../outside.md)')
            (root/'b.md').write_text('# Good heading\n')
            errors = markdown_link_errors(root)
            self.assertEqual(len(errors), 3)
            self.assertTrue(any('missing anchor' in e for e in errors))
            (root/'a.md').write_text('[valid](b.md#good-heading)')
            self.assertEqual(markdown_link_errors(root), [])

    def test_execution_entry_excludes_release_work(self):
        text = (ROOT/'SKILL.md').read_text()
        self.assertIn('(MAINTAINING.md)', text)
        for path in ['validation', 'history', 'SHA256SUMS.txt', 'README.md']:
            self.assertFalse((ROOT/path).exists())
        for script in ['build_starters.py', 'browser_smoke.py', 'validate_skill.py']:
            self.assertNotIn(script, text)
        for path in ['maintenance/provenance.md', 'maintenance/evaluation-tasks.md']:
            self.assertTrue((ROOT/path).is_file())

if __name__ == '__main__':
    unittest.main()
