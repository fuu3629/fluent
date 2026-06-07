"""
Grasshopper Python component script for exporting geometry to STEP/STP.

Inputs expected on the component:
    geometry             Geometry, list, or data tree to export.
    file_path            Output .stp/.step path.
    run_export           Export trigger. Export runs only when True.
    clear_before_export  Optional bool. Default False.
    delete_after_export  Optional bool. Default False.
    layer_name           Optional string. Default "modefrontier_export".

Outputs expected on the component:
    success
    message
    exported_path
    baked_ids
    debug_log

No pip packages are required. This script uses RhinoCommon inside Rhino.
"""

import os

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System


def _optional_input(name, default_value):
    return globals()[name] if name in globals() and globals()[name] is not None else default_value


def _flatten_geometry(value):
    if value is None:
        return []

    if hasattr(value, "Branches"):
        items = []
        for branch in value.Branches:
            items.extend(_flatten_geometry(branch))
        return items

    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            items.extend(_flatten_geometry(item))
        return items

    return [value]


def _ensure_layer(doc, name):
    layer_index = doc.Layers.FindByFullPath(name, -1)
    if layer_index >= 0:
        return layer_index

    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    return doc.Layers.Add(layer)


def _clear_document(doc):
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    ids = [obj.Id for obj in doc.Objects.GetObjectList(settings)]
    if ids:
        doc.Objects.Delete(ids, True)


def _find_rhino_object(doc, object_id):
    if doc is None or not hasattr(doc, "Objects"):
        return None

    rhino_object = doc.Objects.FindId(object_id)
    if rhino_object is None:
        rhino_object = doc.Objects.Find(object_id)
    return rhino_object


def _coerce_guid_geometry(search_docs, object_id):
    current_doc = sc.doc
    try:
        for doc in search_docs:
            if doc is None:
                continue

            sc.doc = doc
            geometry_item = rs.coercegeometry(object_id)
            if isinstance(geometry_item, Rhino.Geometry.GeometryBase):
                return geometry_item

            rhino_object = _find_rhino_object(doc, object_id)
            if rhino_object is not None:
                return rhino_object.Geometry
    finally:
        sc.doc = current_doc

    return None


def _coerce_geometry(search_docs, item):
    if isinstance(item, System.Guid):
        geometry_item = _coerce_guid_geometry(search_docs, item)
        if geometry_item is not None:
            return geometry_item

    if isinstance(item, Rhino.Geometry.GeometryBase):
        return item

    if hasattr(item, "Geometry"):
        geometry_item = item.Geometry
        if isinstance(geometry_item, Rhino.Geometry.GeometryBase):
            return geometry_item

    if hasattr(item, "Value"):
        value = item.Value
        if isinstance(value, Rhino.Geometry.GeometryBase):
            return value

    if hasattr(item, "ScriptVariable"):
        value = item.ScriptVariable()
        if isinstance(value, Rhino.Geometry.GeometryBase):
            return value

    return None


def _copy_geometry(geometry_item):
    if hasattr(geometry_item, "Duplicate"):
        return geometry_item.Duplicate()
    if hasattr(geometry_item, "DuplicateGeometry"):
        return geometry_item.DuplicateGeometry()
    return geometry_item


def _describe_item(item):
    if item is None:
        return "None"
    if isinstance(item, System.Guid):
        return "Guid({0})".format(item)
    return type(item).__name__


def _prepare_geometries(search_docs, items):
    geometries = []
    skipped_types = []
    for item in items:
        geometry_item = _coerce_geometry(search_docs, item)
        if geometry_item is None:
            skipped_types.append(_describe_item(item))
            continue
        geometries.append(_copy_geometry(geometry_item))

    return geometries, skipped_types


def _bake_geometry(doc, geometries, layer_index):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index

    object_ids = []
    for geometry_item in geometries:
        object_id = doc.Objects.Add(geometry_item, attributes)
        if object_id != System.Guid.Empty:
            object_ids.append(object_id)

    doc.Views.Redraw()
    return object_ids


def _quote_path(path):
    return '"' + path.replace('"', '\\"') + '"'


def _export_selected(doc, object_ids, path):
    output_dir = os.path.dirname(path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    if os.path.isfile(path):
        os.remove(path)

    Rhino.RhinoApp.RunScript("_-SelNone", False)
    for object_id in object_ids:
        rhino_object = doc.Objects.FindId(object_id)
        if rhino_object is not None:
            rhino_object.Select(True)

    doc.Views.Redraw()
    command = "_-Export {0} _Enter _Enter".format(_quote_path(path))
    return Rhino.RhinoApp.RunScript(command, False)


def _write_debug_log(path, lines):
    if not path:
        return

    log_path = path + ".export_log.txt"
    with open(log_path, "w") as log_file:
        log_file.write("\n".join(lines) + "\n")


success = False
message = "run_export is False. Export was skipped."
exported_path = file_path if "file_path" in globals() else None
baked_ids = []
debug_log = [message]

if _optional_input("run_export", False):
    old_doc = sc.doc
    rhino_doc = Rhino.RhinoDoc.ActiveDoc

    try:
        if rhino_doc is None:
            raise Exception("No active Rhino document was found.")

        export_path = os.path.abspath(str(file_path))
        if not export_path.lower().endswith((".stp", ".step")):
            export_path += ".stp"
        debug_log = ["Export path: " + export_path]

        export_geometry = _flatten_geometry(geometry)
        debug_log.append("Input geometry count: {0}".format(len(export_geometry)))
        if not export_geometry:
            raise Exception("No geometry was supplied to export.")

        prepared_geometry, skipped_types = _prepare_geometries(
            [old_doc, rhino_doc],
            export_geometry,
        )
        debug_log.append("Prepared geometry count: {0}".format(len(prepared_geometry)))
        if skipped_types:
            debug_log.append("Skipped input types: " + ", ".join(skipped_types))
        if not prepared_geometry:
            raise Exception(
                "No valid Rhino geometry could be prepared. "
                "Input types: {0}".format(", ".join([_describe_item(item) for item in export_geometry]))
            )

        if _optional_input("clear_before_export", False):
            debug_log.append("Clearing Rhino document before export.")
            _clear_document(rhino_doc)

        export_layer = _optional_input("layer_name", "modefrontier_export")
        sc.doc = rhino_doc
        layer_index = _ensure_layer(rhino_doc, export_layer)
        baked_ids = _bake_geometry(rhino_doc, prepared_geometry, layer_index)
        debug_log.append("Baked object count: {0}".format(len(baked_ids)))
        if not baked_ids:
            raise Exception("No valid Rhino geometry could be baked.")

        if not _export_selected(rhino_doc, baked_ids, export_path):
            raise Exception("Rhino STEP export command failed.")
        if not os.path.isfile(export_path):
            raise Exception("STEP export command finished, but file was not created.")

        if _optional_input("delete_after_export", False):
            for object_id in baked_ids:
                rhino_doc.Objects.Delete(object_id, True)
            rhino_doc.Views.Redraw()
            debug_log.append("Deleted baked objects after export.")

        success = True
        message = "STEP export finished."
        exported_path = export_path
        debug_log.append(message)
    except Exception as exc:
        success = False
        message = str(exc)
        debug_log.append("ERROR: " + message)
    finally:
        _write_debug_log(exported_path, debug_log)
        sc.doc = old_doc
