from app.reasons import reject
from app.values import number
from app.errors import DomainError
from app.compat import diff_origin
def evaluate(rows,context):
    explanations=context.get("accesses",{}).get("compat",{}).get("explanations",{})
    good=[];bad=[]
    for row in rows:
        if row.get("observed") not in {"allowed","blocked"}:bad.append(reject(row,"BAD_ACCESS_OUTCOME","访问结果必须为allowed或blocked"));continue
        effect=row["effect"];expected="1" if effect=="allow" else "0";actual="1" if row["observed"]=="allowed" else "0"
        out={**row,"expected":expected,"reported":actual,"upstream_decision":row["reported"],"partition_result":"授权内" if row["matched_rules"] else "未授权分区","violation":"越权放行" if expected=="0" and actual=="1" else "误拦截" if expected=="1" and actual=="0" else "一致"}
        if "legacy_matched_rules" in row:
            legacy_partition="授权内" if row["legacy_matched_rules"] else "未授权分区"
            out["legacy_partition_result"]=legacy_partition;out["partition_changed"]=legacy_partition!=out["partition_result"]
            out["diff_origin"]=sorted(set(out.get("diff_origin",[]))|set(diff_origin(row,explanations,"partitions")))
        good.append(out)
    return {"rows":good,"quarantine":bad,"metrics":{"allowed":sum(r["expected"]=="1" for r in good),"blocked":sum(r["expected"]=="0" for r in good),"violations":sum(r["violation"]=="越权放行" for r in good),"false_blocks":sum(r["violation"]=="误拦截" for r in good),"partition_changed":sum(1 for r in good if r.get("partition_changed"))}}
