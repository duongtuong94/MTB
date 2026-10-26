# -*- coding: utf-8 -*-
"""Revit access only. Called on the command/UI thread, never the file worker."""
from __future__ import unicode_literals

import glob
import os
import shutil
import tempfile

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System.Drawing')
from Autodesk.Revit import DB
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Drawing import Size, Bitmap
from System.Collections.Generic import List

from .service import (category_name, family_group, path_key, file_stamp,
                      placement_reason, needs_label_preview, has_multiple_types, needs_type_visibility)
from .rfa_preview import read_preview_png
from .preview_drawing import load_bitmap, has_content, draw_geometry


def element_name(element):
    try:
        return DB.Element.Name.GetValue(element)
    except Exception:
        return element.Name


def element_id(value):
    try:
        return int(value.Value)
    except AttributeError:
        return int(value.IntegerValue)


def category_info(category):
    if category is None:
        return ('Unknown', 'Unknown Category', 'Other')
    key = str(category.BuiltInCategory)
    return (key, category_name(key, category.Name), family_group(key, str(category.CategoryType)))


class BackgroundDocumentError(RuntimeError):
    fatal = True


def family_row(family):
    key, label, group = category_info(family.FamilyCategory)
    types = []
    for identifier in family.GetFamilySymbolIds():
        symbol = family.Document.GetElement(identifier)
        types.append({'name': element_name(symbol), 'id': element_id(identifier)})
    return {'key': family.UniqueId, 'name': element_name(family),
            'category_key': key, 'category': label, 'group': group,
            'types': sorted(types, key=lambda t: t['name'].lower()),
            'placement': str(family.FamilyPlacementType), 'path': '', 'preview': '', 'error': ''}


class ConflictOptions(DB.IFamilyLoadOptions):
    """Ask per conflict, including nested shared families. Never silently replace."""
    def __init__(self, confirm):
        self.confirm = confirm
        self.declined = False

    def _ask(self, name):
        accepted = self.confirm(
            'A family conflict was detected: {0}.\n\n'
            'Replace the existing family definition, keeping existing parameter '
            'values?\nChoose No to cancel the entire load.'.format(name))
        self.declined = self.declined or not accepted
        return accepted

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = False
        return self._ask('selected family')

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        overwriteParameterValues.Value = False
        source.Value = DB.FamilySource.Family
        return self._ask(element_name(sharedFamily))


class RevitLibrary(object):
    def __init__(self, uiapp, store):
        self.uiapp = uiapp
        self.uidoc = uiapp.ActiveUIDocument
        self.doc = self.uidoc.Document
        self.store = store
        self.engine = str(uiapp.Application.VersionNumber)
        self._preview_workdirs = []

    def project_rows(self):
        rows = []
        document_key = self.doc.ProjectInformation.UniqueId
        for family in DB.FilteredElementCollector(self.doc).OfClass(DB.Family):
            if family.IsInPlace or not family.IsUserCreated:
                continue
            row = family_row(family)
            row['key'] = 'project:{0}:{1}'.format(document_key, family.UniqueId)
            row['family_id'] = element_id(family.Id)
            rows.append(row)
        return rows

    def _existing_family_document(self, path):
        target = path_key(path)
        for document in self.uiapp.Application.Documents:
            if document.IsFamilyDocument and document.PathName and path_key(document.PathName) == target:
                return document
        return None

    def inspect_file(self, path):
        """Open at most one background family; always close owned documents unsaved."""
        key = path_key(path)
        stamp = file_stamp(path)
        existing = self._existing_family_document(path)
        # An already-open document may have unsaved edits. Do not read/cache it.
        if existing is not None:
            raise ValueError('This RFA is already open in Revit. Close it before indexing the disk file.')
        cached = self.store.cached(key, stamp)
        if cached is not None:
            return cached
        info = DB.BasicFileInfo.Extract(path)
        try:
            version = str(info.Format)
            if info.IsSavedInLaterVersion:
                raise ValueError('This file requires a newer Revit version ({0}).'.format(version))
        finally:
            info.Dispose()
        family_doc = self.uiapp.Application.OpenDocumentFile(path)
        try:
            if not family_doc.IsFamilyDocument:
                raise ValueError('The selected file is not a family document.')
            family = family_doc.OwnerFamily
            row = family_row(family)
            # Owner-family types are defined by FamilyManager, not nested symbols.
            row['types'] = sorted([{'name': t.Name, 'id': None}
                                   for t in family_doc.FamilyManager.Types], key=lambda t: t['name'].lower())
            row.update({'key': key, 'path': path, 'stamp': stamp,
                        'version': version, 'bytes': stamp[0]})
            destination = self.store.preview_path(key, stamp)
            if self._save_embedded_preview(path, destination):
                row['preview'] = destination
        finally:
            try:
                closed = family_doc.Close(False)
            except Exception as error:
                raise BackgroundDocumentError('Revit could not close the background RFA: {0}'.format(error))
            if not closed:
                raise BackgroundDocumentError('Revit could not close the background RFA. Stop indexing and check open documents.')
        # Never cache source data if it changed while it was being read.
        if file_stamp(path) != stamp:
            raise ValueError('The file changed while indexing. Select Folder again to retry.')
        self.store.remember(key, stamp, row)
        return row

    def _supports_type_visibility(self, view):
        try:
            modes = view.TemporaryViewModes
            if modes is None:
                return False
            mode = DB.TemporaryViewMode.PreviewFamilyVisibility
            return (modes.IsModeAvailable(mode) and modes.IsModeEnabled(mode) and
                    modes.IsValidState(DB.PreviewFamilyVisibilityMode.On))
        except Exception:
            return False

    def _enable_type_visibility(self, view):
        """Per-view state only. NEVER change Revit's application-wide defaults."""
        if not self._supports_type_visibility(view):
            return False
        modes = view.TemporaryViewModes
        modes.PreviewFamilyVisibility = DB.PreviewFamilyVisibilityMode.On
        return modes.PreviewFamilyVisibility == DB.PreviewFamilyVisibilityMode.On

    def _prepare_preview_visibility(self, document, view, row):
        """Call after CurrentType evaluation, before exporting the chosen view."""
        if not document.IsFamilyDocument or document == self.doc:
            raise ValueError('Preview Visibility may only be changed in an isolated family document.')
        transaction = DB.Transaction(document, 'Temporary type preview visibility')
        try:
            transaction.Start()
            if not self._enable_type_visibility(view) and needs_type_visibility(row):
                row['preview_detail'] = 'Preview Visibility On is unavailable for this family view; no mixed-type image was used.'
                transaction.RollBack()
                return False
            document.Regenerate()
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Could not commit Preview Visibility On.')
            return True
        except Exception:
            if transaction.GetStatus() == DB.TransactionStatus.Started:
                transaction.RollBack()
            raise
        finally:
            transaction.Dispose()

    def _export_preview(self, document, row, destination):
        # Some family views cannot be printed but can still be exported. Try
        # several existing views, rejecting blank output instead of stopping at one.
        views = [v for v in DB.FilteredElementCollector(document).OfClass(DB.View)
                 if not v.IsTemplate and str(v.ViewType) in
                 ('ThreeD', 'FloorPlan', 'CeilingPlan', 'Elevation', 'Section', 'DraftingView', 'Detail')]
        prefer_3d = row['group'] == 'Model'
        views.sort(key=lambda v: (str(v.ViewType) != ('ThreeD' if prefer_3d else 'FloorPlan'), element_name(v)))
        if not views:
            return False
        directory = tempfile.mkdtemp(prefix='export_', dir=self.store.preview_dir)
        options = DB.ImageExportOptions()
        try:
            options.ExportRange = DB.ExportRange.SetOfViews
            options.ZoomType = DB.ZoomFitType.FitToPage
            options.PixelSize = 256
            options.HLRandWFViewsFileType = DB.ImageFileType.PNG
            options.ShadowViewsFileType = DB.ImageFileType.PNG
            for index, view in enumerate(views[:8]):
                try:
                    if not self._prepare_preview_visibility(document, view, row):
                        continue
                    options.SetViewsAndSheets(List[DB.ElementId]([view.Id]))
                    options.FilePath = os.path.join(directory, 'preview_{0}'.format(index))
                    document.ExportImage(options)
                    files = glob.glob(os.path.join(directory, 'preview_{0}*.png'.format(index)))
                    for filename in files:
                        image = load_bitmap(filename)
                        try:
                            if has_content(image):
                                shutil.copyfile(filename, destination)
                                return True
                        finally:
                            image.Dispose()
                except Exception:
                    continue
            return False
        except Exception:
            return False
        finally:
            options.Dispose()
            shutil.rmtree(directory)

    def _save_embedded_preview(self, path, destination):
        try:
            if os.path.isfile(destination):
                return True
            png = read_preview_png(path)
            if png:
                with open(destination, 'wb') as stream:
                    stream.write(png)
                return True
        except (IOError, ValueError):
            pass
        return False

    def _geometry_preview(self, document, row, destination):
        """Draw real curve/region geometry when Revit has no exportable 2D view.

        This is labelled a geometry preview, not a rendered/annotation-exact view.
        Reference planes, dimensions and construction constraints are excluded.
        """
        paths = []
        point_count = [0]
        def add_curve(curve, filled=False):
            vertices = [(float(p.X), float(p.Y), float(p.Z)) for p in curve.Tessellate()]
            point_count[0] += len(vertices)
            if point_count[0] > 100000:
                raise ValueError('Preview geometry exceeds the safe point limit.')
            paths.append((vertices, filled))
        for element in DB.FilteredElementCollector(document).OfClass(DB.CurveElement):
            add_curve(element.GeometryCurve)
        for region in DB.FilteredElementCollector(document).OfClass(DB.FilledRegion):
            for loop in region.GetBoundaries():
                vertices = []
                for curve in loop:
                    vertices.extend((float(p.X), float(p.Y), float(p.Z)) for p in curve.Tessellate())
                point_count[0] += len(vertices)
                if point_count[0] > 100000:
                    raise ValueError('Preview geometry exceeds the safe point limit.')
                paths.append((vertices, True))
        image = draw_geometry(paths, model=row['group'] == 'Model')
        if image is None:
            return False
        try:
            if not has_content(image):
                return False
            from System.Drawing.Imaging import ImageFormat
            image.Save(destination, ImageFormat.Png)
            return True
        finally:
            image.Dispose()

    def _saved_label_preview(self, document, row, destination):
        """Regenerate the family-editor thumbnail, including label sample values.

        Only called for a newly-owned background family document. SaveAs writes
        a uniquely named CACHE COPY, never the source RFA or active project.
        The caller closes the document before removing the working directory.
        """
        if not document.IsFamilyDocument or document == self.doc:
            raise ValueError('Label previews require an isolated family document.')
        settings = document.GetDocumentPreviewSettings()
        options = DB.SaveAsOptions()
        try:
            preferred = document.GetElement(settings.PreviewViewId)
            candidates = [view for view in DB.FilteredElementCollector(document).OfClass(DB.View)
                          if not view.IsTemplate and str(view.ViewType) != 'ThreeD' and
                          settings.IsViewIdValidForPreview(view.Id)]
            candidates.sort(key=lambda view: (preferred is None or view.Id != preferred.Id,
                                               str(view.ViewType) not in ('FloorPlan', 'EngineeringPlan', 'DraftingView'),
                                               element_name(view)))
            candidates = [view for view in candidates if self._supports_type_visibility(view)]
            if not candidates:
                row['preview_detail'] = 'No valid 2D Family Editor view supports Preview Visibility On.'
                return False
            transaction = DB.Transaction(document, 'Temporary label thumbnail settings')
            try:
                transaction.Start()
                if not self._enable_type_visibility(candidates[0]):
                    raise ValueError('Could not enable Preview Visibility On for the label preview.')
                settings.ForceViewUpdate(True)
                document.Regenerate()
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit could not update the label preview view.')
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
            finally:
                transaction.Dispose()
            directory = tempfile.mkdtemp(prefix='label_preview_', dir=self.store.preview_dir)
            self._preview_workdirs.append(directory)
            filename = os.path.join(directory, 'thumbnail.rfa')
            options.PreviewViewId = candidates[0].Id
            options.OverwriteExistingFile = False
            options.MaximumBackups = 1
            document.SaveAs(filename, options)
            if not self._save_embedded_preview(filename, destination):
                return False
            image = load_bitmap(destination)
            try:
                if has_content(image):
                    return True
            finally:
                image.Dispose()
            os.remove(destination)
            return False
        except Exception as error:
            row['preview_detail'] = 'Family Editor thumbnail: {0}'.format(error)
            return False
        finally:
            options.Dispose()
            settings.Dispose()

    def _cleanup_preview_workdirs(self):
        # These are exact mkdtemp directories owned by this preview operation,
        # under the user-cache root; never a user-selected source directory.
        root = os.path.normcase(os.path.realpath(self.store.preview_dir)) + os.sep
        remaining = []
        for directory in self._preview_workdirs:
            target = os.path.normcase(os.path.realpath(directory))
            if not target.startswith(root):
                remaining.append(directory)
                continue
            try:
                shutil.rmtree(directory)
            except OSError:
                remaining.append(directory)
        self._preview_workdirs = remaining

    def _render_type(self, document, row, destination):
        name = row.get('type_name', '')
        if name:
            family_type = next((t for t in document.FamilyManager.Types if t.Name == name), None)
            if family_type is None:
                raise ValueError('The selected type was not found in the temporary family document.')
            # Only the isolated family document is modified, never the project
            # or source RFA. It is ALWAYS closed without saving after rendering.
            transaction = DB.Transaction(document, 'Temporary thumbnail type')
            try:
                transaction.Start()
                document.FamilyManager.CurrentType = family_type
                document.Regenerate()
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit could not evaluate this family type.')
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
            finally:
                transaction.Dispose()
        if needs_label_preview(row):
            if self._saved_label_preview(document, row, destination):
                return 'Family Editor label preview (sample values, not project values)'
            # Export may still include labels on some Revit builds/view types.
            if self._export_preview(document, row, destination):
                return 'Family Editor annotation export'
            # A curve-only approximation omits all Label elements. Never treat
            # a box outline as a complete Tag/Annotation preview.
            return ''
        # Export preserves text/nested symbols and is preferable to a line-only
        # approximation. Curves/filled regions cover profiles with no usable view.
        if self._export_preview(document, row, destination):
            return 'Type preview'
        # Collecting raw curves ignores visibility formulas even if a view is
        # in preview mode. Never use that approximation for multi-type families.
        if not has_multiple_types(row) and self._geometry_preview(document, row, destination):
            return 'Geometry preview'
        return ''

    def preview(self, row):
        """Type-aware native -> temporary family export -> geometry -> saved PNG."""
        source = row.get('path')
        label_preview = needs_label_preview(row)
        multiple_types = has_multiple_types(row)
        symbol = None
        if source:
            stamp = file_stamp(source)
            if stamp != row['stamp']:
                row['preview_note'] = 'RFA changed. Select Folder again.'
                return None
        else:
            if row.get('symbol_id') is not None:
                symbol = self.doc.GetElement(DB.ElementId(row['symbol_id']))
            family = self.doc.GetElement(DB.ElementId(row['family_id']))
            if family is None:
                return None
            stamp = [str(family.VersionGuid), str(symbol.VersionGuid) if symbol else '', 'preview-v2']
        # Old thumbnails were generated with preview visibility Off. Use a new
        # cache identity without deleting the user's other cached data.
        stamp = list(stamp) + ['type-visibility-on-v1']
        if label_preview:
            stamp = list(stamp) + ['annotation-labels-v1']
            # For disk libraries, the original saved preview is the one seen
            # in the Family Open dialog and includes sample label text.
            if source and not multiple_types:
                saved = row.get('preview')
                if not saved or not os.path.isfile(saved):
                    saved = self.store.preview_path(row.get('family_key', row['key']) + '|saved-labels', stamp)
                    if not self._save_embedded_preview(source, saved):
                        saved = None
                if saved and os.path.isfile(saved):
                    image = load_bitmap(saved)
                    if has_content(image):
                        row['preview_note'] = 'Saved FAMILY preview (sample labels; may differ from this type)'
                        return image
                    image.Dispose()
        destination = self.store.preview_path(row['key'], stamp)
        if os.path.isfile(destination):
            row['preview_note'] = ('Cached Family Editor annotation preview (sample values)' if label_preview
                                   else 'Cached type/geometry preview')
            return load_bitmap(destination)
        if symbol is not None and not needs_type_visibility(row):
            try:
                native = symbol.GetPreviewImage(Size(256, 256))
                if native is not None:
                    if has_content(native):
                        row['preview_note'] = 'Revit type thumbnail'
                        return native
                    native.Dispose()
            except Exception as error:
                row['preview_note'] = str(error)
        temporary = None
        note = ''
        try:
            if source:
                if self._existing_family_document(source) is not None:
                    raise ValueError('This RFA is already open; it was not changed for preview.')
                temporary = self.uiapp.Application.OpenDocumentFile(source)
            else:
                if not family.IsEditable:
                    raise ValueError('This family cannot be opened for a temporary preview.')
                before = list(self.uiapp.Application.Documents)
                candidate = self.doc.EditFamily(family)
                if candidate in before:
                    raise ValueError('The family is already open; it was not changed for preview.')
                temporary = candidate
            note = self._render_type(temporary, row, destination)
        except Exception as error:
            row['preview_note'] = 'Type preview failed: {0}'.format(error)
        finally:
            if temporary is not None:
                try:
                    closed = temporary.Close(False)
                except Exception as error:
                    raise BackgroundDocumentError('Could not close temporary preview family: {0}'.format(error))
                if not closed:
                    raise BackgroundDocumentError('Could not close temporary preview family.')
                self._cleanup_preview_workdirs()
        if note:
            row['preview_note'] = note
            return load_bitmap(destination)
        # This fallback is a FAMILY image, not a per-type image. Label it openly.
        saved = row.get('preview')
        if saved and os.path.isfile(saved) and not multiple_types:
            row['preview_note'] = 'Saved FAMILY preview (may differ from this type)'
            return load_bitmap(saved)
        if row.get('preview_detail'):
            row['preview_note'] = row['preview_detail']
        elif multiple_types:
            row['preview_note'] = 'No verified per-type preview; the shared family thumbnail was intentionally skipped.'
        return None

    def apply(self, row, type_name, confirm):
        """Browser is already closed. Loading owns a transaction; placement owns its own."""
        if self.uiapp.ActiveUIDocument is None or self.uiapp.ActiveUIDocument.Document != self.doc:
            raise ValueError('The active project changed. Reopen the browser.')
        if self.doc.IsReadOnly or self.doc.IsModifiable:
            raise ValueError('Finish the current Revit edit/transaction before loading or placing.')
        family = None
        loaded = False
        if row.get('path'):
            if file_stamp(row['path']) != row['stamp']:
                raise ValueError('The RFA changed since indexing. Select Folder again before loading.')
            options = ConflictOptions(confirm)
            reference = clr.Reference[DB.Family]()
            transaction = DB.Transaction(self.doc, 'Library: Load Family')
            try:
                transaction.Start()
                success = self.doc.LoadFamily(row['path'], options, reference)
                family = reference.Value
                if not success or family is None or options.declined:
                    transaction.RollBack()
                    return False, 'Load cancelled or the family is already identical. No placement was started.'
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit did not commit the family load.')
                loaded = True
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
            finally:
                transaction.Dispose()
        else:
            family = self.doc.GetElement(DB.ElementId(row['family_id']))
        if family is None:
            raise ValueError('The selected family is no longer available.')
        current = family_row(family)
        if placement_reason(current):
            return loaded, ('Family loaded.' if loaded else placement_reason(current))
        symbols = [self.doc.GetElement(i) for i in family.GetFamilySymbolIds()]
        symbol = next((s for s in symbols if element_name(s) == type_name), None)
        if symbol is None:
            raise ValueError('The selected type is no longer available. Reopen the browser.')
        # Revit's interactive placement method handles activation/transactions.
        try:
            self.uidoc.PromptForFamilyInstancePlacement(symbol)
        except OperationCanceledException:
            return True, ('Placement ended. The family remains loaded.' if loaded else 'Placement ended.')
        return True, 'Placement ended.'
