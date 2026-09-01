# SiamacContainer

Leitura automática do código ISO 6346 de contêineres na portaria, com três
câmeras IP, correção humana pela API e melhoria contínua alimentada pela
própria operação.

O planejamento completo está em **[PLANO.md](PLANO.md)**.

## Protótipo

O sistema roda hoje, sem câmera e sem modelo treinado. As camadas de captura e
de OCR são interfaces com uma implementação simulada; **todo o resto é código
de produção** — recorte, fusão, validação ISO 6346, banco, API, correção
humana e outbox.

```
┌── simulado ──────────┐  ┌── produção, roda de verdade ────────────────────┐
│ cameras.py           │  │ pipeline · fusion · iso6346 · storage · api     │
│ ocr/simulated.py     │→ │                                                 │
└──────────────────────┘  └─────────────────────────────────────────────────┘
     troque por              nada abaixo muda
   snapshot HTTP +
   ocr/rapid.py (ONNX)
```

### Rodar

```bash
uv venv && uv pip install -e ".[dev]"

pytest                          # 43 testes
python -m siamac.demo           # simula a portaria e mede a fusão
uvicorn siamac.app:app          # sobe a API
```

### A pergunta que o demo responde

Três câmeras votando valem mais que a melhor câmera sozinha? O demo mede as
duas configurações sobre os mesmos eventos:

```
                        auto-aceite correto   erro silencioso   revisão
só a 4K do fundo                    88.8%              0.38%      10.8%
as 3 câmeras                        99.2%              0.43%       0.4%
```

**A fusão compra +10,4 pp de auto-aceite a custo praticamente neutro de erro
silencioso.** Não é o ganho de acurácia bruta que se esperaria — é a redução
da fila de revisão manual, que é onde está o custo operacional.

> ⚠️ **Descoberta do protótipo, e ela mudou o desenho.** Na primeira versão a
> fusão *piorava* o erro silencioso (0,38% → 1,05%): duas laterais a 29 px
> erram 9,6% por caractere contra 1,6% da 4K, e votando com peso igual
> derrubavam a leitura boa. Houve caso de a 4K acertar o código inteiro e a
> fusão corrompê-lo. A correção é `reliability_weight()` em `fusion.py`:
> o voto de cada câmera é ponderado pela sua qualidade óptica. Sem isso,
> três câmeras são piores que uma.

Explore a geometria:

```bash
python -m siamac.demo --side-dist 3.0 --side-offset 1.0 --rear-dist 5.0
python -m siamac.demo --side-dist 5.0 --side-offset 4.0   # laterais inúteis
```

### Trocar o simulado pelo real

| Hoje | Em produção | O que muda a jusante |
|---|---|---|
| `SimulatedCamera` | snapshot HTTP CGI + substream RTSP | nada |
| `SimulatedOcr` | `RapidOcr` (ONNX Runtime, modelos locais) | nada |

`ocr/rapid.py` já está escrito e recusa iniciar se algum modelo faltar — nada
é baixado em tempo de execução.

## Estrutura

| Módulo | Papel |
|---|---|
| `iso6346.py` | Dígito verificador `mod 11`, categorias, correção posicional |
| `fusion.py` | ⭐ Votação por caractere ponderada por qualidade óptica |
| `cameras.py` | Geometria e `px_per_char()` — a conta que decide o projeto |
| `pipeline.py` | captura → recorte → OCR → fusão → decisão → banco |
| `api.py` | Integração, fila de revisão, correção humana, outbox |
| `storage.py` | SQLite: eventos, leituras, outbox, amostras de treino |
| `demo.py` | Simulação da portaria com métricas |

## Licença e atribuições

Uso interno. Ver `PLANO.md` §2 para a análise de licenças de TRUDI
(CC BY-SA 4.0), PaddleOCR e RapidOCR (Apache-2.0).
