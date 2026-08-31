# SiamacContainer — Leitura Automática de Código de Contêiner

**Repositório:** `jobvictorfern-cmd/SiamacContainer` (vazio — projeto novo)
**Data:** 31/08/2026 · **Viagem de instalação:** outubro/2026 · **Produção:** dezembro/2026

---

## 1. O que é

Sistema que lê automaticamente o código ISO 6346 de contêineres sobre caminhão, na portaria, usando 3 câmeras IP. Roda como serviço Windows, **100% offline**, e entrega o resultado ao sistema principal por HTTP. Permite correção manual pela API quando a leitura sai errada.

**A restrição que organiza tudo:** há uma janela de **2 semanas no local, em outubro, com dedicação parcial**. Depois dela, o acesso é apenas remoto por VPN.

**Por isso a viagem tem um objetivo só:** deixar a instalação física correta e voltar com um bom conjunto de imagens. O sistema funcionando é consequência do trabalho remoto que vem depois.

---

## 2. Como funciona

```
3 câmeras RTSP
      ↓
Gatilho  (chamada do sistema principal, ou movimento)
      ↓
Captura de N frames por câmera
      ↓
Recorte da região do código        ← ROI configurada, não modelo treinado
      ↓
PP-OCR no recorte                  → texto + confiança
      ↓
Validação ISO 6346                 → check digit + correção posicional
      ↓
Maior confiança entre as câmeras   → SQLite → API HTTP → sistema principal
```

**Sete módulos:** `capture` · `roi` · `ocr` · `iso6346` · `api` · `db` · `service`

### Decisões-chave

| Decisão | Motivo |
|---|---|
| **Python 3.12 + ONNX Runtime** | ONNX roda os modelos sem PaddlePaddle nem PaddleX no cliente: instalador ~10× menor, sem conflito de DLL, boot rápido |
| **Treinar com PaddleOCR, rodar com ONNX** | O PaddleOCR 3.x **falha ao iniciar offline** mesmo com cache local (tenta HuggingFace/ModelScope antes). Nunca entra no produto |
| **A porta é a face principal de leitura** | Entrega 50–89 px/caractere contra 34 px de uma lateral; superfície plana, estreita (2,44 m), distância uniforme |
| **Recorte configurado, sem detector treinado** | A câmera é fixa e o caminhão para na linha marcada — a região é previsível. Elimina um modelo |
| **Dicionário de 36 caracteres** (`A–Z`, `0–9`) | Reduz a camada de saída de milhares para 36 classes: modelo menor, mais rápido e mais preciso por construção |
| **FastAPI + SQLite** | Zero administração, ideal para offline single-node; OpenAPI automática para a integração |
| **Detector YOLO: YOLOX ou RT-DETR** | ⚠️ Ultralytics YOLO é **AGPL-3.0** — incompatível com produto comercial fechado |

### A escada de complexidade

Comece no degrau 1. **Suba apenas quando uma medição mostrar que é necessário** — nunca por antecipação. Cada degrau é código mantido para sempre.

| | Adicionar | Sintoma que justifica |
|---|---|---|
| **1** | **Porta + ROI + PP-OCR + ISO 6346** | *(ponto de partida)* |
| 2 | Detector YOLO de região | A ROI fixa erra: caminhão fora de posição, 20' e 40' em alturas diferentes |
| 3 | Câmera lateral de 8 MP | A porta falha: virada, suja, ocluída |
| 4 | Fusão entre câmeras | Duas câmeras leem e discordam |
| 5 | *Beam search* com top-K | O OCR erra por 1 caractere de forma recorrente |

---

## 3. Hardware

### A conta que decide tudo

O critério não é megapixel, é **pixels de altura por caractere**. Caracteres do ISO 6346 têm 100 mm. **Meta: ≥30 px.**

```
px/caractere = 0,10 m ÷ (2 × distância × tan(AFOV_vertical ÷ 2)) × altura_do_sensor_px
```

### Situação das câmeras

**As 3 câmeras do projeto:**

| Posição | Modelo | Papel | Veredito |
|---|---|---|---|
| Lateral esquerda | **VIP 5180 PAN FT** ✅ comprada | Contexto, evidência, gatilho | ❌ **Não lê** — 20 px a 6 m |
| Lateral direita | **VIP 5180 PAN FT** ✅ comprada | Contexto, evidência, gatilho | ❌ **Não lê** — 20 px a 6 m |
| **Fundo (portas)** | ⭐ **VIP 5440 IA — lente 3,6 mm** *(recomendada)* | ⭐ **Leitura primária** | ✅ Serve de **2,5 a 6 m** |

**Possível 4ª câmera — decidir após a pergunta 2 do §8:**

| Posição | Especificação | Quando é necessária |
|---|---|---|
| Uma lateral, com leitura real | 8 MP + 2,8 mm a ~6 m → 34 px | Se as portas **não** ficarem sempre voltadas para trás. Recomendada mesmo no caso favorável: depender de uma única face é frágil |

**VIP 5180 PAN FT** — 4 MP (2880×1620), lente 2,1 mm, **180° H / 78° V** → 20,8 px/grau.
A 6 m entrega 20 px no centro e ~10 px nas bordas. Zoom digital não ajuda (é recorte, não cria pixels). **Permanece no projeto como câmera de contexto e gatilho, funções em que é boa.**

#### ⭐ A câmera do fundo — comparação

| | VIP 3230 SL G3 | **VIP 5440 IA (3,6 mm)** |
|---|---|---|
| Resolução | 2 MP (1920×1080) | **4 MP (2688×1520)** |
| AFOV vertical | 56° | **44°** |
| **Resolução angular** | 19,3 px/grau | **34,5 px/grau** |
| Sensor | Starlight | **Starlight** |
| IR | 30 m | **40 m** |

| Distância | 3230 SL G3 | **5440 IA 3,6 mm** |
|---|---|---|
| 2,5 m | 44 px ✓ | **79 px** ✓✓✓ |
| 3 m | 37 px ✓ | **66 px** ✓✓✓ |
| 3,5 m | 32 px ⚠️ | **57 px** ✓✓ |
| 4 m | 28 px ❌ | **49 px** ✓✓ |
| 5 m | 22 px ❌ | **40 px** ✓✓ |
| 6 m | 18 px ❌ | **33 px** ✓ |
| 7 m | 15 px ❌ | 28 px ⚠️ |

> **Recomendação: VIP 5440 IA, lente 3,6 mm.** A 3230 serve só até 3,5 m; a 5440 cobre de 2,5 a 6 m — **elimina a dependência de acertar a distância**, que é o risco criado pela lente fixa. Como a distância disponível ainda é desconhecida (pergunta 1 do §8), essa margem é o que evita comprar errado.

**Ganhos adicionais:** 4 MP permite **recorte digital** se o enquadramento sair torto (2 MP não deixa margem) · **IA embarcada com detecção de veículo** pode servir de gatilho por hardware, dispensando a heurística de movimento no nosso código · IR de 40 m com o mesmo Starlight.

⚠️ **Na compra, exigir a versão de lente 3,6 mm.** A VIP 5440 IA também sai com 2,8 mm, que entrega só 25,8 px/grau (25 px a 6 m) — a diferença **não aparece no nome do modelo**. Enquadramento: 88° horizontais cobrem 7,7 m a 4 m; a porta tem 2,44 m, com folga confortável.

### Levar na mala

PC preparado · switch PoE + reserva · cabos montados · RJ45, alicate, testador · **HD externo 2 TB** · pendrive com instalador · **trena a laser** · **alvo de calibração impresso, 2 cópias** · notebook · nobreak

---

## 4. Os quatro blocos

```
A ──────► B ──────► D
          │         ▲
          └──► C ───┘
```

**A trava tudo.** Sem câmera correta não há coleta; sem coleta não há modelo; sem modelo não há sistema.
**C anda em paralelo com B** — a aplicação é construída contra o modelo v0 e só troca os `.onnx` depois.

### 🅰 Hardware e Instalação · *15%*
*Entregável: 3 câmeras instaladas com ≥30 px/caractere comprovado*

- [ ] **A1** Resolver o arranjo de câmeras com o cliente
- [ ] **A2** Comprar câmeras, switch PoE, acessórios
- [ ] **A3** Preparar o PC (instalado, testado, software embarcado)
- [ ] **A4** Confirmar autorizações e infraestrutura **por escrito**
- [ ] **A5** Teste de bancada: RTSP, substream, alvo impresso aferido
- [ ] **A6** Configurar (IP fixo, senha, hora), etiquetar (`ESQ`/`DIR`/`PORTAS`) e **enviar**
- [ ] **A7** Instalação: **medir → conferir → furar**, nunca o contrário

### 🅱 Dados e Modelo · *40% — o maior e mais incerto*
*Entregável: modelos ONNX com acurácia medida no conjunto local*

- [x] **B1** Auditar datasets públicos → *ver §7*
- [ ] **B2** Gerar 50–100 mil sintéticos (códigos válidos + degradação)
- [ ] **B2b** Preparar o TRUDI: filtrar famílias, converter MMOCR → TSV (§7.1) — *depende da decisão de licença*
- [ ] **B3** Dicionário de 36 caracteres + config de `configs/rec/`
- [ ] **B4** Treinar modelo **v0** (sintéticos + TRUDI) → exportar ONNX
- [ ] **B5** `siamac-recorder` — gravador autônomo
- [ ] **B6** **Coleta em campo** (~5.000 imagens, automática)
- [ ] **B7** Anotação incremental + fine-tune + avaliação

### 🅲 Aplicação · *30%*
*Entregável: serviço Windows funcional*

- [ ] **C1** Esqueleto: config validada, logging, SQLite, Alembic
- [ ] **C2** Núcleo ISO 6346 — check digit + correção posicional, 100% de cobertura
- [ ] **C3** Captura RTSP com reconexão (contra MediaMTX)
- [ ] **C4** Pipeline: recorte → OCR → validação
- [ ] **C5** API HTTP + correção manual + webhook
- [ ] **C6** Empacotamento PyInstaller + WinSW

### 🅳 Entrega e Operação · *15%*
*Entregável: sistema em produção com KPI medido*

- [ ] **D1** Instalador Inno Setup + **teste da rede desligada**
- [ ] **D2** Deploy do modelo treinado via VPN
- [ ] **D3** Calibrar limiares **por medição**
- [ ] **D4** Piloto em paralelo com a digitação manual
- [ ] **D5** Medir KPIs e liberar o modo automático

---

## 5. Cronograma

| Quando | Foco |
|---|---|
| **Semana 1** (31/ago) | Resolver câmeras · comprar · perguntas ao responsável · baixar tudo · esqueleto |
| **Semanas 2–3** | **Kit de campo:** `recorder`, `aim`, `daily_report` · ISO 6346 · captura RTSP |
| **Semana 4** | Sintéticos + TRUDI · modelo v0 · **teste de bancada** · **enviar câmeras** |
| **Semana 5** | Pipeline · API · serviço Windows · instalador |
| **Outubro** | Instalação (2 dias) + coleta automática (~15 min/dia) |
| **Novembro** | Anotar · treinar · avaliar |
| **Dezembro** | Deploy remoto · piloto assistido |

### O kit de campo — as 3 ferramentas que decidem a viagem

| | O quê | Sem ela |
|---|---|---|
| **`siamac-recorder`** | Grava sozinho por 13 dias: snapshots por evento (5 frames × 3 câmeras) + timelapse de 30 s como rede de segurança. ~105–150 GB no período | Você volta sem dataset |
| **`siamac-aim`** | Mede px/caractere, nitidez e exposição ao vivo. Tem calculadora reversa: *"monte a câmera entre X e Y metros"*. **Roda antes de furar** | O enquadramento é chute e o erro só aparece na volta |
| **`daily_report`** | 5 minutos por noite pela VPN: câmeras vivas, contagem de eventos, disco, miniaturas | Uma câmera cai no dia 3 e você descobre no dia 14 |

### O roteiro da viagem

**Dias 1–2 — instalação** *(os únicos dias de dedicação integral)*
Levantamento → marcar a linha de parada → **aferir com o alvo impresso e o `aim`** → só então furar e montar → subir o `recorder` → **testar a VPN de dentro do local**

**Dia 3 — GATE (2 horas)**
Revisar as primeiras imagens · rodar o v0 · decidir se o enquadramento serve. **Sobram 11 dias para corrigir. Descobrir na volta é perder a viagem.**

**Dias 4–14 — coleta autônoma** *(~15 min/dia)*
Verificação diária pelo relatório · coleta deliberada dos casos difíceis: sol contra, chuva, contêiner repintado, duplo 20' e sobretudo a **transição dia↔noite** (a câmera troca o filtro IR-cut; é o pior caso e quase não aparece em amostragem aleatória)

**Último dia** — conferir integridade dos dados no HD · fotografar a instalação · deixar o `recorder` rodando

---

## 6. Estratégia de dados

**Coletar ≠ anotar.** A coleta é automática e gratuita; a anotação é que custa. Colete tudo, anote com critério.

### Coletar ~5.000, anotar de forma incremental

**Colete as ~5.000** (o `recorder` faz sozinho, custa zero) — o excedente é o que permite *escolher* as melhores, em vez de aceitar as que sobraram.

**Anote em rodadas:**

```
Anote 2.000 → treine → meça → só anote mais se o número exigir
```

Se precisar de mais, **anote 500 direcionadas aos casos onde o modelo errou** — valem mais que 2.000 aleatórias.

### Critérios

**Diversidade acima de volume.** Na primeira rodada: 2.000 imagens de **~670 contêineres distintos** (3 câmeras por evento). Se o conjunto crescer para 5.000, ~1.700 contêineres. O que não pode acontecer é 2.000 imagens de 200 contêineres.

Varie proprietário, cor, estado de conservação e tipo.

**Estratificar por luz, não por horário:**

| Condição | % | Observação |
|---|---|---|
| Dia, céu claro | 25% | O caso fácil |
| Dia, nublado | 15% | |
| **Sol direto / contraluz** | 15% | Sobre-representado de propósito |
| **Noite com IR** | 25% | 25% da operação, se 24 h |
| Chuva | 10% | |
| **Casos especiais** | 10% | Repintado, sujo, duplo 20', oclusão |

Os casos difíceis estão **deliberadamente sobre-representados** em relação à frequência real: se apenas 5% dos casos são noturnos com chuva e você anotar 5%, o modelo vê exemplos demais de menos para aprender.

### Custo da anotação

| Modo | 2.000 (1ª rodada) | 5.000 (completo) |
|---|---|---|
| Caixa + transcrição manual | ~8 h | ~21 h |
| **Com o log do sistema principal** | **~2,5 h** | **~6 h** |

⭐ Se o sistema principal registra a entrada digitada pelo porteiro, esse log casado por timestamp entrega a transcrição pronta. **Vale 15 horas de trabalho manual** — e nesse cenário anotar as 5.000 fica tão barato que a estratégia incremental perde importância.

### Pipeline de treino

**Reconhecedor, em três camadas:**

1. **Sintéticos** — 50–100 mil, grátis, transcrição perfeita por construção
2. **TRUDI** — ~3.100 recortes reais com transcrição (§7.1), *sujeito à decisão de licença*
3. **Nossos dados** — fine-tune final com os recortes da portaria, depois realimentado pelas correções manuais da API

As duas primeiras camadas produzem o **modelo v0** que viaja com você. A terceira é a que leva o sistema a 90–97%.

---

## 7. Recursos externos

| Recurso | Situação |
|---|---|
| **PaddleOCR** (repo local, 3.7.x) | ✅ Essencial. Usar `ppocr/` + `tools/` + `configs/` para treinar. A API 3.x não entra no produto |
| **`paddleocr-js`** | ⭐ Roda PP-OCRv5 em ONNX Runtime puro. **Ler antes de escrever nosso wrapper** — traz o pré/pós-processamento já isolado, que é onde a conversão para ONNX costuma falhar em silêncio |
| **Pesos PP-OCR** (`det`, `rec`, `cls`) | 🔴 **Não vêm no repositório.** Baixar na semana 1 — sem eles não há ponto de partida para o treino |
| Dataset Kaggle/Roboflow (`archive`) | 🟡 Uso marginal: o detector saiu da arquitetura. Serve para medir o baseline do PP-OCR (~1 dia) |
| **TRUDI — `text_recognition`** (BMVC 2025) | ✅ **Auditado, e é bom.** Recortes **com transcrição**, formato MMOCR. Ver §7.1 · ⚠️ **CC BY-SA 4.0 — ShareAlike**: resolver com a empresa **antes de treinar** |
| Fontes OFL para sintéticos | 4–6 fontes condensadas e stencil |
| MediaMTX + vídeos de contêiner | ⭐ Serve RTSP falso — **é o que permite desenvolver sem as câmeras** nas semanas 2–3 |
| VC++ Redistributable | Embarcar no instalador; falta num Windows novo e derruba o serviço |

**Regra:** nada baixa em runtime. Todo modelo, fonte e binário vai embarcado, com caminho absoluto vindo do `config.yaml`.

### 7.1 TRUDI `text_recognition` — auditado

Recortes de palavra **com transcrição**, formato MMOCR `TextRecogDataset`. Baixar **só esta pasta** (47 MB) — as outras (`coco`, `labelme`, `yolo`, `text_detection`, 11 GB) são as mesmas imagens em outros formatos.

```json
{"instances": [{"text": "OOLU0208218"}], "img_path": "textrecog_imgs//0276_0.jpg"}
```

**O que serve** — dos 4.365 recortes de `both`:

| Família | Qtd | |
|---|---|---|
| **Código ISO 6346** (`[A-Z]{4}\d{7}`) | **2.080** | ✅ o alvo |
| **Size/type code** (`\d{2}[A-Z]\d`) | **1.026** | ✅ também no escopo |
| Placa alemã (`HRO-M8006`) | 549 | ❌ filtrar |
| Truncados e ruído (`45G`, `H`, `3`) | 680 | ❌ filtrar |

**~3.100 amostras reais com transcrição** — cobre código e size/type.

**Decisões antes de treinar:**

1. **Ignorar `both`** — é cópia byte-a-byte de `aerial`+`ground` (~4,3 mil JPEGs redundantes)
2. **Filtrar por família** — manter só ISO 6346 e size/type; descarta 29%
3. **Dicionário sem hífen** (o hífen só existe por causa das placas) — mas **incluir o `J`**, que não aparece no dataset e é categoria válida do ISO 6346
4. **Filtrar imagens < 16 px de altura** — há recortes de 6×6 px
5. **Resize para altura 32** — a mediana do dataset é 35–46 px, bate com o padrão do PP-OCR sem upscale
6. **Treinar com `aerial`+`ground`, validar em `ground`** — o aerial é drone (AR ~5); o ground (AR ~2,2) parece com a portaria
7. **Converter MMOCR → PaddleOCR** (JSON → TSV `caminho⇥texto`), script de ~15 linhas

⚠️ **Há recortes com AR < 1 — texto vertical**, o código empilhado na porta. Confirma que o pré-processamento não pode assumir texto horizontal.

**Impacto na estimativa do v0:** de 60–80% para **75–85%**. O destino não muda; a linha de partida sim — e um v0 melhor torna o gate do dia 3 mais conclusivo.

---

## 7.2 Dimensionamento

### O produto entregue

| | |
|---|---|
| **Instalador** (Inno Setup, LZMA2) | **~120 MB** |
| Instalado em disco | ~250 MB |
| Composição | OpenCV 50 · modelos ONNX 55 · NumPy 25 · Python 20 · FastAPI e resto 35 · VC++ 25 |

Com GPU: DirectML soma ~40 MB; **CUDA somaria ~1 GB** (DLLs do provider precisam ir junto num sistema offline). **Se precisar de GPU, DirectML.**

### Crescimento em operação — ~100 caminhões/dia

| | Por dia | Por mês |
|---|---|---|
| Banco SQLite | ~200 KB | ~6 MB |
| **Imagens de evidência** | ~350 MB | **~10,5 GB** |

**Com retenção de 30 dias, estabiliza em ~11 GB.** Sem retenção: ~128 GB/ano até o disco encher e o serviço parar — por isso a política de retenção é obrigatória desde o dia 1, não refinamento posterior.

### Espaço necessário

| Onde | Quanto |
|---|---|
| PC do cliente | ~11 GB estáveis (SSD de 512 GB é folgado) |
| PC do local, durante a coleta | ~105–150 GB |
| **Sua máquina de desenvolvimento** | **reservar ~200 GB** — dados da viagem, sintéticos, checkpoints de treino |

## 7.3 Esforço estimado

⚠️ *Estimativas para calibrar expectativa, não compromisso.*

| Bloco | % | Horas |
|---|---|---|
| A — Hardware e Instalação | 15% | 55–70 h |
| **B — Dados e Modelo** | **40%** | **140–180 h** |
| C — Aplicação | 30% | 105–135 h |
| D — Entrega e Operação | 15% | 55–70 h |
| **Total** | | **~355–455 h** |

Distribuídas em ~14 semanas de calendário (set/2026 → dez/2026), com dedicação parcial.

### Hardware a adquirir (fora as 2 VIP 5180 PAN já compradas)

| Item | Estimativa |
|---|---|
| Câmera do fundo — **VIP 5440 IA, lente 3,6 mm** | R$ 1.500 – 2.500 |
| Lateral de leitura 8 MP *(se necessária)* | R$ 1.500 – 2.500 |
| PC | R$ 4.000 – 8.000 |
| Switch PoE, cabos, acessórios | R$ 1.000 – 2.000 |
| HD externo 2 TB, nobreak | R$ 1.000 – 1.500 |
| **Total** | **R$ 8.300 – 15.500** |

*Valores de referência para agosto/2026 — cotar antes de fechar.*

---

## 8. Pendências que travam o projeto

**Perguntar ao responsável — hoje ou amanhã:**

1. **Distância disponível para a câmera do fundo** → a VIP 5440 IA (3,6 mm) cobre 2,5–6 m; confirmar que a distância cai nessa faixa
2. **As portas ficam sempre voltadas para trás?** → decide se a lateral de leitura é obrigatória
3. **Existe link de internet no local?** → ⚠️ *"offline" é o software; a VPN precisa de link.* Sem ele, o comissionamento exige segunda viagem
4. **O sistema principal exporta o log de entradas digitadas?** → decide se a anotação custa 6 h ou 21 h

**Decidir internamente na empresa:**

5. **Licença CC BY-SA 4.0 do TRUDI** → o ShareAlike é compatível com o produto comercial fechado? **Vale ~3.100 amostras reais** (§7.1). Se vetado, o v0 depende só dos sintéticos e cai de ~80% para ~60–70%
6. **Licença do detector** — Ultralytics é AGPL-3.0; usar YOLOX ou RT-DETR. Só relevante se subir ao degrau 2

**Também na semana 1:** distância em cabo até o PC (⚠️ **PoE tem limite de 100 m**) · energia e aterramento · autorização para furar · escada ou plataforma · EPI e integração de segurança · endereço de entrega das câmeras

---

## 9. Riscos

| Risco | Mitigação |
|---|---|
| 🔴 **A câmera não lê** — confirmado na 5180 PAN | Volume de dados não corrige óptica. Depende de o cliente aprovar a câmera de leitura |
| 🔴 **Voltar com dado inutilizável** | `aim` antes de furar · `daily_report` toda noite · **gate do dia 3** · timelapse redundante |
| 🟠 **Erro silencioso** — pior que não ler | O check digit é `mod 11`: **~1 em 11 códigos errados passa por acaso**. Na dúvida, `NEEDS_REVIEW`. **KPI crítico: erro aceito sem aviso ≤ 0,5%** |
| 🟠 **Licenças** | Ultralytics = AGPL · TRUDI = ShareAlike · Roboflow = verificar procedência. **Resolver antes de treinar** — corrigir depois significa retreinar do zero |
| 🟠 **Bloqueio no dia 1** | Autorização, escada, tomada, EPI. Confirmar por escrito antes de viajar |
| 🟡 **Cache não visível ao serviço** | Serviço Windows roda como `LocalSystem`, não vê `C:\Users\victo\.paddlex\`. Resolvido por ONNX com caminho absoluto |

### Expectativa realista

Sistemas comerciais consolidados atingem 95–99% em portaria com veículo parado. Um sistema próprio bem feito chega a **90–97%**. Prometer 99,9% é irrealista.

**Metas a acordar:** auto-aceite correto ≥92% · **erro silencioso ≤0,5%** · resposta ≤3 s · disponibilidade ≥99%

---

## 10. Verificação

**Testes automatizados** — `pytest` no ISO 6346 (vetores conhecidos e o caso `check digit 10 → 0`) · API com `httpx` (fluxo completo: evento → processa → corrige → webhook) · outbox com destino derrubado

**End-to-end sem hardware** — MediaMTX servindo 3 vídeos como RTSP local; dispara evento, verifica resultado e webhook. Roda em CI, sem câmera

**Antes de embarcar (inegociável)** — `recorder` gravando 24 h com corte de energia e de rede no meio · `aim` aferido contra medida real conhecida · `daily_report` acessado de fora da rede · os `.exe` em **Windows limpo, sem Python**

**⭐ Teste da rede desligada** — instalar em Windows limpo **com a placa de rede desabilitada**, reiniciar, processar um evento ponta a ponta. Confirmar com `netstat -b` que nada tenta sair. ⚠️ Verificar com `pyi-archive_viewer` que **`paddle` e `paddleocr` não entraram no executável** — ler o código não basta, um import indireto entra sem aviso

**Em produção** — soak de 72 h · piloto em paralelo com a digitação manual (mede a acurácia real sem risco) · reboot confirmando que o serviço sobe sozinho

---

## Anexo — Alternativas avaliadas e descartadas

Registradas para não serem reabertas sem contexto.

| Alternativa | Por que não |
|---|---|
| **Câmera com OCR embarcado** (VIDAR, Vaxtor) | Reduziria o prazo para ~8 semanas, mas **open source é exigência da empresa**. Nota: Intelbras/Hikvision/Dahua só fazem ANPR (placas), nunca ISO 6346 |
| **YOLO lendo caracteres direto** (36 classes) | Anotação de **110 h** contra 21 h — o PP-OCR já vem pré-treinado. E YOLO também redimensiona: 34 px viram 6 px na imagem completa |
| **OCR na imagem inteira, sem recorte** | Todo modelo redimensiona a entrada. `3840×2160 → 960×540` transforma 34 px em 8 px. Além disso a lateral tem `MAX GROSS`, `TARE`, logos — dezenas de strings sem indicar qual é o código |
| **PaddleOCR em runtime no cliente** | Falha ao iniciar offline mesmo com cache; arrasta PaddleX inteiro. E o nosso modelo é treinado — não vem de cache nenhum |
| **Vídeo contínuo 24/7 na coleta** | 227–453 GB para cobrir um risco pequeno. Substituído por timelapse de 30 s (~6 GB) |
| **Refazer o split do dataset público** | O vazamento envenena a métrica *daquele* dataset — e a nossa régua é o conjunto de validação 100% local |

---

## Resumo

**Trocar complexidade de software por volume de dados:** coletar ~5.000 imagens reais e manter o sistema em sete módulos simples.

**A viagem entrega instalação correta e dataset — não sistema funcionando.** Isso vem depois, pela VPN.

**Três ferramentas precisam estar prontas até outubro:** `recorder`, `aim`, `daily_report`.

**Duas perguntas destravam a semana 1:** distância da câmera das portas, e orientação das portas.

**A regra de ouro no local:** *medir com o alvo → conferir com o `aim` → só então furar.*
