# -*- coding: utf-8 -*-
"""Read the saved RevitPreview PNG from a compound file, without opening Revit.

Read-only, bounded CFB reader. No dependency on an installed shell thumbnail
handler. Unknown/malformed files are rejected; no recovery heuristics or writes.
"""
from __future__ import unicode_literals

import os
import struct
import zlib

FREE = 0xffffffff
END = 0xfffffffe
MAX_STREAM = 32 * 1024 * 1024
PNG = b'\x89PNG\r\n\x1a\n'


def validated_png(data):
    start = data.find(PNG)
    if start < 0:
        return None
    offset = start + len(PNG)
    first = True
    while offset + 12 <= len(data):
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        if size > MAX_STREAM or offset + size + 12 > len(data):
            return None
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        expected = struct.unpack('>I', data[offset + 8 + size:offset + 12 + size])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != expected:
            return None
        if first:
            if kind != b'IHDR' or size != 13:
                return None
            width, height = struct.unpack('>II', payload[:8])
            if not (0 < width <= 4096 and 0 < height <= 4096):
                return None
            first = False
        offset += size + 12
        if kind == b'IEND':
            return data[start:offset] if size == 0 else None
    return None


def read_preview_png(path):
    with open(path, 'rb') as stream:
        header = stream.read(512)
        if len(header) != 512 or header[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return None
        if header[28:30] != b'\xfe\xff':
            raise ValueError('Unsupported compound-file byte order.')
        shift = struct.unpack_from('<H', header, 30)[0]
        mini_shift = struct.unpack_from('<H', header, 32)[0]
        if shift not in (9, 12) or mini_shift != 6:
            raise ValueError('Unsupported compound-file sector size.')
        sector_size = 1 << shift
        sector_count = os.fstat(stream.fileno()).st_size // sector_size - 1

        def sector(index):
            if not 0 <= index < sector_count:
                raise ValueError('Invalid sector reference.')
            stream.seek((index + 1) * sector_size)
            block = stream.read(sector_size)
            if len(block) != sector_size:
                raise ValueError('Truncated sector.')
            return block

        fat_count = struct.unpack_from('<I', header, 44)[0]
        if fat_count > sector_count or fat_count * sector_size > MAX_STREAM:
            raise ValueError('Invalid allocation table size.')
        fat_sectors = [i for i in struct.unpack_from('<109I', header, 76) if i != FREE]
        next_difat, difat_count = struct.unpack_from('<II', header, 68)
        seen = set()
        if difat_count > sector_count:
            raise ValueError('Invalid DIFAT size.')
        for unused in range(difat_count):
            if next_difat in seen:
                raise ValueError('Cyclic DIFAT.')
            seen.add(next_difat)
            values = struct.unpack('<{0}I'.format(sector_size // 4), sector(next_difat))
            fat_sectors.extend(i for i in values[:-1] if i != FREE)
            next_difat = values[-1]
        if len(fat_sectors) != fat_count:
            raise ValueError('Incomplete allocation table.')
        fat = []
        for identifier in fat_sectors:
            fat.extend(struct.unpack('<{0}I'.format(sector_size // 4), sector(identifier)))

        def chain(start, allocation, read_block, requested=None, block_size=sector_size):
            result, visited = [], set()
            current = start
            total = 0
            while current != END:
                if current in visited or not 0 <= current < len(allocation):
                    raise ValueError('Cyclic or invalid stream chain.')
                visited.add(current)
                total += block_size
                if total > MAX_STREAM:
                    raise ValueError('Preview stream exceeds limit.')
                result.append(read_block(current))
                if requested is not None and total >= requested:
                    break
                current = allocation[current]
            data = b''.join(result)
            if requested is not None:
                if requested > len(data):
                    raise ValueError('Truncated stream.')
                return data[:requested]
            return data

        directory = chain(struct.unpack_from('<I', header, 48)[0], fat, sector)
        root, target = None, None
        for offset in range(0, len(directory) - 127, 128):
            entry = directory[offset:offset + 128]
            length = struct.unpack_from('<H', entry, 64)[0]
            if not (2 <= length <= 64 and length % 2 == 0):
                continue
            name = entry[:length - 2].decode('utf-16le', 'replace')
            kind = struct.unpack_from('B', entry, 66)[0]
            start = struct.unpack_from('<I', entry, 116)[0]
            size = struct.unpack_from('<Q', entry, 120)[0]
            if size > MAX_STREAM:
                if kind == 5 or name.lower().startswith('revitpreview'):
                    raise ValueError('Preview storage exceeds limit.')
                continue
            if kind == 5:
                root = (start, size)
            elif kind == 2 and name.lower().startswith('revitpreview'):
                target = (start, size)
        if target is None or not target[1]:
            return None
        cutoff = struct.unpack_from('<I', header, 56)[0]
        if target[1] >= cutoff:
            content = chain(target[0], fat, sector, target[1])
        else:
            if root is None:
                raise ValueError('Missing miniature stream root.')
            mini_data = chain(root[0], fat, sector, root[1])
            mini_start, mini_count = struct.unpack_from('<II', header, 60)
            mini_fat_data = chain(mini_start, fat, sector, mini_count * sector_size)
            mini_fat = struct.unpack('<{0}I'.format(len(mini_fat_data) // 4), mini_fat_data)
            def mini_sector(index):
                start = index * 64
                if start + 64 > len(mini_data):
                    raise ValueError('Invalid miniature sector.')
                return mini_data[start:start + 64]
            content = chain(target[0], mini_fat, mini_sector, target[1], 64)
        return validated_png(content)
