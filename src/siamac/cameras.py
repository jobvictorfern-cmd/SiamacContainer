"""Fontes de quadro.

Na produção cada câmera entrega um JPEG em resolução plena pelo snapshot HTTP
e o substream RTSP serve só de gatilho. Aqui a interface é ``FrameSource`` e a
única implementação é a simulada — que calcula px/caractere com a mesma
geometria do simulador óptico, para que o protótipo e o dimensionamento falem
a mesma língua.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Protocol

from .ocr.simulated import SimulatedCrop

__all__ = [
    "CONDITIONS",
    "PROJECT_CAMERAS",
    "CameraSpec",
    "FrameSource",
    "SimulatedCamera",
    "px_per_char",
]

R2D = 180.0 / math.pi


@dataclass(frozen=True, slots=True)
class CameraSpec:
    """Óptica e posição de uma câmera. Espelha o simulador de enquadramento."""

    name: str
    res_v: int
    afov_v: float
    projection: str  # "rect" | "cyl"
    distance_m: float  # perpendicular à face lida
    offset_m: float = 0.0  # deslocamento longitudinal até o código
    height_delta_m: float = 0.0  # desnível entre câmera e código


def px_per_char(spec: CameraSpec, char_height_m: float = 0.10) -> float:
    """Altura do caractere em pixels — a conta que decide se a câmera lê.

    Retilínea sobre uma face plana mantém escala uniforme: o deslocamento
    lateral não custa pixel. Cilíndrica tem resolução angular constante, então
    tudo que fica fora do eixo encolhe. São comportamentos opostos, e é por
    isso que a mesma fórmula não serve para as duas.
    """
    L = spec.distance_m
    if L <= 0.05:
        return 0.0

    ground = math.hypot(L, spec.offset_m)
    d3 = math.hypot(ground, spec.height_delta_m)
    tilt = math.atan2(abs(spec.height_delta_m), ground)

    if spec.projection == "cyl":
        px = (spec.res_v / spec.afov_v) * (char_height_m / d3) * R2D
    else:
        px = (char_height_m / (2 * L * math.tan(math.radians(spec.afov_v) / 2))) * spec.res_v

    return px * math.cos(tilt)


#: O arranjo do projeto: duas panorâmicas laterais e uma 4K no fundo.
PROJECT_CAMERAS: tuple[CameraSpec, ...] = (
    CameraSpec("left", 1620, 78.0, "cyl", distance_m=3.0, offset_m=1.2),
    CameraSpec("right", 1620, 78.0, "cyl", distance_m=3.0, offset_m=1.2),
    CameraSpec("rear", 2160, 46.0, "rect", distance_m=5.0, height_delta_m=0.8),
)

#: Multiplicadores de dificuldade por condição de luz, com o peso que a
#: estratificação do plano prevê para a coleta.
CONDITIONS: tuple[tuple[str, float, float], ...] = (
    ("dia claro", 1.00, 0.25),
    ("dia nublado", 1.10, 0.15),
    ("sol direto / contraluz", 1.75, 0.15),
    ("noite com IR", 1.90, 0.25),
    ("chuva", 1.60, 0.10),
    ("repintado / sujo", 2.10, 0.10),
)


class FrameSource(Protocol):
    spec: CameraSpec

    def grab(self, *, truth: str, condition: tuple[str, float]) -> object:
        """Captura o recorte da região do código."""
        ...


class SimulatedCamera:
    """Câmera simulada: entrega um recorte descrito pela sua qualidade óptica."""

    def __init__(self, spec: CameraSpec) -> None:
        self.spec = spec
        self._px = px_per_char(spec)

    @property
    def px_per_char(self) -> float:
        return self._px

    def grab(self, *, truth: str, condition: tuple[str, float]) -> SimulatedCrop:
        name, difficulty = condition
        return SimulatedCrop(
            truth=truth,
            px_per_char=self._px,
            condition=difficulty,
            condition_name=name,
        )


def pick_condition(rng: random.Random) -> tuple[str, float]:
    """Sorteia uma condição de luz com os pesos da estratificação do plano."""
    names = [c[0] for c in CONDITIONS]
    weights = [c[2] for c in CONDITIONS]
    chosen = rng.choices(names, weights=weights, k=1)[0]
    difficulty = next(c[1] for c in CONDITIONS if c[0] == chosen)
    return chosen, difficulty
