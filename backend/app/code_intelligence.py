"""Repository code intelligence with AST-first indexing and language fallbacks."""
import ast
import hashlib
import json
import re
from pathlib import Path

from .db import connect, now


EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php"}
IGNORED = {".git", ".codezzn-worktrees", "node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"}
GENERIC_SYMBOL = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|enum|struct|trait|function|func|def)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
GENERIC_IMPORT = re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)|^\s*(?:import|use|include)\s+([^;\n]+))", re.MULTILINE)


def _files(root, limit=5000):
    result = []
    for path in root.rglob("*"):
        if len(result) >= limit:
            break
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS or any(part in IGNORED for part in path.parts):
            continue
        try:
            if path.stat().st_size <= 2_000_000:
                result.append(path)
        except OSError:
            continue
    return result


class PythonVisitor(ast.NodeVisitor):
    def __init__(self, relative):
        self.relative = relative
        self.scope = []
        self.symbols, self.calls, self.imports = [], [], []

    def _symbol(self, node, kind):
        qualified = ".".join([*self.scope, node.name])
        self.symbols.append({"name": node.name, "qualified_name": qualified, "kind": kind, "path": self.relative, "line": node.lineno, "end_line": getattr(node, "end_lineno", node.lineno)})
        self.scope.append(node.name); self.generic_visit(node); self.scope.pop()

    def visit_ClassDef(self, node): self._symbol(node, "class")
    def visit_FunctionDef(self, node): self._symbol(node, "function")
    def visit_AsyncFunctionDef(self, node): self._symbol(node, "function")

    def visit_Call(self, node):
        target = None
        if isinstance(node.func, ast.Name): target = node.func.id
        elif isinstance(node.func, ast.Attribute): target = node.func.attr
        if target:
            self.calls.append({"caller": ".".join(self.scope) or "<module>", "callee": target, "path": self.relative, "line": node.lineno})
        self.generic_visit(node)

    def visit_Import(self, node):
        self.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node):
        if node.module: self.imports.append(node.module)


def _analyze(path, root):
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    symbols, calls, imports = [], [], []
    if path.suffix.lower() == ".py":
        try:
            visitor = PythonVisitor(relative); visitor.visit(ast.parse(text, filename=relative))
            symbols, calls, imports = visitor.symbols, visitor.calls, visitor.imports
        except SyntaxError:
            pass
    if not symbols:
        for match in GENERIC_SYMBOL.finditer(text):
            symbols.append({"name": match.group(1), "qualified_name": match.group(1), "kind": "symbol", "path": relative, "line": text.count("\n", 0, match.start()) + 1, "end_line": text.count("\n", 0, match.end()) + 1})
    if not imports:
        imports = [next(value for value in match.groups() if value).strip() for match in GENERIC_IMPORT.finditer(text)]
    return text, symbols, calls, imports


def rebuild_index(root):
    root = Path(root).resolve(); indexed, symbol_count = 0, 0
    with connect() as db:
        db.execute("DELETE FROM code_symbols WHERE workspace=?", (str(root),))
        db.execute("DELETE FROM code_edges WHERE workspace=?", (str(root),))
        db.execute("DELETE FROM code_files WHERE workspace=?", (str(root),))
        for path in _files(root):
            try: text, symbols, calls, imports = _analyze(path, root)
            except (OSError, UnicodeError): continue
            relative = path.relative_to(root).as_posix(); digest = hashlib.sha256(text.encode()).hexdigest()
            db.execute("INSERT INTO code_files(workspace,path,language,digest,indexed_at) VALUES(?,?,?,?,?)", (str(root), relative, path.suffix.lstrip("."), digest, now()))
            for item in symbols:
                db.execute("INSERT INTO code_symbols(workspace,path,name,qualified_name,kind,line,end_line) VALUES(?,?,?,?,?,?,?)", (str(root), relative, item["name"], item["qualified_name"], item["kind"], item["line"], item["end_line"]))
            for item in calls:
                db.execute("INSERT INTO code_edges(workspace,path,kind,source,target,line) VALUES(?,?,?,?,?,?)", (str(root), relative, "call", item["caller"], item["callee"], item["line"]))
            for target in imports:
                db.execute("INSERT INTO code_edges(workspace,path,kind,source,target,line) VALUES(?,?,?,?,?,?)", (str(root), relative, "import", relative, target, 1))
            indexed += 1; symbol_count += len(symbols)
    return {"workspace": str(root), "files": indexed, "symbols": symbol_count}


def symbols(root, query="", limit=100):
    root = str(Path(root).resolve()); query = str(query or "")
    with connect() as db:
        count = db.execute("SELECT COUNT(*) value FROM code_files WHERE workspace=?", (root,)).fetchone()["value"]
    if not count: rebuild_index(root)
    with connect() as db:
        rows = db.execute("SELECT path,name,qualified_name,kind,line,end_line FROM code_symbols WHERE workspace=? AND (name LIKE ? OR qualified_name LIKE ?) ORDER BY name LIMIT ?", (root, f"%{query}%", f"%{query}%", min(int(limit), 500))).fetchall()
    return [dict(row) for row in rows]


def references(root, symbol, limit=200):
    root = Path(root).resolve(); pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    result = []
    for path in _files(root):
        try:
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    result.append({"path": path.relative_to(root).as_posix(), "line": number, "text": line.strip()[:500]})
                    if len(result) >= limit: return result
        except OSError: continue
    return result


def graph(root, kind="call", symbol="", limit=300):
    root = str(Path(root).resolve())
    with connect() as db:
        count = db.execute("SELECT COUNT(*) value FROM code_files WHERE workspace=?", (root,)).fetchone()["value"]
    if not count: rebuild_index(root)
    with connect() as db:
        rows = db.execute("SELECT path,kind,source,target,line FROM code_edges WHERE workspace=? AND kind=? AND (?='' OR source LIKE ? OR target LIKE ?) LIMIT ?", (root, kind, symbol, f"%{symbol}%", f"%{symbol}%", min(int(limit), 1000))).fetchall()
    return [dict(row) for row in rows]
