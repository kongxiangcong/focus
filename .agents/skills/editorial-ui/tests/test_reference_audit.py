"""Deterministic metadata/snapshot checks, not actual-agent generation evaluations."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_reference import collect, inspect_file, MAX_BYTES


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'reference'
        self.root.mkdir()
        (self.root/'README.md').write_text('reference\n', encoding='utf-8')
    def tearDown(self):
        self.temp.cleanup()
    def test_hash_is_exact(self):
        item = inspect_file(self.root, 'README.md')
        self.assertEqual(item['sha256'], hashlib.sha256(b'reference\n').hexdigest())
        self.assertEqual(item['bytes'], 10)
    def test_missing_declared_file_fails(self):
        self.assertEqual(collect(self.root, ['missing.md'])['status'], 'FAIL')
    def test_missing_directory_fails(self):
        self.assertEqual(collect(self.root/'missing', ['README.md'])['status'], 'FAIL')
    def test_relative_escape_rejected(self):
        self.assertEqual(inspect_file(self.root, '../README.md')['status'], 'FAIL')
    def test_absolute_path_rejected(self):
        self.assertEqual(inspect_file(self.root, str(self.root/'README.md'))['status'], 'FAIL')
    def test_windows_path_rejected(self):
        self.assertEqual(inspect_file(self.root, 'C:\\private\\file.md')['status'], 'FAIL')
    def test_external_symlink_rejected(self):
        outside = self.root.parent/'outside.md'; outside.write_text('outside')
        (self.root/'alias.md').symlink_to(outside)
        self.assertEqual(inspect_file(self.root, 'alias.md')['status'], 'FAIL')
    def test_internal_symlink_can_be_hashed(self):
        (self.root/'alias.md').symlink_to(self.root/'README.md')
        self.assertEqual(inspect_file(self.root, 'alias.md')['sha256'], inspect_file(self.root, 'README.md')['sha256'])
    def test_directory_is_not_file(self):
        (self.root/'dir.md').mkdir()
        self.assertEqual(inspect_file(self.root, 'dir.md')['status'], 'FAIL')
    def test_font_binary_rejected(self):
        (self.root/'font.ttf').write_bytes(b'font')
        self.assertEqual(inspect_file(self.root, 'font.ttf')['status'], 'FAIL')
    def test_environment_file_rejected(self):
        (self.root/'.env.txt').write_text('not for audit')
        self.assertEqual(inspect_file(self.root, '.env.txt')['status'], 'FAIL')
    def test_binary_disguised_as_text_rejected(self):
        (self.root/'bad.md').write_bytes(b'hello\0world')
        self.assertEqual(inspect_file(self.root, 'bad.md')['status'], 'FAIL')
    def test_large_file_rejected(self):
        with (self.root/'large.md').open('wb') as out: out.truncate(MAX_BYTES+1)
        self.assertEqual(inspect_file(self.root, 'large.md')['status'], 'FAIL')
    def test_dirty_content_changes_hash(self):
        before = inspect_file(self.root, 'README.md')['sha256']
        (self.root/'README.md').write_text('different')
        self.assertNotEqual(before, inspect_file(self.root, 'README.md')['sha256'])
    def test_declared_files_only(self):
        (self.root/'not-used.md').write_text('not requested')
        r=collect(self.root, ['README.md', 'README.md'])
        self.assertEqual([f['path'] for f in r['files']], ['README.md'])
    def test_collection_does_not_write_files(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        collect(self.root, ['README.md'])
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
    def test_cli_json_and_exit(self):
        cmd = [sys.executable, str(ROOT/'scripts/audit_reference.py'), '--reference', str(self.root), '--files', 'README.md']
        ok = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertTrue(json.loads(ok.stdout)['read_only'])
        bad = subprocess.run(cmd[:-1]+['unknown.md'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)['status'], 'FAIL')


@unittest.skipUnless(shutil.which('git'), 'Git unavailable')
class GitIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.parent=Path(self.temp.name)/'product';self.parent.mkdir()
    def tearDown(self):self.temp.cleanup()
    def git(self, root, *args):
        p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,check=True)
        return p.stdout.strip()
    def init(self, root):
        self.git(root,'init','-q');self.git(root,'config','user.name','Test')
        self.git(root,'config','user.email','test@example.invalid')
    def commit(self, root):
        self.git(root,'add','README.md');self.git(root,'-c','commit.gpgsign=false','commit','-qm','fixture')
    def test_parent_git_head_is_not_reference_head(self):
        self.init(self.parent)
        (self.parent/'README.md').write_text('product');self.commit(self.parent)
        reference=self.parent/'external/ref';reference.mkdir(parents=True)
        (reference/'README.md').write_text('reference')
        vcs=collect(reference,['README.md'])['vcs']
        self.assertEqual(vcs['kind'],'directory_snapshot')
        self.assertIsNone(vcs['own_head'])
        self.assertEqual(Path(vcs['enclosing_git_root']),self.parent)
    def test_own_clean_and_dirty_repository(self):
        ref=self.parent/'reference';ref.mkdir();self.init(ref)
        (ref/'README.md').write_text('reference');self.commit(ref)
        first=collect(ref,['README.md']);self.assertFalse(first['vcs']['dirty'])
        self.assertEqual(first['vcs']['own_head'],self.git(ref,'rev-parse','HEAD'))
        (ref/'README.md').write_text('changed')
        second=collect(ref,['README.md']);self.assertTrue(second['vcs']['dirty'])
        self.assertEqual(first['vcs']['own_head'],second['vcs']['own_head'])
        self.assertNotEqual(first['files'][0]['sha256'],second['files'][0]['sha256'])
    def test_unborn_repository_has_no_head(self):
        self.init(self.parent);(self.parent/'README.md').write_text('new')
        vcs=collect(self.parent,['README.md'])['vcs']
        self.assertEqual(vcs['kind'],'git_repository');self.assertIsNone(vcs['own_head'])
        self.assertTrue(vcs['dirty'])


if __name__ == '__main__':unittest.main()
