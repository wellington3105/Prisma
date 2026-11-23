# Prisma — Aproveitamento do Hypit

Objetivo. Acelerar a adaptação de referências audiovisuais para cenas editáveis. O primeiro incremento dispara a entrada de **titulo-misto** por uma frase do transcrito do próprio clipe.

## Aceite

- O catálogo encaminha os parâmetros ao host de cenas. A transcrição usa o relógio do mesmo arquivo informado como vídeo.
- A cena converte o início da ocorrência em tempo local, subtraindo o início do trecho. A animação, o corte e o áudio seguem a configuração do modelo.
- O início numérico continua disponível. Frase ausente, fora do trecho ou repetida sem escolha explícita gera erro antes da montagem.
- Verificar o deslocamento, a escolha de ocorrência e os parâmetros existentes por testes e render local.

## Análise e decisões

| Técnica no Hypit | Prisma hoje | Decisão |
|---|---|---|
| [Instantes e intervalos derivados da fala](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/references/production/timing.md) | Remotion já tem whenSaid. Os modelos HyperFrames usam segundos de cena. | Entregar um instante de entrada no título misto. Expandir para intervalos de B-roll e sobreposições após testar o primeiro modelo. |
| [Quadros com transcrição e leitura por passagem](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/references/creation/reference-video.md) | O estudo dos 13 Reels tem quadros e medições. A explicação editorial está agrupada por formato. | Usar a ficha abaixo para aprofundar passagens, reaproveitando quadros e transcrição quando tiverem o mesmo relógio. |
| [Reutilização explícita de mídia e alinhamento entre variantes](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/references/production/runs.md) | Prisma tem receitas, corte aprovado e arquivos por etapa. | Experimentar aberturas sobre o mesmo corte. Recalcular o alinhamento quando o take ou corte mudar. Medir ganho antes de introduzir outra infraestrutura de cache. |
| [Comparação visual alinhada pelo evento](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/references/production/snapshots.md) | Prisma já renderiza demos e usa Motion Gates. | Inspecionar antes, durante e depois da fala-chave para detectar falhas que passam na validação estrutural. |
| [Plano de build e recuperação de saídas](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/references/production/builds.md) | Existem gates e arquivos locais de render. | Reavaliar quando variantes repetirem chamadas pagas ou renders pesados. |
| Seleção de referências por desempenho relativo | O Hypit documenta leitura editorial. O Prisma já avalia potencial de trechos com viral_score.py. | Ordenar por métricas observadas e comparar com o histórico do criador quando disponível. As 13 referências têm curtidas; a coleta local ficou sem visualizações. |

A implementação usa código próprio na stack do Prisma. A [licença do Hypit](https://github.com/hypit-ai/hypit/blob/main/LICENSE) tem termos específicos de redistribuição e hospedagem comercial. A avaliação examinou código e documentação.

## Ficha de referência por evento

| Tempo e fala ou ação | Quadro e áudio observados | Função editorial provável | Adaptação no Prisma |
|---|---|---|---|
| Intervalo no vídeo-fonte + frase ou ação | Entrada e saída, hierarquia do texto, posição, luz aparente, cor, movimento, SFX e quadro de prova | Promessa, contraste, comprovação, revelação ou transição | Modelo, mídia, frase de ativação e frame de conferência |

Em luz de captação, registrar direção e dureza aparentes quando visíveis. Descrever flash, brilho digital e mudança de cor junto do efeito e do ponto em que entram.

## Evidência local do piloto

Com o corte da galeria v916 e a transcrição de teste, **motor que** começa em 1,67 s no arquivo.
O início do trecho é 0,50 s, e a primeira animação da cena foi programada para 1,17 s. O render
de quatro segundos gerou H.264 em 1080 × 1920 com áudio AAC e passou na decodificação completa.
Nos quadros em 1,00 s, 1,43 s e 2,20 s, a animação passa da ausência de título para a entrada dos
textos de apoio e a palavra principal. O piloto verifica o tempo relativo ao JSON de teste.

O HTML com entrada manual em 1,17 s foi idêntico ao HTML da entrada por frase no mesmo instante.
As três suítes de regressão passaram com 74 testes, e a revisão independente aprovou o código.
O preview revisado passou no check do HyperFrames sem erros. O relatório manteve avisos de área
segura e do brilho sobreposto ao título. O piloto usa uma transcrição de teste da galeria.
