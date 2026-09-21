"""抗体改造项目 API 的完整业务链测试。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.models import Job, User
from app.modules.antibody_projects.router import router


def _create_user(factory, username: str) -> User:
    with factory() as db:
        user = User(
            username=username,
            email=f"{username}@example.test",
            password_hash="not-used",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def test_complete_project_api_flow(
    sqlite_sessions,
    active_user,
    tmp_path,
    monkeypatch,
) -> None:
    from app.core.config import settings

    viewer = _create_user(sqlite_sessions, "project-viewer")
    outsider = _create_user(sqlite_sessions, "project-outsider")
    monkeypatch.setattr(settings, "antibody_projects_out_root", tmp_path)

    current_user = {"value": active_user}
    app = FastAPI()
    app.include_router(router)

    def isolated_db():
        with sqlite_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]

    with TestClient(app) as client:
        project_response = client.post(
            "/api/antibody-projects",
            json={
                "project_code": "EGFR-001",
                "name": "EGFR 抗体优化",
                "target_name": "EGFR",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        member_response = client.post(
            f"/api/antibody-projects/{project_id}/members",
            json={"username": viewer.username, "role": "viewer"},
        )
        assert member_response.status_code == 201

        candidate_response = client.post(
            f"/api/antibody-projects/{project_id}/candidates",
            json={
                "candidate_code": "AB-A",
                "name": "候选抗体 A",
                "antibody_category": "RM",
                "antibody_type": "igg",
                "chains": [
                    {"chain_role": "VH", "variable_sequence": "QVQLVQ"},
                    {"chain_role": "VL", "variable_sequence": "DIQMTQ"},
                ],
            },
        )
        assert candidate_response.status_code == 201
        candidate_id = candidate_response.json()["id"]
        assert candidate_response.json()["antibody_category"] == "RM"
        fixed_category_response = client.patch(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/category",
            json={"antibody_category": "RN"},
        )
        assert fixed_category_response.status_code == 409

        versions_response = client.get(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions"
        )
        assert versions_response.status_code == 200
        wt = versions_response.json()[0]
        assert (wt["version_code"], wt["version_number"], wt["status"]) == (
            "WT",
            0,
            "locked",
        )

        m1_response = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions",
            json={
                "parent_version_id": wt["id"],
                "name": "VH 末端优化",
                "chains": [
                    {"chain_role": "VH", "variable_sequence": "QVQLVW"},
                    {"chain_role": "VL", "variable_sequence": "DIQMTQ"},
                ],
            },
        )
        assert m1_response.status_code == 201
        m1 = m1_response.json()
        assert (m1["version_code"], m1["version_number"]) == ("M1-001", 1001)
        assert len(m1["mutations"]) == 1
        assert m1["mutations"][0]["from_aa"] == "Q"
        assert m1["mutations"][0]["to_aa"] == "W"

        import_response = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions/import",
            json={
                "parent_version_id": wt["id"],
                "items": [
                    {
                        "name": "clone_a",
                        "chains": [
                            {"chain_role": "VH", "variable_sequence": "QVQLVA"},
                            {"chain_role": "VL", "variable_sequence": "DIQMTQ"},
                        ],
                    },
                    {
                        "name": "clone_b",
                        "chains": [
                            {"chain_role": "VH", "variable_sequence": "QVQLVC"},
                            {"chain_role": "VL", "variable_sequence": "DIQMTQ"},
                        ],
                    },
                ],
            },
        )
        assert import_response.status_code == 201
        imported = import_response.json()
        assert [item["version_code"] for item in imported] == ["M1-002", "M1-003"]
        assert imported[0]["name"] == "clone_a"

        fasta_response = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions/import-fasta",
            data={"parent_version_id": wt["id"]},
            files={
                "file": (
                    "round1.fasta",
                    ">clone_x_VH\nQVQLVD\n>clone_x_VL\nDIQMTQ\n"
                    ">clone_y_VH\nQVQLVE\n>clone_y_VL\nDIQMTQ\n",
                    "text/plain",
                )
            },
        )
        assert fasta_response.status_code == 201
        fasta_imported = fasta_response.json()
        assert [item["version_code"] for item in fasta_imported] == ["M1-004", "M1-005"]
        assert fasta_imported[0]["name"] == "clone_x"

        mutation_id = m1["mutations"][0]["id"]
        mutation_response = client.patch(
            f"/api/antibody-projects/{project_id}/versions/{m1['id']}"
            f"/mutations/{mutation_id}",
            json={"expected_effect": "KD 降低"},
        )
        assert mutation_response.status_code == 200
        assert mutation_response.json()["mutations"][0]["expected_effect"] == "KD 降低"

        compare_response = client.get(
            f"/api/antibody-projects/{project_id}/compare",
            params={"base_version_id": wt["id"], "target_version_id": m1["id"]},
        )
        assert compare_response.status_code == 200
        assert compare_response.json()["differences"] == [
            {
                "chain_role": "VH",
                "mutation_type": "substitution",
                "sequence_position": 6,
                "from_aa": "Q",
                "to_aa": "W",
            }
        ]

        lock_response = client.post(
            f"/api/antibody-projects/{project_id}/versions/{m1['id']}/lock"
        )
        assert lock_response.status_code == 200
        assert lock_response.json()["status"] == "locked"
        assert (
            client.patch(
                f"/api/antibody-projects/{project_id}/versions/{m1['id']}",
                json={"name": "不允许修改"},
            ).status_code
            == 409
        )

        batch_lock = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions/lock-drafts",
            json={"round": "M1"},
        )
        assert batch_lock.status_code == 200
        assert {item["version_code"] for item in batch_lock.json()} == {
            "M1-002",
            "M1-003",
            "M1-004",
            "M1-005",
        }
        assert all(item["status"] == "locked" for item in batch_lock.json())

        sample_response = client.post(
            f"/api/antibody-projects/{project_id}/samples",
            json={
                "version_id": m1["id"],
                "batch_code": "EXP-001",
                "concentration_value": 2.1,
                "concentration_unit": "mg/mL",
                "purity_percent": 96.5,
            },
        )
        assert sample_response.status_code == 201
        sample_id = sample_response.json()["id"]

        experiment_response = client.post(
            f"/api/antibody-projects/{project_id}/experiments",
            json={
                "version_id": m1["id"],
                "sample_batch_id": sample_id,
                "title": "SPR 检测",
                "experiment_type": "affinity",
                "measurements": [
                    {"metric_name": "KD", "value_numeric": 1.2, "unit": "nM"}
                ],
            },
        )
        assert experiment_response.status_code == 201
        assert experiment_response.json()["measurements"][0]["value_numeric"] == 1.2

        upload_response = client.post(
            f"/api/antibody-projects/{project_id}/artifacts",
            data={"category": "experiment", "experiment_id": experiment_response.json()["id"]},
            files={"file": ("spr-result.csv", b"sample,kd\\nEXP-001,1.2\\n", "text/csv")},
        )
        assert upload_response.status_code == 201
        artifact = upload_response.json()
        assert artifact["size_bytes"] > 0
        assert len(artifact["sha256"]) == 64
        download_response = client.get(
            f"/api/antibody-projects/{project_id}/artifacts/{artifact['id']}/download"
        )
        assert download_response.status_code == 200
        assert download_response.content.startswith(b"sample,kd")

        with sqlite_sessions() as db:
            job = Job(
                user_id=active_user.id,
                name="linked-fold",
                engine="boltz2",
                status="done",
                fasta_text=">H\\nQVQLVW",
                sequence_hash="a" * 64,
                chains_json={"H": 6},
                total_length=6,
                use_msa_server=False,
                params_json={"seed": 1},
                results_json={"confidence": 0.9},
            )
            db.add(job)
            db.commit()
            job_id = job.id
        link_response = client.post(
            f"/api/antibody-projects/{project_id}/job-links",
            json={"version_id": m1["id"], "job_id": job_id, "purpose": "结构验证"},
        )
        assert link_response.status_code == 201
        assert link_response.json()["result_snapshot"] == {"confidence": 0.9}

        audit_response = client.get(
            f"/api/antibody-projects/{project_id}/audit-events"
        )
        assert audit_response.status_code == 200
        assert {item["action"] for item in audit_response.json()} >= {
            "create",
            "update",
            "lock",
        }

        current_user["value"] = viewer
        assert client.get(f"/api/antibody-projects/{project_id}").status_code == 200
        assert (
            client.post(
                f"/api/antibody-projects/{project_id}/samples",
                json={"version_id": m1["id"], "batch_code": "DENIED"},
            ).status_code
            == 403
        )

        current_user["value"] = outsider
        assert client.get(f"/api/antibody-projects/{project_id}").status_code == 404

        current_user["value"] = active_user
        archive_response = client.patch(
            f"/api/antibody-projects/{project_id}",
            json={"status": "archived"},
        )
        assert archive_response.status_code == 200
        assert client.get("/api/antibody-projects").json() == []
        archived = client.get(
            "/api/antibody-projects", params={"include_archived": True}
        ).json()
        assert [item["id"] for item in archived] == [project_id]


def _xlsx_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    from html import escape
    from io import BytesIO
    from zipfile import ZipFile, ZIP_DEFLATED

    shared: list[str] = []

    def add(value: str) -> int:
        shared.append(value)
        return len(shared) - 1

    def row_xml(row_number: int, values: list[str]) -> str:
        cells = []
        for index, value in enumerate(values):
            column = chr(ord("A") + index)
            cells.append(
                f'<c r="{column}{row_number}" t="s"><v>{add(value)}</v></c>'
            )
        return f'<row r="{row_number}">{"".join(cells)}</row>'

    sheet_rows = [row_xml(1, headers)]
    sheet_rows.extend(row_xml(index, row) for index, row in enumerate(rows, start=2))
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    shared_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="{ns}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(item)}</t></si>" for item in shared)
        + "</sst>"
    )
    sheet_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{ns}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def test_xlsx_import_translates_dna_and_uses_protein_name(
    sqlite_sessions,
    active_user,
) -> None:
    current_user = {"value": active_user}
    app = FastAPI()
    app.include_router(router)

    def isolated_db():
        with sqlite_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]

    with TestClient(app) as client:
        project_id = client.post(
            "/api/antibody-projects",
            json={
                "project_code": "IL12B-DNA",
                "name": "核酸导入",
                "target_name": "IL12B",
            },
        ).json()["id"]
        candidate = client.post(
            f"/api/antibody-projects/{project_id}/candidates",
            json={
                "candidate_code": "001",
                "name": "纳米抗体",
                "antibody_category": "RN",
                "antibody_type": "vhh",
                "chains": [{"chain_role": "VHH", "variable_sequence": "M" * 19 + "Q"}],
            },
        )
        assert candidate.status_code == 201
        candidate_id = candidate.json()["id"]
        wt_id = client.get(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions"
        ).json()[0]["id"]

        payload = _xlsx_bytes(
            ["基因名称", "基因序列", "蛋白名称"],
            [
                [
                    "Vh130-20R232_RNBW01AAPHV9",
                    "ATG" * 20,
                    "20R232_RNBW01AAPHV9_h150",
                ],
                [
                    "Vh130-20R232_RNBW01AAPHWA",
                    "ATG" * 19 + "TTT",
                    "20R232_RNBW01AAPHWA_h150",
                ],
            ],
        )
        response = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions/import-xlsx",
            data={"parent_version_id": wt_id},
            files={"file": ("clones.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 201, response.text
        imported = response.json()
        assert [item["version_code"] for item in imported] == ["M1-001", "M1-002"]
        assert imported[0]["name"] == "20R232_RNBW01AAPHV9_h150"
        assert imported[1]["name"] == "20R232_RNBW01AAPHWA_h150"
        assert imported[0]["chains"][0]["variable_sequence"] == "M" * 20
        assert imported[0]["chains"][0]["nucleotide_sequence"] == "ATG" * 20
        assert imported[1]["chains"][0]["variable_sequence"] == "M" * 19 + "F"


def _xlsx_named_sheets(sheets: list[tuple[str, list[str], list[list[str]]]]) -> bytes:
    from html import escape
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    shared: list[str] = []

    def add(value: str) -> int:
        shared.append(value)
        return len(shared) - 1

    def sheet_xml(headers: list[str], rows: list[list[str]]) -> str:
        def row_xml(row_number: int, values: list[str]) -> str:
            cells = []
            for index, value in enumerate(values):
                column = chr(ord("A") + index)
                cells.append(f'<c r="{column}{row_number}" t="s"><v>{add(value)}</v></c>')
            return f'<row r="{row_number}">{"".join(cells)}</row>'

        body = [row_xml(1, headers)]
        body.extend(row_xml(index, row) for index, row in enumerate(rows, start=2))
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<worksheet xmlns="{ns}"><sheetData>{"".join(body)}</sheetData></worksheet>'
        )

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheet_files = []
    sheet_tags = []
    rel_tags = []
    for index, (name, headers, rows) in enumerate(sheets, start=1):
        path = f"xl/worksheets/sheet{index}.xml"
        sheet_files.append((path, sheet_xml(headers, rows)))
        sheet_tags.append(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        rel_tags.append(
            f'<Relationship Id="rId{index}" Type="{r_ns}/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
    workbook_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<workbook xmlns="{ns}" xmlns:r="{r_ns}"><sheets>{"".join(sheet_tags)}</sheets></workbook>'
    )
    rels_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{rel_ns}">{"".join(rel_tags)}</Relationships>'
    )
    shared_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="{ns}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(item)}</t></si>" for item in shared)
        + "</sst>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        for path, content in sheet_files:
            archive.writestr(path, content)
    return buffer.getvalue()


def test_affinity_xlsx_preview_and_import(sqlite_sessions, active_user) -> None:
    current_user = {"value": active_user}
    app = FastAPI()
    app.include_router(router)

    def isolated_db():
        with sqlite_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]

    headers = [
        "Loading Sample ID",
        "Loading Response",
        "Sample ID",
        "Response",
        "KD (M)",
        "ka (1/Ms)",
        "kdis (1/s)",
        "Result diagram",
        "Result",
    ]
    affinity_rows = [
        ["008-20R232_RNBW01AAPHV9_h150", "6.32", "hIL12B-His", "1.72", "2.20E-09", "1.05E+05", "2.30E-04", "", "Positive"],
        ["008-20R232_RNBW01AAPHV9_h150", "6.31", "cynoIL12H-His", "1.81", "8.78E-10", "1.04E+05", "9.18E-05", "", "Positive"],
        ["008-20R232_RNBW01AAPHV9_h150", "2.72", "mIL12B-His", "1.12", "<1.0E-12", "1.71E+05", "<1.0E-07", "", "Positive"],
        ["001-hIgG1", "2.65", "hIL12B-His", "0.07", "-", "-", "-", "", "Negative"],
        ["009-not_in_project", "1.00", "hIL12B-His", "1.00", "1.00E-08", "1.00E+05", "1.00E-04", "", "Positive"],
    ]
    payload = _xlsx_named_sheets(
        [
            ("Sample information", ["A"], [["ignore"]]),
            ("亲和力", headers, affinity_rows),
        ]
    )

    with TestClient(app) as client:
        project_id = client.post(
            "/api/antibody-projects",
            json={"project_code": "IL12B-SPR", "name": "亲和力导入", "target_name": "IL12B"},
        ).json()["id"]
        candidate_id = client.post(
            f"/api/antibody-projects/{project_id}/candidates",
            json={
                "candidate_code": "001",
                "name": "纳米抗体",
                "antibody_category": "RN",
                "antibody_type": "vhh",
                "chains": [{"chain_role": "VHH", "variable_sequence": "M" * 20}],
            },
        ).json()["id"]
        wt_id = client.get(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions"
        ).json()[0]["id"]
        created = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/versions",
            json={
                "parent_version_id": wt_id,
                "name": "20R232_RNBW01AAPHV9_h150",
                "chains": [{"chain_role": "VHH", "variable_sequence": "M" * 19 + "F"}],
            },
        )
        assert created.status_code == 201, created.text
        version_id = created.json()["id"]
        assert client.post(
            f"/api/antibody-projects/{project_id}/versions/{version_id}/lock"
        ).status_code == 200

        preview = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/experiments/preview-affinity-xlsx",
            files={"file": ("spr.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["sheet_name"] == "亲和力"
        statuses = [item["status"] for item in body["rows"]]
        assert statuses == ["matched", "matched", "matched", "control", "unmatched"]
        assert body["rows"][0]["version_id"] == version_id
        assert body["rows"][0]["kd_m"] == 2.2e-09
        assert body["rows"][2]["kd_m"] == 1.0e-12
        assert body["rows"][2]["kd_qualifier"] == "<"
        assert body["rows"][2]["kdis_qualifier"] == "<"
        assert body["rows"][3]["selected"] is False

        def import_payload(rows):
            return {"items": [
                {
                    "excel_row": item["excel_row"],
                    "version_id": item["version_id"],
                    "loading_sample_id": item["loading_sample_id"],
                    "protein_key": item["protein_key"],
                    "antigen": item["antigen"],
                    "loading_response": item["loading_response"],
                    "response": item["response"],
                    "kd_m": item["kd_m"],
                    "kd_qualifier": item["kd_qualifier"],
                    "ka": item["ka"],
                    "ka_qualifier": item["ka_qualifier"],
                    "kdis": item["kdis"],
                    "kdis_qualifier": item["kdis_qualifier"],
                    "result": item["result"],
                }
                for item in rows
            ]}

        selected = [item for item in body["rows"] if item["selected"]]
        imported = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/experiments/import-affinity-xlsx",
            json=import_payload(selected),
        )
        assert imported.status_code == 201, imported.text
        experiments = imported.json()
        assert len(experiments) == 3
        antigens = {item["conditions_json"]["antigen"] for item in experiments}
        assert antigens == {"hIL12B-His", "cynoIL12H-His", "mIL12B-His"}
        kd_rows = {
            metric["value_numeric"]: metric.get("qualifier")
            for item in experiments
            for metric in item["measurements"]
            if metric["metric_name"] == "KD"
        }
        assert kd_rows == {2.2e-09: None, 8.78e-10: None, 1.0e-12: "<"}

        again = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/experiments/preview-affinity-xlsx",
            files={"file": ("spr.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert again.status_code == 200, again.text
        assert [item["status"] for item in again.json()["rows"]] == [
            "duplicate", "duplicate", "duplicate", "control", "unmatched",
        ]
        overwritten = client.post(
            f"/api/antibody-projects/{project_id}/candidates/{candidate_id}/experiments/import-affinity-xlsx",
            json=import_payload([item for item in again.json()["rows"] if item["selected"]]),
        )
        assert overwritten.status_code == 201, overwritten.text
        assert len(overwritten.json()) == 3
