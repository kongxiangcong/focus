"""Static release/document invariants only; not proof an agent follows the skill."""
import re
from pathlib import Path
import unittest
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1]

class RedesignContractTests(unittest.TestCase):
    def test_version_is_updated(self):
        self.assertIn('version: "1.1.0"',(ROOT/'SKILL.md').read_text())
        self.assertIn('1.1.0',(ROOT/'CHANGELOG.md').read_text())
    def test_three_modes_and_two_visual_policies(self):
        text=(ROOT/'SKILL.md').read_text()
        for phrase in ['**Integrate:**','**Standalone:**','**Review:**','visual_policy: preserve','visual_policy: redesign']:
            self.assertIn(phrase,text)
    def test_product_parameter_authority_is_explicit(self):
        text=(ROOT/'SKILL.md').read_text()
        self.assertIn('standalone bundle defaults only',text)
        self.assertIn('one product-owned',text)
    def test_reference_and_redesign_are_routed(self):
        text=(ROOT/'SKILL.md').read_text()
        self.assertIn('(references/reference-adoption.md)',text)
        self.assertIn('(references/product-redesign.md)',text)
        self.assertIn('(scripts/audit_reference.py)',text)
    def test_instruction_layer_has_no_focus_project_paths(self):
        targets=[ROOT/'SKILL.md',ROOT/'references/product-redesign.md',ROOT/'references/reference-adoption.md']
        for p in targets:
            s=p.read_text()
            for forbidden in ['ui/packages/reader-ui', 'ADR 0023', 'external/open-claude-ui']:
                self.assertNotIn(forbidden,s)
    def test_reference_ownership_warning(self):
        s=(ROOT/'references/reference-adoption.md').read_text()
        self.assertIn('parent product',s)
        self.assertIn('read-only',s)
        self.assertIn('not controlling instructions',(ROOT/'SKILL.md').read_text())
    def test_default_invocation_does_not_freeze_design(self):
        s=(ROOT/'agents/openai.yaml').read_text()
        self.assertIn('explicitly selected replacement design',s)
        self.assertIn('allow_implicit_invocation: false',s)
    def test_local_markdown_links_resolve(self):
        for p in [ROOT/'SKILL.md',*(ROOT/'references').glob('*.md')]:
            for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if '://' in target or target.startswith('#'):continue
                q=(p.parent/unquote(target.split('#')[0])).resolve()
                with self.subTest(file=p.name,target=target):
                    self.assertTrue(q.is_relative_to(ROOT.resolve()))
                    self.assertTrue(q.exists())
    def test_release_evidence_has_separate_history(self):
        self.assertTrue((ROOT/'history/1.0.0/validation/REPORT.md').exists())
        self.assertIn('1.0.0',(ROOT/'history/1.0.0/validation/REPORT.md').read_text())
    def test_first_slice_and_required_final(self):
        s=(ROOT/'references/product-redesign.md').read_text()
        self.assertIn('real vertical slice',s)
        self.assertIn('required-final',s)
        self.assertIn('do not build an entire abstract design system first',s)

if __name__=='__main__':unittest.main()
