# -*- coding: utf-8 -*-
"""Background Git checks; ribbon changes run only on the WPF dispatcher."""
from __future__ import unicode_literals

import os
import threading
import time

from bim_update import check_for_updates

MONITOR_KEY = 'BIM_TEST_UPDATE_ICON_MONITOR'
CHECK_INTERVAL = 15 * 60


class UpdateIconMonitor(object):
    def __init__(self, root, bundle, button):
        from System import TimeSpan
        from System.Windows.Threading import DispatcherTimer
        self.root = root
        self.bundle = bundle
        self.button = button
        self.stopped = False
        self.busy = False
        self.next_check = 0
        self.generation = 0
        self.results = []
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromSeconds(2)
        self.timer.Tick += self.on_tick

    def start(self):
        self.timer.Start()

    def stop(self):
        self.stopped = True
        self.timer.Stop()
        self.timer.Tick -= self.on_tick

    def set_icon(self, has_updates):
        from pyrevit.coreutils.ribbon import ICON_LARGE
        filename = 'icon_hasupdates.png' if has_updates else 'icon.png'
        self.button.set_icon(os.path.join(self.bundle, filename), icon_size=ICON_LARGE)

    def mark_current(self):
        # Invalidate an in-flight check that may have observed the previous HEAD.
        self.generation += 1
        self.set_icon(False)
        self.next_check = time.time() + CHECK_INTERVAL

    def check(self, generation):
        try:
            result = check_for_updates(self.root)
        except Exception:
            result = None  # Unknown is not the same as up to date.
        self.results.append((generation, result))

    def on_tick(self, sender, args):
        if self.stopped:
            return
        while self.results:
            generation, result = self.results.pop(0)
            self.busy = False
            if generation == self.generation and result is not None:
                try:
                    self.set_icon(result)
                except Exception:
                    pass  # A missing ribbon item must not interrupt Revit.
        if not self.busy and time.time() >= self.next_check:
            self.busy = True
            self.next_check = time.time() + CHECK_INTERVAL
            worker = threading.Thread(target=self.check, args=(self.generation,))
            worker.daemon = True
            worker.start()


def start_monitor(root, bundle, button):
    from pyrevit.coreutils import envvars
    old = envvars.get_pyrevit_env_var(MONITOR_KEY)
    if old is not None:
        old.stop()
    monitor = UpdateIconMonitor(root, bundle, button)
    envvars.set_pyrevit_env_var(MONITOR_KEY, monitor)
    monitor.start()
    return monitor


def mark_current():
    from pyrevit.coreutils import envvars
    monitor = envvars.get_pyrevit_env_var(MONITOR_KEY)
    if monitor is not None:
        monitor.mark_current()
