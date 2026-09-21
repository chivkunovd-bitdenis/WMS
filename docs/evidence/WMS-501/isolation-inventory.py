"""Rebuild the static route catalogue without importing app/settings or reading .env."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = []
for path in sorted((root / 'backend/app/api').glob('*.py')):
    source = path.read_text()
    tree = ast.parse(source)
    routers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'APIRouter':
            prefix = next((ast.literal_eval(k.value) for k in node.value.keywords if k.arg == 'prefix'), '')
            for target in node.targets:
                if isinstance(target, ast.Name):
                    routers[target.id] = prefix
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name) and dec.func.value.id in routers):
                continue
            body = ast.get_source_segment(source, node)
            deps = sorted({ast.unparse(call.args[0]) for call in ast.walk(node)
                           if isinstance(call, ast.Call) and ast.unparse(call.func) == 'Depends' and call.args})
            calls = sorted({ast.unparse(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)})
            out.append({'file': str(path.relative_to(root)), 'line': node.lineno, 'method': dec.func.attr.upper(),
                        'router': dec.func.value.id,
                        'path': routers[dec.func.value.id] + (ast.literal_eval(dec.args[0]) if dec.args else ''),
                        'handler': node.name, 'direct_depends': deps, 'calls': calls,
                        'tenant_literal': 'tenant_id' in body})
output = Path(__file__).with_name('isolation-route-inventory.json')
output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print(f'{len(out)} static declarations, {len({r["file"] for r in out})} modules')
