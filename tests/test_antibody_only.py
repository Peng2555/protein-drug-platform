from app.antibody_only import AntibodySpec, parse_antibody_text, prepare_antibody_only_jobs


def test_csv_vhh_and_hl():
    text = "id,heavy,light\nVHH_001,QVQLQESGGGLVQPGGSLRLSCAASG\nIgG_001,EVQLVESGGGLVQPGGSLRLSCAASG,DIQMTQSPSSLSASVGDRVTITCRAS"
    rows, fmt = parse_antibody_text(text)
    assert fmt == "csv"
    assert len(rows) == 2
    assert rows[0].id == "VHH_001" and rows[0].light is None
    assert rows[1].id == "IgG_001" and rows[1].light.startswith("DIQMT")


def test_fasta_pairing():
    text = """>VHH_001
QVQLQESGGGLVQPGGSLRLSCAASG
>IgG_001_H
EVQLVESGGGLVQPGGSLRLSCAASG
>IgG_001_L
DIQMTQSPSSLSASVGDRVTITCRAS
"""
    rows, fmt = parse_antibody_text(text)
    assert fmt == "fasta"
    by_id = {r.id: r for r in rows}
    assert by_id["VHH_001"].light is None
    assert by_id["IgG_001"].light.startswith("DIQMT")


def test_generic_h_l_pair():
    text = ">H\nQVQLQESGGGLVQPGGSLRLSCAASG\n>L\nDIQMTQSPSSLSASVGDRVTITCRAS\n"
    rows, _ = parse_antibody_text(text)
    assert len(rows) == 1
    assert rows[0].id == "Ab"
    assert rows[0].light


def test_prepare_fasta_no_antigen():
    antibodies = [
        AntibodySpec(id="VHH_001", heavy="QVQLQESGGGLVQPGGSLRLSCAASG"),
        AntibodySpec(id="IgG_001", heavy="EVQLVESGGGLVQPGGSLRLSCAASG", light="DIQMTQSPSSLSASVGDRVTITCRAS"),
    ]
    name, jobs, skipped = prepare_antibody_only_jobs(batch_name="ab_test", antibodies=antibodies)
    assert name == "ab_test"
    assert skipped == 0
    assert len(jobs) == 2
    _n, hid, fasta = jobs[0]
    assert hid == "VHH_001"
    assert fasta.startswith(">H\n")
    assert ">A\n" not in fasta
    _n, hid, fasta = jobs[1]
    assert ">L\n" in fasta
    assert fasta.count(">") == 2
