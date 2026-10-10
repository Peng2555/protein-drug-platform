"""下载附件头必须能按 latin-1 编码。"""

from __future__ import annotations

from starlette.responses import Response

from app.common.job_paths import attachment_content_disposition


def test_attachment_content_disposition_accepts_chinese_job_names() -> None:
    header = attachment_content_disposition("抗体折叠_samples.zip")
    Response(content=b"PK", media_type="application/zip", headers={"Content-Disposition": header})
    assert 'filename="download_samples.zip"' in header or 'filename="' in header
    assert "filename*=UTF-8''" in header
    encoded = header.split("filename*=UTF-8''", 1)[1]
    assert encoded
    # ASCII filename 部分必须能按 latin-1 编码
    header.encode("latin-1")
    assert "zip" in header

