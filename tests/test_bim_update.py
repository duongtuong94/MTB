"""Offline integration tests: stable tag releases, no GitHub writes."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from bim_update import UpdateError, update_tools, check_for_updates, parse_release_tags


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
        self.tag('v1.0.0')
        subprocess.check_output(['git', 'clone', self.source, self.local], stderr=subprocess.STDOUT)
        self.configure(self.local)

    def configure(self, root):
        self.git(root, ['config', 'user.name', 'Update Test'])
        self.git(root, ['config', 'user.email', 'test@example.invalid'])
        self.git(root, ['config', 'core.autocrlf', 'false'])
        self.git(root, ['config', 'tag.gpgsign', 'false'])

    def commit(self, root, text):
        self.git(root, ['-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-m', text])

    def tag(self, name):
        self.git(self.source, ['tag', '-a', name, '-m', name])

    def release(self):
        self.commit(self.source, 'published fix')
        self.tag('v1.1.0')

    def test_up_to_date(self):
        result = update_tools(self.local, self.runner)
        self.assertFalse(result['changed'])
        self.assertEqual('v1.0.0', result['release'])
        self.assertFalse(check_for_updates(self.local, self.runner))

    def test_unpublished_main_commits_do_not_trigger_or_install(self):
        self.commit(self.source, 'unfinished fix')
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        self.assertFalse(check_for_updates(self.local, self.runner))
        self.assertFalse(update_tools(self.local, self.runner)['changed'])
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))

    def test_install_exact_tag_not_later_main(self):
        self.release()
        target = self.git(self.source, ['rev-parse', 'v1.1.0^{commit}'])
        self.commit(self.source, 'next unfinished fix')
        self.assertTrue(check_for_updates(self.local, self.runner))
        result = update_tools(self.local, self.runner)
        self.assertTrue(result['changed'])
        self.assertEqual('v1.1.0', result['release'])
        self.assertEqual(target, result['after'])
        self.assertEqual('main', self.git(self.local, ['branch', '--show-current']))
        self.assertFalse(check_for_updates(self.local, self.runner))
        self.assertFalse(update_tools(self.local, self.runner)['changed'])

    def test_untracked_file_is_preserved(self):
        self.release()
        filename = os.path.join(self.local, 'local.txt')
        with open(filename, 'w') as stream:
            stream.write('keep me')
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)
        with open(filename) as stream:
            self.assertEqual('keep me', stream.read())

    def test_divergence_preserves_head(self):
        self.commit(self.local, 'local work')
        self.release()
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        self.assertTrue(check_for_updates(self.local, self.runner))
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))

    def test_wrong_branch(self):
        self.release()
        self.git(self.local, ['checkout', '-b', 'development'])
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.runner)

    def test_wrong_remote(self):
        with self.assertRaises(UpdateError):
            update_tools(self.local, self.git)

    def test_icon_check_does_not_fetch(self):
        self.release()
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        remote_ref = self.git(self.local, ['rev-parse', 'origin/main'])
        self.assertTrue(check_for_updates(self.local, self.runner))
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))
        self.assertEqual(remote_ref, self.git(self.local, ['rev-parse', 'origin/main']))

    def test_developer_ahead_never_downgrades(self):
        self.release()
        self.git(self.local, ['fetch', 'origin', 'main'])
        self.git(self.local, ['merge', '--ff-only', 'FETCH_HEAD'])
        self.commit(self.local, 'developer work')
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        self.assertFalse(check_for_updates(self.local, self.runner))
        self.assertFalse(update_tools(self.local, self.runner)['changed'])
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))

    def test_icon_dirty_tree_still_checks(self):
        with open(os.path.join(self.local, 'draft.txt'), 'w') as stream:
            stream.write('draft')
        self.release()
        self.assertTrue(check_for_updates(self.local, self.runner))

    def test_network_failure_is_not_current(self):
        def offline(root, args):
            if args[0] == 'ls-remote':
                raise UpdateError('Offline')
            return self.runner(root, args)
        with self.assertRaises(UpdateError):
            check_for_updates(self.local, offline)

    def test_no_published_tags(self):
        self.git(self.source, ['tag', '-d', 'v1.0.0'])
        self.commit(self.source, 'unpublished')
        self.assertFalse(check_for_updates(self.local, self.runner))
        result = update_tools(self.local, self.runner)
        self.assertIsNone(result['release'])
        self.assertFalse(result['changed'])

    def test_prerelease_is_ignored(self):
        self.commit(self.source, 'beta')
        self.tag('v2.0.0-beta.1')
        self.assertFalse(check_for_updates(self.local, self.runner))
        self.assertFalse(update_tools(self.local, self.runner)['changed'])

    def test_lightweight_tag(self):
        self.commit(self.source, 'lightweight release')
        self.git(self.source, ['tag', 'v1.2.0'])
        self.assertTrue(check_for_updates(self.local, self.runner))
        self.assertEqual('v1.2.0', update_tools(self.local, self.runner)['release'])

    def test_tag_changed_during_fetch_is_rejected(self):
        self.release()
        before = self.git(self.local, ['rev-parse', 'HEAD'])
        def moved_tag(root, args):
            if args[0] == 'fetch':
                self.commit(self.source, 'different contents')
                self.git(self.source, ['tag', '-f', 'v1.1.0'])
            return self.runner(root, args)
        with self.assertRaises(UpdateError):
            update_tools(self.local, moved_tag)
        self.assertEqual(before, self.git(self.local, ['rev-parse', 'HEAD']))


class TagParsingTests(unittest.TestCase):
    def test_semantic_numeric_order(self):
        lines = ['%s refs/tags/%s' % ('a' * 40, name)
                 for name in ['v1.9.0', 'v1.10.0', 'v1.2.99', 'v2.0.0-beta']]
        self.assertEqual('v1.10.0', parse_release_tags('\n'.join(lines))['tag'])

    def test_annotated_tag_uses_peeled_commit(self):
        output = '%s refs/tags/v1.0.0\n%s refs/tags/v1.0.0^{}' % ('a' * 40, 'b' * 40)
        self.assertEqual('b' * 40, parse_release_tags(output)['commit'])

    def test_invalid_tags_are_not_releases(self):
        output = '\n'.join('%s refs/tags/%s' % ('a' * 40, name)
                           for name in ['v01.0.0', 'v1.0', 'release', 'v1.0.0-rc.1'])
        self.assertIsNone(parse_release_tags(output))


if __name__ == '__main__':
    unittest.main()
