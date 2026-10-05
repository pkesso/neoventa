import re
def parse(s):
    tok = re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', s)
    st = [[]]
    for t in tok:
        if t == "(": st.append([])
        elif t == ")":
            x = st.pop(); st[-1].append(x)
        else: st[-1].append(t)
    return st[0]
def fmt(n, ind=0):
    T = "\t" * ind
    if all(not isinstance(x, list) for x in n):
        return T + "(" + " ".join(n) + ")"
    atoms = []
    i = 0
    while i < len(n) and not isinstance(n[i], list):
        atoms.append(n[i]); i += 1
    out = [T + "(" + " ".join(atoms)]
    rest = n[i:]
    if rest and all(isinstance(x, list) and x and x[0] == "xy" for x in rest):
        out.append("\t" * (ind + 1) + " ".join("(" + " ".join(x) + ")" for x in rest))
    else:
        for x in rest:
            out.append(fmt(x, ind + 1) if isinstance(x, list) else "\t" * (ind + 1) + x)
    out.append(T + ")")
    return "\n".join(out)
def k10_symbol(v8text, name):
    """convert one of my v8 lib_symbol strings into KiCad 10 structure."""
    n = parse(v8text)[0]
    n[1] = '"' + name + '"'
    out = [n[0], n[1]]
    for x in n[2:]:
        if isinstance(x, list) and x[0] == "pin_names":
            out.append(x)
        elif isinstance(x, list) and x[0] == "on_board":
            out += [x, ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"]]
        elif isinstance(x, list) and x[0] == "property":
            if x[2] == '"~"': x[2] = '""'
            new = x[:4] + [["show_name", "no"], ["do_not_autoplace", "no"]]
            hidden = any(isinstance(e, list) and e[0] == "effects" and any(isinstance(f, list) and f[0] == "hide" for f in e) for e in x)
            if hidden: new.append(["hide", "yes"])
            for e in x[4:]:
                if isinstance(e, list) and e[0] == "effects":
                    new.append([f for f in e if not (isinstance(f, list) and f[0] == "hide")])
            out.append(new)
        else:
            out.append(x)
    def fixnames(node):
        for e in node:
            if isinstance(e, list):
                if e[0] == "name" and len(e) > 1 and e[1] == '"~"':
                    e[1] = '""'
                fixnames(e)
    fixnames(out)
    out.append(["embedded_fonts", "no"])
    return fmt(out, 1)
