# SiamacContainer — Leitura Automática de Código de Contêiner

Planejamento escrito do zero a partir dos requisitos declarados, sem reaproveitar análise anterior. A versão anterior deste documento permanece recuperável no histórico do git (até o commit `5e9f603`).

---

## 1. Contexto

Hoje o código ISO 6346 dos contêineres que entram e saem é digitado manualmente na portaria. Digitação manual é lenta, gera erro de transcrição e não deixa evidência visual do que entrou.

O objetivo é ler esse código automaticamente com câmeras já em posse, entregar o resultado ao sistema principal por API, e — quando a leitura não for confiável — deixar que um humano corrija sem travar a operação.

**Resultado esperado:** ≥90% dos eventos lidos e aceitos automaticamente, com taxa de **erro silencioso** (código errado aceito sem aviso) abaixo de 0,5%. O resto vai para fila de revisão humana.

### Restrições dadas

| | |
|---|---|
| Câmeras laterais | 2× **Intelbras VIP 5180 PAN FT** (já adquiridas) |
| Câmera traseira | 1× Intelbras **4K**, modelo a definir |
| Veículo | **Para completamente** na portaria |
| Plataforma | **Windows, como serviço** — sem janela gráfica aberta |
| Configuração | Precisa de interface, mas não pode ser app de desktop aberto |
| Correção humana | Acontece **no outro sistema, via nossa API** |
| Licenciamento | **Uso interno, um cliente só** — sem distribuição a terceiros |
| Base técnica | PaddleOCR + dataset TRUDI |
| Dataset próprio | ~3.000 imagens, coletadas uma vez, embarcadas no produto |

---

## 2. Decisões de arquitetura

| Decisão | Por quê |
|---|---|
| **Treinar com PaddleOCR, executar com ONNX Runtime** | PaddlePaddle/PaddleX em produção arrasta ~1 GB de dependências, conflita com DLLs no Windows e tenta baixar modelos na inicialização. ONNX Runtime roda o mesmo modelo com ~50 MB e sem rede. |
| **Usar RapidOCR (Apache-2.0) como camada de inferência** | Ele já é exatamente isso: modelos PaddleOCR em ONNX Runtime, com pré/pós-processamento (DBNet unclip, CTC decode, angle cls) implementado e testado. Aceita `det_model_path`, `rec_model_path`, `rec_keys_path` locais. **Economiza a parte onde a conversão para ONNX falha em silêncio.** |
| **Fusão das 3 câmeras por votação de caractere** | O mesmo código de 11 caracteres está impresso nos 3 lados. Três leituras independentes + check digit ISO 6346 como árbitro elevam a acurácia muito acima de qualquer câmera isolada. Esta é a alavanca principal do projeto. |
| **Captura híbrida: substream RTSP + snapshot em resolução plena** | Ver §3. |
| **ROI configurada, sem detector treinado no degrau 1** | Câmera fixa + veículo parado em posição marcada = região previsível. Elimina um modelo inteiro. Detector entra só se a medição mostrar necessidade. |
| **Dicionário de 36 caracteres (`A–Z`, `0–9`)** | Camada de saída cai de ~6.600 classes (dicionário chinês do PP-OCR) para 36. Modelo menor, mais rápido, e impossibilita por construção a saída de caracteres inválidos. |
| **FastAPI + SQLite + Jinja2/HTMX** | Serviço único que atende a API de integração *e* serve as páginas de configuração. Zero administração, zero build de frontend, arquivo único de banco. |
| **Nada baixa em tempo de execução** | Todo modelo, fonte e binário vai embarcado com caminho absoluto vindo do `config.yaml`. Requisito de serviço Windows rodando como `LocalSystem`. |

### Licenças — resolvidas pela resposta "uso interno, um cliente só"

- **TRUDI (CC BY-SA 4.0): liberado.** As obrigações da CC BY-SA disparam ao *compartilhar* material adaptado. Sem distribuição a terceiros, não disparam. Registrar a atribuição no `NOTICE.md` do repositório de qualquer forma. → **~3.100 recortes reais rotulados entram no treino.**
- **Ultralytics YOLO (AGPL-3.0): evitável, então evite.** Sem distribuição, o gatilho principal da AGPL não dispara, mas a cláusula §13 (interação remota por rede) é área cinzenta que não vale defender. **YOLOX é Apache-2.0** e resolve o mesmo problema — use YOLOX se o degrau 2 for acionado.
- **PaddleOCR: Apache-2.0.** Sem restrição. **RapidOCR: Apache-2.0.** Sem restrição.

### A escada de complexidade

Comece no degrau 1. Suba apenas quando uma **medição** mostrar necessidade — nunca por antecipação.

| | Adicionar | Sintoma que justifica |
|---|---|---|
| **1** | ROI fixa + PP-OCR + ISO 6346 + fusão 3 câmeras | *(ponto de partida)* |
| 2 | Detector YOLOX da região do código | ROI fixa erra: caminhão fora de posição, 20' e 40' em alturas diferentes |
| 3 | Beam search com top-K por posição | Erros recorrentes de exatamente 1 caractere |
| 4 | Super-resolução no recorte antes do OCR | px/caractere ficou entre 20 e 28 e não dá para reposicionar a câmera |

---

## 3. Conectividade das câmeras — RTSP é parte da resposta, não toda ela

**Pergunta feita: "RTSP ou tem forma melhor?"** — A melhor forma é usar **três canais diferentes da mesma câmera, cada um para o que faz bem**. Câmeras Intelbras VIP são baseadas em Dahua e expõem os três.

| Canal | Uso | Custo |
|---|---|---|
| **RTSP substream** (`.../cam/realmonitor?channel=1&subtype=1`, ~704×576) | Ficar sempre ligado. Detecção de presença/movimento e "o caminhão parou". | ~1% de CPU por câmera |
| **HTTP CGI snapshot** (`/cgi-bin/snapshot.cgi?channel=0`) | **Os frames que vão para o OCR.** JPEG em resolução plena direto do ISP da câmera. | Sob demanda |
| **ONVIF** (`onvif-zeep-async`) | Descoberta, URI de snapshot e de stream, sincronismo de hora, e **eventos de IVS/motion por PullPoint** — a própria câmera pode ser o gatilho. | Desprezível |

**Por que snapshot em vez de frame do RTSP main:** o frame extraído do H.264/H.265 carrega artefato de compressão inter-quadro exatamente na borda de caractere, que é o que o OCR precisa. O snapshot é um JPEG intra-quadro gerado pelo ISP. Além disso, decodificar 3 streams 4K continuamente custa CPU real; o substream custa quase nada.

⚠️ **Limitações a validar em bancada, semana 1:**
1. O `snapshot.cgi` de linha Dahua costuma ser limitado a ~1 fps e **pode travar a câmera se chamado em laço apertado**. Com veículo parado isso basta: 3–5 snapshots em 4 s. Testar antes de fechar o desenho.
2. A resolução do snapshot segue a configuração de *foto* da câmera, não a do stream — **conferir que está em 8 MP**, não no padrão baixo.
3. Se o snapshot não entregar resolução plena, o plano B é decodificar o RTSP **main** só durante a janela do evento (~4 s), com `ffmpeg`/PyAV, e desligar entre eventos.

**Ordem de gatilho, do melhor para o pior:**
1. **Chamada do sistema principal** (`POST /v1/events`) — ele já sabe que um caminhão chegou. Preferível: zero falso positivo.
2. Evento ONVIF de IVS da câmera (line crossing / intrusion).
3. Detecção de movimento própria sobre o substream (diferença de frames + estabilização).

O sistema deve suportar os três, configuráveis. Implementar 1 e 3; 2 se o modelo da câmera expuser.

---

## 4. Óptica — a conta que decide se o projeto funciona

O critério não é megapixel, é **altura em pixels por caractere**. Caracteres ISO 6346 têm 100 mm. **Meta: ≥30 px. Abaixo de 20 px nenhum OCR lê de forma confiável.**

### 4.1 Câmeras laterais — VIP 5180 PAN FT

Especificação: sensor 1/2.7" 4 MP, **2880×1620**, lente fixa **2,1 mm**, **180° H × 78° V**.

Como é uma panorâmica com projeção cilíndrica (não retilínea), a conta correta é angular, não por tangente:

```
px/caractere = (1620 px ÷ 78°) × (5,73° ÷ d)  ≈  119 ÷ d      [d em metros]
```

| Distância até o código | px/caractere | |
|---|---|---|
| 2,0 m | 60 | ✓✓ folgado |
| 2,5 m | 48 | ✓✓ |
| 3,0 m | 40 | ✓✓ |
| 3,5 m | 34 | ✓ |
| **4,0 m** | **30** | ✓ **limite** |
| 5,0 m | 24 | ⚠️ degrada |
| 6,0 m | 20 | ❌ não lê |

**⚠️ A distância que conta não é a lateral, é a diagonal.** Com a câmera a `L` metros da lateral do contêiner e o código a `x` metros de deslocamento longitudinal em relação ao eixo da câmera:

```
d = √(L² + x²)
```

Um contêiner de 40' tem 12,19 m. Com a câmera a 3 m da lateral, mirando o meio: código no centro → 40 px; código a 6 m do centro → `d = 6,7 m` → **18 px, ilegível**.

**Consequência de projeto, e é a mais importante do documento:**

> As VIP 5180 PAN **leem**, mas só se forem montadas **a ≤3,5 m da lateral do contêiner E longitudinalmente alinhadas com onde o código realmente está** — não com o meio do contêiner. Alinhar com o meio desperdiça a câmera.

O FOV de 180° é vantagem aqui: mesmo montada bem perto, ela enxerga o caminhão inteiro, então o alinhamento é sobre *resolução*, não sobre *enquadramento*. Precisa-se saber onde o código fica na lateral — normalmente na parte superior, próximo à extremidade das portas. **Item A1 do plano: fotografar 10 contêineres típicos do cliente e medir a posição do código.**

### 4.2 Câmera traseira — 4K, a definir

Projeção retilínea, conta padrão:

```
px/caractere = 0,10 m ÷ (2 × d × tan(AFOV_v ÷ 2)) × 2160 px
```

| Distância | 2,8 mm (AFOV_v ≈ 58°) | **3,6 mm (AFOV_v ≈ 47°)** | 6 mm (AFOV_v ≈ 29°) |
|---|---|---|---|
| 3 m | 65 ✓✓ | **84 ✓✓** | 139 ✓✓ |
| 5 m | 39 ✓✓ | **50 ✓✓** | 84 ✓✓ |
| 7 m | 28 ⚠️ | **36 ✓✓** | 60 ✓✓ |
| 9 m | 22 ❌ | **28 ⚠️** | 46 ✓✓ |
| 12 m | 16 ❌ | 21 ❌ | 35 ✓ |

**Recomendação de compra, em ordem:**

1. ⭐ **4K com zoom motorizado / varifocal** (linha Intelbras VIP 9860 IA FT ou equivalente 8 MP com lente motorizada). **Elimina o risco da distância por completo** — ajusta-se no local, sem refazer furação. Vale a diferença de preço, porque o erro de enquadramento é o modo de falha mais caro do projeto.
2. **4K fixa 3,6 mm** (linha VIP 3830 B IA: 8 MP, 3,6 mm, Starlight, IR 30 m, PoE). Cobre 3–8 m confortavelmente. Escolha correta **se a distância já estiver medida e travada**.
3. ❌ **Evitar 4K com lente 2,1 mm ou fisheye/panorâmica.** Recai no mesmo problema da 5180 PAN.

**⚠️ A armadilha noturna, contraintuitiva:** 8 MP num sensor 1/2.8" tem pixels *menores* que 4 MP no mesmo sensor — capta menos luz e gera mais ruído. Se a portaria opera 24 h, ~25% dos eventos serão com IR. Antes de comprar, verificar:

- **Tamanho do sensor** — 1/1.8" é muito superior a 1/2.8" em 4K
- **Starlight** presente e **iluminação mínima ≤0,005 lux**
- **Alcance do IR** ≥30 m
- **Taxa de quadros em 8 MP** — algumas caem para 15 fps (irrelevante com veículo parado, mas indica limitação do ISP)

> Uma 4 MP Starlight num sensor grande pode ler melhor à noite que uma 4K comum. **A pergunta muda de "tem resolução?" para "enxerga no escuro?".**

### 4.3 Ferramenta obrigatória: `siamac-aim`

Utilitário de linha de comando que, apontado para uma câmera, mede **ao vivo**: px/caractere sobre um alvo impresso de dimensão conhecida, nitidez (variância do Laplaciano) e histograma de exposição. Tem calculadora reversa: *"para 30 px/caractere com esta lente, monte entre X e Y metros."*

**Roda antes de furar a parede.** Sem ela, o enquadramento é chute e o erro só aparece semanas depois, quando o modelo não converge.

---

## 5. Arquitetura de software

```
siamac-container/
├─ pyproject.toml                 # uv / hatchling
├─ config.example.yaml
├─ NOTICE.md                      # atribuições: TRUDI, PaddleOCR, RapidOCR
├─ src/siamac/
│  ├─ config.py                   # pydantic-settings, valida no boot e falha alto
│  ├─ cameras/
│  │  ├─ onvif_client.py          # descoberta, URIs, hora, eventos PullPoint
│  │  ├─ substream.py             # RTSP substream em loop, com reconexão
│  │  └─ snapshot.py              # HTTP CGI + fallback RTSP main
│  ├─ trigger/
│  │  ├─ api_trigger.py           # POST /v1/events
│  │  └─ motion.py                # diferença de frames sobre o substream
│  ├─ capture.py                  # rajada 3–5 frames × 3 câmeras + score de nitidez
│  ├─ roi.py                      # recorte por ROI configurada (+ YOLOX no degrau 2)
│  ├─ ocr/
│  │  ├─ engine.py                # wrapper fino sobre RapidOCR, modelos locais
│  │  └─ preprocess.py            # deskew, CLAHE, upscale, texto vertical
│  ├─ iso6346.py                  # check digit mod-11, size/type, correção posicional
│  ├─ fusion.py                   # ⭐ votação por caractere entre as 3 câmeras
│  ├─ storage/
│  │  ├─ models.py                # SQLAlchemy: Event, Read, Image, OutboxItem
│  │  ├─ retention.py             # purga por idade — obrigatória desde o dia 1
│  │  └─ migrations/              # Alembic
│  ├─ api/
│  │  ├─ routes_events.py         # integração + correção humana
│  │  ├─ routes_admin.py          # saúde, câmeras, diagnóstico
│  │  └─ outbox.py                # webhook com retry exponencial e DLQ
│  ├─ webui/                      # Jinja2 + HTMX, sem build step
│  │  ├─ cameras.html             # credenciais, teste de conexão, snapshot ao vivo
│  │  ├─ roi.html                 # desenhar ROI sobre snapshot, em canvas
│  │  ├─ thresholds.html          # limiares de confiança e auto-aceite
│  │  └─ diagnostics.html         # últimos eventos, latência, disco
│  └─ service/
│     ├─ supervisor.py            # laço principal, watchdog das câmeras
│     └─ winservice.py            # entrypoint para WinSW
├─ tools/
│  ├─ aim.py                      # §4.3 — medidor de px/caractere
│  ├─ recorder.py                 # coletor de dataset autônomo
│  ├─ synth.py                    # gerador de sintéticos
│  ├─ trudi_convert.py            # MMOCR JSON → TSV do PaddleOCR
│  └─ export_onnx.py              # Paddle → ONNX + verificação de paridade
└─ tests/
```

### 5.1 O módulo que carrega o projeto: `fusion.py`

O mesmo código de 11 caracteres está nos 3 lados do contêiner. Três leituras independentes permitem votação:

```
Câmera ESQ:  M S C U 4 5 6 7 8 2 1   conf: [.99 .98 .97 .91 .99 .88 .95 .99 .97 .93 .99]
Câmera DIR:  M S C U 4 5 6 7 8 2 1   conf: [.97 .99 .95 .96 .98 .94 .89 .98 .99 .90 .98]
Câmera FUN:  M 5 C U 4 5 6 7 8 2 1   conf: [.99 .61 .99 .99 .99 .97 .99 .99 .99 .96 .99]
             ─────────────────────
Votação:     M S C U 4 5 6 7 8 2 1   ← posição 2 resolvida por maioria + confiança
Check digit: ✓ válido
Resultado:   MSCU4567821  · confiança agregada 0,96 · AUTO_ACCEPT
```

Regras, em ordem:
1. Votação ponderada por confiança, caractere a caractere
2. **Check digit ISO 6346 (`mod 11`) sobre o resultado da votação**
3. Se falhar, testar as combinações top-2 por posição (busca limitada) procurando uma que valide
4. Se ainda falhar, ou se as câmeras discordarem acima de um limiar, → `NEEDS_REVIEW`
5. Correção posicional determinística: posições 1–4 são sempre letras, 5–11 sempre dígitos. `O↔0`, `I↔1`, `S↔5`, `B↔8`, `Z↔2`, `G↔6` são resolvidos pela posição antes de qualquer outra coisa

⚠️ **O check digit `mod 11` não é garantia:** aproximadamente **1 em cada 11 códigos errados passa por acaso**. Ele reduz o erro silencioso, não o elimina. Por isso o limiar de auto-aceite considera *também* a concordância entre câmeras — dois erros idênticos em duas câmeras diferentes são muito improváveis.

### 5.2 API — contrato com o sistema principal

**Transporte: HTTP puro, sem TLS.** Decisão consciente, adequada ao cenário (rede interna, um cliente, serviço offline). O que se ganha: nenhum certificado para emitir, instalar, renovar ou depurar — e certificado autoassinado num serviço offline é fonte garantida de aviso de navegador e de expiração silenciosa daqui a um ano. Toda resposta em JSON.

⚠️ **O que HTTP puro implica, e como compensar:**

| Consequência | Compensação obrigatória |
|---|---|
| A API key viaja em texto claro | Tratar como **credencial de rede interna, não como segredo forte**. Rotacionável pela tela de configuração. Nunca reutilizar senha de outro sistema |
| Qualquer host da rede alcança a API | **Bind explícito** ao IP da interface interna (nunca `0.0.0.0`) + **allowlist de IPs de origem** em middleware. Regra de firewall do Windows criada pelo instalador |
| A tela de configuração vai pelo mesmo canal | Servir a UI **apenas em `127.0.0.1`**, numa porta separada da API. Configuração local, integração pela rede — dois binds, dois escopos |
| As imagens de evidência são acessíveis por URL | URLs de imagem com token opaco por evento, não sequenciais. Evita varredura trivial |
| Webhook de saída também é HTTP | Combinar com o time do sistema principal: se eles oferecerem HTTPS no receptor, usar — o cliente HTTP nosso suporta os dois sem mudança de código |

Registrar essa decisão no `NOTICE.md`/README com a justificativa, para que uma auditoria futura encontre a escolha documentada em vez de parecer descuido. **Se o sistema um dia sair da rede interna, TLS deixa de ser opcional** — deixar a configuração de `scheme` preparada no `config.yaml` para não exigir mudança de código.

Autenticação por API key em header (`X-API-Key`).

| Método | Rota | Uso |
|---|---|---|
| `POST` | `/v1/events` | Dispara uma leitura. Aceita `{"gate":"in","external_ref":"..."}`. Retorna `202` + `event_id`, ou `200` com resultado se `sync=true` |
| `GET` | `/v1/events` | Lista com filtros `status`, `from`, `to`, paginado. `status=needs_review` é a **fila de correção humana** |
| `GET` | `/v1/events/{id}` | Detalhe: código, confiança, leitura de cada câmera, URLs das imagens |
| `GET` | `/v1/events/{id}/images/{camera}` | JPEG da evidência (`left`, `right`, `rear`, e `_crop` para o recorte) |
| `PATCH` | `/v1/events/{id}` | **Correção humana.** `{"container_code":"MSCU4567821","iso_type":"45G1","corrected_by":"joao"}`. Valida o check digit e recusa código inválido com `422` |
| `POST` | `/v1/events/{id}/confirm` | Confirma sem alterar (operador validou a leitura automática) |
| `GET` | `/v1/cameras/status` | Estado de cada câmera: viva, último frame, latência |
| `GET` | `/health` | Liveness/readiness |

**Webhook de saída (outbox):** toda transição de estado gera um item numa tabela `outbox` e um worker entrega ao endpoint configurado com retry exponencial. **Não é `POST` direto e otimista** — se o sistema principal cair por 20 minutos, nada se perde. Item vencido vai para DLQ visível no diagnóstico.

⭐ **Toda correção via `PATCH` grava o par (recorte, texto correto) numa tabela `training_samples`.** É rotulagem de graça, vinda da operação, que alimenta o próximo fine-tune. Este é o motor de melhoria contínua do sistema.

### 5.3 Interface de configuração sem GUI aberta

O serviço sobe **dois binds HTTP separados**, e a separação é o que torna o HTTP puro defensável:

| | Bind | Alcance |
|---|---|---|
| **API de integração** | `<IP interno>:8477` | Rede interna, com allowlist de IPs e API key |
| **Tela de configuração** | `127.0.0.1:8478` | **Só a própria máquina.** Nunca exposta na rede |

O operador abre o navegador em `http://127.0.0.1:8478` no PC da portaria. **Nenhuma janela fica aberta; o serviço não depende de sessão de usuário logada.**

Páginas: câmeras (credenciais, teste, snapshot ao vivo) · ROI (desenhar retângulo sobre o snapshot em `<canvas>`) · limiares · webhook e retenção · diagnóstico (últimos eventos com miniatura, latência, disco).

Sem React, sem `npm`. Jinja2 + HTMX servidos pelo mesmo processo — o instalador não precisa de toolchain de frontend.

---

## 6. Modelo e dados

### 6.1 As três camadas de treino

| Camada | Volume | Papel |
|---|---|---|
| **1. Sintéticos** | 50–100 mil | Grátis, rótulo perfeito por construção. Ensina a forma dos 36 caracteres, fontes condensadas/stencil típicas de contêiner, degradação (desfoque, ruído, JPEG, perspectiva, ferrugem, repintura, IR monocromático) |
| **2. TRUDI** | ~3.100 reais | ✅ Liberado (§2). Recortes reais com transcrição. Ensina a textura do mundo real |
| **3. Dados próprios** | **~3.000** | O fine-tune que leva de ~80% para 90–97%. Sai da portaria do cliente |

Camadas 1 e 2 produzem o **modelo v0**, que já viaja instalado com o sistema. Camada 3 é o que fecha a conta.

### 6.2 A meta de ~3.000 imagens — e por que ela é mais barata do que parece

Com **3 câmeras lendo o mesmo código**, cada evento gera **3 recortes rotulados com uma única transcrição**:

```
1.000 eventos  →  3.000 recortes rotulados  →  1 transcrição digitada por evento
```

**Isso é uma redução de 3× no custo de anotação.** Com ~100 caminhões/dia, 10 dias de coleta atingem a meta.

E fica ainda melhor: **se o sistema principal registra o código que o porteiro digitou hoje**, o casamento por timestamp entrega as 1.000 transcrições prontas. A anotação cai de ~13 h para ~2 h de conferência. **Pergunta nº 4 do §9 — é a que mais vale dinheiro.**

⚠️ **Diversidade vem de contêineres distintos, não de fotos.** 3.000 recortes de 1.000 contêineres valem muito mais que 3.000 de 300. Deduplicar por código antes de anotar.

### 6.3 Estratificação — por luz, não por horário

Casos difíceis **deliberadamente sobre-representados**: se apenas 5% dos eventos são noturnos com chuva e você anotar 5%, o modelo vê exemplos de menos para aprender.

| Condição | Alvo |
|---|---|
| Dia, céu claro | 25% |
| Dia, nublado | 15% |
| Sol direto / contraluz | 15% |
| Noite com IR | 25% |
| Chuva | 10% |
| Especiais (repintado, sujo, ocluído, duplo 20') | 10% |

⚠️ **Incluir deliberadamente a transição dia↔noite.** A câmera troca o filtro IR-cut e a imagem muda por completo por alguns segundos. É o pior caso e quase não aparece em amostragem aleatória.

### 6.4 `siamac-recorder` — coletor autônomo

Roda no PC da portaria durante a coleta, sem supervisão: por evento, N snapshots de cada câmera + metadados (hora, condição de luz estimada, resultado do v0). Rotação por espaço em disco. Relatório diário consultável remotamente: câmeras vivas, contagem de eventos, disco livre, miniaturas.

Sem o relatório diário, uma câmera cai no dia 3 e você descobre no dia 14.

### 6.5 Pipeline de treino

```
tools/synth.py        → 50–100k sintéticos            (TextRecognitionDataGenerator ou SynthTIGER)
tools/trudi_convert.py→ TRUDI MMOCR JSON → TSV        (~3.100, filtrado)
PPOCRLabel            → anotação semiautomática dos dados próprios
PaddleOCR configs/rec → treino (PP-OCRv5 rec como pesos iniciais, dicionário de 36 chars)
tools/export_onnx.py  → paddle2onnx + verificação de paridade numérica
                      → src/siamac/models/rec.onnx
```

**Filtros ao preparar o TRUDI** (o dataset mistura famílias):
- Manter apenas `[A-Z]{4}\d{7}` (código ISO) e `\d{2}[A-Z]\d` (size/type); descartar placas alemãs e fragmentos truncados
- Descartar recortes com altura < 16 px
- Dicionário **sem hífen** (o hífen só existe por causa das placas), mas **com `J`** — categoria válida do ISO 6346 que pode não aparecer no dataset
- Redimensionar para altura 32 (padrão PP-OCR, bate com a mediana do dataset sem upscale)

⚠️ **Há recortes com aspect ratio < 1 — texto vertical**, o código empilhado na porta. O pré-processamento **não pode assumir texto horizontal**: detectar AR < 0,8 e rotacionar antes do reconhecedor.

**Verificação de paridade após exportar ONNX (obrigatória):** rodar as mesmas 200 imagens no Paddle e no ONNX e comparar as saídas. Divergência silenciosa na conversão é o bug mais caro deste projeto — o modelo "funciona", só que 4% pior, e ninguém percebe.

---

## 7. Recursos externos pesquisados

| Recurso | Licença | Papel | Link |
|---|---|---|---|
| ⭐ **RapidOCR** | Apache-2.0 | **Camada de inferência ONNX.** Pré/pós-processamento PP-OCR já resolvido. Aceita `det_model_path` / `rec_model_path` / `rec_keys_path` locais → funciona 100% offline | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) |
| **PaddleOCR** | Apache-2.0 | **Só treino.** `configs/rec/` + `tools/train.py`. Não entra no produto | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| **PaddleOCRModelConvert** | Apache-2.0 | Conversão Paddle → ONNX pronta, do time do RapidOCR | [RapidAI/PaddleOCRModelConvert](https://github.com/RapidAI/PaddleOCRModelConvert) |
| ⭐ **TRUDI / TITUS** (BMVC 2025) | CC BY-SA 4.0 | ~3.100 recortes reais com transcrição. Baixar **só** `text_recognition` — as pastas `coco`/`yolo`/`labelme` são as mesmas imagens em outros formatos (GBs desperdiçados) | [egulsoylu/trudi](https://github.com/egulsoylu/trudi) |
| **PPOCRLabel v3** | Apache-2.0 | Anotação semiautomática: pré-rotula com o próprio modelo, humano corrige. Exporta direto no formato de treino do PP-OCR | [PFCCLab/PPOCRLabel](https://github.com/PFCCLab/PPOCRLabel) |
| **MediaMTX** | MIT | ⭐ Serve vídeo local como RTSP falso. **É o que permite desenvolver e rodar CI sem as câmeras** | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) |
| **python-onvif-zeep-async** | MIT | ONVIF: descoberta, snapshot URI, hora, eventos PullPoint | [openvideolibs/python-onvif-zeep-async](https://github.com/openvideolibs/python-onvif-zeep-async) |
| **SynthTIGER** | MIT | Gerador de sintéticos de qualidade superior ao TRDG (degradação mais realista) | [clovaai/synthtiger](https://github.com/clovaai/synthtiger) |
| **TextRecognitionDataGenerator** | MIT | Alternativa mais simples ao SynthTIGER; suficiente para 36 classes | [Belval/TextRecognitionDataGenerator](https://github.com/Belval/TextRecognitionDataGenerator) |
| **YOLOX** | Apache-2.0 | Detector, **se** o degrau 2 for acionado. Substituto livre do Ultralytics (AGPL) | [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) |
| Roboflow Universe — container | verificar caso a caso | 5+ datasets de detecção de código (1.230 / 1.001 / 304 imagens). Úteis para **medir baseline** e treinar detector; procedência de licença precisa ser conferida por dataset | [busca](https://universe.roboflow.com/search?q=class%3Acontainer+number) |
| `lbf4616/ContainerNumber-OCR` | ⚠️ **sem licença** | Referência de arquitetura (PixelLink + LSTM). Dataset no Google Drive. **Sem licença = não usar código nem dados**; ler apenas | [lbf4616/ContainerNumber-OCR](https://github.com/lbf4616/ContainerNumber-OCR) |
| `lamnguyenkhoa/container-code-recognition` | verificar | YOLOv4 + OCR sobre vídeo. Referência de pipeline | [lamnguyenkhoa/container-code-recognition](https://github.com/lamnguyenkhoa/container-code-recognition) |
| ISO 6346 — validadores | vários | Vetores de teste para o `pytest`, incluindo o caso `check digit 10 → 0` | [datasets/ISO-Container-Codes](https://github.com/datasets/ISO-Container-Codes), [solyarisoftware/iso6346](https://github.com/solyarisoftware/iso6346) |
| Fontes OFL condensadas/stencil | OFL | 4–6 fontes para os sintéticos | Google Fonts |
| **WinSW** | MIT | Empacota o `.exe` como serviço Windows | [winsw/winsw](https://github.com/winsw/winsw) |
| VC++ Redistributable | — | **Embarcar no instalador.** Falta num Windows limpo e derruba o serviço sem mensagem útil | — |

**Referência de acurácia de mercado:** sistemas comerciais consolidados (Adaptive Recognition Carmen, Vaxtor, Intlab) declaram 95–99% em portaria com veículo parado. Um sistema próprio bem feito chega a **90–97%**. Prometer 99,9% é irrealista e cria conflito na entrega.

---

## 8. Fases de execução

Ordem de dependência, não calendário fixo. **A fase 1 trava tudo:** sem câmera bem posicionada não há dado; sem dado não há modelo.

### Fase 0 — Fundação
- Esqueleto do projeto, `pyproject.toml`, config validada por Pydantic (falha alto no boot)
- **`iso6346.py` com 100% de cobertura** — check digit, size/type, correção posicional. É o módulo mais barato de acertar e o mais caro de errar
- SQLite + Alembic + modelos
- MediaMTX no ambiente de dev servindo 3 vídeos como RTSP local

### Fase 1 — Óptica e captura ⚠️ *bloqueante*
- **`tools/aim.py`** e alvo de calibração impresso
- Medir no local: distância disponível para cada câmera, posição do código na lateral dos contêineres do cliente
- Decidir e comprar a 4K com a conta do §4.2 em mãos
- Bancada: validar RTSP substream, `snapshot.cgi` em resolução plena, ONVIF, limite de taxa do snapshot
- `cameras/` + `capture.py` com reconexão e watchdog

### Fase 2 — OCR v0 e medição de baseline
- `ocr/engine.py` sobre RapidOCR com PP-OCRv5 **pré-treinado** (ainda sem treino próprio)
- `roi.py`, `fusion.py`
- **Medir a acurácia do v0 nas primeiras imagens reais.** Este número decide todo o resto do projeto — não avance sem ele

### Fase 3 — API e integração
- Rotas do §5.2, outbox com retry, webhook
- Interface web de configuração
- Tabela `training_samples` alimentada pelo `PATCH`
- Política de retenção **ativa desde já** — não é refinamento posterior; sem ela o disco enche e o serviço para

### Fase 4 — Coleta ⭐
- `tools/recorder.py` + relatório diário
- ~10 dias de coleta → ~1.000 eventos → ~3.000 recortes
- **Verificação diária remota.** Não deixe para conferir no fim

### Fase 5 — Treino
- Sintéticos → TRUDI → fine-tune com dados próprios
- Export ONNX + **verificação de paridade**
- Avaliação num conjunto de validação 100% local, separado por contêiner (não por imagem — senão vaza)

### Fase 6 — Empacotamento
- PyInstaller → `.exe`; WinSW → serviço; Inno Setup → instalador
- **Teste da rede desligada** (§10)

### Fase 7 — Piloto
- Rodar **em paralelo** com a digitação manual por 2 semanas. Mede a acurácia real sem risco operacional
- Calibrar os limiares **por medição**, não por chute
- Só então liberar o modo automático

---

## 9. Pendências que travam o início

**Perguntar ao responsável pela operação:**

1. **Qual a distância disponível para cada câmera?** Decide o modelo da 4K e se as VIP 5180 PAN conseguem ler (§4).
2. **Onde fica o código na lateral dos contêineres típicos do cliente?** Decide o alinhamento longitudinal das laterais. Fotografar 10 unidades resolve.
3. **As portas ficam sempre voltadas para trás?** Se variar, a câmera traseira às vezes vê a frente do contêiner — que não tem o código no mesmo lugar. Afeta a meta de auto-aceite.
4. ⭐ **O sistema principal exporta o log dos códigos digitados pelo porteiro?** Decide se a anotação custa 2 h ou 13 h (§6.2). **A pergunta de maior retorno da lista.**
5. **Existe link de rede no local para manutenção remota?** "Offline" é o software; suporte remoto precisa de link.
6. **A portaria opera 24 h?** Define o peso do caso noturno com IR no dataset e na escolha do sensor.

**Verificações técnicas na primeira semana:**
- `snapshot.cgi` entrega 8 MP? Qual o limite de taxa antes de a câmera travar?
- Distância em cabo até o PC — **PoE tem limite de 100 m**
- Energia, aterramento, autorização para furar, escada/plataforma, EPI

---

## 10. Verificação

**Testes automatizados**
- `pytest` sobre `iso6346.py` com vetores conhecidos, incluindo `check digit 10 → 0` e todos os prefixos de proprietário do arquivo `ISO-Container-Codes`
- `fusion.py`: casos sintéticos de 3 leituras discordantes → resultado esperado e estado esperado (`AUTO_ACCEPT` vs `NEEDS_REVIEW`)
- API com `httpx`: fluxo completo — dispara evento → processa → `PATCH` de correção → webhook entregue → linha em `training_samples`
- Outbox com o destino derrubado: itens acumulam, destino volta, tudo é entregue na ordem
- **Escopo dos binds:** teste que confirma que `127.0.0.1:8478` (configuração) **não responde** a partir de outro host da rede, e que a API em `:8477` recusa origem fora da allowlist com `403` — antes de checar a API key

**End-to-end sem hardware**
MediaMTX servindo 3 vídeos como RTSP local. Roda em CI, sem câmera nenhuma. É a diferença entre desenvolver bloqueado e desenvolver.

**Paridade Paddle ↔ ONNX**
200 imagens, saídas comparadas caractere a caractere. Divergência > 0,5% reprova o export.

**⭐ Teste da rede desligada (inegociável)**
Instalar em Windows limpo **com a placa de rede desabilitada**, reiniciar a máquina, processar um evento ponta a ponta com câmeras numa rede isolada. Confirmar com `netstat -b` que nada tenta sair. Verificar com `pyi-archive_viewer` que **`paddle` e `paddleocr` não entraram no executável** — ler o código não basta, um import indireto entra sem aviso e só falha no cliente.

**Antes de ir a campo**
`recorder` gravando 24 h com corte de energia e de rede no meio · `aim` aferido contra medida real de trena · relatório diário acessado de fora da rede · o `.exe` rodando em Windows limpo, sem Python instalado

**Em produção**
Soak de 72 h · piloto em paralelo com a digitação manual · reboot confirmando que o serviço sobe sozinho, sem login

---

## 11. Riscos

| Risco | Mitigação |
|---|---|
| 🔴 **Câmera montada longe demais** — modo de falha nº 1 | Volume de dados não corrige óptica. `aim` + alvo impresso **antes de furar**. 4K com zoom motorizado elimina o risco |
| 🔴 **Voltar da coleta com dado inutilizável** | Relatório diário remoto · rodar o v0 sobre as imagens do dia 1 e revisar antes de deixar rodando |
| 🟠 **Erro silencioso** — pior que não ler | `mod 11` deixa passar ~1 em 11 erros. Por isso a **concordância entre 3 câmeras** entra no critério de auto-aceite, não só o check digit. **KPI crítico: ≤0,5%** |
| 🟠 **Divergência silenciosa na conversão ONNX** | Verificação de paridade obrigatória no CI de export |
| 🟠 **Snapshot CGI limitado ou em baixa resolução** | Validar em bancada na semana 1. Plano B: decodificar RTSP main só na janela do evento |
| 🟠 **Desempenho noturno da 4K** | Exigir Starlight, sensor ≥1/1.8", ≤0,005 lux **antes de comprar** |
| 🟡 **Serviço `LocalSystem` não enxerga cache de usuário** | Resolvido por design: ONNX com caminho absoluto, nada baixado em runtime |
| 🟡 **Disco enche e o serviço para** | Retenção obrigatória desde a fase 3, com alarme em `/health` |
| 🟡 **API em HTTP puro numa rede que deixe de ser confiável** | Bind por IP + allowlist + UI só em loopback (§5.2/§5.3). Decisão documentada e `scheme` configurável, para que habilitar TLS depois não exija mudança de código |

### Metas a acordar formalmente

Auto-aceite correto **≥92%** · erro silencioso **≤0,5%** · resposta **≤3 s** · disponibilidade **≥99%**

---

## Resumo

1. **A fusão das 3 câmeras é a alavanca do projeto.** Mesmo código, três ângulos, votação por caractere + check digit. Vale mais que qualquer refinamento de modelo.
2. **As VIP 5180 PAN leem — a ≤3,5 m e alinhadas com o código.** A 6 m, não. A montagem decide, não a câmera.
3. **A 4K traseira deve ser varifocal motorizada** se o orçamento permitir. Elimina o risco de enquadramento, que é o mais caro do projeto.
4. **Snapshot HTTP para OCR, substream RTSP para gatilho, ONVIF para controle.** Não é "RTSP ou outra coisa" — são três canais com papéis diferentes.
5. **RapidOCR evita escrever a camada mais arriscada do sistema** (pré/pós-processamento ONNX do PP-OCR).
6. **TRUDI está liberado** pela decisão de uso interno. Vale ~3.100 amostras reais.
7. **3 câmeras tornam a meta de 3.000 imagens barata:** 1.000 eventos, 1 transcrição cada.
8. **A pergunta de maior retorno:** o sistema principal exporta o log digitado pelo porteiro?
