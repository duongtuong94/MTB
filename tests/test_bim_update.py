"""Offline integration tests: real Git repositories, no GitHub writes."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from bim_update import UpdateError, update_tools, check_for_updates


class UpdateTests(unittest.TestCase):
    def git(self, root, args):
        return subprocess.check_output(['git', '-C', root] + args,
                                       stderr=subprocess.STDOUT).decode('utf-8').strip()

    def runner(self, root, args):
        if args == ['remote', 'get-url', 'origin']:
            return 'https://github.com/duongtuong94/MTB.git'
        return self.git(root, args)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = os.path.join(self.temp.name, 'source')
        self.local = os.path.join(self.temp.name, 'local')
        os.mkdir(self.source)
        self.git(self.source, ['init', '-b', 'main'])
        self.configure(self.source)
        self.commit(self.source, 'initial')
        subprocess.check_output(['git', 'clone', self.source, self.local], stderr=subprocess.STDOUT)
        self.configure(self.local)

    def configure(self, root):
        self.git(root, ['config', 'user.name', 'Update Test'])
        self.git(root, ['config', 'user.email', 'test@example.invalid'])
        self.git(root, ['config', 'core.autocrlf', 'false'])

    def commit(self, root, text):
        self.git(root, ['-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m', text])

    def test_up_to_date(self):
        self.assertFalse(update_tools(self.local, self.runner)['changed'])

    def test_fast_forward(self):
        self.commit(self.source, 'new release')
        result = update_tools(self.local, self.runner)
        self.assertTrue(result['changed'])
        self.assertEqual(result['after'], self.git(self.source, ['rev-parse', 'HEAD']))

    def test_untracked_file_is_preserved(self):
        filename = os.path.join(self.local, 'local.txt')
        with open(filename, 'w') as stream:
            stream.write('keep me')
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)
        with open(filename) as stream:
            self.assertEqual('keep me', stream.read())

    def test_divergence_preserves_head(self):
        self.commit(self.local, 'local work')
        self.commit(self.source, 'remote work')
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))

    def test_wrong_branch(self):
        self.git(self.local, ['checkout', '-b', 'development'])
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)

    def test_wrong_remote(self):
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.git)

    def test_icon_current(self):
        self.assertFalse(check_for_updates(self.local, self.runner))

    def test_icon_new_remote_without_fetch(self):
        self.commit(self.source, 'new version')
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        remote_ref = self.git(self.local, ['rev-parse', 'origin/main'])
        self.assertTrue(check_for_updates(self.local, self.runner))
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))
        self.assertEqual(remote_ref, self.git(self.local, ['rev-parse', 'origin/main']))

    def test_icon_local_ahead(self):
        self.commit(self.local, 'local version')
        self.assertFalse(check_for_updates(self.local, self.runner))

    def test_icon_dirty_tree_still_checks(self):
        with open(os.path.join(self.local, 'draft.txt'), 'w') as stream:
            stream.write('draft')
        self.commit(self.source, 'new version')
        self.assertTrue(check_for_updates(self.local, self.runner))

    def test_icon_diverged(self):
        self.commit(self.local, 'local version')
        self.commit(self.source, 'remote version')
        self.assertTrue(check_for_updates(self.local, self.runner))

    def test_icon_network_failure_is_not_current(self):
        def offline(root, args):
            if args[0] == 'ls-remote':
                raise UpdateError('Offline')
            return self.runner(root, args)
        with self.assertRaises(UpdateError):
            check_for_updates(self.local, offline)


if __name__ == '__main__':
    unittest.main()
