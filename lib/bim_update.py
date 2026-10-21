# -*- coding: utf-8 -*-
"""Conservative updater for a Git checkout, compatible with IronPython 2.7."""
from __future__ import unicode_literals

import os
import subprocess


class UpdateError(Exception):
    pass


def find_git():
    candidates = [os.path.join(folder.strip('"'), 'git.exe')
                  for folder in os.environ.get('PATH', '').split(os.pathsep) if folder]
    for variable in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        folder = os.environ.get(variable)
        if folder:
            candidates.append(os.path.join(folder, 'Git', 'cmd', 'git.exe'))
            candidates.append(os.path.join(folder, 'Programs', 'Git', 'cmd', 'git.exe'))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise UpdateError(u'Không tìm thấy Git. Cài Git for Windows và mở lại Revit.')


def run_git(root, arguments):
    # .NET Process supports timeouts on IronPython and hides console windows.
    from System.Diagnostics import Process, ProcessStartInfo
    output, errors = [], []
    start = ProcessStartInfo()
    start.FileName = find_git()
    start.Arguments = subprocess.list2cmdline(arguments)
    start.WorkingDirectory = root
    start.UseShellExecute = False
    start.CreateNoWindow = True
    start.RedirectStandardOutput = True
    start.RedirectStandardError = True
    start.EnvironmentVariables['GIT_TERMINAL_PROMPT'] = '0'
    start.EnvironmentVariables['GCM_INTERACTIVE'] = 'Never'
    start.EnvironmentVariables['GIT_MERGE_AUTOEDIT'] = 'no'
    process = Process()
    process.StartInfo = start

    def capture_output(sender, event):
        if event.Data is not None:
            output.append(event.Data)

    def capture_error(sender, event):
        if event.Data is not None:
            errors.append(event.Data)

    process.OutputDataReceived += capture_output
    process.ErrorDataReceived += capture_error
    try:
        process.Start()
        process.BeginOutputReadLine()
        process.BeginErrorReadLine()
        if not process.WaitForExit(60000):
            process.Kill()
            process.WaitForExit()
            raise UpdateError(u'Git quá thời gian chờ (60 giây). Kiểm tra kết nối và trạng thái Git trước khi thử lại.')
        process.WaitForExit()  # Drain asynchronous output events.
        if process.ExitCode != 0:
            detail = '\n'.join(errors + output)[-3000:]
            raise UpdateError(u'Git không hoàn tất. Kiểm tra mạng, quyền GitHub và trạng thái repository.\n\n' + detail)
        return '\n'.join(output).strip()
    finally:
        process.Dispose()


def check_for_updates(root, runner=None):
    """Read remote refs without fetch, checkout changes, or dirty-tree checks."""
    git = runner or run_git
    validate_repository(root, git)
    remote = git(root, ['ls-remote', '--exit-code', 'origin', 'refs/heads/main'])
    parts = remote.split()
    if len(parts) != 2 or parts[1] != 'refs/heads/main':
        raise UpdateError(u'Không đọc được nhánh main trên GitHub.')
    # A local branch ahead of remote main does not need to download that commit.
    ancestors = set(git(root, ['rev-list', 'HEAD']).split())
    return parts[0] not in ancestors


def validate_repository(root, git):
    """Only allow the extension checkout and its configured GitHub repository."""
    actual_root = git(root, ['rev-parse', '--show-toplevel'])
    if os.path.normcase(os.path.realpath(actual_root)) != os.path.normcase(os.path.realpath(root)):
        raise UpdateError(u'Extension phải nằm tại thư mục gốc của Git repository. Hãy cài bằng git clone.')
    remote = git(root, ['remote', 'get-url', 'origin']).rstrip('/')
    if remote not in ('https://github.com/duongtuong94/MTB',
                      'https://github.com/duongtuong94/MTB.git',
                      'git@github.com:duongtuong94/MTB.git',
                      'ssh://git@github.com/duongtuong94/MTB.git'):
        raise UpdateError(u'origin không trỏ tới repository duongtuong94/MTB. Hãy kiểm tra cấu hình Git.')


def update_tools(root, runner=None):
    git = runner or run_git
    validate_repository(root, git)
    if git(root, ['status', '--porcelain', '--untracked-files=all']):
        raise UpdateError(u'Có thay đổi local chưa commit (hoặc file chưa được Git theo dõi).\n'
                          u'Hãy commit và đồng bộ bằng Git trước khi cập nhật. Tool không tự xóa hoặc ghi đè thay đổi.')
    if git(root, ['rev-parse', '--abbrev-ref', 'HEAD']) != 'main':
        raise UpdateError(u'Update Tools chỉ cập nhật nhánh main. Hãy chuyển về main bằng Git trước.')
    before = git(root, ['rev-parse', 'HEAD'])
    git(root, ['fetch', '--no-tags', 'origin', 'refs/heads/main'])
    target = git(root, ['rev-parse', 'FETCH_HEAD'])
    counts = git(root, ['rev-list', '--left-right', '--count', 'HEAD...' + target]).split()
    if int(counts[0]):
        raise UpdateError(u'Máy này có commit chưa có trên GitHub hoặc lịch sử đã phân nhánh.\n'
                          u'Hãy đồng bộ bằng Git trước; Update Tools chỉ nhận bản mới bằng fast-forward.')
    if before != target:
        # Recheck after the network call, in case files changed during fetch.
        if git(root, ['status', '--porcelain', '--untracked-files=all']):
            raise UpdateError(u'File local đã thay đổi trong lúc kiểm tra. Hãy lưu thay đổi bằng Git rồi thử lại.')
        git(root, ['-c', 'merge.autostash=false', 'merge', '--ff-only', '--no-edit', target])
    after = git(root, ['rev-parse', 'HEAD'])
    if after != target:
        raise UpdateError(u'Chưa xác nhận được bản cập nhật. Hãy kiểm tra git status.')
    return {'changed': before != after, 'before': before, 'after': after}
