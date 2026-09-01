"""Backend de OCR simulado, com o erro em função da resolução.

Não é um mock que devolve o gabarito. É um modelo do reconhecedor: dada a
qualidade óptica do recorte (px por caractere), ele erra na taxa que um
reconhecedor real erraria, e erra nas *confusões que um reconhecedor real
comete* — ``0``/``O``, ``5``/``S``, ``8``/``B`` — em vez de sortear letras.

Isso é o que torna o protótipo capaz de responder à pergunta que o plano faz:
quanto a fusão das três câmeras realmente ganha sobre uma câmera só.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..fusion import CODE_LEN, OcrRead

__all__ = ["SimulatedCrop", "SimulatedOcr", "error_rate_for"]

#: Pares que o reconhecedor troca de verdade, por semelhança de forma.
CONFUSABLE: dict[str, tuple[str, ...]] = {
    "0": ("O", "D", "Q"), "O": ("0", "D", "Q"),
    "1": ("I", "7", "L"), "I": ("1", "L", "T"),
    "2": ("Z", "7"),      "Z": ("2", "7"),
    "5": ("S", "6"),      "S": ("5", "8"),
    "6": ("G", "5", "8"), "G": ("6", "C"),
    "8": ("B", "3", "6"), "B": ("8", "R"),
    "3": ("8", "9"),      "4": ("A", "9"),
    "7": ("1", "T", "2"), "9": ("4", "3", "0"),
    "A": ("4", "R"),      "C": ("G", "O"),
    "D": ("0", "O"),      "E": ("F", "B"),
    "F": ("E", "P"),      "H": ("N", "M"),
    "K": ("X", "R"),      "L": ("1", "I"),
    "M": ("N", "H"),      "N": ("M", "H"),
    "P": ("R", "F"),      "Q": ("O", "0"),
    "R": ("P", "B", "K"), "T": ("7", "I"),
    "U": ("V", "J"),      "V": ("U", "Y"),
    "W": ("V", "M"),      "X": ("K", "Y"),
    "Y": ("V", "X"),      "J": ("U", "I"),
}

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"


def error_rate_for(px_per_char: float) -> float:
    """Probabilidade de errar um caractere, dado px de altura.

    Calibrada contra a régua prática da literatura de OCR: acima de ~30 px a
    leitura é confiável, entre 20 e 30 px degrada rápido, abaixo de 20 px não
    se sustenta. Decai exponencialmente a partir de 18 px, onde fica em 50%.
    """
    if px_per_char <= 0:
        return 1.0
    return min(0.85, 0.5 * math.exp(-(px_per_char - 18.0) / 7.0))


@dataclass(slots=True)
class SimulatedCrop:
    """O que uma câmera simulada entrega no lugar de uma imagem."""

    truth: str
    px_per_char: float
    #: Multiplicador de dificuldade da condição: 1,0 = dia claro.
    condition: float = 1.0
    condition_name: str = "dia claro"


class SimulatedOcr:
    """Reconhecedor simulado. Determinístico quando recebe uma ``seed``."""

    name = "simulated"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def read(self, crop: SimulatedCrop, *, camera: str) -> OcrRead:
        base_rate = error_rate_for(crop.px_per_char) * crop.condition
        base_rate = min(base_rate, 0.9)

        chars: list[str] = []
        confs: list[float] = []

        for i, true_ch in enumerate(crop.truth[:CODE_LEN]):
            if self._rng.random() < base_rate:
                chars.append(self._confuse(true_ch, i))
                confs.append(self._wrong_confidence())
            else:
                chars.append(true_ch)
                confs.append(self._right_confidence())

        return OcrRead(
            camera=camera,
            text="".join(chars),
            char_confs=confs,
            px_per_char=crop.px_per_char,
        )

    #: Fração dos erros que sai com confiança alta. É o parâmetro que governa
    #: o erro silencioso: se acerto e erro fossem separáveis pela confiança,
    #: bastaria um limiar e o problema não existiria.
    CONFIDENT_WHEN_WRONG = 0.30

    def _right_confidence(self) -> float:
        # Acerto quase sempre confiante, mas com cauda baixa: contraluz e IR
        # produzem leitura correta e insegura o tempo todo.
        return 0.72 + 0.28 * self._rng.random() ** 0.45

    def _wrong_confidence(self) -> float:
        if self._rng.random() < self.CONFIDENT_WHEN_WRONG:
            return 0.88 + 0.11 * self._rng.random()
        return 0.45 + 0.43 * self._rng.random()

    def _confuse(self, ch: str, position: int) -> str:
        """Troca por um caractere parecido; às vezes por um qualquer."""
        alts = CONFUSABLE.get(ch, ())
        if alts and self._rng.random() < 0.75:
            return self._rng.choice(alts)
        pool = _LETTERS if position < 4 else _DIGITS
        return self._rng.choice([c for c in pool if c != ch])
