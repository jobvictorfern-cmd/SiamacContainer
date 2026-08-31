"""Reconhecimento de caracteres.

A interface é ``OcrBackend``. Hoje existem duas implementações:

* ``SimulatedOcr`` — modela o erro em função de px/caractere. Permite exercitar
  o sistema inteiro sem câmera e sem modelo treinado.
* ``RapidOcr`` — o backend real, sobre ONNX Runtime. Importado sob demanda para
  que o protótipo rode sem as dependências pesadas instaladas.

Trocar um pelo outro não muda nada a jusante: pipeline, fusão, validação, banco
e API só conhecem ``OcrRead``.
"""

from __future__ import annotations

from typing import Protocol

from ..fusion import OcrRead

__all__ = ["OcrBackend", "OcrRead", "get_backend"]


class OcrBackend(Protocol):
    name: str

    def read(self, crop, *, camera: str) -> OcrRead:
        """Lê o recorte e devolve o texto com confiança por caractere."""
        ...


def get_backend(kind: str, **kwargs) -> OcrBackend:
    """Instancia o backend pelo nome, importando só o que for necessário."""
    if kind == "simulated":
        from .simulated import SimulatedOcr

        return SimulatedOcr(**kwargs)
    if kind == "rapidocr":
        from .rapid import RapidOcr

        return RapidOcr(**kwargs)
    raise ValueError(f"backend de OCR desconhecido: {kind!r}")
