# -*- coding: utf-8 -*-
"""User-local JSON cache; no files are written to the extension or source RFA."""
from __future__ import unicode_literals

import hashlib
import io
import json
import os
import tempfile


class UserStore(object):
    SCHEMA = 2  # invalidate old family-level, possibly empty thumbnail caches

    def __init__(self, filename, engine):
        self.filename = filename
        self.engine = engine
        self.preview_dir = os.path.splitext(filename)[0] + '_previews'
        self.data = {'schema': self.SCHEMA, 'favorites': [], 'recent': [], 'files': {}}
        self.warning = ''
        try:
            with io.open(filename, 'r', encoding='utf-8') as stream:
                loaded = json.load(stream)
            if loaded.get('schema') == self.SCHEMA:
                self.data.update(loaded)
        except (IOError, ValueError, AttributeError):
            pass
        for key in ('favorites', 'recent'):
            if not isinstance(self.data.get(key), list):
                self.data[key] = []
        if not isinstance(self.data.get('files'), dict):
            self.data['files'] = {}

    def cached(self, key, stamp):
        item = self.data['files'].get(key, {})
        if item.get('stamp') == stamp and item.get('engine') == self.engine:
            row = item.get('row')
            if isinstance(row, dict) and not row.get('error'):
                return dict(row)
        return None

    def remember(self, key, stamp, row):
        if not row.get('error'):
            self.data['files'][key] = {'stamp': stamp, 'engine': self.engine, 'row': row}

    def preview_path(self, key, stamp):
        if not os.path.isdir(self.preview_dir):
            os.makedirs(self.preview_dir)
        token = json.dumps([self.engine, key, stamp], ensure_ascii=True)
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        return os.path.join(self.preview_dir, digest + '.png')

    def toggle_favorite(self, key):
        values = self.data['favorites']
        if key in values:
            values.remove(key)
        else:
            values.append(key)

    def touch(self, key):
        self.data['recent'] = [key] + [x for x in self.data['recent'] if x != key][:59]

    def save(self):
        # A failed cache write must not stop browsing or leave a half-written file.
        temporary = None
        try:
            directory = os.path.dirname(self.filename)
            if not os.path.isdir(directory):
                os.makedirs(directory)
            handle, temporary = tempfile.mkstemp(prefix='mtb_family_', dir=directory)
            os.close(handle)
            with io.open(temporary, 'w', encoding='utf-8') as stream:
                stream.write(json.dumps(self.data, ensure_ascii=True))
            # os.replace is unavailable in IronPython 2.7. .NET provides atomic
            # replacement on Windows; CPython tests use os.replace.
            if hasattr(os, 'replace'):
                os.replace(temporary, self.filename)
            else:
                from System.IO import File
                if File.Exists(self.filename):
                    File.Replace(temporary, self.filename, None)
                else:
                    File.Move(temporary, self.filename)
            temporary = None
            return True
        except Exception as error:
            self.warning = 'Could not save the local library cache: {0}'.format(error)
            return False
        finally:
            if temporary and os.path.isfile(temporary):
                os.remove(temporary)
