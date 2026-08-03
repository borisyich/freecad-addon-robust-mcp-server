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
    '''
).strip()
