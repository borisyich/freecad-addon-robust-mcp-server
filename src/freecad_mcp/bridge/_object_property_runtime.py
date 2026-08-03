"""Generated-runtime helpers for safe FreeCAD object property assignment."""

from textwrap import dedent

OBJECT_PROPERTY_COERCION_RUNTIME = dedent(
    r'''
    def _resolve_object_link(doc, value, property_name):
        if not isinstance(value, str):
            return value
        target = doc.getObject(value)
        if target is None:
            raise ValueError(
                f"Property {property_name!r} expects an object link, but "
                f"no object named {value!r} exists"
            )
        return target


    def _resolve_object_sublink(doc, value, property_name):
        if not isinstance(value, str):
            return value
        object_name, separator, subelement = value.partition(".")
        target = _resolve_object_link(doc, object_name, property_name)
        return (target, [subelement] if separator else [""])


    def _coerce_object_property_value(doc, obj, property_name, value):
        try:
            property_type = obj.getTypeIdOfProperty(property_name)
        except Exception:
            property_type = ""

        direct_link_types = {
            "App::PropertyLink",
            "App::PropertyLinkChild",
            "App::PropertyLinkGlobal",
            "App::PropertyLinkHidden",
        }
        if property_type in direct_link_types:
            return _resolve_object_link(doc, value, property_name)
        if property_type == "App::PropertyLinkList" and isinstance(value, list):
            return [
                _resolve_object_link(doc, item, property_name) for item in value
            ]
        if property_type == "App::PropertyLinkSub":
            return _resolve_object_sublink(doc, value, property_name)
        if property_type == "App::PropertyLinkSubList" and isinstance(value, list):
            return [
                _resolve_object_sublink(doc, item, property_name)
                for item in value
            ]
        return value


    def _normalize_hole_thread_type(value):
        if not isinstance(value, str):
            return value
        key = value.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
        aliases = {
            "NONE": "None",
            "ISO": "ISOMetricProfile",
            "ISOMETRICPROFILE": "ISOMetricProfile",
            "ISOFINE": "ISOMetricFineProfile",
            "ISOMETRICFINEPROFILE": "ISOMetricFineProfile",
            "UNC": "UNC",
            "UNF": "UNF",
            "UNEF": "UNEF",
        }
        return aliases.get(key, value)


    def _set_object_properties(doc, obj, properties):
        updates = dict(properties)
        for property_name in updates:
            if not hasattr(obj, property_name):
                raise ValueError(
                    f"Property {property_name!r} not found on object {obj.Name!r}"
                )

        is_hole = getattr(obj, "TypeId", "") == "PartDesign::Hole"
        original_thread_type = None
        original_thread_size = None
        if is_hole and "ThreadType" in updates:
            updates["ThreadType"] = _normalize_hole_thread_type(
                updates["ThreadType"]
            )
            original_thread_type = str(obj.ThreadType)
            original_thread_size = str(obj.ThreadSize)
            changing_profile = updates["ThreadType"] != original_thread_type
            if (
                changing_profile
                and updates["ThreadType"] != "None"
                and "ThreadSize" not in updates
            ):
                raise ValueError(
                    "Changing PartDesign::Hole.ThreadType requires ThreadSize "
                    "in the same edit_object call because FreeCAD resets the "
                    "size when the profile changes"
                )

        ordered_names = list(updates)
        if is_hole and "ThreadType" in updates:
            ordered_names.remove("ThreadType")
            ordered_names.insert(0, "ThreadType")
        if is_hole and "ThreadSize" in updates:
            ordered_names.remove("ThreadSize")
            thread_index = 1 if "ThreadType" in updates else 0
            ordered_names.insert(thread_index, "ThreadSize")

        try:
            for property_name in ordered_names:
                property_value = updates[property_name]
                if is_hole and property_name == "ThreadSize":
                    available_sizes = list(
                        obj.getEnumerationsOfProperty("ThreadSize")
                    )
                    if available_sizes and property_value not in available_sizes:
                        raise ValueError(
                            f"Unsupported ThreadSize {property_value!r} for "
                            f"{obj.ThreadType}. Available examples: "
                            + ", ".join(available_sizes[:12])
                        )
                setattr(
                    obj,
                    property_name,
                    _coerce_object_property_value(
                        doc, obj, property_name, property_value
                    ),
                )
        except Exception:
            if original_thread_type is not None:
                try:
                    obj.ThreadType = original_thread_type
                    available_sizes = list(
                        obj.getEnumerationsOfProperty("ThreadSize")
                    )
                    if original_thread_size in available_sizes:
                        obj.ThreadSize = original_thread_size
                except Exception:
                    pass
            raise
    '''
).strip()
