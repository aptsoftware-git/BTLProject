import os
import re
from pathlib import Path

src_dir = Path(r"C:\Users\sanju\INTERNSHIP-APT\BTLProject\ai-proofreader-frontend\src")

# Common browser globals & React builtins
GLOBALS = {
    "console", "window", "document", "localStorage", "sessionStorage", "fetch",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval", "alert",
    "confirm", "prompt", "URLSearchParams", "FormData", "XMLHttpRequest",
    "Error", "Math", "Date", "JSON", "Object", "Array", "String", "Number",
    "Boolean", "RegExp", "Promise", "Event", "URL", "Blob", "navigator",
    "isNaN", "parseInt", "parseFloat", "encodeURIComponent", "decodeURIComponent",
    "React", "useRef", "useState", "useEffect", "useMemo", "useCallback", "useContext", "useReducer",
    "Map", "Set", "t", "e", "i", "err", "evt", "props", "globalThis", "undefined"
}

def analyze_file(filepath):
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find identifier usages vs declarations
    # Look for handlers or JSX attributes like onClick={() => setX(...)} or condition {statusDetailsExpanded && ...}
    # Specifically search for set[A-Z]\w+ calls or identifiers that are not declared
    
    # 1. Extract all state setters called: set[A-Z]\w+
    setters = set(re.findall(r'\b(set[A-Z]\w+)\b', content))
    # 2. Extract all state getters referenced in setX(!getter) or condition
    
    # Declarations in content: const/let/var [x, setX], const/let/var x, function x, import ...
    declared = set(GLOBALS)
    for match in re.finditer(r'\b(?:const|let|var|function|class)\s+([a-zA-Z0-9_$,\s{}\[\]]+)', content):
        decl_str = match.group(1)
        names = re.findall(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b', decl_str)
        declared.update(names)
    
    for match in re.finditer(r'\bimport\s+({[^}]+}|[^{}\n]+)\s+from', content):
        names = re.findall(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b', match.group(1))
        declared.update(names)
        
    for match in re.finditer(r'(?:function\s+[a-zA-Z0-9_$]*|\(([^)]*)\)|([a-zA-Z0-9_$]+)\s*=>)\s*[{=]', content):
        params_str = match.group(1) or match.group(2) or ""
        names = re.findall(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b', params_str)
        declared.update(names)

    missing_setters = setters - declared
    print(f"File: {filepath.name}")
    if missing_setters:
        print(f"  Missing setters/decls: {missing_setters}")
    
    # Also check identifiers in JSX braces { ... }
    jsx_braces = re.findall(r'\{([^}]+)\}', content)
    missing_vars = set()
    for block in jsx_braces:
        # tokens in block
        tokens = re.findall(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b', block)
        for t in tokens:
            if t not in declared and not t.isdigit() and t not in ["true", "false", "null", "undefined", "style", "className", "id", "key", "onClick", "onChange"]:
                # Ignore object properties like obj.t
                missing_vars.add(t)
    
    if missing_vars:
        print(f"  Potentially undeclared JSX vars: {missing_vars}")

for p in src_dir.glob("**/*.jsx"):
    analyze_file(p)
