# -*- coding: utf-8 -*-
"""Pure filtering and presentation decisions. No Revit, .NET or UI imports."""
from __future__ import unicode_literals

import os
import re

GROUPS = ('All', 'Model', 'Detail', 'Annotation', 'Profile')
PAGE_SIZE = 40

# Use actual built-in category keys, not translated display-name guesses.
CATEGORY_NAMES = {
    'OST_Doors': 'Doors', 'OST_Windows': 'Windows', 'OST_Furniture': 'Furniture',
    'OST_FurnitureSystems': 'Furniture Systems', 'OST_Casework': 'Casework',
    'OST_GenericModel': 'Generic Models', 'OST_DetailComponents': 'Detail Items',
    'OST_GenericAnnotation': 'Generic Annotations', 'OST_ProfileFamilies': 'Profiles',
    'OST_StructuralFraming': 'Structural Framing', 'OST_StructuralColumns': 'Structural Columns',
    'OST_StructuralFoundation': 'Structural Foundations', 'OST_Columns': 'Columns',
    'OST_Entourage': 'Entourage', 'OST_Planting': 'Planting', 'OST_Parking': 'Parking',
    'OST_Site': 'Site', 'OST_Topography': 'Topography', 'OST_Mass': 'Mass',
    'OST_SpecialityEquipment': 'Specialty Equipment', 'OST_MechanicalEquipment': 'Mechanical Equipment',
    'OST_PlumbingFixtures': 'Plumbing Fixtures', 'OST_PlumbingEquipment': 'Plumbing Equipment',
    'OST_LightingFixtures': 'Lighting Fixtures', 'OST_LightingDevices': 'Lighting Devices',
    'OST_ElectricalFixtures': 'Electrical Fixtures', 'OST_ElectricalEquipment': 'Electrical Equipment',
    'OST_DataDevices': 'Data Devices', 'OST_TelephoneDevices': 'Telephone Devices',
    'OST_CommunicationDevices': 'Communication Devices', 'OST_SecurityDevices': 'Security Devices',
    'OST_FireAlarmDevices': 'Fire Alarm Devices', 'OST_NurseCallDevices': 'Nurse Call Devices',
    'OST_DuctTerminal': 'Air Terminals', 'OST_DuctFitting': 'Duct Fittings',
    'OST_DuctAccessory': 'Duct Accessories', 'OST_PipeFitting': 'Pipe Fittings',
    'OST_PipeAccessory': 'Pipe Accessories', 'OST_Sprinklers': 'Sprinklers',
    'OST_ConduitFitting': 'Conduit Fittings', 'OST_CableTrayFitting': 'Cable Tray Fittings',
    'OST_CurtainWallPanels': 'Curtain Panels', 'OST_CurtainWallMullions': 'Curtain Wall Mullions',
    'OST_Railings': 'Railings', 'OST_StairsRailingBaluster': 'Balusters',
    'OST_StairsRailingTermination': 'Railing Terminations',
    'OST_StairsRailingSupport': 'Railing Supports',
    'OST_TitleBlocks': 'Title Blocks', 'OST_AnnotationCrop': 'Annotation Crop',
    'OST_DoorTags': 'Door Tags', 'OST_WindowTags': 'Window Tags',
    'OST_GenericModelTags': 'Generic Model Tags', 'OST_MultiCategoryTags': 'Multi-Category Tags',
    'OST_MaterialTags': 'Material Tags', 'OST_RoomTags': 'Room Tags',
    'OST_AreaTags': 'Area Tags', 'OST_MEPSpaceTags': 'Space Tags',
    'OST_DetailComponentTags': 'Detail Item Tags', 'OST_KeynoteTags': 'Keynote Tags',
    'OST_StructuralFramingTags': 'Structural Framing Tags',
    'OST_StructuralColumnTags': 'Structural Column Tags',
    'OST_StructuralFoundationTags': 'Structural Foundation Tags',
    'OST_FurnitureTags': 'Furniture Tags', 'OST_CaseworkTags': 'Casework Tags',
    'OST_MechanicalEquipmentTags': 'Mechanical Equipment Tags',
    'OST_PlumbingFixtureTags': 'Plumbing Fixture Tags',
    'OST_LightingFixtureTags': 'Lighting Fixture Tags',
    'OST_ElectricalFixtureTags': 'Electrical Fixture Tags',
    'OST_ElectricalEquipmentTags': 'Electrical Equipment Tags',
    'OST_DuctTerminalTags': 'Air Terminal Tags', 'OST_PipeFittingTags': 'Pipe Fitting Tags',
    'OST_DuctFittingTags': 'Duct Fitting Tags', 'OST_PipeAccessoryTags': 'Pipe Accessory Tags',
    'OST_DuctAccessoryTags': 'Duct Accessory Tags', 'OST_SprinklerTags': 'Sprinkler Tags',
    'OST_PlantingTags': 'Planting Tags', 'OST_ParkingTags': 'Parking Tags',
    'OST_SpecialityEquipmentTags': 'Specialty Equipment Tags',
    'OST_SpotElevations': 'Spot Elevations', 'OST_SpotCoordinates': 'Spot Coordinates',
    'OST_SectionHeads': 'Section Marks', 'OST_LevelHeads': 'Level Heads',
    'OST_GridHeads': 'Grid Heads', 'OST_CalloutHeads': 'Callout Heads',
}


def category_name(key, revit_name):
    # Never invent/merge categories; unknown categories retain Revit's label.
    return CATEGORY_NAMES.get(key, revit_name or 'Unknown Category')


def expand_types(families):
    """Each gallery card identifies exactly one type, retaining its parent family."""
    result = []
    for family in families:
        for item in family.get('types') or [{'name': '', 'id': None}]:
            row = dict(family)
            row['family_key'] = family['key']
            row['family_type_count'] = len(family.get('types', []))
            row['type_name'] = item['name']
            row['symbol_id'] = item.get('id')
            row['key'] = family['key'] + '|type:' + item['name']
            row['types'] = [item] if item['name'] else []
            result.append(row)
    return result


def family_group(key, category_type):
    if key == 'OST_ProfileFamilies':
        return 'Profile'
    if key == 'OST_DetailComponents':
        return 'Detail'
    if category_type == 'Annotation':
        return 'Annotation'
    if category_type == 'Model':
        return 'Model'
    return 'Other'


def needs_label_preview(row):
    """Annotation glyphs/Tags need text, not an apparently valid outline bitmap."""
    return row.get('group') == 'Annotation' or row.get('category_key', '').endswith('Tags')


def has_multiple_types(row):
    # Expanded cards hold only one entry in types; retain the parent count.
    return row.get('family_type_count', len(row.get('types', []))) > 1


def needs_type_visibility(row):
    return needs_label_preview(row) or has_multiple_types(row)


def path_key(path):
    return os.path.normcase(os.path.abspath(path)).lower()


def file_stamp(path):
    stat = os.stat(path)
    return [stat.st_size, stat.st_mtime]


def iter_family_paths(folder, recursive=True):
    """Filesystem only; caller may consume this on a worker thread."""
    def fail(error):
        raise error
    for directory, children, names in os.walk(folder, onerror=fail, followlinks=False):
        children[:] = sorted(n for n in children if not os.path.islink(os.path.join(directory, n)))
        for name in sorted(names):
            if name.lower().endswith('.rfa') and not re.search(r'\.\d{4}\.rfa$', name, re.I):
                yield os.path.join(directory, name)
        if not recursive:
            break


def filter_rows(rows, group='All', category=None, search='', scope='All Families',
                favorites=(), recent=()):
    words = search.lower().split()
    favorites, recent = set(favorites), list(recent)
    result = []
    for row in rows:
        if group != 'All' and row['group'] != group:
            continue
        if category is not None and row['category_key'] != category:
            continue
        if scope == 'Favorites' and row['key'] not in favorites:
            continue
        if scope == 'Recent' and row['key'] not in recent:
            continue
        haystack = ' '.join([row['name'], row['category']] +
                            [t['name'] for t in row.get('types', [])]).lower()
        if all(word in haystack for word in words):
            result.append(row)
    if scope == 'Recent':
        ranks = dict((key, index) for index, key in enumerate(recent))
        return sorted(result, key=lambda r: ranks[r['key']])
    return sorted(result, key=lambda r: (r['name'].lower(), r['key']))


def category_counts(rows):
    result = {}
    for row in rows:
        key = row['category_key']
        label, count = result.get(key, (row['category'], 0))
        result[key] = (label, count + 1)
    return sorted([(key, label, count) for key, (label, count) in result.items()],
                  key=lambda item: item[1].lower())


def page_rows(rows, page, size=PAGE_SIZE):
    pages = max(1, (len(rows) + size - 1) // size)
    page = max(0, min(page, pages - 1))
    return rows[page * size:(page + 1) * size], page, pages


def placement_reason(row):
    if row['group'] == 'Profile':
        return 'Profiles are used by other Revit tools, not placed directly.'
    if row['group'] == 'Annotation' and row['category_key'] != 'OST_GenericAnnotation':
        return 'Use the native Revit annotation/tag command for this category.'
    if row['category_key'] in ('OST_CurtainWallPanels', 'OST_CurtainWallMullions',
                               'OST_StairsRailingBaluster', 'OST_TitleBlocks',
                               'OST_StairsRailingTermination', 'OST_StairsRailingSupport'):
        return 'This family is assigned through its native Revit tool.'
    if row.get('placement') in ('Adaptive', 'Invalid'):
        return 'This placement method is not supported by this browser.'
    if not row.get('types'):
        return 'No named types are available for placement.'
    return ''


def action_for(row, source):
    if row is None or row.get('error'):
        return ('Select a family', False)
    blocked = bool(placement_reason(row))
    if source == 'Folder':
        return ('Load' if blocked else 'Load & Place', True)
    return ('Place', not blocked)
