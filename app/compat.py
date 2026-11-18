from app.config import COLUMNS,COLUMN_EXPLANATIONS
from app.errors import DomainError
from app.values import SENTINELS
DIMENSIONS=("principal","grants","partitions")
def split_header(header):
    "表头判定：原列接收 / 兼容扩展 / 整批退回。返回(结论, 新增列)。"
    if header==COLUMNS: return "legacy",[]
    if isinstance(header,list) and len(header)>len(COLUMNS) and header[:len(COLUMNS)]==COLUMNS:
        extension=header[len(COLUMNS):]
        if (any(not isinstance(c,str) or not c or c!=c.strip() for c in extension)
                or len(set(extension))!=len(extension)
                or set(extension)&set(COLUMNS)
                or any(c.startswith("_") for c in extension)):
            raise DomainError("BAD_HEADER","新增列名为空、重复或与原列冲突，整批退回")
        return "extended",extension
    raise DomainError("BAD_HEADER","原列缺失或顺序变化，不兼容，整批退回")
def normalize_explanation(raw):
    "完整解释：note非空且affects显式覆盖主体/授权/分区三个布尔。"
    if not isinstance(raw,dict): return None
    note=raw.get("note");affects=raw.get("affects")
    if not isinstance(note,str) or not note.strip(): return None
    if not isinstance(affects,dict) or set(affects)!=set(DIMENSIONS) or not all(isinstance(affects[d],bool) for d in DIMENSIONS): return None
    return {"note":note.strip(),"affects":{d:affects[d] for d in DIMENSIONS}}
def resolve_explanations(extension,parameters):
    "参数解释优先于登记簿；返回{列: 解释}与整体完整标记。"
    overrides=parameters.get("column_explanations",{})
    if not isinstance(overrides,dict): raise DomainError("BAD_EXPLANATION","列差异解释需要对象")
    explanations={};complete=True
    for column in extension:
        normalized=None;origin=None
        if column in overrides:
            normalized=normalize_explanation(overrides[column]);origin="parameters"
            if normalized is None: raise DomainError("BAD_EXPLANATION",f"列{column}的解释需要note与principal/grants/partitions布尔affects")
        elif column in COLUMN_EXPLANATIONS:
            normalized=normalize_explanation(COLUMN_EXPLANATIONS[column]);origin="registry"
        if normalized is None:
            explanations[column]={"note":"","affects":{},"complete":False,"origin":None};complete=False
        else: explanations[column]={**normalized,"complete":True,"origin":origin}
    return explanations,complete
def build_compat(header,parameters):
    "每份文件的兼容结论：接收决策、原列与新增列依据、列差异解释。"
    conclusion,extension=split_header(header)
    explanations,complete=resolve_explanations(extension,parameters or {})
    return {"conclusion":conclusion,"decision":"原列接收" if conclusion=="legacy" else "兼容扩展","base_columns":list(COLUMNS),"extension_columns":extension,"explanations":explanations,"explanation_complete":complete}
def extension_values(row,extension):
    "新增列非空取值（哨兵视为缺失），作为行级差异依据。"
    values={}
    for column in extension:
        value=str(row.get(column,"")).strip()
        if value and value.upper() not in SENTINELS: values[column]=value
    return values
def affects(explanations,column,dimension):
    "该列是否影响指定结论维度；解释缺失时保守视为影响。"
    explanation=explanations.get(column)
    if not explanation or not explanation.get("complete"): return True
    return explanation["affects"][dimension]
def diff_origin(row,explanations,dimension):
    "行级差异来源：对该维度有影响且带值的新增列。"
    return sorted(c for c in row.get("_extension",{}) if affects(explanations,c,dimension))
