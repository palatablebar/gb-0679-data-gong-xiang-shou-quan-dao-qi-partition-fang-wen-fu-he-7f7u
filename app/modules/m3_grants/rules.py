from app.values import instant,number
from app.reasons import reject
from app.errors import DomainError
GRANTS=[{"id":"G-01","principal":"analyst","resource":"orders","start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"},{"id":"G-02","principal":"analyst","resource":"orders","start":"2026-11-10T00:00:00Z","end":"2026-11-20T00:00:00Z","from_partition":"2026-10","to_partition":"2026-11","effect":"deny"},{"id":"G-03","principal":"auditor","resource":"customers","start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"},{"id":"G-04","principal":"analyst","resource":"orders","start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"deny","sources":["HXDB"]},{"id":"G-05","principal":"guest","resource":"orders","start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow","sources":["HXDB"]}]
def validate_grants(grants):
    ids=set()
    for g in grants:
        if g["id"] in ids or instant(g["start"])>=instant(g["end"]) or g["effect"] not in {"allow","deny"} or g["from_partition"]>=g["to_partition"]:raise DomainError("BAD_GRANT","授权版本无效")
        sources=g.get("sources")
        if sources is not None and (not isinstance(sources,list) or not sources or any(not isinstance(s,str) or not s for s in sources)):raise DomainError("BAD_GRANT","授权来源范围无效")
        ids.add(g["id"])
    return grants
def source_of(row): return row.get("_extension",{}).get("source_system")
def matches(grant,row,at):
    if not (grant["principal"]==row["principal"] and grant["resource"]==row["resource"] and instant(grant["start"])<=at<instant(grant["end"])): return False
    sources=grant.get("sources")
    return sources is None or source_of(row) in sources
def matches_legacy(grant,row,at):
    "原列口径：文件无新增列时的匹配，来源范围授权不参与。"
    return grant.get("sources") is None and grant["principal"]==row["principal"] and grant["resource"]==row["resource"] and instant(grant["start"])<=at<instant(grant["end"])
def evaluate(rows,context):
    grants=validate_grants(context.get("parameters",{}).get("grants",GRANTS));good=[];bad=[]
    for row in rows:
        try:
            at=instant(row["access_time"]);reported=number(row["reported"])
            if reported not in {0,1}:raise DomainError("BAD_OBSERVED","报送判定必须为0或1")
            active=[g for g in grants if matches(g,row,at)]
            out={**row,"at":at.isoformat(),"candidates":active,"candidate_count":len(active),"reported":str(reported)}
            if source_of(row) is not None: out["legacy_candidates"]=[g for g in grants if matches_legacy(g,row,at)]
            good.append(out)
        except (DomainError,KeyError) as e:bad.append(reject(row,getattr(e,"code","MISSING_FIELD"),str(e)))
    return {"rows":good,"quarantine":bad,"metrics":{"active_hits":sum(r["candidate_count"] for r in good),"grant_versions":len(grants),"rederived":sum(1 for r in good if "legacy_candidates" in r)}}
