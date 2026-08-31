"""Validação e correção de códigos de contêiner conforme a ISO 6346.

Um código tem 11 caracteres: quatro letras (três do proprietário mais a
categoria do equipamento), seis dígitos de série e um dígito verificador.

    M S C U  1 2 3 4 5 6  5
    └─ owner ┘└─ serial ─┘└ dv

O dígito verificador é `mod 11` e deixa passar por acaso cerca de um em cada
onze códigos errados. Ele reduz o erro silencioso, não o elimina — quem lê
este módulo esperando garantia vai se decepcionar em produção.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CODE_RE",
    "EQUIPMENT_CATEGORIES",
    "SIZE_TYPE_RE",
    "ValidationResult",
    "apply_positional_correction",
    "check_digit",
    "is_valid",
    "validate",
]

# Valores das letras: começa em 10 e pula todo múltiplo de 11.
_LETTER_VALUES: dict[str, int] = {}
_v = 10
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    while _v % 11 == 0:
        _v += 1
    _LETTER_VALUES[_ch] = _v
    _v += 1

_WEIGHTS = [2**i for i in range(10)]

#: Categorias válidas de equipamento (4ª letra). O ``J`` é o que mais falta em
#: dataset público — não deixe de fora do dicionário do reconhecedor.
EQUIPMENT_CATEGORIES = frozenset("UJZ")

CODE_RE = re.compile(r"^[A-Z]{4}\d{7}$")
SIZE_TYPE_RE = re.compile(r"^\d[0-9A-Z][A-Z0-9]\d$")

#: Confusões que o reconhecedor comete e a posição resolve sozinha.
LETTER_FOR_DIGIT = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
DIGIT_FOR_LETTER = {v: k for k, v in LETTER_FOR_DIGIT.items()}
# Q e D também colidem com 0 na prática; só na direção dígito→letra é ambíguo,
# então mantemos a correção letra→dígito, que é a que a posição autoriza.
DIGIT_FOR_LETTER.update({"D": "0", "Q": "0", "T": "7", "A": "4"})


def check_digit(first_ten: str) -> int:
    """Calcula o dígito verificador dos dez primeiros caracteres.

    Levanta ``ValueError`` se o trecho não tiver dez caracteres alfanuméricos
    maiúsculos — código malformado é erro de programação, não valor de retorno.
    """
    if len(first_ten) != 10:
        raise ValueError(f"esperados 10 caracteres, recebidos {len(first_ten)}")

    total = 0
    for pos, ch in enumerate(first_ten):
        if ch.isdigit():
            value = int(ch)
        elif ch in _LETTER_VALUES:
            value = _LETTER_VALUES[ch]
        else:
            raise ValueError(f"caractere inválido {ch!r} na posição {pos}")
        total += value * _WEIGHTS[pos]

    # O resto 10 é representado por 0 — é o caso que a maioria das
    # implementações caseiras erra.
    return total % 11 % 10


def is_valid(code: str) -> bool:
    """True se o código tem o formato correto e o dígito verificador confere."""
    return validate(code).ok


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    code: str
    reason: str = ""
    expected_check_digit: int | None = None

    def __bool__(self) -> bool:
        return self.ok


def validate(code: str) -> ValidationResult:
    """Valida formato, categoria de equipamento e dígito verificador."""
    normalized = (code or "").strip().upper().replace(" ", "").replace("-", "")

    if not CODE_RE.match(normalized):
        return ValidationResult(False, normalized, "formato fora de [A-Z]{4}[0-9]{7}")

    if normalized[3] not in EQUIPMENT_CATEGORIES:
        return ValidationResult(
            False,
            normalized,
            f"categoria de equipamento {normalized[3]!r} não é U, J nem Z",
        )

    expected = check_digit(normalized[:10])
    if expected != int(normalized[10]):
        return ValidationResult(
            False, normalized, "dígito verificador não confere", expected
        )

    return ValidationResult(True, normalized, expected_check_digit=expected)


def apply_positional_correction(text: str) -> str:
    """Resolve confusões letra/dígito pela posição, antes de qualquer validação.

    As quatro primeiras posições só aceitam letras e as sete últimas só
    dígitos, então metade das confusões clássicas do OCR (``0``/``O``,
    ``1``/``I``, ``5``/``S``, ``8``/``B``) é determinística e não precisa
    consumir orçamento de busca.
    """
    chars = list((text or "").strip().upper())
    if len(chars) != 11:
        return "".join(chars)

    for i in range(4):
        if chars[i].isdigit():
            chars[i] = LETTER_FOR_DIGIT.get(chars[i], chars[i])
    for i in range(4, 11):
        if chars[i].isalpha():
            chars[i] = DIGIT_FOR_LETTER.get(chars[i], chars[i])

    return "".join(chars)
