import ast
import json
from pathlib import Path

root = Path("src/freecad_mcp/tools")
artifact_path = Path("artifacts/tool_inventory.json")
artifact_path.parent.mkdir(parents=True, exist_ok=True)

items = []

for p in sorted(root.glob("*.py")):
    if p.name in {"__init__.py", "utils.py"}:
        continue

    tree = ast.parse(p.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "tool"
                ):
                    items.append({
                        "module": p.stem,
                        "tool": node.name,
                        "args": [
                            a.arg for a in node.args.args
                            if a.arg not in {"self", "mcp", "get_bridge"}
                        ],
                        "lineno": node.lineno,
                    })

with open(artifact_path, "w", encoding="utf-8") as file:
    json.dump(items, file, indent=4, ensure_ascii=False)

print(f"Artifacts saved: {artifact_path}")
print(f"\nTOTAL_TOOLS={len(items)}")
