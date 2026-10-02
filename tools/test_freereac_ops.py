# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/freereac_ops.py on throwaway git repos: the public-tree guard, the resolver rungs and the
ops export. Run: python3 -m unittest discover -s tools -p 'test_*.py'"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import freereac_ops as fo  # noqa: E402

MOVED = ['findings.md', 'specs/2026-01-01-x-design.md', 'plans/2026-01-02-y-plan.md']


def sh(cwd, *args):
    subprocess.run(['git', '-c', 'commit.gpgsign=false', *args], cwd=cwd, check=True,
                   capture_output=True)


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        f.write(text)


class Fixture(unittest.TestCase):
    """<tmp>/pub: a repo whose base commit holds MOVED, whose tip moved them out."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pub = os.path.join(self.tmp, 'pub')
        os.makedirs(self.pub)
        sh(self.pub, 'init', '-q', '-b', 'main')
        sh(self.pub, 'config', 'user.email', 't@example.com')
        sh(self.pub, 'config', 'user.name', 'T')
        write(self.pub, 'README.md', 'docs\n')
        write(self.pub, 'obs-studio.md', 'guide\n')
        for p in MOVED:
            write(self.pub, p, 'internal %s\n' % p)
        sh(self.pub, 'add', '-A')
        sh(self.pub, 'commit', '-qm', 'base')
        self.base = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.pub, capture_output=True,
                                   text=True).stdout.strip()
        sh(self.pub, 'rm', '-q', *MOVED)
        write(self.pub, fo.MOVES, '# base %s\n%s\n' % (self.base, '\n'.join(MOVED)))
        sh(self.pub, 'add', '-A')
        sh(self.pub, 'commit', '-qm', 'move')
        env = {k: v for k, v in os.environ.items() if not k.startswith('FREEREAC_')}
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def run_check(self):
        buf = io.StringIO()
        n = fo.check(self.pub, out=buf)
        return n, buf.getvalue()

    def add(self, rel, text):
        write(self.pub, rel, text)
        sh(self.pub, 'add', rel)

    def make_ops(self, root, paths=MOVED):
        for p in paths:
            write(root, os.path.join(fo.OPS_SUBDIR, p), 'internal %s\n' % p)


class Classifier(unittest.TestCase):
    def test_rule(self):
        for p in ('findings.md', 'rig-recipe.md', 'aes67-firmware-feasibility.md',
                  '2026-09-01-obs-route-assessment.md', 'specs/2026-05-30-x-design.md',
                  'design-specs/x.md', 'runbooks/rig.md', 'journal/2026-06-10-x.md',
                  'plans/wave-3.txt', 'notes/x.json', 'adr/0001-x.md', 'audits/2026-09-25-x.tsv',
                  '.claude/skills/x/SKILL.md', 'ROADMAP.md', 'CLAUDE.md', 'x-plan.md'):
            self.assertTrue(fo.belongs_in_ops(p), p)
        for p in ('README.md', 'NOTICE', 'LICENSE', 'BUILDING.md', 'CONTRIBUTING.md',
                  'obs-studio.md', 'tools/ops-moves.txt', 'tools/freereac_ops.py',
                  '.github/workflows/check.yml'):
            self.assertFalse(fo.belongs_in_ops(p), p)

    def test_slug(self):
        self.assertEqual(fo.slug('findings.md'), 'findings')
        self.assertEqual(fo.slug('specs/2026-01-01-x-design.md'), 'specs/2026-01-01-x-design')

    def test_gone_dirs(self):
        self.assertEqual(fo.gone_dirs(MOVED, ['README.md', 'obs-studio.md']), ['plans', 'specs'])


class Check(Fixture):
    def test_clean_tree_passes_and_names_the_skip(self):
        n, out = self.run_check()
        self.assertEqual(n, 0, out)
        self.assertIn('OPS-ABSENT moves-resolve: skipped', out)
        self.assertIn('CHECK OK', out)

    def test_moved_path_still_public_fails(self):
        self.add('findings.md', 'back\n')
        n, out = self.run_check()
        self.assertIn('STILL-PUBLIC findings.md', out)
        self.assertGreater(n, 0)

    def test_new_notebook_entry_fails(self):
        self.add('notes/2026-10-02-x.md', 'new entry\n')
        self.add('2026-10-02-assessment.md', 'a dated work product\n')
        n, out = self.run_check()
        self.assertIn('INTERNAL notes/2026-10-02-x.md', out)
        self.assertIn('INTERNAL 2026-10-02-assessment.md', out)
        self.assertEqual(n, 2, out)

    def test_citation_by_file_fails_and_slug_passes(self):
        self.add('obs-studio.md', 'see [findings](findings.md) and 2026-01-02-y-plan.md\n')
        n, out = self.run_check()
        self.assertIn('CITES obs-studio.md:1 findings.md', out)
        self.assertIn('CITES obs-studio.md:1 plans/2026-01-02-y-plan.md', out)
        self.assertEqual(n, 2, out)
        self.add('obs-studio.md', 'see the findings slug and plans/2026-01-02-y-plan\n')
        self.assertEqual(self.run_check()[0], 0)

    def test_naming_a_directory_that_moved_out_fails(self):
        self.add('README.md', 'the dated specs are in `specs/`\n')
        n, out = self.run_check()
        self.assertIn('CITES README.md:1 specs/: a directory that moved', out)
        self.assertEqual(n, 1, out)
        # the word is prose, and a slug inside the directory is a citation
        self.add('README.md', 'dated specs and plans; see specs/2026-01-01-x-design\n')
        self.assertEqual(self.run_check()[0], 0)
        # a directory that still holds a public file is not gone
        self.add('tools/README.md', 'tools\n')
        self.add('README.md', 'the tools are in `tools/`\n')
        self.assertEqual(self.run_check()[0], 0)

    def test_require_ops_fails_when_absent(self):
        os.environ['FREEREAC_REQUIRE_OPS'] = '1'
        n, out = self.run_check()
        self.assertIn('OPS-ABSENT moves-resolve: FREEREAC_REQUIRE_OPS=1', out)
        self.assertEqual(n, 1)

    def test_env_rung_resolves_every_move(self):
        ops = os.path.join(self.tmp, 'elsewhere')
        self.make_ops(ops)
        os.environ['FREEREAC_OPS'] = ops
        n, out = self.run_check()
        self.assertEqual(n, 0, out)
        self.assertIn('OPS OK 3 moved paths', out)
        self.assertEqual(fo.resolve('findings', self.pub), os.path.join(ops, 'reac-docs', 'findings.md'))
        self.assertEqual(fo.resolve('findings.md', self.pub), os.path.join(ops, 'reac-docs', 'findings.md'))

    def test_sibling_rung_and_half_moved_fails(self):
        sib = os.path.join(self.tmp, 'freereac-ops')
        self.make_ops(sib, MOVED[:2])
        self.assertEqual(fo.ops_root(self.pub), sib)
        n, out = self.run_check()
        self.assertIn('UNRESOLVED plans/2026-01-02-y-plan', out)
        self.assertEqual(n, 1, out)
        os.environ['FREEREAC_OPS'] = os.path.join(self.tmp, 'nope')
        self.assertIsNone(fo.ops_root(self.pub), 'a set but missing $FREEREAC_OPS never falls through')

    def test_resolve_absent(self):
        self.assertIsNone(fo.resolve('findings', self.pub))


class Export(Fixture):
    def ops_repo(self, seeded):
        ops = os.path.join(self.tmp, 'freereac-ops')
        os.makedirs(ops)
        sh(ops, 'init', '-q', '-b', 'main')
        sh(ops, 'config', 'user.email', 't@example.com')
        sh(ops, 'config', 'user.name', 'T')
        sh(ops, 'config', 'commit.gpgsign', 'false')
        if seeded:
            write(ops, 'README.md', 'ops\n')
            sh(ops, 'add', '-A')
            sh(ops, 'commit', '-qm', 'seed')
        return ops

    def ls(self, ops, ref):
        return subprocess.run(['git', 'ls-tree', '-r', ref], cwd=ops, capture_output=True,
                              text=True).stdout

    def test_export_onto_main_is_byte_identical_and_idempotent(self):
        ops = self.ops_repo(seeded=True)
        buf = io.StringIO()
        c = fo.export(ops, repo=self.pub, out=buf)
        self.assertIn('EXPORT lane/docs-reac-docs', buf.getvalue())
        tree = self.ls(ops, fo.BRANCH)
        self.assertIn('\tREADME.md\n', tree)
        for p in MOVED:
            src = subprocess.run(['git', 'rev-parse', '%s:%s' % (self.base, p)], cwd=self.pub,
                                 capture_output=True, text=True).stdout.strip()
            self.assertIn('%s\treac-docs/%s\n' % (src, p), tree)
        parent = subprocess.run(['git', 'rev-parse', fo.BRANCH + '^'], cwd=ops,
                                capture_output=True, text=True).stdout.strip()
        main = subprocess.run(['git', 'rev-parse', 'main'], cwd=ops, capture_output=True,
                              text=True).stdout.strip()
        self.assertEqual(parent, main)
        buf = io.StringIO()
        self.assertEqual(fo.export(ops, repo=self.pub, out=buf), c)
        self.assertIn('EXPORT EXISTS', buf.getvalue())
        # the exported checkout is what `check` then resolves through the sibling rung
        subprocess.run(['git', '-c', 'advice.detachedHead=false', 'checkout', '-q', fo.BRANCH],
                       cwd=ops, check=True)
        self.assertEqual(self.run_check()[0], 0)

    def test_export_signs_when_commit_gpgsign_is_set(self):
        ops = self.ops_repo(seeded=True)
        sh(ops, 'config', 'commit.gpgsign', 'true')
        sh(ops, 'config', 'gpg.program', os.path.join(self.tmp, 'no-gpg'))
        with self.assertRaises(SystemExit) as e:
            fo.export(ops, repo=self.pub, out=io.StringIO())
        self.assertIn('commit-tree', str(e.exception), 'the export asked gpg to sign, and gpg failed')

    def test_export_into_empty_ops_is_a_root_commit(self):
        ops = self.ops_repo(seeded=False)
        fo.export(ops, repo=self.pub, out=io.StringIO())
        self.assertEqual(len(self.ls(ops, fo.BRANCH).splitlines()), len(MOVED))

    def test_export_refuses_a_path_missing_at_base(self):
        ops = self.ops_repo(seeded=True)
        write(self.pub, fo.MOVES, '# base %s\nnot/there.md\n' % self.base)
        with self.assertRaises(SystemExit) as e:
            fo.export(ops, repo=self.pub, out=io.StringIO())
        self.assertIn('not/there.md is not in', str(e.exception))


if __name__ == '__main__':
    unittest.main()
