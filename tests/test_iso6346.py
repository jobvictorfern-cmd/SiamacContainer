import pytest

from siamac.iso6346 import (
    apply_positional_correction,
    check_digit,
    is_valid,
    validate,
)

# Vetores publicados e códigos reais de proprietários conhecidos.
VALID = [
    "CSQU3054383",  # o exemplo canônico da norma
    "MSCU0000060",  # resto 10 -> dígito 0, o caso que quase toda implementação erra
    "TCNU1234565",
    "HLCU1234568",
]


@pytest.mark.parametrize("code", VALID)
def test_codigos_validos_passam(code):
    assert is_valid(code), validate(code).reason


@pytest.mark.parametrize("code", VALID)
def test_alterar_um_digito_reprova(code):
    # Trocar o dígito verificador tem de reprovar sempre.
    other = "0" if code[-1] != "0" else "1"
    assert not is_valid(code[:10] + other)


def test_exemplo_da_norma_tem_digito_3():
    assert check_digit("CSQU305438") == 3


def test_resto_dez_vira_zero():
    # Sem o "% 10" final, este caso devolveria 10 e o código seria rejeitado.
    assert check_digit("MSCU000006") == 0


def test_ida_e_volta_para_todo_prefixo_e_serie():
    """Gerar com check_digit e validar tem de fechar sempre.

    Vale mais que vetor cravado à mão: pega qualquer regressão no mapa de
    letras, nos pesos ou no tratamento do resto 10.
    """
    for owner in ("MSC", "HLC", "TCN", "OOL", "ZIM"):
        for cat in "UJZ":
            for serial in (0, 1, 6, 99999, 123456, 999999):
                body = f"{owner}{cat}{serial:06d}"
                assert is_valid(body + str(check_digit(body)))


def test_categoria_de_equipamento_invalida():
    r = validate("MSCA1234561")
    assert not r.ok
    assert "categoria" in r.reason


def test_categoria_j_e_valida():
    # O J quase não aparece em dataset público, mas é categoria legítima —
    # deixá-lo fora do dicionário do reconhecedor custa leituras reais.
    body = "MSCJ123456"
    assert is_valid(body + str(check_digit(body)))


def test_formato_errado():
    assert not validate("MSC123456").ok
    assert not validate("MSCU12345").ok
    assert not validate("").ok


def test_normaliza_espaco_hifen_e_minuscula():
    assert validate("csqu 305438-3").ok


def test_check_digit_rejeita_entrada_malformada():
    with pytest.raises(ValueError):
        check_digit("CURTO")
    with pytest.raises(ValueError):
        check_digit("MSCU12345!")


def test_correcao_posicional_letras_e_digitos():
    # 0->O nas quatro primeiras, letras->dígitos nas sete últimas.
    assert apply_positional_correction("0SCU1234S6S") == "OSCU1234565"
    assert apply_positional_correction("1SCU12345B7") == "ISCU1234587"


def test_correcao_posicional_nao_mexe_no_que_esta_certo():
    assert apply_positional_correction("CSQU3054383") == "CSQU3054383"


def test_correcao_posicional_ignora_tamanho_errado():
    assert apply_positional_correction("ABC") == "ABC"
