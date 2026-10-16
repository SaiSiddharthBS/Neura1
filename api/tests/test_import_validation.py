from neura1.ingest.validate import SPECS, template_csv, validate

EXISTING = {"items": {"NB54360", "PSU-24"}, "revisions": {"PSU-24-2"}, "_item_kind": {"PSU-24": "assembly"},
            "_rev_item": {"PSU-24-2": "PSU-24"}}


def issues(report, level="error"):
    return [(i["file"], i["row"], i["column"]) for i in report["issues"] if i["level"] == level]


def test_every_template_validates_against_itself():
    # Templates reference each other's example ids only partly, so the only errors allowed are unknown references.
    report = validate({f"{n}.csv": template_csv(n) for n in SPECS})
    errors = [i for i in report["issues"] if i["level"] == "error"]
    assert all("is not a known" in i["message"] for i in errors), errors


def test_broken_bom_reports_precise_rows():
    bom = ("parent_rev,child_item,child_rev,qty,uom,refdes\n"
           "VC-300-A,NB54360,,two,ea,U1\n"        # bad qty, unknown parent revision
           "VC-300-A,PSU-24,,1,ea,PS1\n"          # assembly without a pinned revision
           "VC-300-A,ZZ-1,,0,ea,U9\n")            # unknown part, zero qty
    r = validate({"my_bom_export.csv": bom}, EXISTING)
    assert not r["ok"]
    errs = issues(r)
    assert ("my_bom_export.csv", 2, "qty") in errs
    assert ("my_bom_export.csv", 2, "parent_rev") in errs
    assert ("my_bom_export.csv", 3, "child_rev") in errs
    assert ("my_bom_export.csv", 4, "child_item") in errs
    assert ("my_bom_export.csv", 4, "qty") in errs


def test_valid_upload_can_reference_existing_graph_records():
    revs = "id,item_id,rev,status,effective_from\nVC-300-A,VC-300,A,released,2026-10-01\n"
    items = "id,kind,name,mpn,manufacturer\nVC-300,product,VC-300 Controller,,\n"
    bom = "parent_rev,child_item,child_rev,qty,uom,refdes\nVC-300-A,PSU-24,PSU-24-2,1,ea,PS1\nVC-300-A,NB54360,,2,ea,U1\n"
    r = validate({"revisions.csv": revs, "items.csv": items, "bom.csv": bom}, EXISTING)
    assert r["ok"], r["issues"]


def test_cycle_and_bad_dates_are_errors():
    revs = "id,item_id,rev,status,effective_from\nA-1,A,1,released,16/10/2026\nB-1,B,1,released,\n"
    items = "id,kind,name,mpn,manufacturer\nA,assembly,A,,\nB,assembly,B,,\n"
    bom = "parent_rev,child_item,child_rev,qty,uom,refdes\nA-1,B,B-1,1,ea,\nB-1,A,A-1,1,ea,\n"
    r = validate({"revisions.csv": revs, "items.csv": items, "bom.csv": bom})
    msgs = " ".join(i["message"] for i in r["issues"])
    assert "contains itself" in msgs and "must be a date" in msgs


def test_kicad_style_bom_is_converted_and_matched_by_mpn():
    kicad = ('"Reference","Value","Qty","Manufacturer","Manufacturer Part Number"\n'
             '"U1,U2","Buck regulator","2","Northbridge Semi","nb54360"\n'
             '"C1;C2;C3","22uF","","Corewind","CAP-NEW-1"\n')
    existing = {**EXISTING, "revisions": {"PSU-24-2"}, "_mpn": {"NB54360": "NB54360"}}
    r = validate({"kicad_bom.csv": kicad}, existing, eda_parent_rev="PSU-24-2")
    assert r["ok"], r["issues"]
    bom = r["_parsed"]["bom"]
    assert [(b["child_item"], b["qty"]) for b in bom] == [("NB54360", "2"), ("CAP-NEW-1", "3")]
    assert [i["id"] for i in r["_parsed"]["items"]] == ["CAP-NEW-1"]


def test_eda_bom_without_revision_asks_for_one():
    r = validate({"altium.csv": "Designator,Quantity,Manufacturer Part Number\nU1,1,NB54360\n"}, EXISTING)
    assert not r["ok"] and "which revision" in r["issues"][0]["message"]


def test_semicolon_csv_and_human_headers_are_understood():
    stock = "Item ID;On Hand;Allocated\nNB54360;180;120\n"
    r = validate({"stock_export.csv": stock}, EXISTING)
    assert r["ok"], r["issues"]


def test_cad_bom_row_naming_an_existing_assembly_is_not_recreated_as_a_part():
    kicad = '"Reference","Qty","Manufacturer Part Number"\n"PS1","1","PSU-24"\n'
    r = validate({"cad.csv": kicad}, {**EXISTING, "revisions": {"VC-300-A"}}, eda_parent_rev="VC-300-A")
    assert "items" not in r["_parsed"] or not r["_parsed"]["items"]
    assert any(i["column"] == "child_rev" for i in r["issues"])  # assembly needs a pinned revision
