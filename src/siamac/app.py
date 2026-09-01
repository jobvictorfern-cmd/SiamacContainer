"""Ponto de entrada do serviço.

    uvicorn siamac.app:app --host 127.0.0.1 --port 8477

Em produção quem sobe isto é o WinSW, como serviço Windows, sem sessão de
usuário logada — por isso nada aqui abre janela, lê de ``stdin`` ou depende de
caminho relativo.
"""

from __future__ import annotations

import os
import random

from .api import create_app
from .cameras import PROJECT_CAMERAS, SimulatedCamera
from .ocr import get_backend
from .pipeline import Pipeline, PipelineConfig
from .storage import make_engine, make_session_factory

__all__ = ["app", "build"]


def build():
    """Monta o serviço a partir do ambiente.

    O backend de OCR é escolhido por ``SIAMAC_OCR``. O padrão é o simulado,
    para que o protótipo suba sem modelo em disco; ``rapidocr`` exige os três
    caminhos de modelo e falha alto se algum faltar.
    """
    engine = make_engine(os.environ.get("SIAMAC_DB", "sqlite:///siamac.db"))
    session_factory = make_session_factory(engine)

    backend = os.environ.get("SIAMAC_OCR", "simulated")
    if backend == "rapidocr":
        ocr = get_backend(
            "rapidocr",
            det_model_path=os.environ["SIAMAC_DET_MODEL"],
            rec_model_path=os.environ["SIAMAC_REC_MODEL"],
            rec_keys_path=os.environ["SIAMAC_REC_KEYS"],
        )
    else:
        ocr = get_backend("simulated")

    pipeline = Pipeline(
        [SimulatedCamera(spec) for spec in PROJECT_CAMERAS],
        ocr,
        config=PipelineConfig(
            min_confidence=float(os.environ.get("SIAMAC_MIN_CONFIDENCE", "0.75")),
            min_agreement=float(os.environ.get("SIAMAC_MIN_AGREEMENT", "0.60")),
        ),
        session_factory=session_factory,
        rng=random.Random(),
    )

    return create_app(
        session_factory=session_factory,
        pipeline=pipeline,
        api_key=os.environ.get("SIAMAC_API_KEY"),
    )


app = build()
