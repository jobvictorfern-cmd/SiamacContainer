# SiamacContainer — Leitura Automática de Contêineres na Balança

> **Este documento substitui `PLANO.md` e `PLANO-LACUNAS.md`.** Os dois anteriores
> permanecem no histórico do git. O primeiro foi escrito para uma **portaria** lendo **um**
> campo; as informações posteriores do cliente (câmeras na **balança**, captura **durante a
> pesagem**, "ler **todas** as informações", desktop Windows indefinido) mudaram premissas
> que atravessam o plano inteiro. Onde os documentos anteriores se contradiziam, este
> resolve — e marca a resolução com ⚙️.

---

## Sumário

1. [Contexto e escopo](#1-contexto-e-escopo)
2. [Decisões de arquitetura](#2-decisões-de-arquitetura)
3. [O evento: da pesagem à entrega](#3-o-evento-da-pesagem-à-entrega)
4. [Óptica, montagem e obra](#4-óptica-montagem-e-obra)
5. [Conectividade das câmeras](#5-conectividade-das-câmeras)
6. [Arquitetura de software](#6-arquitetura-de-software)
7. [API — contrato com o sistema principal](#7-api--contrato-com-o-sistema-principal)
8. [Modelo e dados](#8-modelo-e-dados)
9. [Recursos externos](#9-recursos-externos)
10. [Fases de execução](#10-fases-de-execução)
11. [Verificação](#11-verificação)
12. [Riscos](#12-riscos)
13. [Operação e conformidade](#13-operação-e-conformidade)
14. [Pendências que travam o início](#14-pendências-que-travam-o-início)
15. [Como usar este documento com o Codex](#15-como-usar-este-documento-com-o-codex)

---

## 1. Contexto e escopo

### 1.1 O problema

Hoje as informações dos contêineres que passam pela balança são digitadas manualmente.
Digitação manual é lenta, gera erro de transcrição e não deixa evidência visual do que passou.

O objetivo é **ler automaticamente as informações do contêiner durante a pesagem do
caminhão**, entregar o resultado ao sistema principal por API, e — quando a leitura não for
confiável — deixar que um humano corrija **no sistema principal**, sem travar a operação.

### 1.2 Restrições dadas

| | |
|---|---|
| Câmeras laterais | 2× **Intelbras VIP 5180 PAN FT** (já adquiridas) — 1/2.7" 4 MP, 2880×1620, lente fixa 2,1 mm F2.0, 180° H × 78° V, 3 streams, ePTZ |
| Câmera traseira | 1× Intelbras **4K**, modelo a definir — lê as portas |
| ⚙️ **Local** | **Área da balança** (não a portaria) |
| ⚙️ **Momento da captura** | **Durante a pesagem** — veículo parado por 20–60 s |
| ⚙️ **Condições** | Horários e clima **variam** — opera de dia, de noite, com sol direto e com chuva |
| Plataforma | **Windows, como serviço** — sem janela gráfica aberta |
| ⚙️ **Hardware** | Desktop Windows, **modelo indefinido** — ver §6.5 para o requisito mínimo que precisa ser acordado |
| Funcionamento | **Sem internet.** Nada pode ser baixado em tempo de execução |
| Configuração | Precisa de interface, mas não pode ser app de desktop aberto |
| Correção humana | Acontece **no sistema principal, via nossa API** |
| Licenciamento | **Uso interno, um cliente só** — sem distribuição a terceiros |
| Base técnica | PaddleOCR (treino) + RapidOCR/ONNX (produção) + dataset TRUDI |

### 1.3 ⚠️ O escopo de leitura ainda NÃO está fechado

**Esta é a pendência número 1 do projeto.** "Ler todas as informações do contêiner" pode
significar 1 campo ou 12, e a diferença muda o modelo, o dataset, a API, a tela de revisão
e o número de câmeras.

A tabela abaixo precisa ser **preenchida e assinada pelo responsável da operação** antes de
a primeira linha de código de OCR ser escrita. A coluna "Obrigatório?" é dele, não nossa.

| Campo | Onde fica no contêiner | Câmera | Viabilidade | Obrigatório? |
|---|---|---|---|---|
| **Código ISO 6346** (11 car., 100 mm) | Laterais, porta, frente, teto | Todas as 3 | ✅ Alta — o núcleo do sistema | ☐ |
| **Código tamanho/tipo** (4 car., ex. `45G1`, `22G1`) | Ao lado ou abaixo do código | Todas as 3 | ✅ Alta — a tabela ISO de combinações válidas é um **segundo validador**, tão forte quanto o check digit | ☐ |
| **MAX GROSS / TARE / NET / CUBE** (kg e lb) | Porta, às vezes lateral | Traseira | 🟡 Média — texto menor e multilinha, mas formato rígido (`MAX GROSS 30.480 KG 67.200 LB`) permite regex + coerência com o tipo ISO **e com o peso da balança** | ☐ |
| **Placas de risco IMO / número ONU** | Laterais e porta | Todas as 3 | 🟡 Média — o número ONU no painel laranja tem 65–100 mm e é legível. A classe de risco é **classificação de imagem**, não OCR | ☐ |
| **Porta aberta/fechada, avaria, amassado, furo** | Porta e laterais | Todas as 3 | 🟡 Média — modelo de classificação/segmentação **separado**, fase posterior. No dia 1: apenas guardar a evidência fotográfica | ☐ |
| **Logo do armador/operador** | Laterais | Laterais | 🟡 Média — mas em geral **derivável do prefixo do código**, o que torna a visão desnecessária | ☐ |
| **Vazio / carregado** | — | — | ✅ Derivável do peso (bruto − tara ≈ 0), sem visão | ☐ |
| **Peso bruto** | — | Balança | ✅ Vem do indicador (§3) | ☐ |
| **Placa do cavalo / semirreboque** | Veículo | Traseira, laterais | 🟡 Média — é **outro modelo** (ALPR Mercosul + padrão antigo). Antes de construir: **o sistema de pesagem já registra a placa?** | ☐ |
| **Número do lacre** | Barra de travamento da porta direita | Traseira | ❌ **Inviável com 3 câmeras — ver §4.4** | ☐ |
| **Placa CSC / ACEP** (validade, fabricação) | Porta | Traseira | ❌ Inviável — caracteres de 5–10 mm, mesmo problema do lacre | ☐ |
| **Reefer: set point, temperatura, horímetro** | Display na **frente** do contêiner | ❌ nenhuma | ❌ Nenhuma câmera cobre a frente. Se necessário, é uma 4ª câmera | ☐ |

**Regra de decisão:** todo campo marcado como obrigatório entra no contrato de API, no
dataset e nas metas de acurácia — com meta **própria**, porque a acurácia de `MAX GROSS` não
será a mesma do código ISO. Campo não marcado não é implementado, nem "por garantia".

### 1.4 Metas

| Métrica | Meta | Observação |
|---|---|---|
| Auto-aceite correto do **código ISO** | **≥92%** | Referência de mercado: sistemas comerciais consolidados (Carmen, Vaxtor, Intlab) declaram 95–99% com veículo parado. Um sistema próprio bem feito chega a 90–97%. **Prometer 99,9% cria conflito na entrega** |
| **Erro silencioso** (código errado aceito sem aviso) | **≤0,5%** | O KPI mais crítico. Pior que não ler |
| Auto-aceite dos demais campos obrigatórios | **a definir por campo** após a medição de baseline da Fase 2 | Não prometer antes de medir |
| Latência da leitura | **≤3 s** após o fim da janela de captura | ⚙️ Mas a pesagem **nunca** espera — ver §3.4 |
| Disponibilidade | **≥99%** | |

---

## 2. Decisões de arquitetura

| Decisão | Por quê |
|---|---|
| **Treinar com PaddleOCR, executar com ONNX Runtime** | PaddlePaddle/PaddleX em produção arrasta ~1 GB de dependências, conflita com DLLs no Windows e tenta baixar modelos na inicialização. ONNX Runtime roda o mesmo modelo com ~50 MB e sem rede |
| **Usar RapidOCR (Apache-2.0) como camada de inferência** | Ele já é exatamente isso: modelos PaddleOCR em ONNX Runtime, com pré/pós-processamento (DBNet unclip, CTC decode, angle cls) implementado e testado. Aceita `det_model_path`, `rec_model_path`, `rec_keys_path` locais. **Economiza a parte onde a conversão para ONNX falha em silêncio** |
| **Fusão multi-câmera e multi-frame por votação de caractere** | O mesmo código está impresso nos 3 lados. ⚙️ E na balança o veículo fica parado 20–60 s, o que dá **dezenas de frames por câmera** em vez de 3–5. Votação + check digit ISO 6346 como árbitro é a alavanca principal do projeto |
| ⚙️ **Gatilho pelo indicador de peso** | Peso estável acima de um limiar é um sinal limpo, sem falso positivo e sem visão computacional. É melhor que detecção de movimento |
| **Captura híbrida: substream RTSP + snapshot em resolução plena** | Ver §5 |
| **ROI configurada, sem detector treinado no degrau 1** | Câmera fixa + veículo parado em posição marcada = região previsível. Elimina um modelo inteiro. Detector entra só se a medição mostrar necessidade |
| **Dicionário de 36 caracteres (`A–Z`, `0–9`)** | A camada de saída cai de ~6.600 classes (dicionário chinês do PP-OCR) para 36. Modelo menor, mais rápido, e **impossibilita por construção a saída de caractere inválido** |
| **FastAPI + SQLite + Jinja2/HTMX** | Serviço único que atende a API de integração *e* serve as páginas de configuração. Zero administração, zero build de frontend, arquivo único de banco |
| **Nada baixa em tempo de execução** | Todo modelo, fonte e binário vai embarcado, com caminho absoluto vindo do `config.yaml`. Requisito de serviço Windows rodando como `LocalSystem` |

### 2.1 Licenças — resolvidas pela resposta "uso interno, um cliente só"

- **TRUDI (CC BY-SA 4.0): liberado.** As obrigações da CC BY-SA disparam ao *compartilhar*
  material adaptado. Sem distribuição a terceiros, não disparam. Registrar a atribuição no
  `NOTICE.md` de qualquer forma. → **~3.100 recortes reais rotulados entram no treino.**
- **Ultralytics YOLO (AGPL-3.0): evitável, então evite.** Sem distribuição o gatilho
  principal não dispara, mas a cláusula §13 (interação remota por rede) é área cinzenta que
  não vale defender. **YOLOX é Apache-2.0** e resolve o mesmo problema.
- **PaddleOCR: Apache-2.0.** **RapidOCR: Apache-2.0.** Sem restrição.

### 2.2 A escada de complexidade

Comece no degrau 1. Suba apenas quando uma **medição** mostrar necessidade — nunca por
antecipação. **Esta regra é dura e vale para todo o projeto.**

| | Adicionar | Sintoma que justifica |
|---|---|---|
| **1** | ROI fixa + PP-OCR + ISO 6346 + fusão multi-câmera/multi-frame | *(ponto de partida)* |
| 2 | Detector YOLOX da região do código | ROI fixa erra: caminhão fora de posição, 20' e 40' em alturas diferentes, duplo 20' |
| 3 | Beam search com top-K por posição | Erros recorrentes de exatamente 1 caractere |
| 4 | Super-resolução no recorte antes do OCR | px/caractere ficou entre 20 e 28 e não dá para reposicionar a câmera |

---

## 3. O evento: da pesagem à entrega

⚙️ **Seção nova.** A balança não é um detalhe de contexto: ela é o gatilho, a fonte do
vínculo com o negócio e a razão pela qual a janela de captura é generosa.

### 3.1 Fluxo

```
caminhão sobe na balança
        │
        ▼
indicador de peso estabiliza acima do limiar  ──►  GATILHO
        │
        ▼
janela de captura (20–60 s, enquanto o peso estiver estável)
   3 câmeras × N snapshots  ──►  buffer em disco
        │
        ▼
pesagem termina, caminhão sai   ◄── NUNCA espera o OCR
        │
        ▼
processamento assíncrono: ROI → OCR → fusão → validação ISO
        │
        ├── AUTO_ACCEPT   ──►  outbox ──► webhook ──► sistema principal
        └── NEEDS_REVIEW  ──►  outbox ──► webhook ──► fila de correção humana
```

### 3.2 O indicador de peso

**Pendência bloqueante:** qual indicador está instalado? (Toledo, Alfa, Filizola, Balmak,
Coester, Micheletti, Ramuza…). A maioria dos indicadores brasileiros emite um quadro ASCII
contínuo por RS‑232 com um bit ou caractere de estabilidade; alguns têm Ethernet/TCP.
**Ler o manual do indicador que está no local — não presumir protocolo.**

Dois caminhos, e o primeiro é muito mais barato:

| Caminho | Quando | Custo |
|---|---|---|
| ⭐ **O software de pesagem existente chama `POST /v1/events`** | Se já existe software de pesagem | Baixo. E ele já traz o `ticket_id`, a `placa` e o `peso` prontos |
| Ler a serial/TCP do indicador diretamente | Se não existe software, ou ele não pode ser alterado | Um módulo `scale/` a mais, com parser por marca |

Suportar os dois, configurável. Implementar o primeiro; o segundo se a resposta exigir.

### 3.3 A janela de captura é uma vantagem — use-a

O plano anterior dimensionava "3–5 snapshots em 4 s", pensando numa portaria. Na balança o
veículo fica parado **20 a 60 s**, o que permite **15–30 snapshots por câmera**. A fusão
por votação (§6.4) deixa de arbitrar entre 3 leituras e passa a arbitrar entre **45 a 90**.
Isso vale mais que qualquer refinamento de modelo.

⚠️ **Mas isso colide com o limite de taxa do `snapshot.cgi` (~1 fps, §5).** Teste de bancada
obrigatório na semana 1: quantos snapshots consecutivos a câmera entrega em 30 s antes de
degradar ou travar. **Se o limite atrapalhar, o "plano B" do §5 — decodificar o RTSP main só
durante a janela do evento — deixa de ser plano B e vira a escolha certa.** Decodificar 30 s
de um stream 4K por evento é perfeitamente pagável quando os eventos são esparsos.

### 3.4 A pesagem nunca bloqueia

Requisito explícito: **a leitura é assíncrona e se anexa ao ticket depois.** Caminhão parado
esperando OCR é fila na balança, e fila na balança é o tipo de problema que faz o cliente
desligar o sistema. O `POST /v1/events` responde `202` imediatamente.

### 3.5 Entrada e saída — uma validação de graça

Numa balança o mesmo caminhão costuma ser pesado **duas vezes** (entrada e saída). Isso dá
uma verificação que não custa nada:

> Se o código lido na entrada não bater com o da saída, **uma das duas leituras está errada**
> — mesmo que ambas tenham passado no check digit. Marcar as duas para revisão.

Isso ataca diretamente o risco de erro silencioso, que o `mod 11` sozinho não elimina
(§6.4). Implementar assim que houver `ticket_id` vinculando as duas pesagens.

---

## 4. Óptica, montagem e obra

**O critério não é megapixel, é altura em pixels por caractere.** Caracteres do código
ISO 6346 têm 100 mm.

> **Meta: ≥30 px/caractere. Abaixo de 20 px nenhum OCR lê de forma confiável.**

### 4.1 Câmeras laterais — VIP 5180 PAN FT

Sensor 1/2.7" 4 MP, **2880×1620**, lente fixa **2,1 mm F2.0**, **180° H × 78° V**, sensor
único (sem costura de imagem). O "zoom digital 16×" do ePTZ é **recorte, não ganha
resolução** — não conte com ele.

Como é uma panorâmica com projeção cilíndrica (não retilínea), a conta correta é angular:

```
px/caractere = (1620 px ÷ 78°) × (5,73° ÷ d)  ≈  119 ÷ d      [d em metros]
```

**A distância que conta não é a lateral, é a diagonal.** Com a câmera a `L` metros da
lateral do contêiner e o código a `x` metros de deslocamento longitudinal em relação ao eixo
da câmera:

```
d = √(L² + x²)
```

Disso sai a **janela longitudinal útil** — o quanto o caminhão pode parar fora do ponto
ideal sem que a leitura degrade:

| `L` (distância lateral) | `x` máximo para 30 px | Janela útil |
|---|---|---|
| 3,5 m | 1,87 m | ±1,9 m |
| 3,0 m | 2,60 m | ±2,6 m |
| **2,5 m** | **3,08 m** | **±3,1 m** |
| 2,0 m | 3,43 m | ±3,4 m |

#### ⚙️ O caso que decide a montagem: dois contêineres de 20'

Dois 20' num mesmo chassi colocam os dois códigos a **~6 m um do outro**. Nenhuma janela
acima comporta os dois a partir de um único ponto. A saída é mirar o **ponto médio** entre
eles — cada código fica então a `x = ±3,05 m`:

| `L` | px/caractere em **cada um** dos dois códigos |
|---|---|
| 3,5 m | 26 ⚠️ |
| 3,0 m | 28 ⚠️ |
| **2,5 m** | **30 ✓ — no limite** |
| 2,0 m | 33 ✓ |

> ⚙️ **Correção em relação ao plano anterior, e é a conclusão mais importante deste
> documento.** O `PLANO.md` admitia montagem "a ≤3,5 m da lateral". **A 3,5 m o caso duplo
> 20' não fecha.** As laterais devem ser montadas **a ~2,5 m da lateral do contêiner**, e a
> mira longitudinal é o **ponto médio entre as duas posições de código possíveis** — não o
> meio de um contêiner de 40'.

**Verificação de enquadramento vertical**, que é o que impede descer abaixo de 2,5 m:

| `L` | Altura coberta (78° V) | Veredito |
|---|---|---|
| 2,0 m | 3,24 m | ⚠️ apertado para high cube sobre chassi (topo a ~4,4 m) |
| **2,5 m** | **4,05 m** | ✓ folgado |
| 3,0 m | 4,86 m | ✓ |

Com a câmera a ~2,9 m do solo e `L` = 2,5 m, a cobertura vai de ~0,9 m a ~4,9 m. Cobre o
contêiner inteiro sobre chassi. **2,5 m é o ponto ótimo.**

⚠️ Um poste a 2,5 m da lateral do contêiner fica a ~2,2 m da borda da plataforma da balança.
**Precisa de proteção física** (balizador ou defensa) contra manobra — ver §4.7.

⚠️ **Item bloqueante de campo:** é preciso saber **onde o código realmente fica** na lateral
dos contêineres que passam nesta balança. Normalmente na parte superior, próximo à
extremidade das portas — mas isso varia por armador. **Fotografar 10 contêineres típicos do
cliente e medir.** Alinhar com o meio do contêiner desperdiça a câmera.

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

1. ⭐ **4K com zoom motorizado / varifocal** (linha Intelbras VIP 9860 IA FT ou equivalente
   8 MP com lente motorizada). **Elimina o risco de distância por completo** — ajusta-se no
   local, sem refazer furação. Vale a diferença de preço, porque erro de enquadramento é o
   modo de falha mais caro do projeto.
2. **4K fixa 3,6 mm** (linha VIP 3830 B IA: 8 MP, 3,6 mm, Starlight, IR 30 m, PoE). Cobre
   3–8 m confortavelmente. Escolha correta **se a distância já estiver medida e travada**.
3. ❌ **Evitar 4K com lente 2,1 mm ou fisheye/panorâmica.** Recai no mesmo problema da 5180 PAN.

**⚠️ A armadilha noturna, contraintuitiva:** 8 MP num sensor 1/2.8" tem pixels *menores* que
4 MP no mesmo sensor — capta menos luz e gera mais ruído. Se a balança opera 24 h, boa parte
dos eventos será com pouca luz. Antes de comprar, verificar:

- **Tamanho do sensor** — 1/1.8" é muito superior a 1/2.8" em 4K
- **Starlight** presente e iluminação mínima **≤0,005 lux**
- **Alcance do IR** ≥30 m (mas ver o alerta de IR de perto em §4.5)
- **Taxa de quadros em 8 MP** — algumas caem para 15 fps

> Uma 4 MP Starlight num sensor grande pode ler melhor à noite que uma 4K comum.
> **A pergunta muda de "tem resolução?" para "enxerga no escuro?".**

### 4.3 ⚙️ O que a traseira vê — e o que ela não vê no duplo 20'

A câmera traseira enxerga apenas as portas do **contêiner de trás**. No caso duplo 20', o
contêiner da frente tem **2 votos, não 3**. Isso não é detalhe de implementação: a meta de
erro silencioso ≤0,5% se apoia na concordância entre três câmeras independentes. Com duas,
o mesmo limiar não se sustenta. **O limiar de auto-aceite precisa ser diferente por posição**
(§6.4).

### 4.4 ⚙️ O lacre não é legível com este arranjo — o número

Caracteres de lacre têm **~5 mm**, não 100 mm. Com a 4K traseira a 5 m entregando 50 px num
caractere de 100 mm (§4.2), o mesmo pixel sobre 5 mm dá **2,5 px**. Nenhum OCR, nenhuma
super-resolução e nenhum volume de dataset resolvem isso.

Para chegar a 25 px/caractere num caractere de 5 mm com 2160 px na vertical, a câmera
precisa enquadrar uma faixa vertical de apenas:

```
campo vertical = 0,005 m × 2160 px ÷ 25 px = 0,43 m
```

A 3 m isso é um AFOV vertical de ~8° — **lente de 25–35 mm**. E como a posição longitudinal
de parada varia muito mais que 43 cm, uma câmera fixa com esse enquadramento erra o alvo
quase sempre.

**Duas saídas, e a decisão é do cliente:**

| Saída | Consequência |
|---|---|
| ⭐ **O lacre continua sendo digitado** | Custo zero. O lacre normalmente já consta no documento de transporte |
| **4ª câmera PTZ com preset e zoom óptico real** | Custo de equipamento, de instalação e de um subsistema de controle PTZ. E ainda assim com autofoco a resolver |

**Decidir isto antes da Fase 1** — é a diferença entre um projeto de 3 e de 4 câmeras.

O mesmo cálculo condena a **placa CSC** (caracteres de 5–10 mm).

### 4.5 ⚙️ Ambiente físico — clima é engenharia antes de ser dataset

O §8.3 trata clima como variedade de treino. Mas na balança clima é primeiro um problema
físico, e **nenhum volume de imagens corrige uma lente suja**.

| Problema | Contramedida — entra no escopo de instalação |
|---|---|
| ⚠️ **IR estourando de perto** | A 2,5 m, um IR dimensionado para 30 m **satura a imagem em branco**. Contraintuitivo e comum. Ou Smart IR com potência reduzida, ou **iluminação branca externa** — que ainda dá imagem colorida, ajuda nas placas de risco e inibe |
| **Sol direto na lente** no nascer/pôr | Descobrir o **azimute da balança**. Se as laterais ficam voltadas leste/oeste, haverá minutos diários de imagem inutilizável. Viseira longa, inclinação, WDR configurado |
| **Respingo e sujeira de pneu** | Altura e ângulo que protejam a lente; revestimento hidrofóbico; **rotina de limpeza com periodicidade definida no runbook** |
| **Teias e insetos no housing IR** | Causa clássica de falso movimento e borrão em câmera externa. Entra na rotina de limpeza |
| **Condensação** | Housing IP67 com sílica; verificar se o modelo tem aquecedor |
| **Surto atmosférico** | Câmera em poste na área de balança é alvo clássico de raio. **Protetor de surto no PoE + aterramento.** Sem isso, perde-se câmera e switch juntos |
| **Exposição e shutter** | A configuração da câmera (WDR/BLC, shutter mín./máx., ganho) **faz parte do produto**, não é ajuste de instalador. Versionada no repositório e aplicável via CGI Dahua, para poder ser restaurada após troca de equipamento |

### 4.6 Ferramenta obrigatória: `siamac-aim`

Utilitário de linha de comando que, apontado para uma câmera, mede **ao vivo**:
px/caractere sobre um alvo impresso de dimensão conhecida, nitidez (variância do Laplaciano)
e histograma de exposição. Com calculadora reversa: *"para 30 px/caractere com esta lente,
monte entre X e Y metros."*

**Roda antes de furar a parede.** Sem ela o enquadramento é chute, e o erro só aparece
semanas depois, quando o modelo não converge.

### 4.7 ⚙️ Obra civil — a contramedida mais barata do projeto

Numa balança a posição de parada já é mais repetível que numa portaria: todos os eixos
precisam estar sobre a plataforma. **Reforçar isso reduz a variação longitudinal para ±1 m
e resolve o problema do §4.1 praticamente de graça** — muito mais barato que trocar câmera.

Escopo de obra a acordar com o cliente:

- **Linha de parada pintada** na plataforma, mais semáforo ou sinaleira de "pare aqui"
- **Postes** para as laterais a ~2,5 m da lateral do contêiner, altura ~2,9 m, com
  **balizador/defensa** contra manobra
- **Poste da traseira** na distância definida pelo §4.2 com o `aim` em mãos
- **Infraestrutura**: eletrodutos, PoE (⚠️ **limite de 100 m de cabo**), aterramento,
  protetor de surto, autorização para furar, escada/plataforma, EPI

---

## 5. Conectividade das câmeras

**RTSP é parte da resposta, não toda ela.** A melhor forma é usar **três canais diferentes
da mesma câmera, cada um para o que faz bem**. Câmeras Intelbras VIP são baseadas em Dahua e
expõem os três.

| Canal | Uso | Custo |
|---|---|---|
| **RTSP substream** (`.../cam/realmonitor?channel=1&subtype=1`, ~704×576) | Ficar sempre ligado: presença, "o caminhão parou", saúde da câmera | ~1% de CPU por câmera |
| **HTTP CGI snapshot** (`/cgi-bin/snapshot.cgi?channel=0`) | **Os frames que vão para o OCR.** JPEG em resolução plena direto do ISP | Sob demanda |
| **ONVIF** (`onvif-zeep-async`) | Descoberta, URI de snapshot e de stream, sincronismo de hora, eventos de IVS/motion por PullPoint | Desprezível |

**Por que snapshot em vez de frame do RTSP main:** o frame extraído do H.264/H.265 carrega
artefato de compressão inter-quadro exatamente na borda do caractere, que é o que o OCR
precisa. O snapshot é um JPEG intra-quadro gerado pelo ISP. Além disso, decodificar 3 streams
4K continuamente custa CPU real; o substream custa quase nada.

⚠️ **Limitações a validar em bancada, semana 1:**

1. O `snapshot.cgi` de linha Dahua costuma ser limitado a **~1 fps** e **pode travar a câmera
   se chamado em laço apertado**. ⚙️ Com a janela de 20–60 s da balança (§3.3) queremos
   15–30 snapshots — **este teste passa a ser decisivo, não apenas prudente**.
2. A resolução do snapshot segue a configuração de *foto* da câmera, não a do stream —
   **conferir que está no máximo**, não no padrão baixo.
3. Se o snapshot não sustentar a taxa ou a resolução, decodificar o **RTSP main** apenas
   durante a janela do evento, com PyAV, e desligar entre eventos.

### ⚙️ Ordem de gatilho, do melhor para o pior

| | Gatilho | Observação |
|---|---|---|
| **1** ⭐ | **Indicador de peso estável** — direto ou via `POST /v1/events` do software de pesagem | Zero falso positivo, e traz o vínculo de negócio (`ticket_id`) junto |
| 2 | Evento ONVIF de IVS da câmera (line crossing / intrusion) | Se o modelo expuser |
| 3 | Detecção de movimento própria sobre o substream | Fallback |

Implementar 1 e 3; o 2 se a câmera expuser. Todos configuráveis.

---

## 6. Arquitetura de software

### 6.1 Stack

**A decisão estrutural é que existem dois ambientes, e eles nunca se misturam.**

```
┌─ TREINO ──────────────────┐        ┌─ PRODUÇÃO ────────────────┐
│ nossa máquina, com GPU    │        │ PC da balança, offline    │
│ PaddlePaddle + PaddleOCR  │ .onnx  │ ONNX Runtime + RapidOCR   │
│ pesado, ~4 GB             │ ─────► │ leve, ~250 MB             │
│ roda algumas vezes        │        │ roda 24/7 como serviço    │
└───────────────────────────┘        └───────────────────────────┘
```

O produto entregue **não contém PaddlePaddle**. O único artefato que atravessa a fronteira é
o `.onnx`. O CI verifica isso (§11).

#### Produção

| Camada | Escolha | Por quê |
|---|---|---|
| Runtime | **Python 3.13** | Wheels maduras em `onnxruntime`, `opencv` e `PyInstaller` |
| Dependências | **uv** + lockfile | Reprodutível. `uv export` gera o requirements travado para build sem rede |
| Inferência | **onnxruntime** (CPU) | ~50 MB. Sem PaddlePaddle, sem PaddleX, sem conflito de DLL |
| OCR | **rapidocr** (Apache-2.0) | Pré/pós-processamento PP-OCR já resolvido |
| Visão | **opencv-python-headless** | ⚠️ **`headless`, não o pacote cheio.** O completo arrasta Qt, e um serviço Windows não tem sessão gráfica para inicializá-lo |
| RTSP | **PyAV** | ⚠️ `cv2.VideoCapture` **trava indefinidamente** quando a câmera some — sem timeout confiável. Num serviço 24/7 isso é uma thread morta silenciosa |
| HTTP client | **httpx** | Snapshot CGI e webhook. Timeouts sãos por padrão |
| ONVIF | **onvif-zeep-async** | Descoberta, snapshot URI, hora, eventos PullPoint |
| ⚙️ Serial | **pyserial** | Leitura do indicador de peso, se o caminho direto for necessário (§3.2) |
| API + UI | **FastAPI** + **uvicorn** | Um processo serve os dois binds (§6.6). OpenAPI automática |
| Templates | **Jinja2 + HTMX** (arquivo local) | Sem `npm`, sem build step |
| Banco | **SQLite** (⚙️ **WAL + `synchronous=FULL`**) + **SQLAlchemy 2.x** + **Alembic** | Arquivo único, zero administração, migração versionada. ⚙️ WAL porque queda de energia na balança é rotina |
| Config | **pydantic-settings** + **PyYAML** | Valida no boot e **falha alto** |
| Logs | **structlog** → JSON em arquivo rotativo | Serviço não tem console |
| Empacotamento | **PyInstaller** modo **`onedir`** | ⚠️ **Não `onefile`:** extrai tudo para o temp a cada boot e dispara heurística de antivírus |
| Serviço | **WinSW** (MIT) | Envelopa o `.exe` como serviço Windows, com restart automático |
| Instalador | **Inno Setup** | Embarca o VC++ Redistributable e cria a regra de firewall |

#### Treino — máquina separada

| Camada | Escolha |
|---|---|
| Runtime | **Python 3.12** — o ecossistema de treino é mais rodado nele |
| Framework | **PaddlePaddle (GPU)** + **PaddleOCR clonado do repositório** (não o pacote pip — precisamos de `configs/rec/` e `tools/train.py`) |
| Export | **paddle2onnx** + **onnxsim** |
| Sintéticos | **SynthTIGER** ou **TextRecognitionDataGenerator** |
| Anotação | **PPOCRLabel v3** |
| Experimentos | CSV ou SQLite simples. MLflow só se o número de experimentos justificar |

#### Desenvolvimento e CI

**pytest** + `pytest-asyncio` + `pytest-cov` · **httpx** como cliente de teste ·
**MediaMTX** servindo RTSP falso · **ruff** · **mypy** no núcleo (`iso6346`, `fusion`,
`storage`) · GitHub Actions em matriz Linux + Windows

### 6.2 Descartados, e por quê

| Alternativa | Por que não |
|---|---|
| **Docker no cliente** | Windows offline, serviço nativo. Docker Desktop adiciona licença, virtualização e um ponto de falha no boot |
| **PostgreSQL** | Nó único, banco pequeno. SQLite não tem administração |
| **React / Vue** | Build step de frontend dentro de um instalador offline é dor sem retorno |
| **Celery + Redis** | O outbox é uma tabela SQLite com um worker asyncio. Dois serviços a menos no boot |
| **Nuitka** no lugar do PyInstaller | Binário melhor, build frágil com `opencv` e `onnxruntime` |
| **GPU (CUDA)** | Só se a medição exigir. E aí **DirectML (~40 MB)**, não CUDA — as DLLs do provider CUDA somam ~1 GB num sistema que vai embarcado |
| **PaddleOCR em runtime** | Tenta baixar modelo na inicialização mesmo com cache local, e arrasta PaddleX inteiro |

### 6.3 Estrutura do projeto

```
siamac-container/
├─ pyproject.toml                 # uv / hatchling
├─ config.example.yaml
├─ NOTICE.md                      # atribuições: TRUDI, PaddleOCR, RapidOCR
├─ docs/
│  ├─ DECISOES.md                 # ⚙️ toda decisão não óbvia, com justificativa
│  ├─ RUNBOOK.md                  # ⚙️ o que fazer quando algo quebra
│  └─ INSTALACAO.md               # ⚙️ checklist de campo
├─ src/siamac/
│  ├─ config.py                   # pydantic-settings, valida no boot e falha alto
│  ├─ cameras/
│  │  ├─ onvif_client.py          # descoberta, URIs, hora, eventos PullPoint
│  │  ├─ substream.py             # RTSP substream em loop, com reconexão
│  │  └─ snapshot.py              # HTTP CGI + fallback RTSP main
│  ├─ scale/                      # ⚙️ NOVO
│  │  ├─ indicator.py             # leitura serial/TCP do indicador
│  │  └─ parsers/                 # um parser por marca de indicador
│  ├─ trigger/
│  │  ├─ scale_trigger.py         # ⚙️ peso estável — gatilho preferencial
│  │  ├─ api_trigger.py           # POST /v1/events
│  │  └─ motion.py                # diferença de frames sobre o substream
│  ├─ capture.py                  # ⚙️ rajada durante a janela de pesagem + score de nitidez
│  ├─ roi.py                      # recorte por ROI configurada (+ YOLOX no degrau 2)
│  ├─ ocr/
│  │  ├─ engine.py                # wrapper fino sobre RapidOCR, modelos locais
│  │  └─ preprocess.py            # deskew, CLAHE, upscale, texto vertical
│  ├─ fields/                     # ⚙️ NOVO — um extrator por campo do §1.3
│  │  ├─ iso6346.py               # check digit mod-11, size/type, correção posicional
│  │  ├─ weights.py               # MAX GROSS / TARE / NET / CUBE
│  │  └─ placards.py              # ONU / classe de risco
│  ├─ fusion.py                   # ⭐ agrupamento por contêiner + votação por caractere
│  ├─ storage/
│  │  ├─ models.py                # Event, Container, Read, Field, Image, OutboxItem
│  │  ├─ retention.py             # purga por idade — obrigatória desde o dia 1
│  │  └─ migrations/              # Alembic
│  ├─ api/
│  │  ├─ routes_events.py         # integração + correção humana
│  │  ├─ routes_admin.py          # saúde, câmeras, diagnóstico
│  │  └─ outbox.py                # webhook com retry exponencial, HMAC e DLQ
│  ├─ webui/                      # Jinja2 + HTMX, sem build step
│  │  ├─ cameras.html             # credenciais, teste de conexão, snapshot ao vivo
│  │  ├─ roi.html                 # desenhar ROI sobre snapshot, em canvas
│  │  ├─ scale.html               # ⚙️ configuração e monitor do indicador
│  │  ├─ thresholds.html          # limiares de confiança e auto-aceite, por campo e por posição
│  │  └─ diagnostics.html         # últimos eventos, latência, disco
│  └─ service/
│     ├─ supervisor.py            # laço principal, watchdog das câmeras
│     └─ winservice.py            # entrypoint para WinSW
├─ tools/
│  ├─ aim.py                      # §4.6 — medidor de px/caractere
│  ├─ recorder.py                 # coletor de dataset autônomo
│  ├─ diag_bundle.py              # ⚙️ pacote de diagnóstico para pendrive
│  ├─ synth.py                    # gerador de sintéticos
│  ├─ trudi_convert.py            # MMOCR JSON → TSV do PaddleOCR
│  └─ export_onnx.py              # Paddle → ONNX + verificação de paridade
└─ tests/
```

### 6.4 O módulo que carrega o projeto: `fusion.py`

O mesmo código está impresso nos lados do contêiner, e a balança dá dezenas de frames por
lado. Isso permite votação:

```
Câmera ESQ (18 frames):  M S C U 4 5 6 7 8 2 1   conf: [.99 .98 .97 .91 .99 .88 .95 .99 .97 .93 .99]
Câmera DIR (21 frames):  M S C U 4 5 6 7 8 2 1   conf: [.97 .99 .95 .96 .98 .94 .89 .98 .99 .90 .98]
Câmera FUN (19 frames):  M 5 C U 4 5 6 7 8 2 1   conf: [.99 .61 .99 .99 .99 .97 .99 .99 .99 .96 .99]
                         ─────────────────────
Votação:                 M S C U 4 5 6 7 8 2 1   ← posição 2 resolvida por maioria + confiança
Check digit:             ✓ válido
Resultado:               MSCU4567821 · confiança 0,96 · AUTO_ACCEPT
```

**Regras, em ordem:**

0. ⚙️ **Agrupar as leituras por contêiner antes de votar.** No duplo 20' há dois códigos
   distintos no mesmo lado. Agrupar por posição espacial na imagem e por similaridade de
   string. **Esta etapa não existia no plano anterior e é pré-requisito de todas as demais.**
1. **Correção posicional determinística primeiro:** posições 1–4 são sempre letras, 5–11
   sempre dígitos. `O↔0`, `I↔1`, `S↔5`, `B↔8`, `Z↔2`, `G↔6` são resolvidos pela posição
   antes de qualquer outra coisa
2. Votação ponderada por confiança, caractere a caractere, **sobre todos os frames de todas
   as câmeras** daquele contêiner
3. **Check digit ISO 6346 (`mod 11`)** sobre o resultado da votação
4. Se falhar, testar as combinações top-2 por posição (busca limitada) procurando uma que valide
5. **Coerência com o código tamanho/tipo:** a tabela ISO de combinações válidas descarta
   leituras impossíveis
6. Se ainda falhar, ou se as câmeras discordarem acima do limiar → `NEEDS_REVIEW`

⚠️ **O check digit `mod 11` não é garantia:** aproximadamente **1 em cada 11 códigos errados
passa por acaso**. Ele reduz o erro silencioso, não o elimina. Por isso o limiar de
auto-aceite considera *também* a concordância entre câmeras — dois erros idênticos em duas
câmeras diferentes são muito improváveis.

⚙️ **E por isso o limiar precisa ser por posição:**

| Situação | Votos independentes | Limiar |
|---|---|---|
| Contêiner único (20' ou 40') | 3 câmeras | Limiar padrão |
| Duplo 20' — contêiner **de trás** | 3 câmeras | Limiar padrão |
| Duplo 20' — contêiner **da frente** | **2 câmeras** | **Limiar mais exigente** — a meta de ≤0,5% não se sustenta com o mesmo número |

⚙️ E a validação entrada×saída do §3.5 entra como sexta regra, fora do evento isolado.

### 6.5 ⚙️ Requisito mínimo de hardware e dimensionamento

O plano anterior escolhia a stack inteira sem dizer em que máquina ela roda. "Não sei o
modelo" é resposta aceitável do cliente; **"não especificamos" não é aceitável do projeto.**

Proposta, **a validar por medição na Fase 3**:

| | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 núcleos, geração ≥ Intel 8ª / Ryzen 2000 | 6–8 núcleos |
| RAM | 8 GB | 16 GB |
| Disco | SSD 256 GB | SSD 512 GB |
| Rede | 1 porta Gigabit **dedicada às câmeras** | + 1 porta para a rede corporativa |
| SO | Windows 10/11 x64 ou Server | — |
| Energia | **Nobreak** | Nobreak com desligamento gerenciado |

**Dimensionamento de disco:**

```
produção : ~10 MB/evento (recortes + 1 frame por câmera)  × 200 eventos/dia ≈ 2 GB/dia
coleta   : ~40 MB/evento (todos os snapshots em resolução plena) × 200/dia ≈ 8 GB/dia
```

Com retenção de 30 dias em produção: **~60 GB**. Os 10 dias de coleta da Fase 5: **~80 GB**.
Cabe num SSD de 256 GB, mas **só com a retenção ativa desde o dia 1**. O número existe aqui
para que ninguém compre um disco de 128 GB.

**Itens de instalação que costumam ser esquecidos:**

- **Antivírus corporativo:** pedir formalmente ao TI do cliente a exclusão da pasta do
  serviço. O PyInstaller dispara heurística
- **Nobreak** e desligamento gracioso — queda de energia com SQLite sem WAL é corrupção
- **Backup**: cópia diária do `.db` (e opcionalmente das imagens) para pasta de rede quando
  houver link. Definir, nem que a resposta seja "não há backup" — mas que seja por escrito

### 6.6 Interface de configuração sem GUI aberta

O serviço sobe **dois binds HTTP separados**, e a separação é o que torna o HTTP puro
defensável:

| | Bind | Alcance |
|---|---|---|
| **API de integração** | `<IP interno>:8477` | Rede interna, com allowlist de IPs e API key |
| **Tela de configuração** | `127.0.0.1:8478` | **Só a própria máquina.** Nunca exposta na rede |

O operador abre o navegador em `http://127.0.0.1:8478` no PC da balança. **Nenhuma janela
fica aberta; o serviço não depende de sessão de usuário logada.**

Páginas: câmeras · ROI (desenhar retângulo sobre o snapshot em `<canvas>`) · ⚙️ balança
(monitor do indicador ao vivo, para conferir o parser) · limiares por campo e por posição ·
webhook e retenção · diagnóstico.

---

## 7. API — contrato com o sistema principal

> ⚠️ **Congelar este contrato antes de implementar.** É a interface com um sistema de
> terceiros: gerar o OpenAPI, aprovar com o time do outro sistema, e só então codificar.
> Refazer contrato depois de integrado custa muito mais do que discuti-lo agora.

### 7.1 Transporte

**HTTP puro, sem TLS.** Decisão consciente, adequada ao cenário (rede interna, um cliente,
serviço offline). O que se ganha: nenhum certificado para emitir, instalar, renovar ou
depurar — e certificado autoassinado num serviço offline é fonte garantida de aviso de
navegador e de expiração silenciosa daqui a um ano. Toda resposta em JSON.

⚠️ **O que HTTP puro implica, e como compensar:**

| Consequência | Compensação obrigatória |
|---|---|
| A API key viaja em texto claro | Tratar como **credencial de rede interna, não como segredo forte**. Rotacionável pela tela de configuração. Nunca reutilizar senha de outro sistema |
| Qualquer host da rede alcança a API | **Bind explícito** ao IP da interface interna (nunca `0.0.0.0`) + **allowlist de IPs de origem** em middleware. Regra de firewall criada pelo instalador |
| A tela de configuração vai pelo mesmo canal | Servir a UI **apenas em `127.0.0.1`**, em porta separada (§6.6) |
| As imagens de evidência são acessíveis por URL | URLs com token opaco por evento, não sequenciais |
| ⚙️ **Qualquer host pode forjar um webhook nosso** | **Assinatura HMAC no webhook de saída.** Custa cinco linhas e é a compensação que faltava na tabela anterior |
| Webhook de saída também é HTTP | Se o sistema principal oferecer HTTPS no receptor, usar — nosso cliente suporta os dois sem mudança de código |

Registrar a decisão no `docs/DECISOES.md` com a justificativa, para que uma auditoria futura
encontre a escolha documentada em vez de parecer descuido. **Se o sistema um dia sair da
rede interna, TLS deixa de ser opcional** — deixar `scheme` configurável no `config.yaml`.

Autenticação por API key em header (`X-API-Key`).

### 7.2 O evento — ⚙️ modelo de dados revisado

O contrato anterior era singular (`container_code`). Não comporta duplo 20' nem múltiplos
campos com confiança independente.

```json
{
  "event_id": "01J8X...",
  "status": "needs_review",
  "trigger": "scale_stable",

  "weighing": {
    "ticket_id": "PES-2026-004512",
    "scale_id": "BAL-01",
    "direction": "in",
    "gross_weight_kg": 34120,
    "weighed_at": "2026-09-01T14:32:07-03:00",
    "plate": "ABC1D23"
  },

  "containers": [
    {
      "position": "front",
      "fields": {
        "code":      {"value": "MSCU4567821", "confidence": 0.96, "status": "auto_accept", "crop_url": "..."},
        "iso_type":  {"value": "22G1",        "confidence": 0.93, "status": "auto_accept", "crop_url": "..."},
        "max_gross": {"value": null,          "confidence": 0.00, "status": "unreadable",  "crop_url": "..."},
        "tare":      {"value": 2250,          "confidence": 0.71, "status": "needs_review","crop_url": "..."}
      },
      "cameras_used": ["left", "right"],
      "frames_used": 38
    },
    {
      "position": "rear",
      "fields": { "...": "..." },
      "cameras_used": ["left", "right", "rear"],
      "frames_used": 57
    }
  ],

  "images": {
    "left":  "/v1/events/01J8X.../images/left?t=<token>",
    "right": "/v1/events/01J8X.../images/right?t=<token>",
    "rear":  "/v1/events/01J8X.../images/rear?t=<token>"
  },

  "created_at": "2026-09-01T14:32:11-03:00"
}
```

**Pontos que mudaram e por quê:**

| Mudança | Motivo |
|---|---|
| `containers: []` em vez de `container_code` | Duplo 20' (§4.3) |
| **Confiança e status por campo** | O código pode estar ótimo e o `MAX GROSS` ilegível. `PATCH` corrige campo a campo |
| Bloco `weighing` com `ticket_id`, `direction`, `gross_weight_kg`, `plate` | O vínculo de negócio (§3) |
| `crop_url` **por campo** | Quem corrige precisa ver o recorte **ao lado do campo**. Se tiver que abrir outra tela, a correção fica lenta e o operador desiste — e operador desistindo envenena o `training_samples` |
| `cameras_used` / `frames_used` | Auditoria da confiança: 2 câmeras e 12 frames não valem o mesmo que 3 e 90 |

### 7.3 Estados

```
CAPTURING ─► PROCESSING ─┬─► AUTO_ACCEPT ──┐
                         ├─► NEEDS_REVIEW ─┼─► CORRECTED ─► SENT
                         └─► UNREADABLE ───┘
```

⚙️ **`UNREADABLE` é um estado novo e necessário.** Contêiner repintado, coberto, sujo ou
avariado a ponto de não ter código legível existe. Sem esse estado ele fica em
`NEEDS_REVIEW` para sempre, poluindo a fila.

### 7.4 Rotas

| Método | Rota | Uso |
|---|---|---|
| `POST` | `/v1/events` | Dispara uma leitura. Aceita `{"ticket_id":"...","direction":"in","plate":"...","gross_weight_kg":34120}`. Retorna `202` + `event_id`. ⚙️ **Exige header `Idempotency-Key`** |
| `GET` | `/v1/events` | Lista com filtros `status`, `from`, `to`, `ticket_id`, paginado. `status=needs_review` é a **fila de correção humana** |
| `GET` | `/v1/events/{id}` | Detalhe completo (payload do §7.2) |
| `GET` | `/v1/events/{id}/images/{camera}` | JPEG da evidência (`left`, `right`, `rear`) |
| `PATCH` | `/v1/events/{id}/containers/{position}/fields/{field}` | ⚙️ **Correção humana, campo a campo.** `{"value":"MSCU4567821","corrected_by":"joao"}`. Valida o check digit e recusa código inválido com `422` |
| `POST` | `/v1/events/{id}/confirm` | Confirma sem alterar (operador validou a leitura automática) |
| `POST` | `/v1/events/{id}/reprocess` | ⚙️ **Reprocessa as imagens guardadas com o modelo atual.** Depois do fine-tune permite medir o ganho sobre o histórico inteiro **sem recoletar nada.** Vale muito e custa pouco |
| `GET` | `/v1/cameras/status` | Estado de cada câmera: viva, último frame, latência |
| `GET` | `/v1/scale/status` | ⚙️ Estado do indicador: conectado, último peso, estabilidade |
| `GET` | `/health` | Liveness/readiness, incluindo espaço em disco |

⚙️ **Idempotência:** o sistema de pesagem vai reenviar em timeout. Sem chave de
idempotência, um retry cria um segundo evento para a mesma pesagem — e aí o operador vê
duas linhas na fila para o mesmo caminhão.

### 7.5 Webhook de saída (outbox)

Toda transição de estado gera um item numa tabela `outbox` e um worker entrega ao endpoint
configurado com retry exponencial. **Não é `POST` direto e otimista** — se o sistema
principal cair por 20 minutos, nada se perde. Item vencido vai para DLQ visível no
diagnóstico. ⚙️ Assinado com HMAC (§7.1).

### 7.6 ⭐ O motor de melhoria contínua

**Toda correção via `PATCH` grava o par (recorte, texto correto) numa tabela
`training_samples`.** É rotulagem de graça, vinda da operação, que alimenta o próximo
fine-tune. Guardar também `corrected_by`, `corrected_at` e o **valor anterior** — auditoria
e procedência do rótulo.

---

## 8. Modelo e dados

### 8.1 As três camadas de treino

| Camada | Volume | Papel |
|---|---|---|
| **1. Sintéticos** | 50–100 mil | Grátis, rótulo perfeito por construção. Ensina a forma dos 36 caracteres, fontes condensadas/stencil típicas de contêiner, e a degradação (desfoque, ruído, JPEG, perspectiva, ferrugem, repintura, IR monocromático) |
| **2. TRUDI** | ~3.100 reais | ✅ Liberado (§2.1). Recortes reais com transcrição. Ensina a textura do mundo real |
| **3. Dados próprios** | **~3.000** | O fine-tune que leva de ~80% para 90–97%. Sai da balança do cliente |

Camadas 1 e 2 produzem o **modelo v0**, que já viaja instalado com o sistema. A camada 3 é o
que fecha a conta.

### 8.2 A meta de ~3.000 recortes — e por que ela é barata

Com **3 câmeras lendo o mesmo código**, cada evento gera vários recortes rotulados com uma
única transcrição:

```
1.000 eventos  →  ~3.000 recortes rotulados  →  1 transcrição digitada por evento
```

**Redução de 3× no custo de anotação.** Com ~100 caminhões/dia, 10 dias de coleta atingem a
meta.

E fica melhor: **se o sistema principal registra o código digitado hoje pelo operador da
balança**, o casamento por `ticket_id` entrega as 1.000 transcrições prontas. A anotação cai
de ~13 h para ~2 h de conferência.

⚙️ **Ressalvas que o plano anterior não fazia:**

- **Duplo 20' dobra o número de recortes por evento, não de transcrições.** Bom para o
  dataset, mas exige que a transcrição venha identificada por posição
- **Cada campo obrigatório do §1.3 tem seu próprio custo de anotação.** A conta de 3.000
  vale para o código ISO. `MAX GROSS` e tipo/tamanho precisam de sua própria meta — não
  saem de graça junto
- ⚠️ **Diversidade vem de contêineres distintos, não de fotos.** 3.000 recortes de 1.000
  contêineres valem muito mais que 3.000 de 300. **Deduplicar por código antes de anotar**

### 8.3 Estratificação — por luz, não por horário

Casos difíceis **deliberadamente sobre-representados**: se apenas 5% dos eventos são
noturnos com chuva e você anotar 5%, o modelo vê exemplos de menos para aprender.

| Condição | Alvo |
|---|---|
| Dia, céu claro | 25% |
| Dia, nublado | 15% |
| Sol direto / contraluz | 15% |
| Noite com IR ou iluminação artificial | 25% |
| Chuva | 10% |
| Especiais (repintado, sujo, ocluído, **duplo 20'**) | 10% |

⚠️ **Incluir deliberadamente a transição dia↔noite.** A câmera troca o filtro IR-cut e a
imagem muda por completo por alguns segundos. É o pior caso e quase não aparece em
amostragem aleatória.

### 8.4 `siamac-recorder` — coletor autônomo

Roda no PC da balança durante a coleta, sem supervisão: por evento, N snapshots de cada
câmera + metadados (hora, condição de luz estimada, peso, `ticket_id`, resultado do v0).
Rotação por espaço em disco.

**Relatório diário consultável remotamente:** câmeras vivas, contagem de eventos, disco
livre, miniaturas. **Sem o relatório diário, uma câmera cai no dia 3 e você descobre no dia 14.**

### 8.5 Pipeline de treino

```
tools/synth.py         → 50–100k sintéticos       (TextRecognitionDataGenerator ou SynthTIGER)
tools/trudi_convert.py → TRUDI MMOCR JSON → TSV   (~3.100, filtrado)
PPOCRLabel             → anotação semiautomática dos dados próprios
PaddleOCR configs/rec  → treino (PP-OCRv5 rec como pesos iniciais, dicionário de 36 chars)
tools/export_onnx.py   → paddle2onnx + verificação de paridade numérica
                       → src/siamac/models/rec.onnx
```

**Filtros ao preparar o TRUDI** (o dataset mistura famílias):

- Manter apenas `[A-Z]{4}\d{7}` (código ISO) e `\d{2}[A-Z]\d` (size/type); descartar placas
  alemãs e fragmentos truncados
- Descartar recortes com altura < 16 px
- Dicionário **sem hífen** (o hífen só existe por causa das placas), mas **com `J`** —
  categoria válida do ISO 6346 que pode não aparecer no dataset
- Redimensionar para altura 32 (padrão PP-OCR, bate com a mediana do dataset sem upscale)

⚠️ **Há recortes com aspect ratio < 1 — texto vertical**, o código empilhado na porta. O
pré-processamento **não pode assumir texto horizontal**: detectar AR < 0,8 e rotacionar
antes do reconhecedor.

**Verificação de paridade após exportar ONNX (obrigatória):** rodar as mesmas 200 imagens no
Paddle e no ONNX e comparar as saídas. **Divergência silenciosa na conversão é o bug mais
caro deste projeto** — o modelo "funciona", só que 4% pior, e ninguém percebe.

---

## 9. Recursos externos

| Recurso | Licença | Papel | Link |
|---|---|---|---|
| ⭐ **RapidOCR** | Apache-2.0 | **Camada de inferência ONNX.** Aceita `det_model_path` / `rec_model_path` / `rec_keys_path` locais → 100% offline | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) |
| **PaddleOCR** | Apache-2.0 | **Só treino.** `configs/rec/` + `tools/train.py`. Não entra no produto | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| **PaddleOCRModelConvert** | Apache-2.0 | Conversão Paddle → ONNX pronta, do time do RapidOCR | [RapidAI/PaddleOCRModelConvert](https://github.com/RapidAI/PaddleOCRModelConvert) |
| ⭐ **TRUDI / TITUS** (BMVC 2025) | CC BY-SA 4.0 | ~3.100 recortes reais com transcrição. Baixar **só** `text_recognition` — as pastas `coco`/`yolo`/`labelme` são as mesmas imagens em outros formatos | [egulsoylu/trudi](https://github.com/egulsoylu/trudi) |
| **PPOCRLabel v3** | Apache-2.0 | Anotação semiautomática: pré-rotula com o próprio modelo, humano corrige | [PFCCLab/PPOCRLabel](https://github.com/PFCCLab/PPOCRLabel) |
| **MediaMTX** | MIT | ⭐ Serve vídeo local como RTSP falso. **É o que permite desenvolver e rodar CI sem as câmeras** | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) |
| **python-onvif-zeep-async** | MIT | ONVIF: descoberta, snapshot URI, hora, eventos PullPoint | [openvideolibs/python-onvif-zeep-async](https://github.com/openvideolibs/python-onvif-zeep-async) |
| **SynthTIGER** | MIT | Gerador de sintéticos, degradação mais realista que o TRDG | [clovaai/synthtiger](https://github.com/clovaai/synthtiger) |
| **TextRecognitionDataGenerator** | MIT | Alternativa mais simples; suficiente para 36 classes | [Belval/TextRecognitionDataGenerator](https://github.com/Belval/TextRecognitionDataGenerator) |
| **YOLOX** | Apache-2.0 | Detector, **se** o degrau 2 for acionado. Substituto livre do Ultralytics (AGPL) | [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) |
| Roboflow Universe — container | verificar caso a caso | 5+ datasets de detecção. Úteis para **medir baseline**; procedência de licença precisa ser conferida por dataset | [busca](https://universe.roboflow.com/search?q=class%3Acontainer+number) |
| `lbf4616/ContainerNumber-OCR` | ⚠️ **sem licença** | Referência de arquitetura (PixelLink + LSTM). **Sem licença = não usar código nem dados**; ler apenas | [lbf4616/ContainerNumber-OCR](https://github.com/lbf4616/ContainerNumber-OCR) |
| `lamnguyenkhoa/container-code-recognition` | verificar | YOLOv4 + OCR sobre vídeo. Referência de pipeline | [lamnguyenkhoa/container-code-recognition](https://github.com/lamnguyenkhoa/container-code-recognition) |
| ISO 6346 — validadores | vários | Vetores de teste para o `pytest`, incluindo o caso `check digit 10 → 0` | [datasets/ISO-Container-Codes](https://github.com/datasets/ISO-Container-Codes), [solyarisoftware/iso6346](https://github.com/solyarisoftware/iso6346) |
| Fontes OFL condensadas/stencil | OFL | 4–6 fontes para os sintéticos | Google Fonts |
| **WinSW** | MIT | Empacota o `.exe` como serviço Windows | [winsw/winsw](https://github.com/winsw/winsw) |
| **Datasheet VIP 5180 Pan FT** | — | Confirmação da óptica do §4.1 | [Intelbras](https://backend.intelbras.com/sites/default/files/2023-04/Novo%20Datasheet%20-%20VIP%205180%20Pan%20FT.pdf) |
| VC++ Redistributable | — | **Embarcar no instalador.** Falta num Windows limpo e derruba o serviço sem mensagem útil | — |

---

## 10. Fases de execução

Ordem de dependência, não calendário fixo. **As fases 0 e 2 travam tudo:** sem escopo
definido não há contrato, e sem câmera bem posicionada não há dado.

### ⚙️ Fase 0 — Definição de escopo *(bloqueante, não é código)*
- Preencher e **assinar a tabela de campos do §1.3**
- **Decidir o lacre** (§4.4): 3 ou 4 câmeras
- Responder as pendências bloqueantes do §14
- Fechar e aprovar o **contrato de API** (§7) com o time do sistema principal

### Fase 1 — Fundação
- Esqueleto do projeto, `pyproject.toml`, config validada por Pydantic (falha alto no boot)
- **`fields/iso6346.py` com 100% de cobertura** — check digit, size/type, correção
  posicional. É o módulo mais barato de acertar e o mais caro de errar
- SQLite (WAL) + Alembic + modelos, já com `Container` separado de `Event`
- MediaMTX no ambiente de dev servindo 3 vídeos como RTSP local

### Fase 2 — Óptica, obra e captura ⚠️ *bloqueante*
- **`tools/aim.py`** e alvo de calibração impresso
- Medir no local: distância disponível para cada câmera, **azimute da balança**, posição do
  código na lateral dos contêineres do cliente (fotografar 10 unidades)
- Decidir e comprar a 4K com a conta do §4.2 em mãos
- **Obra: postes a ~2,5 m, linha de parada, balizadores, aterramento e surto** (§4.7)
- Bancada: RTSP substream, `snapshot.cgi` **e a taxa sustentada em 30 s** (§3.3), ONVIF
- `cameras/` + `capture.py` com reconexão e watchdog

### ⚙️ Fase 3 — Integração com a balança
- `scale/` com o parser do indicador identificado, ou o gatilho por `POST /v1/events`
- Vínculo `ticket_id` ↔ evento, e a garantia de que a pesagem não bloqueia (§3.4)
- **Medir a latência real do pipeline no desktop do cliente** → valida ou corrige o §6.5

### Fase 4 — OCR v0 e medição de baseline
- `ocr/engine.py` sobre RapidOCR com PP-OCRv5 **pré-treinado** (ainda sem treino próprio)
- `roi.py`, `fusion.py` **com o agrupamento por contêiner desde já**
- **Medir a acurácia do v0 nas primeiras imagens reais.** Este número decide todo o resto do
  projeto — **não avance sem ele**

### Fase 5 — API e integração
- Rotas do §7, outbox com retry e HMAC, webhook
- Interface web de configuração
- Tabela `training_samples` alimentada pelo `PATCH`
- **Retenção ativa desde já** — não é refinamento posterior; sem ela o disco enche e o
  serviço para

### Fase 6 — Coleta ⭐
- `tools/recorder.py` + relatório diário
- ~10 dias → ~1.000 eventos → ~3.000 recortes
- **Verificação diária remota.** Não deixe para conferir no fim

### Fase 7 — Treino
- Sintéticos → TRUDI → fine-tune com dados próprios
- Export ONNX + **verificação de paridade**
- Avaliação num conjunto de validação local, **separado por contêiner** (não por imagem —
  senão vaza)
- ⚙️ `POST /reprocess` sobre o histórico para medir o ganho real

### Fase 8 — Empacotamento
- PyInstaller → `.exe`; WinSW → serviço; Inno Setup → instalador
- **Teste da rede desligada** (§11)
- ⚙️ `docs/RUNBOOK.md` e `docs/INSTALACAO.md` escritos

### Fase 9 — Piloto
- Rodar **em paralelo** com a digitação manual por 2 semanas
- Calibrar os limiares **por medição**, não por chute
- ⚙️ Treinar quem vai operar a revisão (§13)
- Só então liberar o modo automático

---

## 11. Verificação

**Testes automatizados**

- `pytest` sobre `fields/iso6346.py` com vetores conhecidos, incluindo `check digit 10 → 0`
  e todos os prefixos de proprietário do arquivo `ISO-Container-Codes`
- `fusion.py`: leituras discordantes → resultado e estado esperados (`AUTO_ACCEPT` vs
  `NEEDS_REVIEW`). ⚙️ **Incluir o caso duplo 20': duas séries de leituras no mesmo lado
  devem produzir dois contêineres, não um código embaralhado**
- ⚙️ Limiar por posição: o contêiner da frente com 2 câmeras não pode auto-aceitar com a
  mesma confiança que o de trás com 3
- API com `httpx`: fluxo completo — dispara evento → processa → `PATCH` de correção →
  webhook entregue → linha em `training_samples`
- ⚙️ **Idempotência**: dois `POST /v1/events` com a mesma chave produzem **um** evento
- Outbox com o destino derrubado: itens acumulam, destino volta, tudo é entregue na ordem
- **Escopo dos binds:** teste que confirma que `127.0.0.1:8478` **não responde** de outro
  host, e que a API em `:8477` recusa origem fora da allowlist com `403` — **antes** de
  checar a API key

**End-to-end sem hardware**
MediaMTX servindo 3 vídeos como RTSP local. Roda em CI, sem câmera nenhuma. É a diferença
entre desenvolver bloqueado e desenvolver.

**Paridade Paddle ↔ ONNX**
200 imagens, saídas comparadas caractere a caractere. Divergência > 0,5% reprova o export.

**⭐ Teste da rede desligada (inegociável)**
Instalar em Windows limpo **com a placa de rede desabilitada**, reiniciar a máquina,
processar um evento ponta a ponta com câmeras numa rede isolada. Confirmar com `netstat -b`
que nada tenta sair. Verificar com `pyi-archive_viewer` que **`paddle` e `paddleocr` não
entraram no executável** — ler o código não basta, um import indireto entra sem aviso e só
falha no cliente.

**Antes de ir a campo**
`recorder` gravando 24 h com corte de energia e de rede no meio · `aim` aferido contra
trena · relatório diário acessado de fora da rede · o `.exe` rodando em Windows limpo sem
Python instalado · ⚙️ **corte de energia com o banco em escrita, confirmando que o SQLite
sobrevive**

**Em produção**
Soak de 72 h · piloto em paralelo com a digitação manual · reboot confirmando que o serviço
sobe sozinho, sem login

---

## 12. Riscos

| Risco | Mitigação |
|---|---|
| 🔴 **Câmera montada longe demais** — modo de falha nº 1 | Volume de dados não corrige óptica. `aim` + alvo impresso **antes de furar**. ⚙️ E a montagem a 2,5 m, não a 3,5 m (§4.1) |
| 🔴 ⚙️ **Escopo de "todas as informações" nunca fechado** | A tabela do §1.3 assinada na Fase 0. Sem isso o projeto não tem critério de pronto |
| 🔴 **Voltar da coleta com dado inutilizável** | Relatório diário remoto · rodar o v0 sobre as imagens do dia 1 e revisar antes de deixar rodando |
| 🟠 **Erro silencioso** — pior que não ler | `mod 11` deixa passar ~1 em 11 erros. Por isso a **concordância entre câmeras** entra no critério, não só o check digit. ⚙️ Mais a validação entrada×saída (§3.5). **KPI crítico: ≤0,5%** |
| 🟠 ⚙️ **Duplo 20' tratado como caso raro** | Modelo de dados plural desde a Fase 1, limiar por posição, e a montagem do §4.1 |
| 🟠 ⚙️ **Snapshot não sustenta a taxa na janela de 20–60 s** | Teste de bancada na semana 1. Plano B: RTSP main só na janela do evento |
| 🟠 **Divergência silenciosa na conversão ONNX** | Verificação de paridade obrigatória no CI de export |
| 🟠 **Desempenho noturno da 4K** | Exigir Starlight, sensor ≥1/1.8", ≤0,005 lux **antes de comprar** |
| 🟠 ⚙️ **IR saturando a imagem a 2,5 m** | Smart IR com potência reduzida ou iluminação branca externa (§4.5) |
| 🟡 ⚙️ **Desktop do cliente abaixo do necessário** | Requisito mínimo escrito (§6.5) e medição de latência na Fase 3 |
| 🟡 **Serviço `LocalSystem` não enxerga cache de usuário** | Resolvido por design: ONNX com caminho absoluto, nada baixado em runtime |
| 🟡 **Disco enche e o serviço para** | Retenção obrigatória desde a Fase 5, com alarme em `/health` |
| 🟡 ⚙️ **Queda de energia corrompe o SQLite** | WAL + `synchronous=FULL` + nobreak |
| 🟡 **API em HTTP puro numa rede que deixe de ser confiável** | Bind por IP + allowlist + UI só em loopback + ⚙️ HMAC no webhook. Decisão documentada e `scheme` configurável |

---

## 13. Operação e conformidade

⚙️ **Seção nova.** Nada disto estava no plano anterior, e cada item já travou entrega de
projeto parecido.

| Item | O que precisa existir |
|---|---|
| **Relógio do PC** | O plano sincroniza a hora **das câmeras** por ONVIF, mas não a do PC. Sem NTP o PC deriva, e casar leitura com pesagem por timestamp quebra. **Solução dupla:** usar `ticket_id` como chave de vínculo (não o timestamp) **e** rodar um servidor NTP local no próprio PC para as câmeras |
| **LGPD** | As imagens capturam motorista e placas. Precisa de: finalidade declarada, prazo de retenção, controle de acesso e registro escrito da decisão. Não é burocracia — é o que trava a entrega no jurídico do cliente |
| **Suporte sem link de rede** | `tools/diag_bundle.py`: gera um `.zip` com logs, últimos N eventos e config, que o operador copia num pendrive. Desenho offline-first de verdade |
| **Runbook** (`docs/RUNBOOK.md`) | Uma página: o que fazer quando a câmera cai, o disco enche, o sistema principal não responde, a leitura fica sistematicamente errada, o indicador para de responder |
| **Checklist de instalação** (`docs/INSTALACAO.md`) | Exclusão no antivírus, regra de firewall, IPs fixos das câmeras, nobreak, aterramento, teste de aceitação com o `aim` |
| **Treinamento do operador** | Meia hora ensinando a ler a confiança e conferir o recorte. **Correção displicente envenena o `training_samples`**, que é o motor de melhoria contínua do §7.6 |
| **Backup** | Cópia diária do `.db` para pasta de rede quando houver link. Definir por escrito, ainda que a resposta seja "não há" |
| **Rotina de limpeza das lentes** | Periodicidade definida no runbook. É manutenção preventiva, não conserto |

---

## 14. Pendências que travam o início

**Bloqueantes — não dá para começar sem resposta:**

1. ⭐ **Quais campos do §1.3 são obrigatórios?** Sem isso o escopo é indefinido e qualquer
   estimativa é ficção.
2. ⭐ **O lacre é obrigatório?** Decide se o projeto tem 3 ou 4 câmeras, e é o item mais caro
   e mais arriscado da lista.
3. ⭐ **O sistema principal exporta o log dos códigos digitados hoje?** Decide se a anotação
   custa 2 h ou 13 h (§8.2). **A pergunta de maior retorno financeiro.**
4. **Qual o indicador de peso, e já existe software de pesagem?** Decide se existe o módulo
   `scale/` (§3.2).
5. **Qual a distância disponível para cada câmera na área da balança?** Decide o modelo da
   4K e se as VIP 5180 PAN conseguem ler (§4).
6. **Duplo 20' acontece com que frequência?** Se >10% dos eventos, a montagem a 2,5 m é
   obrigatória e o limiar por posição também (§4.1, §6.4).

**Importantes — travam a Fase 2:**

7. **Onde fica o código na lateral dos contêineres típicos do cliente?** Fotografar 10
   unidades resolve.
8. **As portas ficam sempre voltadas para trás?** Se variar, a traseira às vezes vê a frente
   do contêiner, que não tem o código no mesmo lugar.
9. **Qual o azimute da balança?** Decide o risco de sol direto na lente (§4.5).
10. **É possível pintar linha de parada e instalar sinaleira?** Contramedida mais barata do
    projeto (§4.7).
11. **A balança opera 24 h?** Define o peso do caso noturno no dataset e na escolha do sensor.
12. **Qual a especificação do desktop?** Se for máquina fraca, o degrau 2 fica caro e a
    arquitetura muda (§6.5).
13. **Qual o volume diário de pesagens?** Dimensiona disco, retenção e prazo de coleta.

**Comerciais e de conformidade:**

14. **O sistema de pesagem já registra a placa do caminhão?** Se sim, não precisamos de ALPR.
15. **Contêiner reefer entra na balança, e o set point é exigido?** Se sim, falta câmera.
16. **Existe link de rede no local para manutenção remota?** "Offline" é o software; suporte
    remoto precisa de link — e se não houver, o `diag_bundle` vira obrigatório (§13).

**Verificações técnicas na primeira semana:**

- O `snapshot.cgi` entrega resolução plena? **Qual a taxa sustentada em 30 s** antes de a
  câmera degradar ou travar?
- Distância em cabo até o PC — **PoE tem limite de 100 m**
- Energia, aterramento, autorização para furar, escada/plataforma, EPI

---

## 15. Como usar este documento com o Codex

1. **Não mande este documento inteiro como prompt.** É contexto demais para uma tarefa só e
   o modelo dilui. Deixe-o **commitado no repositório** e escreva prompts do tamanho de uma
   fase, referenciando as seções (*"veja `PLANO-V2.md` §6.4"*).
2. **Uma fase por prompt, na ordem do §10.** Comece pela Fase 1 (`fields/iso6346.py` com
   100% de cobertura): escopo fechado, verificável por teste, e é o módulo mais caro de errar.
   A Fase 0 não é código — é conversa com o cliente.
3. **Peça os testes antes da implementação** nos módulos de núcleo (`iso6346`, `fusion`,
   `storage`). Os vetores de teste do §9 dão a referência.
4. **Congele o contrato da API antes de implementar** (§7). É a interface com um sistema de
   terceiros.
5. **Dê a escada de complexidade (§2.2) como regra dura**, com esta frase literal: *"não suba
   de degrau sem uma medição que justifique"*. Sem isso o modelo entrega um detector YOLO na
   primeira iteração.
6. **Liste as proibições explicitamente** — são contraintuitivas e o modelo vai violar todas
   por padrão:
   - nada de chamada de rede em tempo de execução, nada de download de modelo
   - `opencv-python-headless`, nunca o pacote completo
   - `PyAV`, nunca `cv2.VideoCapture` (trava sem timeout)
   - PyInstaller `onedir`, nunca `onefile`
   - `paddle`/`paddleocr` não podem entrar no executável de produção
   - `container_code` singular não existe — o modelo de dados é plural desde o dia 1
7. **Peça um `docs/DECISOES.md`** onde cada decisão não óbvia é registrada com a
   justificativa. É o que evita que a próxima sessão reverta uma escolha deliberada.

---

## Resumo

1. ⚙️ **O escopo ainda não está fechado.** "Todas as informações" são ~12 campos com
   viabilidades muito diferentes. A tabela do §1.3 assinada é a Fase 0.
2. ⚙️ **O lacre não é legível com 3 câmeras.** 5 mm de caractere dão 2,5 px na traseira.
   Ou é uma 4ª câmera PTZ, ou continua digitado. Decidir antes de comprar qualquer coisa.
3. ⚙️ **As laterais vão a ~2,5 m, não a 3,5 m.** É o duplo 20' que decide: os dois códigos
   ficam a ~6 m, e só a 2,5 m mirando o ponto médio ambos chegam a 30 px/caractere.
4. ⚙️ **A balança é o melhor gatilho do projeto** e dá uma janela de 20–60 s — 15 a 30
   snapshots por câmera em vez de 3 a 5. A fusão fica muito mais forte, se o `snapshot.cgi`
   sustentar a taxa.
5. **A fusão multi-câmera continua sendo a alavanca.** Mesmo código, vários ângulos, dezenas
   de frames, votação por caractere + check digit. Vale mais que qualquer refinamento de modelo.
6. ⚙️ **Duplo 20' é plural em tudo:** modelo de dados, API, agrupamento na fusão, e limiar de
   auto-aceite diferente para o contêiner da frente, que só tem 2 votos.
7. **Snapshot HTTP para OCR, substream RTSP para saúde, ONVIF para controle, indicador de
   peso para gatilho.** Quatro canais com papéis diferentes.
8. **RapidOCR evita escrever a camada mais arriscada do sistema.** **TRUDI está liberado**
   pela decisão de uso interno e vale ~3.100 amostras reais.
9. ⚙️ **A validação entrada×saída é de graça** e ataca diretamente o erro silencioso, que o
   `mod 11` sozinho não elimina.
10. ⚙️ **Sobraram 16 perguntas em aberto** (§14), e as seis primeiras são bloqueantes de verdade.
