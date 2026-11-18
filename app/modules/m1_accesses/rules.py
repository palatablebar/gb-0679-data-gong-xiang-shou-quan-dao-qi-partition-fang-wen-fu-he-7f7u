import csv,io
from app.config import COLUMNS
from app.errors import DomainError
from app.reasons import reject
from app.compat import build_compat,extension_values
def decode(raw):
    for encoding in ("utf-8-sig","gb18030"):
        try: return raw.decode(encoding),encoding
        except UnicodeDecodeError: continue
    raise DomainError("ENCODING","无法识别文件编码")
def evaluate(raw,context=None):
    text,encoding=decode(raw)
    if not text: raise DomainError("EMPTY_FILE","文件为空")
    if not text.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    parameters=(context or {}).get("parameters",{})
    stream=csv.reader(io.StringIO(text,newline=""));header=next(stream,None)
    compat=build_compat(header,parameters);extension=compat["extension_columns"]
    rows=[];bad=[];seen={};duplicate=blank=repeated=count=0
    try:
        for cells in stream:
            count+=1;line=stream.line_num
            if not cells or not any(c.strip() for c in cells): blank+=1;continue
            if cells==header: repeated+=1;continue
            row={"_line":line,"_sources":[line],"_raw":cells}
            if len(cells)!=len(header): bad.append(reject(row,"BAD_COLUMNS","列数不匹配"));continue
            row.update(dict(zip(header,[x.strip() for x in cells])))
            if not row[header[0]]: bad.append(reject(row,"EMPTY_VALUE","业务键为空"));continue
            key=row[header[0]]
            if key in seen:
                previous=seen[key]
                if cells==previous["_raw"]: duplicate+=1
                else: bad.append(reject(row,"DUPLICATE_CONFLICT","同键不同值"))
                continue
            values=extension_values(row,extension)
            if values: row["_extension"]=values;row["affected"]=True
            seen[key]=row;rows.append(row)
    except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    metrics={"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,"blank":blank,"repeated_headers":repeated,"encoding":encoding,"compat":compat["conclusion"],"decision":compat["decision"],"extension_columns":len(extension),"extension_rows":sum(1 for r in rows if r.get("affected")),"explanation_complete":compat["explanation_complete"]}
    return {"rows":rows,"quarantine":bad,"metrics":metrics,"compat":compat}
