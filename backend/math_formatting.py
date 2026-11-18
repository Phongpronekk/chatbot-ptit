"""Format and extract mathematical notation for uploaded documents (PDF, DOCX, XLSX, MD)."""

import re

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

SUPER_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+-=()ni")
SUB_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓ", "0123456789+-=()aeox")

VULGAR_FRACTIONS = {
    "½": r"\frac{1}{2}",
    "⅓": r"\frac{1}{3}",
    "⅔": r"\frac{2}{3}",
    "¼": r"\frac{1}{4}",
    "¾": r"\frac{3}{4}",
    "⅕": r"\frac{1}{5}",
    "⅖": r"\frac{2}{5}",
    "⅗": r"\frac{3}{5}",
    "⅘": r"\frac{4}{5}",
    "⅙": r"\frac{1}{6}",
    "⅚": r"\frac{5}{6}",
    "⅛": r"\frac{1}{8}",
    "⅜": r"\frac{3}{8}",
    "⅝": r"\frac{5}{8}",
    "⅞": r"\frac{7}{8}",
}

NARY_MAP = {
    "∑": r"\sum",
    "∫": r"\int",
    "∬": r"\iint",
    "∭": r"\iiint",
    "∮": r"\oint",
    "∏": r"\prod",
    "⋃": r"\bigcup",
    "⋂": r"\bigcap",
}


def _clean_tag(elem):
    tag = elem.tag
    return tag.split("}")[-1] if "}" in tag else tag


def _clean_tag_str(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _get_attr_val(elem, name, default=""):
    for k, v in elem.attrib.items():
        if _clean_tag_str(k) == name:
            return v
    return default


def omml_to_latex(elem):
    """Convert an OMML XML element into a LaTeX math string."""
    tag = _clean_tag(elem)

    if tag in ("oMath", "oMathPara"):
        inner = "".join(omml_to_latex(c) for c in elem).strip()
        if not inner:
            return ""
        return f"${inner}$"

    if tag == "r":
        parts = []
        for c in elem:
            if _clean_tag(c) == "t":
                parts.append(c.text or "")
        return "".join(parts)

    if tag == "f":
        num, den = "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "num":
                num = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "den":
                den = "".join(omml_to_latex(ch) for ch in c).strip()
        return rf"\frac{{{num}}}{{{den}}}"

    if tag == "rad":
        deg, expr = "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "deg":
                deg = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "e":
                expr = "".join(omml_to_latex(ch) for ch in c).strip()
        if deg:
            return rf"\sqrt[{deg}]{{{expr}}}"
        return rf"\sqrt{{{expr}}}"

    if tag == "sSup":
        base, sup = "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "e":
                base = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "sup":
                sup = "".join(omml_to_latex(ch) for ch in c).strip()
        return rf"{{{base}}}^{{{sup}}}"

    if tag == "sSub":
        base, sub = "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "e":
                base = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "sub":
                sub = "".join(omml_to_latex(ch) for ch in c).strip()
        return rf"{{{base}}}_{{{sub}}}"

    if tag == "sSubSup":
        base, sub, sup = "", "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "e":
                base = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "sub":
                sub = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "sup":
                sup = "".join(omml_to_latex(ch) for ch in c).strip()
        return rf"{{{base}}}_{{{sub}}}^{{{sup}}}"

    if tag == "d":
        beg, end, sep = "(", ")", "|"
        exprs = []
        for c in elem:
            ct = _clean_tag(c)
            if ct == "dPr":
                for dc in c:
                    dct = _clean_tag(dc)
                    if dct == "begChr":
                        beg = _get_attr_val(dc, "val", "(")
                    elif dct == "endChr":
                        end = _get_attr_val(dc, "val", ")")
                    elif dct == "sepChr":
                        sep = _get_attr_val(dc, "val", "|")
            elif ct == "e":
                exprs.append("".join(omml_to_latex(ch) for ch in c).strip())
        beg_tex = r"\{" if beg == "{" else beg
        end_tex = r"\}" if end == "}" else end
        content = sep.join(exprs)
        return f"{beg_tex}{content}{end_tex}"

    if tag == "func":
        fname, expr = "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "fName":
                fname = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "e":
                expr = "".join(omml_to_latex(ch) for ch in c).strip()
        if fname in ("sin", "cos", "tan", "cot", "log", "ln", "lim", "exp", "min", "max"):
            return rf"\{fname}({expr})"
        return f"{fname}({expr})"

    if tag == "nary":
        op_char = "∑"
        sub, sup, expr = "", "", ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "naryPr":
                for nc in c:
                    if _clean_tag(nc) == "chr":
                        op_char = _get_attr_val(nc, "val", "∑")
            elif ct == "sub":
                sub = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "sup":
                sup = "".join(omml_to_latex(ch) for ch in c).strip()
            elif ct == "e":
                expr = "".join(omml_to_latex(ch) for ch in c).strip()
        op = NARY_MAP.get(op_char, op_char)
        bounds = ""
        if sub:
            bounds += f"_{{{sub}}}"
        if sup:
            bounds += f"^{{{sup}}}"
        return f"{op}{bounds}{{{expr}}}"

    if tag == "bar":
        pos = "top"
        expr = ""
        for c in elem:
            ct = _clean_tag(c)
            if ct == "barPr":
                for bc in c:
                    if _clean_tag(bc) == "pos":
                        pos = _get_attr_val(bc, "val", "top")
            elif ct == "e":
                expr = "".join(omml_to_latex(ch) for ch in c).strip()
        if pos == "bot":
            return rf"\underline{{{expr}}}"
        return rf"\overline{{{expr}}}"

    if tag == "eqArr":
        rows = []
        for c in elem:
            if _clean_tag(c) == "e":
                rows.append("".join(omml_to_latex(ch) for ch in c).strip())
        return r"\begin{aligned}" + r" \\ ".join(rows) + r"\end{aligned}"

    if tag == "m":
        rows = []
        for c in elem:
            if _clean_tag(c) == "mr":
                cells = []
                for rc in c:
                    if _clean_tag(rc) == "e":
                        cells.append("".join(omml_to_latex(ch) for ch in rc).strip())
                rows.append(" & ".join(cells))
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"

    return "".join(omml_to_latex(c) for c in elem)


def extract_docx_paragraph(p):
    """Extract text from a python-docx Paragraph, including OMML equations and superscripts."""
    parts = []
    element = getattr(p, "_p", p)
    for child in element:
        tag = _clean_tag(child)
        if tag == "r":
            valign = ""
            for rpr in child:
                if _clean_tag(rpr) == "rPr":
                    for va in rpr:
                        if _clean_tag(va) == "vertAlign":
                            valign = _get_attr_val(va, "val", "")
            r_text = ""
            for rc in child:
                rct = _clean_tag(rc)
                if rct == "t":
                    r_text += rc.text or ""
                elif rct == "br":
                    r_text += "\n"
                elif rct == "tab":
                    r_text += "\t"
            if r_text:
                if valign == "superscript":
                    parts.append(f"^{{{r_text}}}")
                elif valign == "subscript":
                    parts.append(f"_{{{r_text}}}")
                else:
                    parts.append(r_text)
        elif tag in ("oMath", "oMathPara"):
            math_latex = omml_to_latex(child)
            if math_latex:
                parts.append(math_latex)
        elif tag == "hyperlink":
            for r in child:
                if _clean_tag(r) == "r":
                    for rc in r:
                        if _clean_tag(rc) == "t":
                            parts.append(rc.text or "")
        elif tag in ("smartTag", "customXml", "ins", "sdt"):
            sub_p = extract_docx_paragraph(child)
            if sub_p:
                parts.append(sub_p)
    return "".join(parts)


def extract_docx_cell(cell):
    """Extract text and math from a python-docx table Cell."""
    parts = []
    for p in getattr(cell, "paragraphs", []):
        text = extract_docx_paragraph(p).strip()
        if text:
            parts.append(text)
    if not parts:
        raw = getattr(cell, "text", "")
        return raw.replace("\n", " ").strip()
    return " ".join(parts).replace("\n", " ")


def _replace_sqrt_parens(text):
    """Replace square roots written like √(expression) with \\sqrt{expression} using balanced parens."""
    res = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "√":
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            if j < n and text[j] == "(":
                depth = 0
                k = j
                while k < n:
                    if text[k] == "(":
                        depth += 1
                    elif text[k] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                if k < n and text[k] == ")":
                    inner = text[j + 1:k]
                    res.append(rf"\sqrt{{{inner}}}")
                    i = k + 1
                    continue
            elif j < n and text[j] == "[":
                depth = 0
                k = j
                while k < n:
                    if text[k] == "[":
                        depth += 1
                    elif text[k] == "]":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                if k < n and text[k] == "]":
                    inner = text[j + 1:k]
                    res.append(rf"\sqrt{{{inner}}}")
                    i = k + 1
                    continue
            elif j < n and text[j].isalnum():
                k = j
                while k < n and (text[k].isalnum() or text[k] == "_"):
                    k += 1
                res.append(rf"\sqrt{{{text[j:k]}}}")
                i = k
                continue
        res.append(text[i])
        i += 1
    return "".join(res)


def format_math_text(text):
    """Normalize and format mathematical notation and symbols into standard LaTeX."""
    if not text:
        return text

    # Handle HTML tags for math formatting in markdown
    text = re.sub(r"<sup>(.*?)</sup>", r"^{\1}", text, flags=re.I)
    text = re.sub(r"<sub>(.*?)</sub>", r"_{\1}", text, flags=re.I)

    # Vulgar fractions
    for vf, repl in VULGAR_FRACTIONS.items():
        text = text.replace(vf, repl)

    # Unicode superscripts and subscripts
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ]+", lambda m: f"^{{{m.group(0).translate(SUPER_MAP)}}}", text)
    text = re.sub(r"[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓ]+", lambda m: f"_{{{m.group(0).translate(SUB_MAP)}}}", text)

    # Square roots
    text = _replace_sqrt_parens(text)

    # Common division patterns in formulas: (a + b + c)/2 -> \frac{a + b + c}{2}
    text = re.sub(r"\(([a-zA-Z0-9_\s+-]+)\)\s*/\s*([0-9a-zA-Z_]+)", r"\\frac{\1}{\2}", text)

    # Standalone math equations with = and \sqrt or \frac: wrap in $...$ if not already wrapped
    # e.g., S = \sqrt{...} or p = \frac{...}
    def wrap_equation(m):
        raw = m.group(1).strip()
        return f"${raw}$"

    text = re.sub(
        r"(?<!\$)\b([a-zA-Z_]\s*=\s*(?:\\sqrt\{[^{}]+\}|\\frac\{[^{}]+\}\{[^{}]+\}))(?!\$)",
        wrap_equation,
        text
    )

    # Also wrap standalone \frac{...}{...} or \sqrt{...} if not wrapped in $ and not preceded by $
    text = re.sub(
        r"(?<!\$)(?<!\\)\b(\\frac\{[^{}]+\}\{[^{}]+\}|\\sqrt\{[^{}]+\})(?!\$)",
        lambda m: f"${m.group(1)}$",
        text
    )

    return text
