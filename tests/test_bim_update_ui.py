"""Monitor state tests without requiring Revit or WPF."""
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from bim_update_ui import UpdateIconMonitor


class MonitorTests(unittest.TestCase):
    def monitor(self):
        monitor = UpdateIconMonitor.__new__(UpdateIconMonitor)
        monitor.stopped = False
        monitor.busy = True
        monitor.next_check = float('inf')
        monitor.generation = 0
        monitor.results = []
        monitor.root = 'test'
        monitor.set_icon = Mock()
        return monitor

    def test_remote_update_sets_icon(self):
        monitor = self.monitor()
        monitor.results.append((0, True))
        monitor.on_tick(None, None)
        monitor.set_icon.assert_called_once_with(True)

    def test_offline_keeps_icon(self):
        monitor = self.monitor()
        with patch('bim_update_ui.check_for_updates', side_effect=RuntimeError('offline')):
            monitor.check(0)
        monitor.on_tick(None, None)
        monitor.set_icon.assert_not_called()
        self.assertFalse(monitor.busy)

    def test_successful_update_discards_stale_check(self):
        monitor = self.monitor()
        monitor.mark_current()
        monitor.results.append((0, True))
        monitor.on_tick(None, None)
        monitor.set_icon.assert_called_once_with(False)


if __name__ == '__main__':
    unittest.main()
