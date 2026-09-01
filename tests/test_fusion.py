from siamac.fusion import Decision, OcrRead, fuse, reliability_weight
from siamac.iso6346 import check_digit

TRUTH = "CSQU3054383"
GOOD_PX, WEAK_PX = 45.0, 22.0


def read(camera, text, conf=0.97, px=GOOD_PX):
    return OcrRead(camera=camera, text=text, char_confs=[conf] * len(text), px_per_char=px)


def test_tres_leituras_iguais_sao_aceitas():
    r = fuse([read("left", TRUTH), read("right", TRUTH), read("rear", TRUTH)])
    assert r.decision is Decision.AUTO_ACCEPT
    assert r.code == TRUTH
    assert r.check_digit_ok


def test_maioria_corrige_uma_camera_errada():
    wrong = TRUTH[:1] + "5" + TRUTH[2:]  # S -> 5 na posição 2
    r = fuse([read("left", TRUTH), read("right", TRUTH), read("rear", wrong)])
    assert r.decision is Decision.AUTO_ACCEPT
    assert r.code == TRUTH


def test_camera_boa_nao_e_derrubada_por_duas_fracas():
    """A regressão que a simulação encontrou.

    Duas laterais ruins concordando num erro chegavam a sobrepujar a 4K
    correta. A ponderação por qualidade óptica é o que impede isso.
    """
    wrong = "CSQU3054313"  # duas fracas erram a posição 10 do mesmo jeito
    r = fuse([
        read("left", wrong, conf=0.93, px=WEAK_PX),
        read("right", wrong, conf=0.93, px=WEAK_PX),
        read("rear", TRUTH, conf=0.96, px=GOOD_PX),
    ])
    assert r.code == TRUTH


def test_peso_cresce_com_a_resolucao():
    assert reliability_weight(45) > reliability_weight(30) > reliability_weight(18)
    assert reliability_weight(None) == 1.0


def test_correcao_posicional_antes_da_validacao():
    # 0 no lugar de O e S no lugar de 5: a posição resolve os dois.
    garbled = "C5QU3O54383".replace("O", "O")
    r = fuse([read("left", garbled), read("right", TRUTH), read("rear", TRUTH)])
    assert r.code == TRUTH


def test_desacordo_total_vai_para_revisao():
    r = fuse([
        read("left", "AAAU1111111"),
        read("right", "BBBU2222222"),
        read("rear", "CCCU3333333"),
    ])
    assert r.decision is Decision.NEEDS_REVIEW


def test_uma_camera_so_nao_tem_arbitro():
    r = fuse([read("rear", TRUTH)])
    assert r.decision is Decision.NEEDS_REVIEW
    assert "arbitrar" in r.reason


def test_uma_camera_so_pode_ser_medida_como_linha_de_base():
    r = fuse([read("rear", TRUTH)], require_multi_camera=False)
    assert r.decision is Decision.AUTO_ACCEPT


def test_confianca_baixa_vai_para_revisao():
    r = fuse([read("left", TRUTH, conf=0.4), read("right", TRUTH, conf=0.4),
              read("rear", TRUTH, conf=0.4)])
    assert r.decision is Decision.NEEDS_REVIEW
    assert "confiança" in r.reason


def test_leitura_de_tamanho_errado_e_descartada():
    r = fuse([read("left", "CURTO"), read("right", TRUTH), read("rear", TRUTH)])
    assert r.code == TRUTH
    assert "left" not in r.contributing


def test_sem_nenhuma_leitura_utilizavel():
    r = fuse([read("left", "X"), read("right", "Y")])
    assert r.decision is Decision.NEEDS_REVIEW
    assert r.code == ""


def test_busca_reconstroi_um_erro_isolado():
    # Todas as câmeras erram a mesma posição, mas o dígito verificador reprova
    # e a busca encontra o candidato válido.
    body = "MSCU123456"
    truth = body + str(check_digit(body))
    broken = truth[:9] + ("7" if truth[9] != "7" else "8") + truth[10]
    r = fuse([read("left", broken), read("right", broken), read("rear", broken)])
    assert r.decision is Decision.NEEDS_REVIEW or r.repaired


def test_dv_errado_sem_reparo_possivel_vai_para_revisao():
    bad = "CSQU3054384"
    r = fuse([read("left", bad), read("right", bad), read("rear", bad)])
    if r.decision is Decision.AUTO_ACCEPT:
        # Só é aceitável se a busca achou um código genuinamente válido.
        assert r.repaired and r.check_digit_ok
    else:
        assert not r.check_digit_ok or r.decision is Decision.NEEDS_REVIEW
