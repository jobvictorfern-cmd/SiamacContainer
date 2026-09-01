# Lacunas do PLANO.md — revisão após as informações novas

Documento complementar ao `PLANO.md`. Não substitui nada: aponta o que as informações
novas do cliente mudam e o que o plano ainda não cobre.

**Informações novas que disparam esta revisão:**

| Nova informação | O que ela quebra ou muda |
|---|---|
| As câmeras ficam **na área da balança**, não na portaria | Gatilho, geometria de montagem, integração com o indicador de peso |
| As imagens são coletadas **durante a pesagem** | Janela de captura passa de ~4 s para 20–60 s — é uma vantagem grande e não explorada |
| **"Ler todas as informações do contêiner"** | O plano inteiro foi desenhado para **um** campo (o código ISO 6346). São ~12 campos |
| Desktop **Windows de modelo desconhecido** | O plano não declara requisito mínimo de hardware em lugar nenhum |
| **Horários e clima variam** | Coberto no dataset (§6.3), **não** coberto na engenharia física (sol, IR, sujeira, surto) |

---

## Lacuna 1 — "Todas as informações" não está definido, e o plano lê 1 de 12 campos

Esta é a maior lacuna. `fusion.py`, a ROI, o dicionário de 36 caracteres, o dataset, o
contrato de API e a tela de revisão foram todos desenhados para uma string de 11
caracteres. "Todas as informações" é um requisito de escopo diferente.

**Antes de escrever qualquer código, esta tabela precisa ser preenchida e aprovada pelo cliente** —
com uma coluna a mais: *"é obrigatório ou é desejável?"*.

| Campo | Onde fica | Qual câmera vê | Viabilidade com o arranjo atual |
|---|---|---|---|
| **Código ISO 6346** (11 car., 100 mm) | Laterais, porta, frente, teto | Todas as 3 | ✅ Alta — é o que o plano já resolve |
| **Código tamanho/tipo** (4 car., ex. `45G1`, `22G1`) | Ao lado/abaixo do código | Todas as 3 | ✅ Alta — e a tabela ISO de combinações válidas é um **segundo validador forte**, tão bom quanto o check digit |
| **MAX GROSS / TARE / NET / CUBE** (kg e lb) | Porta, às vezes lateral | Traseira | 🟡 Média — texto menor e multilinha, mas formato rígido (`MAX GROSS 30.480 KG 67.200 LB`) permite regex + coerência cruzada com o tipo ISO |
| **Placas de risco IMO / número ONU** | Laterais e porta | Todas as 3 | 🟡 Média — o número ONU no painel laranja tem ~65–100 mm, é legível. A classe é **classificação de imagem**, não OCR |
| **Porta aberta/fechada, avaria, amassado, furo** | Porta e laterais | Todas as 3 | 🟡 Média — é um modelo de classificação/segmentação **separado**, fase posterior. No dia 1: só guardar a evidência |
| **Logo do armador/operador** | Laterais | Laterais | 🟡 Média — classificação, e em geral **derivável do prefixo do código**, o que a torna quase desnecessária |
| **Número do lacre** | Barra de travamento da porta direita | Traseira | ❌ **Inviável — ver o cálculo abaixo** |
| **Placa CSC / ACEP** (validade, fabricação) | Porta | Traseira | ❌ Inviável pelo mesmo motivo (caracteres de 5–10 mm) |
| **Reefer: set point, temperatura, horímetro** | Display na **frente** do contêiner | ❌ Nenhuma | ❌ Nenhuma câmera cobre a frente. Se for necessário, é uma 4ª câmera |
| **Placa do cavalo e do semirreboque** | Veículo | Traseira / laterais | 🟡 Média — é **outro modelo** (ALPR Mercosul + padrão antigo). Não está no plano. Primeiro pergunte: o sistema de pesagem já tem a placa? |
| **Vazio / carregado** | — | — | 🟡 Derivável do peso da balança (bruto − tara ≈ 0), sem visão nenhuma |
| **Peso** | — | Balança | ✅ Vem do indicador, não da visão |

### ⚠️ O lacre não é legível com este arranjo — o número

Caracteres de lacre têm **~5 mm**, não 100 mm. Com a 4K traseira a 5 m entregando
50 px num caractere de 100 mm (§4.2 do plano), o mesmo pixel sobre 5 mm dá **2,5 px**.
Nenhum OCR, nenhuma super-resolução, nenhum volume de dataset resolve isso.

Para chegar a 25 px/caractere num caractere de 5 mm com um sensor de 2160 px na vertical,
a câmera precisa **enquadrar uma faixa vertical de apenas ~43 cm**:

```
campo vertical necessário = 0,005 m × 2160 px ÷ 25 px = 0,43 m
```

A 3 m de distância isso é um AFOV vertical de ~8°, ou seja, **lente de 25–35 mm**. E como
a posição longitudinal em que o caminhão para na balança varia mais de 43 cm, uma câmera
fixa com esse enquadramento erra o alvo quase sempre.

**Conclusão:** ou o lacre é uma **4ª câmera PTZ com preset e zoom óptico real** (custo e
complexidade adicionais), ou **o lacre continua sendo digitado**. Recomendação: mantenha
manual — o lacre normalmente já consta no documento de transporte. Mas **decida isso agora**,
porque é a diferença entre 3 e 4 câmeras.

---

## Lacuna 2 — A balança é um subsistema inteiro, e o plano não a menciona

O `PLANO.md` §3 lista três gatilhos possíveis e nenhum deles é a balança. Na prática o
**melhor gatilho do projeto passa a ser o indicador de peso**: "peso estável acima de X kg
por N segundos" é um sinal limpo, sem falso positivo e sem visão computacional nenhuma.

**O que precisa ser especificado e não está:**

1. **Qual indicador está instalado?** (Toledo, Alfa, Filizola, Balmak, Coester, Micheletti,
   Ramuza…). A maioria emite um quadro ASCII contínuo por RS‑232 com um bit de estabilidade;
   alguns têm Ethernet/TCP. **Ler o manual do indicador que está no local** — não presumir.
2. **Já existe software de pesagem rodando?** Se existe, o caminho mais barato é ele chamar
   `POST /v1/events` e passar o `ticket_id`. Se não, é preciso ler a serial direto e o
   projeto ganha um módulo `scale/`.
3. **O evento de leitura precisa carregar o vínculo com a pesagem.** Sem `ticket_id`, casar
   leitura e pesagem por timestamp é frágil — e num PC offline o relógio deriva (ver Lacuna 8).
4. **A pesagem nunca pode ficar bloqueada esperando o OCR.** Defina explicitamente: a leitura
   é assíncrona e se anexa ao ticket depois. Caminhão parado na balança é fila na guarita.
5. **Entrada e saída são duas pesagens do mesmo caminhão.** Isso é uma **validação de graça**:
   se o código lido na entrada e na saída não bater, alguma das duas leituras está errada —
   sinalize para revisão mesmo que ambas tenham passado no check digit.

### A vantagem que o plano ainda não explora

O plano dimensiona "3–5 snapshots em 4 s". Na balança o caminhão fica parado **20 a 60 s**.
Isso permite **15–30 snapshots por câmera**, e a fusão por votação (§5.1, a alavanca do
projeto) fica muito mais forte: em vez de 3 leituras, você vota entre 45 a 90.

⚠️ Mas isso choca com o limite de taxa do `snapshot.cgi` (~1 fps) já sinalizado no §3.
**Teste de bancada obrigatório:** quantos snapshots consecutivos a câmera entrega em 30 s
antes de degradar ou travar. Se o limite atrapalhar, o plano B do §3 (decodificar o RTSP
main só na janela do evento) deixa de ser plano B e vira a escolha certa — 30 s de decode
de um stream 4K por evento é perfeitamente pagável.

---

## Lacuna 3 — Dois contêineres de 20' quebram o modelo de dados **e** a óptica

O plano cita "duplo 20'" uma única vez, na tabela de estratificação do dataset (§6.3), como
se fosse um caso raro de treino. Não é: numa balança de carga é rotina, e ele quebra duas
coisas ao mesmo tempo.

### Quebra o modelo de dados

Todo o contrato do §5.2 é singular: `{"container_code": "MSCU4567821"}`. Precisa virar
uma lista, com posição:

```json
{
  "event_id": "...",
  "containers": [
    {"position": "front", "code": "MSCU4567821", "iso_type": "22G1", "confidence": 0.96, "status": "auto_accept"},
    {"position": "rear",  "code": "TGHU7654321", "iso_type": "22G1", "confidence": 0.71, "status": "needs_review"}
  ]
}
```

E `fusion.py` precisa de uma etapa nova antes da votação: **agrupar as leituras por
contêiner**. Hoje ele assume que toda leitura é do mesmo código.

⚠️ **O contêiner da frente só tem 2 votos, não 3** — a câmera traseira vê apenas as portas
do contêiner de trás. O limiar de auto-aceite tem que ser **diferente por posição**. Isso
não é detalhe: é o §5.1 inteiro dizendo que a concordância entre 3 câmeras é o que segura
o erro silencioso em ≤0,5%. Com 2 câmeras, esse número não se sustenta no mesmo limiar.

### Quebra a óptica — e aqui está a conta que decide a montagem

Usando a própria fórmula do plano (§4.1), `px/caractere ≈ 119 ÷ d`, com `d = √(L² + x²)`:

| `L` (distância lateral) | `x` máximo para 30 px | Janela longitudinal útil |
|---|---|---|
| 3,5 m | 1,87 m | ±1,9 m |
| **3,0 m** | **2,60 m** | ±2,6 m |
| 2,5 m | 3,08 m | ±3,1 m |
| 2,0 m | 3,43 m | ±3,4 m |

Dois contêineres de 20' colocam os dois códigos a **~6 m um do outro**. Nenhuma janela
acima comporta os dois. Mirando o **ponto médio** entre eles (cada código a x = ±3,05 m):

| `L` | px/caractere em **cada** código |
|---|---|
| 3,5 m | 26 ⚠️ |
| 3,0 m | 28 ⚠️ |
| **2,5 m** | **30 ✓ — no limite** |
| 2,0 m | 33 ✓ |

> **Conclusão de montagem, e ela contraria o §4.1 do plano:** as laterais devem ser montadas
> **a ~2,5 m** da lateral do contêiner, não nos "≤3,5 m" que o plano admite. A 3,5 m o caso
> duplo 20' não fecha. E a mira longitudinal é o **ponto médio entre as duas posições de
> código possíveis**, não o código de um 40'.

Verificação de enquadramento vertical a 2,5 m: com 78° V, a câmera cobre 4,05 m de altura —
sobra para um high cube sobre chassi (topo a ~4,4 m) com a câmera a ~2,9 m do solo. A 2,0 m
cobre 3,24 m e fica apertado. **2,5 m é o ponto ótimo.**

⚠️ Um poste a 2,5 m da lateral do contêiner fica a ~2,2 m da borda da plataforma. Precisa
de proteção física (balizador/defensa) contra manobra.

### A contramedida barata que o plano não cita

Numa balança a posição de parada já é mais repetível que numa portaria (todos os eixos
precisam estar na plataforma). **Reforçar isso com linha de parada pintada + semáforo ou
sinaleira** reduz a variação longitudinal para ±1 m e resolve o problema de graça — muito
mais barato que trocar câmera. **Inclua isso no escopo de obra civil.**

---

## Lacuna 4 — O ambiente físico externo não está no plano

O §6.3 trata clima como **variedade de dataset**. Mas clima na balança é primeiro um
problema de **engenharia física**, e nenhum volume de imagens corrige uma lente suja.

| Problema | Contramedida — precisa entrar no escopo |
|---|---|
| **Sol direto na lente** no nascer/pôr | Descobrir o **azimute da balança**. Se as laterais ficam voltadas leste/oeste, haverá minutos diários de imagem inutilizável. Viseira longa + inclinação da câmera + WDR configurado |
| ⚠️ **IR estourando de perto** | A 2,5 m, um IR dimensionado para 30 m **satura a imagem em branco**. Contraintuitivo e comum. Ou Smart IR com potência reduzida, ou **iluminação branca externa** (melhor: dá imagem colorida, ajuda placas de risco e o lacre, e ainda inibe) |
| **Respingo e sujeira de pneu** | Altura e ângulo de montagem que protejam a lente; revestimento hidrofóbico; **rotina de limpeza no checklist de manutenção** com periodicidade definida |
| **Teias e insetos no housing IR** | Causa clássica de falso movimento e borrão em câmera externa. Entra na rotina de limpeza |
| **Condensação** | Housing IP67 com sílica; verificar se o modelo tem aquecedor |
| **Surto atmosférico** | Câmera externa em poste na área de balança é alvo clássico de raio. **Protetor de surto no PoE + aterramento** — sem isso você perde câmera e switch juntos |
| **Exposição e shutter** | A configuração da câmera (WDR/BLC, shutter mínimo/máximo, ganho) **faz parte do produto**, não é ajuste de instalador. Deve estar versionada e ser aplicável via CGI Dahua, para poder ser restaurada após troca de equipamento |

---

## Lacuna 5 — O desktop Windows não tem requisito mínimo declarado

O plano escolhe a stack inteira sem dizer em que máquina ela roda. "Não sei o modelo" é
resposta aceitável do cliente; **"não especificamos" não é aceitável do projeto**.

Proposta a validar por medição na Fase 2:

| | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 núcleos, geração ≥ Intel 8ª / Ryzen 2000 | 6–8 núcleos |
| RAM | 8 GB | 16 GB |
| Disco | SSD 256 GB | SSD 512 GB |
| Rede | 1 porta Gigabit dedicada às câmeras | + 1 porta para a rede corporativa |
| SO | Windows 10/11 x64 (ou Server) | — |
| Energia | **Nobreak** | Nobreak com desligamento gerenciado |

**Dimensionamento de disco que o plano não faz:**

```
produção : ~10 MB/evento (recortes + 1 frame por câmera) × 200 eventos/dia ≈  2 GB/dia
coleta   : ~40 MB/evento (todos os snapshots em 8 MP)   × 200 eventos/dia ≈  8 GB/dia
```

Com retenção de 30 dias em produção: ~60 GB. Os 10 dias de coleta da Fase 4: ~80 GB.
Cabe num SSD de 256 GB, mas **só se a retenção estiver ativa desde o dia 1**, como o plano
já exige. Coloque o número no documento para que ninguém compre um disco de 128 GB.

**Outros itens de instalação ausentes:**
- **Antivírus corporativo**: pedir exclusão da pasta do serviço. O plano já prevê a heurística
  do PyInstaller, mas não prevê o pedido formal ao TI do cliente.
- **SQLite com WAL + `synchronous=FULL`**: queda de energia numa balança é rotina. Sem isso,
  corrupção de banco é questão de tempo.
- **Backup**: nada no plano fala em backup do `.db` nem das imagens. Defina — nem que seja
  cópia diária para uma pasta de rede quando o link estiver disponível.

---

## Lacuna 6 — O contrato de API não comporta o cenário novo

Ajustes necessários no §5.2:

| Ajuste | Por quê |
|---|---|
| `containers: []` em vez de `container_code` | Lacuna 3 |
| **Confiança e status por campo**, não só por evento | O código pode estar ótimo e o `MAX GROSS` ilegível. `PATCH` tem que corrigir campo a campo |
| Campos novos no evento: `ticket_id`, `scale_id`, `direction` (`in`/`out`), `gross_weight`, `plate`, `weighed_at` | Lacuna 2 |
| **Chave de idempotência** no `POST /v1/events` | O sistema de pesagem vai reenviar em timeout. Sem isso, evento duplicado por retry |
| **Assinatura HMAC no webhook de saída** | O plano assume HTTP puro conscientemente (§5.2). HMAC custa 5 linhas e impede que qualquer host da rede forje um evento de contêiner. É a compensação que falta na tabela |
| `POST /v1/events/{id}/reprocess` | Reprocessar imagens guardadas com um modelo novo. Depois do fine-tune, permite medir o ganho sobre o histórico inteiro **sem recoletar nada**. Vale muito e custa pouco |
| Estado `UNREADABLE` explícito | Contêiner sem código legível (repintado, coberto, avariado) existe. Hoje ele cairia em `NEEDS_REVIEW` para sempre |
| Miniatura/recorte **embutido na resposta** de `GET /v1/events/{id}` | Quem corrige precisa ver o recorte ao lado do campo. Se tiver que abrir outra URL, a correção fica lenta e o operador desiste |
| `corrected_by` + `corrected_at` + valor anterior | Auditoria. E é o que alimenta `training_samples` com procedência |

---

## Lacuna 7 — Operação, conformidade e relógio

| Item | Situação |
|---|---|
| **Relógio do PC offline** | O plano sincroniza a hora **das câmeras** por ONVIF, mas não a do PC. Sem NTP, o PC deriva e o casamento por timestamp com a pesagem quebra. Solução: usar `ticket_id` como chave primária de vínculo **e** rodar um servidor NTP local no próprio PC para as câmeras |
| **LGPD** | Ausente do plano. As imagens capturam motorista e placas. Precisa de: finalidade declarada, prazo de retenção, controle de acesso, e registro da decisão. Não é burocracia — é o tipo de coisa que trava a entrega no jurídico do cliente |
| **Suporte sem link de rede** | A pergunta 5 do §9 está certa, mas falta o plano B: um comando que gere um **pacote de diagnóstico** (logs + últimos N eventos + config, em `.zip`) que o operador copia num pendrive. Desenho offline-first de verdade |
| **Runbook do operador** | Nada no plano. O que fazer quando: câmera caiu, disco encheu, o sistema principal não responde, a leitura está sistematicamente errada. Uma página, entregue junto |
| **Treinamento** | Quem opera a revisão precisa saber ler a confiança e o recorte. Meia hora de treino evita meses de correção displicente — e correção displicente **envenena o `training_samples`**, que é o motor de melhoria contínua do §5.2 |

---

## Perguntas novas que travam o início

Somam-se às 6 do `PLANO.md` §9.

1. ⭐ **Quais campos são obrigatórios de verdade?** (tabela da Lacuna 1). Sem isso, o escopo
   é indefinido e o Codex vai gerar o que imaginar.
2. ⭐ **O lacre é obrigatório?** Se sim, o projeto tem 4 câmeras e um PTZ. Se não, economiza-se
   o item mais caro e mais arriscado.
3. **Qual o indicador de peso e ele já tem software?** Decide se existe o módulo `scale/`.
4. **Duplo 20' acontece com que frequência?** Se for >10% dos eventos, a Lacuna 3 é bloqueante
   e a montagem a 2,5 m é obrigatória.
5. **Qual o azimute da balança?** Decide o risco de sol direto.
6. **Existe linha de parada / semáforo, ou é possível instalar?** Contramedida mais barata do
   projeto.
7. **O sistema de pesagem já registra a placa do caminhão?** Se sim, não precisamos de ALPR.
8. **Contêiner reefer entra na balança?** Se sim e o set point for exigido, falta câmera.
9. **Qual a especificação do desktop?** Se for uma máquina fraca, o degrau 2 (detector) fica
   caro e isso muda a arquitetura.
10. **Qual o volume diário de pesagens?** Dimensiona disco, retenção e o prazo da coleta.

---

## Sobre o prompt para o Codex

Observações sobre o formato, já que é esse o objetivo:

1. **Não mande o `PLANO.md` inteiro como prompt.** 568 linhas + este documento é contexto
   demais para uma tarefa só; o modelo dilui. Deixe os dois **commitados no repositório** e
   escreva prompts do tamanho de uma fase, referenciando as seções (`veja PLANO.md §5.1`).
2. **Uma fase por prompt, na ordem do §8.** A Fase 0 (`iso6346.py` com 100% de cobertura) é
   a ideal para começar: escopo fechado, verificável por teste, e é o módulo mais caro de errar.
3. **Peça os testes antes da implementação** nos módulos de núcleo (`iso6346`, `fusion`,
   `storage`). Os vetores de teste do §7 dão a referência.
4. **Congele o contrato da API antes de implementar.** É a interface com um sistema de
   terceiros — gere o OpenAPI, aprove com o time do outro sistema, e só então implemente.
   Refazer contrato depois de integrado custa muito mais.
5. **Dê a "escada de complexidade" (§2) como regra dura**, com esta frase literal: *"não suba
   de degrau sem uma medição que justifique"*. Sem isso o modelo entrega um detector YOLO
   na primeira iteração.
6. **Liste as proibições explicitamente**, porque são contraintuitivas e o modelo vai violar
   todas por padrão:
   - nada de chamada de rede em tempo de execução, nada de download de modelo
   - `opencv-python-headless`, nunca o pacote completo
   - `PyAV`, nunca `cv2.VideoCapture` (trava sem timeout)
   - PyInstaller `onedir`, nunca `onefile`
   - `paddle`/`paddleocr` não podem entrar no executável de produção
7. **Peça um `docs/DECISOES.md`** onde cada decisão não óbvia é registrada com a justificativa.
   É o que evita que a próxima sessão reverta uma escolha deliberada.
