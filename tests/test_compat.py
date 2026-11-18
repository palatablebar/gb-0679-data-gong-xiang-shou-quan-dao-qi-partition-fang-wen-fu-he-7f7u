import csv,io,json
import pytest
from app.pipeline import calculate,execute,load_sample
from app.modules.m1_accesses.rules import evaluate as intake
from app.modules.m3_grants.rules import evaluate as grants_eval,validate_grants,GRANTS
from app.modules.m7_seals.rules import evaluate as seals_eval
from app.compat import split_header,build_compat
from app.config import COLUMNS
from app.errors import DomainError
from app import store
def csv_bytes(header,rows): return (",".join(header)+"\n"+"\n".join(",".join(r) for r in rows)+"\n").encode()
BASE=["00001","analyst","orders","2026-10","2026-11-16T00:00:00Z","allowed","1","测试"]
def ext_csv(column="source_system",value="HXDB",row=BASE): return csv_bytes(COLUMNS+[column],[row+[value]])
def test_extended_header_accepted_not_rejected():
    "TRAP-27 新增列走兼容扩展而非整批退回"
    r=intake(ext_csv());m=r["metrics"]
    assert m["compat"]=="extended" and m["decision"]=="兼容扩展" and m["accepted"]==1 and m["extension_columns"]==1
def test_legacy_header_still_accepted():
    r=intake(load_sample("clean.csv"))
    assert r["metrics"]["compat"]=="legacy" and r["metrics"]["decision"]=="原列接收" and r["compat"]["explanation_complete"] is True
def test_incompatible_header_still_rejected():
    for header in [COLUMNS[:-1],list(reversed(COLUMNS)),COLUMNS+["principal"],COLUMNS+["source_system","source_system"],COLUMNS+[""],COLUMNS+["_secret"]]:
        with pytest.raises(DomainError) as e: intake(csv_bytes(header,[BASE[:len(header)-1]+["x"]]))
        assert e.value.code=="BAD_HEADER"
def test_column_diff_evidence_kept():
    "原列与新增列依据都保留在兼容结论里"
    compat=build_compat(COLUMNS+["source_system"],{})
    assert compat["base_columns"]==COLUMNS and compat["extension_columns"]==["source_system"]
    assert compat["explanations"]["source_system"]["complete"] is True
def test_row_level_extension_evidence():
    r=intake(ext_csv())["rows"][0]
    assert r["_extension"]=={"source_system":"HXDB"} and r["affected"] is True and r["source_system"]=="HXDB"
def test_empty_and_sentinel_source_not_affected():
    for value in ("","NULL","未知"):
        rows=intake(ext_csv(value=value))["rows"]
        assert "_extension" not in rows[0] and "affected" not in rows[0]
def test_affected_accesses_rederive_grant_and_partition():
    "TRAP-28 受影响访问重取授权与分区结论，页面可见差异来源"
    result=calculate(load_sample("extended.csv"));rows={r["event_id"]:r for r in result["stages"][4]["rows"]}
    hit=rows["10001"]
    assert hit["effect"]=="deny" and hit["legacy_effect"]=="allow" and hit["grant_changed"] is True and hit["diff_origin"]==["source_system"]
    guest=rows["10003"]
    assert guest["partition_result"]=="授权内" and guest["legacy_partition_result"]=="未授权分区" and guest["partition_changed"] is True
    old=rows["10004"]
    assert "legacy_effect" not in old and "partition_changed" not in old
    other=rows["10005"]
    assert other["grant_changed"] is False and other["diff_origin"]==["source_system"]
def test_source_scoped_grant_matching():
    scoped={**GRANTS[0],"id":"G-X","sources":["HXDB"]}
    row={"access_time":"2026-11-16T00:00:00Z","reported":"1","principal":"analyst","resource":"orders","partition":"2026-10"}
    assert grants_eval([dict(row)],{"parameters":{"grants":[scoped]}})["rows"][0]["candidate_count"]==0
    assert grants_eval([{**row,"_extension":{"source_system":"HXDB"}}],{"parameters":{"grants":[scoped]}})["rows"][0]["candidate_count"]==1
def test_grant_sources_shape_validated():
    for sources in ("HXDB",[],[""],[1]):
        with pytest.raises(DomainError): validate_grants([{**GRANTS[0],"id":"G-X","sources":sources}])
def test_unexplained_column_pauses_seal():
    "TRAP-29 列差异解释不完整时暂停封存，但批次不失败"
    result=calculate(ext_csv(column="future_col"))
    seal=result["stages"][6]["metrics"]
    assert seal["ready"] is False and seal["seal"]=="暂停封存" and "future_col" in seal["pause_reasons"]
def test_explanation_via_parameters_resumes_seal():
    params={"column_explanations":{"future_col":{"note":"试点列，仅留证","affects":{"principal":False,"grants":False,"partitions":False}}}}
    assert calculate(ext_csv(column="future_col"),params)["stages"][6]["metrics"]["ready"] is True
def test_bad_explanation_parameter_rejected():
    with pytest.raises(DomainError) as e: calculate(ext_csv(column="future_col"),{"column_explanations":{"future_col":{"note":"缺affects"}}})
    assert e.value.code=="BAD_EXPLANATION"
def test_retry_same_file_no_new_version():
    "TRAP-30 同一文件重试不新增版本，结论唯一"
    raw=ext_csv();a=execute(raw);b=execute(raw)
    assert a["run_id"]==b["run_id"] and a["version"]==1 and len(store.history())==1
    record=store.compat_for(a["manifest"]["input_sha256"])
    assert record["conclusion"]=="extended" and record["decision"]=="兼容扩展" and record["extension_columns"]==["source_system"]
def test_unique_conclusion_per_file_across_parameters():
    raw=ext_csv(column="future_col");first=execute(raw)
    execute(raw,{"column_explanations":{"future_col":{"note":"补充解释","affects":{"principal":False,"grants":False,"partitions":False}}}})
    assert len(store.history())==2
    assert store.compat_for(first["manifest"]["input_sha256"])["run_id"]==first["run_id"]
def test_failure_keeps_old_conclusion():
    raw=ext_csv();saved=execute(raw);sha=saved["manifest"]["input_sha256"];before=store.compat_for(sha)
    with pytest.raises(DomainError): execute(b"not,a,valid,header\n1,2,3,4\n")
    assert store.compat_for(sha)==before and len(store.history())==1
def test_archive_blocked_while_seal_paused(client):
    run=client.post("/api/runs",json={"csv":ext_csv(column="future_col").decode()}).get_json()
    r=client.get("/api/runs/"+run["run_id"]+"/archive")
    assert r.status_code==409 and r.get_json()["code"]=="SEAL_PAUSED"
def test_archive_exports_compat_evidence(client):
    run=client.post("/api/runs",json={"sample":"extended.csv"}).get_json()
    rows=list(csv.reader(io.StringIO(client.get("/api/runs/"+run["run_id"]+"/archive").data.decode("utf-8-sig"))))
    compat=[x for x in rows[1:] if x[3]=="compat"]
    assert compat and json.loads(compat[0][6])["extension_columns"]==["source_system"]
def test_extended_sample_full_flow(client):
    p=client.post("/api/runs",json={"sample":"extended.csv"}).get_json()
    assert len(p["stages"])==7 and p["stages"][5]["metrics"]["balanced"] is True
    assert p["stages"][0]["metrics"]["extension_rows"]==4 and p["stages"][6]["metrics"]["ready"] is True
def test_module_pages_render_extended(client):
    client.post("/api/runs",json={"sample":"extended.csv"})
    for slug in ("accesses","conflicts","partitions","seals"):
        assert client.get("/"+slug).status_code==200
