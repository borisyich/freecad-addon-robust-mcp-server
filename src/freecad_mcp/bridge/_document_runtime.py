"""Shared FreeCAD-side document resolution contract."""

DOCUMENT_RESOLUTION_RUNTIME = r'''
def _resolve_document(requested_name, create_if_missing=False, default_name="Unnamed"):
    """Resolve one explicit/active document under a caller-selected policy."""
    doc = (
        FreeCAD.ActiveDocument
        if requested_name is None
        else FreeCAD.listDocuments().get(requested_name)
    )
    if doc is None and create_if_missing:
        doc = FreeCAD.newDocument(requested_name or default_name)
    if doc is None:
        target = (
            f"named document {requested_name!r}"
            if requested_name is not None
            else "an active document"
        )
        raise ValueError(
            f"Document not found: expected {target}. "
            "Create it explicitly with create_document first."
        )
    return doc
'''.strip()
