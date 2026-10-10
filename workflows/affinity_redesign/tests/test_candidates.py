from pathlib import Path

from affinity_redesign.common.candidates import enumerate_single_point_mutations
from affinity_redesign.common.cdr import annotate_antibody_chain
from affinity_redesign.pipeline.prepare import prepare_campaign


EXAMPLE = Path(__file__).resolve().parents[1] / "campaigns" / "examples" / "lycov1404_7mmo"
RUN_DEMO = Path(__file__).resolve().parents[3] / "runs" / "lycov1404_7mmo__demo"


def test_annotate_lycov_heavy():
    fasta = (EXAMPLE / "sequences.fasta").read_text(encoding="utf-8")
    # crude parse
    lines = fasta.strip().splitlines()
    seq = "".join(l for l in lines[1:] if not l.startswith(">")).split(">")[0].replace("\n", "")
    # better: only H
    from affinity_redesign.common.fasta import parse_fasta
    seqs = parse_fasta(fasta)
    ab = annotate_antibody_chain(seqs["H"])
    assert ab is not None
    assert ab["domain"] == "H"
    assert ab["query_end"] - ab["query_start"] + 1 == 119


def test_enumerate_counts():
    from affinity_redesign.common.fasta import parse_fasta
    seqs = parse_fasta((EXAMPLE / "sequences.fasta").read_text(encoding="utf-8"))
    recs = enumerate_single_point_mutations("H", seqs["H"])
    # 119 positions * 19 = 2261
    assert len(recs) == 119 * 19


def test_prepare_demo_campaign():
    if not (RUN_DEMO / "input" / "complex.pdb").is_file():
        return  # skip if demo not materialised
    manifest = prepare_campaign(RUN_DEMO)
    assert manifest["candidates"]["raw_count"] > 4000
    assert (RUN_DEMO / "prepare" / "candidates_filtered.csv").is_file()
