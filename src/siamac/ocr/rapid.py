"""Backend real: modelos PP-OCR em ONNX Runtime, via RapidOCR.

Nada é baixado em tempo de execução. Os três caminhos de modelo e o dicionário
de 36 caracteres vêm do ``config.yaml`` e precisam existir em disco — um
serviço Windows rodando como ``LocalSystem`` não enxerga o cache de usuário, e
descobrir isso em produção custa uma viagem.
"""

from __future__ import annotations

from pathlib import Path

from ..fusion import OcrRead

__all__ = ["RapidOcr"]


class RapidOcr:
    """Envelopa o RapidOCR e normaliza a saída para ``OcrRead``."""

    name = "rapidocr"

    def __init__(
        self,
        *,
        det_model_path: str | Path,
        rec_model_path: str | Path,
        rec_keys_path: str | Path,
        cls_model_path: str | Path | None = None,
    ) -> None:
        from rapidocr import RapidOCR  # import tardio: dependência opcional

        for label, p in [
            ("det", det_model_path),
            ("rec", rec_model_path),
            ("dicionário", rec_keys_path),
        ]:
            if not Path(p).is_file():
                raise FileNotFoundError(
                    f"modelo {label} não encontrado em {p!r}. "
                    "Todo modelo vai embarcado com caminho absoluto — "
                    "nada é baixado em runtime."
                )

        params = {
            "Det.model_path": str(det_model_path),
            "Rec.model_path": str(rec_model_path),
            "Rec.rec_keys_path": str(rec_keys_path),
        }
        if cls_model_path:
            params["Cls.model_path"] = str(cls_model_path)

        self._engine = RapidOCR(params=params)

    def read(self, crop, *, camera: str) -> OcrRead:
        result = self._engine(crop)

        texts = getattr(result, "txts", None) or []
        scores = getattr(result, "scores", None) or []

        if not texts:
            return OcrRead(camera=camera, text="", char_confs=[])

        # O recorte é de uma linha só; se o detector partiu em mais de uma,
        # junta na ordem em que vieram.
        text = "".join(texts).upper().replace(" ", "")

        # O PP-OCR devolve confiança por linha, não por caractere. Até termos
        # a saída bruta do CTC, replicar a confiança da linha é a aproximação
        # honesta — e a fusão continua funcionando sobre ela.
        line_conf = sum(scores) / len(scores) if scores else 0.0
        return OcrRead(
            camera=camera,
            text=text,
            char_confs=[float(line_conf)] * len(text),
        )
