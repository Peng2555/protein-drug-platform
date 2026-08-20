"""Lightweight cavity detection for CB-Dock-style blind docking.

基于受体重原子附近的溶剂可及网格 + 埋藏度过滤，估算候选口袋中心与搜索盒。
不依赖 fpocket / CurPocket，便于在现有环境中直接运行。
"""

from __future__ import annotations

from pathlib import Path


def _protein_coords(path: Path) -> list[list[float]]:
    suffix = path.suffix.lower()
    if suffix in {".cif", ".mmcif"}:
        import gemmi

        structure = gemmi.read_structure(str(path))
        return [
            [atom.pos.x, atom.pos.y, atom.pos.z]
            for model in structure
            for chain in model
            for residue in chain
            for atom in residue
            if atom.element.name != "H" and residue.name not in {"HOH", "WAT", "SOL"}
        ]
    coords: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM"):
            continue
        try:
            res = line[17:20].strip()
            if res in {"HOH", "WAT", "SOL"}:
                continue
            coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        except ValueError:
            continue
    if not coords:
        raise ValueError("受体中未找到可用的蛋白原子坐标")
    return coords


def detect_cavities(
    receptor_path: Path,
    *,
    num_cavities: int = 5,
    grid_spacing: float = 1.4,
    probe_radius: float = 1.5,
    max_surface_dist: float = 4.5,
    bury_radius: float = 8.0,
    min_bury_neighbors: int = 45,
    min_points: int = 18,
    box_padding: float = 4.0,
    min_box: float = 18.0,
    max_box: float = 28.0,
) -> list[dict]:
    """Return ranked cavities with center/size suitable for Vina boxes."""
    import numpy as np
    from scipy.ndimage import label
    from scipy.spatial import cKDTree

    coords = np.asarray(_protein_coords(receptor_path), dtype=float)
    if coords.shape[0] < 20:
        raise ValueError("受体原子过少，无法检测口袋")

    tree = cKDTree(coords)
    mins = coords.min(axis=0) - max_surface_dist
    maxs = coords.max(axis=0) + max_surface_dist
    xs = np.arange(mins[0], maxs[0] + grid_spacing, grid_spacing)
    ys = np.arange(mins[1], maxs[1] + grid_spacing, grid_spacing)
    zs = np.arange(mins[2], maxs[2] + grid_spacing, grid_spacing)
    max_cells = 160
    if len(xs) > max_cells or len(ys) > max_cells or len(zs) > max_cells:
        spacing = max(
            grid_spacing,
            (maxs[0] - mins[0]) / max_cells,
            (maxs[1] - mins[1]) / max_cells,
            (maxs[2] - mins[2]) / max_cells,
        )
        xs = np.arange(mins[0], maxs[0] + spacing, spacing)
        ys = np.arange(mins[1], maxs[1] + spacing, spacing)
        zs = np.arange(mins[2], maxs[2] + spacing, spacing)
        grid_spacing = float(spacing)

    xx, yy, zz = np.meshgrid(xs, ys, zs, indexing="ij")
    grid = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
    dist, _ = tree.query(grid, k=1, workers=-1)
    # near-surface empty points (not inside atoms, not far away in bulk solvent)
    near = (dist > probe_radius) & (dist < max_surface_dist)
    if not np.any(near):
        raise ValueError("未检测到候选口袋，请改用参考配体或手动指定搜索盒")

    near_idx = np.flatnonzero(near)
    near_pts = grid[near_idx]
    # buriedness: concave/pocket-like points have many protein atoms around them
    bury_counts = tree.query_ball_point(near_pts, r=bury_radius, return_length=True)
    buried = bury_counts >= min_bury_neighbors
    if not np.any(buried):
        # fallback: take the most buried near-surface points
        order = np.argsort(-bury_counts)[: max(80, int(0.08 * len(bury_counts)))]
        buried = np.zeros_like(bury_counts, dtype=bool)
        buried[order] = True

    keep_idx = near_idx[buried]
    shape = (len(xs), len(ys), len(zs))
    volume = np.zeros(shape, dtype=np.uint8)
    volume.ravel()[keep_idx] = 1
    labeled, n_feat = label(volume)
    cavities: list[dict] = []
    for cid in range(1, n_feat + 1):
        idx = np.argwhere(labeled == cid)
        if idx.shape[0] < min_points:
            continue
        pts = np.column_stack(
            [
                xs[idx[:, 0]],
                ys[idx[:, 1]],
                zs[idx[:, 2]],
            ]
        )
        center = pts.mean(axis=0)
        extent = pts.max(axis=0) - pts.min(axis=0) + 2 * box_padding
        size = np.clip(extent, min_box, max_box)
        volume_a3 = float(idx.shape[0] * (grid_spacing**3))
        cavities.append(
            {
                "cavity_id": 0,
                "n_points": int(idx.shape[0]),
                "volume": round(volume_a3, 1),
                "center_x": round(float(center[0]), 3),
                "center_y": round(float(center[1]), 3),
                "center_z": round(float(center[2]), 3),
                "size_x": round(float(size[0]), 3),
                "size_y": round(float(size[1]), 3),
                "size_z": round(float(size[2]), 3),
            }
        )

    cavities.sort(key=lambda c: (-c["volume"], -c["n_points"]))
    # 过大的连通域通常是外表面残壳，优先保留中等体积口袋
    preferred = [c for c in cavities if 50.0 <= c["volume"] <= 6000.0]
    pool = preferred if preferred else cavities
    top = pool[: max(1, min(19, int(num_cavities)))]
    for i, cav in enumerate(top, start=1):
        cav["cavity_id"] = i
    if not top:
        raise ValueError("口袋聚类后为空，请增大 num_cavities 或改用指定口袋模式")
    return top
