"""Business modules and their ordered FastAPI router registry."""

from app.modules.affinity_redesign.router import router as affinity_router
from app.modules.antibody_projects.router import router as antibody_projects_router
from app.modules.auth.router import router as auth_router
from app.modules.cic_profile.router import router as cic_router
from app.modules.developability.router import router as developability_router
from app.modules.design.router import router as design_router
from app.modules.docking.router import router as docking_router
from app.modules.fold.batch_router import router as fold_batch_router
from app.modules.fold.router import router as fold_router
from app.modules.hydro_redesign.router import router as hydro_router
from app.modules.masking_peptide.router import router as masking_router
from app.modules.maturation.router import router as maturation_router
from app.modules.md.router import router as md_router
from app.modules.ras_docking.router import router as ras_docking_router
from app.modules.rosetta_eval.router import router as rosetta_eval_router
from app.modules.synthesis.router import router as synthesis_router
from app.modules.tnp_profile.router import router as tnp_router

ROUTERS = (
    auth_router,
    antibody_projects_router,
    fold_router,
    fold_batch_router,
    md_router,
    maturation_router,
    synthesis_router,
    ras_docking_router,
    docking_router,
    developability_router,
    design_router,
    rosetta_eval_router,
    affinity_router,
    masking_router,
    hydro_router,
    cic_router,
    tnp_router,
)

__all__ = ["ROUTERS"]
