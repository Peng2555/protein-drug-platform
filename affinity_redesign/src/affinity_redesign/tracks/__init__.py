"""打分轨：PLM 与 AntiFold。

注意：不要在此做 eager import。结构轨 worker 在 maxwell env 中运行，
不应被迫加载 pydantic_settings 等编排层依赖。
"""

__all__ = ["score_plm_track", "score_structure_track"]


def __getattr__(name: str):
    if name == "score_plm_track":
        from affinity_redesign.tracks.plm import score_plm_track

        return score_plm_track
    if name == "score_structure_track":
        from affinity_redesign.tracks.antifold import score_structure_track

        return score_structure_track
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
