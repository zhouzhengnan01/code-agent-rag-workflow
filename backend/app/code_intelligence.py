"""Repository code intelligence with AST-first indexing and language fallbacks."""
import ast
import hashlib
import json
import os
import re
from pathlib import Path

from .db import connect, now


EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php"}
IGNORED = {".git", ".codezzn-worktrees", "node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"}
GENERIC_SYMBOL = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|enum|struct|trait|function|func|def)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
GENERIC_IMPORT = re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)|^\s*(?:import|use|include)\s+([^;\n]+))", re.MULTILINE)


def _files(root, limit=5000):
    result = []
    for directory, folders, names in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if name not in IGNORED and not (Path(directory) / name).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix.lower() not in EXTENSIONS: continue
            try:
                path.resolve().relative_to(root.resolve())
                if path.stat().st_size <= 2_000_000: result.append(path)
            except (OSError, ValueError): continue
            if len(result) >= limit: return result
    return result


class PythonVisitor(ast.NodeVisitor):
    def __init__(self, relative):
        self.relative = relative
        self.scope = []
        self.symbols, self.calls, self.imports = [], [], []
        self.references, self.bindings, self.pending = [], {}, []
        self.import_targets = {}

    def _bind(self, name, scope=None):
        scope = tuple(self.scope) if scope is None else tuple(scope)
        self.bindings.setdefault(scope, set()).add(name)
        self.import_targets.pop((scope, name), None)

    def _resolve(self, name, scope):
        for length in range(len(scope), -1, -1):
            prefix = tuple(scope[:length])
            if name in self.bindings.get(prefix, set()):
                return self.import_targets.get((prefix, name), ".".join([*prefix, name]))
        return None

    def finish(self):
        for item, scope, name in self.pending:
            first, *tail = name.split(".")
            resolved = self._resolve(first, scope)
            # Attribute call resolution is only justified for explicit import aliases.
            is_import = False
            for length in range(len(scope), -1, -1):
                prefix = tuple(scope[:length])
                if first in self.bindings.get(prefix, set()):
                    is_import = (prefix, first) in self.import_targets
                    break
            item["resolved_target"] = ".".join([resolved, *tail]) if resolved and (not tail or is_import) else None
            item["analysis"] = "python-lexical" if item["resolved_target"] else "unresolved"

    def _symbol(self, node, kind):
        qualified = ".".join([*self.scope, node.name])
        self._bind(node.name)
        self.symbols.append({"name": node.name, "qualified_name": qualified, "kind": kind, "path": self.relative, "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno)})
        self.scope.append(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]: self._bind(arg.arg)
            for arg in (node.args.vararg, node.args.kwarg):
                if arg: self._bind(arg.arg)
        self.generic_visit(node); self.scope.pop()

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Param)): self._bind(node.id)
        item = {"name": node.id, "path": self.relative, "line": node.lineno, "column": node.col_offset, "scope": ".".join(self.scope), "definition": isinstance(node.ctx, ast.Store)}
        self.references.append(item); self.pending.append((item, self.scope[:], node.id))

    def visit_ClassDef(self, node): self._symbol(node, "class")
    def visit_FunctionDef(self, node): self._symbol(node, "function")
    def visit_AsyncFunctionDef(self, node): self._symbol(node, "function")

    def visit_Call(self, node):
        target = None
        if isinstance(node.func, ast.Name): target = node.func.id
        elif isinstance(node.func, ast.Attribute): target = node.func.attr
        if target:
            item = {"caller": ".".join(self.scope) or "<module>", "callee": target, "path": self.relative, "line": node.lineno, "analysis": "unresolved-attribute"}
            self.calls.append(item)
            def dotted(value):
                if isinstance(value, ast.Name): return value.id
                if isinstance(value, ast.Attribute):
                    prefix = dotted(value.value)
                    return prefix + "." + value.attr if prefix else None
            full = dotted(node.func)
            if full: self.pending.append((item, self.scope[:], full))
        self.generic_visit(node)

    def visit_Import(self, node):
        self.imports.extend(alias.name for alias in node.names)
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self._bind(name)
            self.import_targets[(tuple(self.scope), name)] = alias.name if alias.asname else name

    def visit_ImportFrom(self, node):
        if node.module: self.imports.append(node.module)
        for alias in node.names:
            name = alias.asname or alias.name
            self._bind(name)
            self.import_targets[(tuple(self.scope), name)] = "." * node.level + ".".join(part for part in (node.module, alias.name) if part)


def _analyze(path, root):
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    symbols, calls, imports = [], [], []
    if path.suffix.lower() == ".py":
        try:
            visitor = PythonVisitor(relative); visitor.visit(ast.parse(text, filename=relative)); visitor.finish()
            symbols, calls, imports = visitor.symbols, visitor.calls, visitor.imports
        except SyntaxError:
            pass
    if not symbols:
        for match in GENERIC_SYMBOL.finditer(text):
            symbols.append({"name": match.group(1), "qualified_name": match.group(1), "kind": "symbol", "path": relative, "line": text.count("\n", 0, match.start()) + 1, "end_line": text.count("\n", 0, match.end()) + 1})
    if not imports:
        imports = [next(value for value in match.groups() if value).strip() for match in GENERIC_IMPORT.finditer(text)]
    return text, symbols, calls, imports


def rebuild_index(root, force=False):
    """Digest-checked incremental index; deleted files are removed on every query."""
    root = Path(root).resolve(); indexed, symbol_count, changed = 0, 0, 0
    with connect() as db:
        previous = {row["path"]: row["digest"] for row in db.execute("SELECT path,digest FROM code_files WHERE workspace=?", (str(root),))}
        present = set()
        for path in _files(root):
            try:
                relative = path.relative_to(root).as_posix()
                digest = hashlib.sha256(path.read_text(encoding="utf-8", errors="replace").encode()).hexdigest()
                present.add(relative); indexed += 1
                if not force and previous.get(relative) == digest: continue
                text, symbols, calls, imports = _analyze(path, root)
            except (OSError, UnicodeError): continue
            changed += 1
            for table in ("code_files", "code_symbols", "code_edges"):
                db.execute(f"DELETE FROM {table} WHERE workspace=? AND path=?", (str(root), relative))
            db.execute("INSERT INTO code_files(workspace,path,language,digest,indexed_at) VALUES(?,?,?,?,?)", (str(root), relative, path.suffix.lstrip("."), digest, now()))
            for item in symbols:
                db.execute("INSERT INTO code_symbols(workspace,path,name,qualified_name,kind,line,end_line) VALUES(?,?,?,?,?,?,?)", (str(root), relative, item["name"], item["qualified_name"], item["kind"], item["line"], item["end_line"]))
            for item in calls:
                db.execute("INSERT INTO code_edges(workspace,path,kind,source,target,line) VALUES(?,?,?,?,?,?)", (str(root), relative, "call", item["caller"], item.get("resolved_target") or item["callee"], item["line"]))
            for target in imports:
                db.execute("INSERT INTO code_edges(workspace,path,kind,source,target,line) VALUES(?,?,?,?,?,?)", (str(root), relative, "import", relative, target, 1))
        for relative in previous.keys() - present:
            for table in ("code_files", "code_symbols", "code_edges"):
                db.execute(f"DELETE FROM {table} WHERE workspace=? AND path=?", (str(root), relative))
        symbol_count = db.execute("SELECT COUNT(*) FROM code_symbols WHERE workspace=?", (str(root),)).fetchone()[0]
    return {"workspace": str(root), "files": indexed, "symbols": symbol_count, "changed_files": changed, "deleted_files": len(previous.keys() - present), "analysis": "python-lexical; non-Python heuristic"}


def symbols(root, query="", limit=100):
    root = str(Path(root).resolve()); query = str(query or "")
    with connect() as db:
        count = db.execute("SELECT COUNT(*) value FROM code_files WHERE workspace=?", (root,)).fetchone()["value"]
    rebuild_index(root)
    with connect() as db:
        rows = db.execute("SELECT path,name,qualified_name,kind,line,end_line FROM code_symbols WHERE workspace=? AND (name LIKE ? OR qualified_name LIKE ?) ORDER BY name LIMIT ?", (root, f"%{query}%", f"%{query}%", min(int(limit), 500))).fetchall()
    return [{**dict(row), "analysis": "python-ast" if row["path"].endswith(".py") else "heuristic"} for row in rows]


def references(root, symbol, limit=200):
    root = Path(root).resolve(); pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    result = []
    for path in _files(root):
        try:
            if path.suffix.lower() == ".py":
                visitor = PythonVisitor(path.relative_to(root).as_posix())
                visitor.visit(ast.parse(path.read_text(encoding="utf-8", errors="replace"))); visitor.finish()
                for item in visitor.references:
                    if (item["resolved_target"] == symbol if "." in symbol else item["name"] == symbol):
                        result.append(item)
                        if len(result) >= limit: return result
                for item in visitor.symbols:
                    if item["qualified_name"] == symbol or ("." not in symbol and item["name"] == symbol): result.append({**item, "definition": True, "analysis": "python-ast"})
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    result.append({"path": path.relative_to(root).as_posix(), "line": number, "text": line.strip()[:500], "analysis": "heuristic-text"})
                    if len(result) >= limit: return result
        except (OSError, SyntaxError): continue
    return result


def graph(root, kind="call", symbol="", limit=300):
    root = str(Path(root).resolve())
    with connect() as db:
        count = db.execute("SELECT COUNT(*) value FROM code_files WHERE workspace=?", (root,)).fetchone()["value"]
    rebuild_index(root)
    with connect() as db:
        rows = db.execute("SELECT path,kind,source,target,line FROM code_edges WHERE workspace=? AND kind=? AND (?='' OR source LIKE ? OR target LIKE ?) LIMIT ?", (root, kind, symbol, f"%{symbol}%", f"%{symbol}%", min(int(limit), 1000))).fetchall()
    return [{**dict(row), "analysis": "python-lexical" if row["path"].endswith(".py") else "heuristic"} for row in rows]
