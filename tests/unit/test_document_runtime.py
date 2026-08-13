"""Tests for the centralized FreeCAD-side document policy."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from freecad_mcp.bridge._document_runtime import DOCUMENT_RESOLUTION_RUNTIME


def _resolver_namespace(active_document=None):
    documents = {}

    def new_document(name):
        document = SimpleNamespace(Name=name)
        documents[name] = document
        return document

    freecad = SimpleNamespace(
        ActiveDocument=active_document,
        listDocuments=lambda: documents,
        newDocument=new_document,
    )
    namespace = {"FreeCAD": freecad}
    exec(DOCUMENT_RESOLUTION_RUNTIME, namespace)  # noqa: S102
    return namespace["_resolve_document"], documents


def test_resolver_is_strict_by_default_and_import_can_opt_in() -> None:
    resolve_document, documents = _resolver_namespace()

    with pytest.raises(ValueError, match="Create it explicitly with create_document"):
        resolve_document("TypoModel")
    assert documents == {}

    imported = resolve_document(
        "ImportedModel", create_if_missing=True, default_name="Imported"
    )
    assert imported.Name == "ImportedModel"
    assert list(documents) == ["ImportedModel"]


def test_non_import_tool_modules_do_not_create_documents_directly() -> None:
    root = Path(__file__).parents[2] / "src" / "freecad_mcp" / "tools"
    strict_modules = (
        "objects.py",
        "spreadsheet.py",
        "draft.py",
        "partdesign.py",
        "view.py",
    )
    for filename in strict_modules:
        source = (root / filename).read_text(encoding="utf-8")
        assert "FreeCAD.newDocument" not in source, filename

    import_source = (root / "export.py").read_text(encoding="utf-8")
    assert "create_if_missing=True" in import_source
    assert 'default_name="Imported"' in import_source
