# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
from pyrevit import forms, script
from bim_update import UpdateError, update_tools
from bim_update_ui import start_monitor, mark_current

__persistentengine__ = True


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    bundle = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(bundle, '..', '..', '..'))
    try:
        start_monitor(root, bundle, ui_button_cmp)
    except Exception:
        script.get_logger().exception('Could not start update icon monitor')
    return True


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    try:
        with forms.ProgressBar(title='BIM Test | Updating from GitHub...', indeterminate=True):
            result = update_tools(root)
    except UpdateError as error:
        message = u'{0}'.format(error)
        script.get_logger().warning(message)
        forms.alert(message, title='BIM Test | Update Tools', warn_icon=True)
        return
    except Exception as error:
        script.get_logger().exception('Update Tools failed')
        forms.alert(u'Không thể cập nhật.\n\n{0}'.format(error),
                    title='BIM Test | Update Tools', warn_icon=True)
        return
    try:
        mark_current()
    except Exception:
        script.get_logger().exception('Could not refresh update icon')
    if result['changed']:
        message = (u'Đã cập nhật BIM Test: {0} → {1}.\n\n'
                   u'Chạy pyRevit > Reload để nạp giao diện và code mới.').format(
                       result['before'][:8], result['after'][:8])
    else:
        message = u'BIM Test đang ở bản mới nhất ({0}).'.format(result['after'][:8])
    forms.alert(message, title='BIM Test | Update Tools')


if __name__ == '__main__':
    main()
