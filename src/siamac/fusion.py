"""Fusão das leituras das três câmeras.

O mesmo código de 11 caracteres está impresso nos dois lados e no fundo do
contêiner, então três leituras independentes do mesmo evento podem votar
caractere a caractere. O dígito verificador da ISO 6346 arbitra o resultado.

É a alavanca principal do sistema: dois reconhecedores errarem o *mesmo*
caractere para o *mesmo* valor errado é muito menos provável que um errar
sozinho, e é isso que separa 'lê às vezes' de 'lê o suficiente para confiar'.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from .iso6346 import apply_positional_correction, validate

__all__ = ["Decision", "FusionResult", "OcrRead", "fuse", "reliability_weight"]

CODE_LEN = 11
#: Quantas alternativas por posição a busca considera quando o dígito
#: verificador reprova o vencedor da votação. Mantido baixo de propósito:
#: com `mod 11` deixando passar ~1 em 11, uma busca larga encontra códigos
#: "válidos" que são apenas coincidência aritmética.
BEAM_TOP_K = 2
BEAM_MAX_POSITIONS = 2


class Decision(StrEnum):
    AUTO_ACCEPT = "AUTO_ACCEPT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


def reliability_weight(px_per_char: float | None) -> float:
    """Peso do voto de uma câmera, em função da sua qualidade óptica.

    Sem isto, duas câmeras ruins derrubam uma boa por maioria simples — e o
    sistema fica *pior* que a melhor câmera sozinha. A curva é logística em
    torno de 24 px: a 42 px o voto vale 0,99; a 29 px, 0,78; a 20 px, 0,27.
    """
    if px_per_char is None:
        return 1.0
    return 1.0 / (1.0 + math.exp(-(px_per_char - 24.0) / 4.0))


@dataclass(slots=True)
class OcrRead:
    """Uma leitura de uma câmera, com confiança por caractere."""

    camera: str
    text: str
    char_confs: list[float]
    px_per_char: float | None = None

    @property
    def mean_conf(self) -> float:
        return sum(self.char_confs) / len(self.char_confs) if self.char_confs else 0.0

    @property
    def weight(self) -> float:
        return reliability_weight(self.px_per_char)

    @property
    def usable(self) -> bool:
        return len(self.text) == CODE_LEN and len(self.char_confs) == CODE_LEN


@dataclass(slots=True)
class FusionResult:
    code: str
    decision: Decision
    confidence: float
    agreement: float
    check_digit_ok: bool
    reason: str
    per_camera: dict[str, str] = field(default_factory=dict)
    contributing: list[str] = field(default_factory=list)
    repaired: bool = False


def _vote(reads: list[OcrRead]) -> tuple[str, list[float], list[list[tuple[str, float]]]]:
    """Votação ponderada por confiança, posição a posição.

    Devolve o texto vencedor, a confiança normalizada de cada posição e, para
    cada posição, os candidatos ordenados — que a busca usa se o dígito
    verificador reprovar.
    """
    winners: list[str] = []
    confs: list[float] = []
    ranked: list[list[tuple[str, float]]] = []

    for i in range(CODE_LEN):
        scores: dict[str, float] = defaultdict(float)
        for r in reads:
            # Ponderar pela qualidade óptica é o que impede duas câmeras
            # fracas de sobrepujarem a boa por maioria simples.
            scores[r.text[i]] += r.char_confs[i] * r.weight

        total = sum(scores.values()) or 1.0
        order = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        winners.append(order[0][0])
        confs.append(order[0][1] / total)
        ranked.append([(ch, s / total) for ch, s in order])

    return "".join(winners), confs, ranked


def _search_valid(ranked: list[list[tuple[str, float]]], base: str) -> str | None:
    """Procura, entre as alternativas mais fracas, um código que valide.

    Só mexe nas posições menos confiantes e só considera ``BEAM_TOP_K``
    candidatos em cada — a busca existe para consertar um erro isolado, não
    para caçar qualquer string que satisfaça o `mod 11`.
    """
    # posições mais duvidosas primeiro
    order = sorted(
        range(CODE_LEN),
        key=lambda i: ranked[i][0][1] if ranked[i] else 1.0,
    )[:BEAM_MAX_POSITIONS]

    options: list[list[str]] = []
    for i in range(CODE_LEN):
        if i in order:
            alts = [ch for ch, _ in ranked[i][:BEAM_TOP_K]]
            if base[i] not in alts:
                alts.insert(0, base[i])
            options.append(alts)
        else:
            options.append([base[i]])

    for combo in itertools.product(*options):
        candidate = apply_positional_correction("".join(combo))
        if candidate == base:
            continue
        if validate(candidate).ok:
            return candidate
    return None


def fuse(
    reads: list[OcrRead],
    *,
    min_confidence: float = 0.75,
    min_agreement: float = 0.60,
    require_multi_camera: bool = True,
) -> FusionResult:
    """Combina as leituras num único código e decide se aceita automaticamente.

    ``min_agreement`` é a concordância média entre câmeras exigida para o
    auto-aceite. Ele existe porque o dígito verificador sozinho não basta:
    com ``mod 11`` deixando passar cerca de 1 em 11 códigos errados, a
    concordância é o que impede o erro silencioso de virar rotina.

    ``require_multi_camera`` manda para revisão o evento em que só uma câmera
    leu — não há com que arbitrar. Em produção fica ligado; desligue apenas
    para medir uma câmera isolada como linha de base.
    """
    usable = [r for r in reads if r.usable]
    per_camera = {r.camera: r.text for r in reads}

    if not usable:
        return FusionResult(
            code="",
            decision=Decision.NEEDS_REVIEW,
            confidence=0.0,
            agreement=0.0,
            check_digit_ok=False,
            reason="nenhuma câmera entregou uma leitura de 11 caracteres",
            per_camera=per_camera,
        )

    raw, confs, ranked = _vote(usable)
    voted = apply_positional_correction(raw)

    # A correção posicional pode ter mudado caracteres; refaz o ranking para
    # que a busca opere sobre o mesmo alfabeto que a validação vai ver.
    agreement = sum(confs) / CODE_LEN
    confidence = min(
        sum(r.mean_conf for r in usable) / len(usable),
        agreement,
    )

    result = validate(voted)
    code, repaired = voted, False

    if not result.ok:
        recovered = _search_valid(ranked, voted)
        if recovered is not None:
            code, repaired, result = recovered, True, validate(recovered)

    contributing = [r.camera for r in usable]

    if not result.ok:
        return FusionResult(
            code=code,
            decision=Decision.NEEDS_REVIEW,
            confidence=confidence,
            agreement=agreement,
            check_digit_ok=False,
            reason=result.reason or "dígito verificador não confere",
            per_camera=per_camera,
            contributing=contributing,
            repaired=repaired,
        )

    if require_multi_camera and len(usable) == 1:
        return FusionResult(
            code=code,
            decision=Decision.NEEDS_REVIEW,
            confidence=confidence,
            agreement=agreement,
            check_digit_ok=True,
            reason="apenas uma câmera leu — sem concordância para arbitrar",
            per_camera=per_camera,
            contributing=contributing,
            repaired=repaired,
        )

    if confidence < min_confidence:
        return FusionResult(
            code=code,
            decision=Decision.NEEDS_REVIEW,
            confidence=confidence,
            agreement=agreement,
            check_digit_ok=True,
            reason=f"confiança {confidence:.2f} abaixo do mínimo {min_confidence:.2f}",
            per_camera=per_camera,
            contributing=contributing,
            repaired=repaired,
        )

    if agreement < min_agreement:
        return FusionResult(
            code=code,
            decision=Decision.NEEDS_REVIEW,
            confidence=confidence,
            agreement=agreement,
            check_digit_ok=True,
            reason=f"câmeras discordam demais (concordância {agreement:.2f})",
            per_camera=per_camera,
            contributing=contributing,
            repaired=repaired,
        )

    return FusionResult(
        code=code,
        decision=Decision.AUTO_ACCEPT,
        confidence=confidence,
        agreement=agreement,
        check_digit_ok=True,
        reason="reconstruído pela busca e validado" if repaired else "votação válida",
        per_camera=per_camera,
        contributing=contributing,
        repaired=repaired,
    )
