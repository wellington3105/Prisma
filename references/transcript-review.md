# Revisão da transcrição

O transcritor ouve rápido e bem, e ainda assim escreve "Delta" onde se disse "Deocar", "Um" onde se disse "Então,", ou "em Tem Real" para "em Tempo Real". A revisão é o passo em que o agente lê o texto, corrige o que ouviu errado e marca o que não é vídeo (take abandonado, instrução de gravação, conversa paralela). O áudio e os tempos não mudam; só o texto e o que as legendas mostram.

## Quando rodar

1. **Depois de transcrever o corte** (a transcrição do `cut.mp4` final, ou das fontes, antes do EDL), e **antes das legendas** (`captions_for_remotion.py`, `captions_srt.py`).
2. Se a revisão marcar `drop` em fontes brutas, rode **antes de montar o EDL**; se a transcrição for do corte final, `drop` não se aplica (o trecho já está no vídeo).
3. Refazer é barato: cada execução parte do texto bruto. Mudou o `revisao.json`, rode de novo.

## Fluxo

```
uv run python helpers/pack_transcripts.py --edit-dir <edit>      # takes_packed.md, frases numeradas (#n)
# o agente LÊ takes_packed.md (nunca o JSON) e escreve <edit>/revisao.json
uv run python helpers/revise_transcript.py --edit-dir <edit>     # aplica; imprime antes/depois por frase
uv run python helpers/pack_transcripts.py --edit-dir <edit>      # relê: frases corrigidas saem com *, drops com [DROP: motivo]
```

`--dry-run` só relata. `--undo` apaga as cópias revisadas (o bruto nunca é tocado).

## revisao.json

Chave = nome da transcrição sem `.json` (o mesmo `## título` do `takes_packed.md`). Frases numeradas como no `takes_packed.md`: o `#n` logo depois do `[início-fim]`. A numeração é contada nas palavras brutas, então não muda entre revisões.

```json
{
  "cut": {
    "fix":   [{"n": 7, "text": "... garantia de fábrica até final de 2027. Então, excelente custo-benefício ..."}],
    "drop":  [{"n": 2, "why": "instrução de gravação"}],
    "terms": {"Delta": "Deocar"}
  }
}
```

Também vale em português: `corrigir` / `remover` / `termos` (e `texto` / `motivo`).

- **`fix`**: `text` é a frase inteira como deve ser lida. O helper alinha o texto às palavras com tempo (maior subsequência comum, sem caixa, acento ou pontuação): palavra igual mantém o tempo; palavra trocada herda o tempo da que substitui ("Um" vira "Então," no mesmo instante); palavra inserida ganha tempo interpolado entre as vizinhas; palavra omitida some do texto revisado. Nenhuma palavra sai do intervalo `[início, fim]` da própria frase. Se menos de 50% do texto novo casa com o falado (reescrita), o helper avisa: os tempos ficam aproximados. Corrija o que se ouve; não reescreva.
- **`terms`**: troca global preservando a caixa (`delta` → `deocar`, `DELTA` → `DEOCAR`, `Delta.` → `Deocar.`; marca com maiúscula interna, como `ChatGPT`, entra como escrita). Chave com várias palavras funciona (`"Tem Real": "Tempo Real"`). Palavras já definidas por um `fix` não são tocadas. Use para marca e glossário (`glossary.txt`).
- **`drop`**: a frase **não é apagada**. Suas palavras ganham `drop: true` e `drop_why`; o arquivo revisado lista `revision.drop` com `n`, `start`, `end`, `why`. O construtor de EDL lê isso com `drop_ranges(transcricao)` (de `helpers/revise_transcript.py`) e corta o intervalo. `why` com no máximo 6 palavras.

## O que fica pronto

`<edit>/transcripts/.revised/<nome>.json`: mesmo formato do bruto, mais um bloco `revision` (o que mudou). Fica numa pasta oculta de propósito: quem faz `transcripts/*.json` continua vendo só o bruto.

`pack_transcripts.py`, `captions_for_remotion.py` (nos dois modos) e `captions_srt.py` usam a cópia revisada sozinhos quando ela existe e é mais nova que o bruto (se o bruto for mais novo, avisam e usam o bruto). `--raw` em qualquer um dos três ignora a revisão.

## Cuidados

- Tipo `spacing` entre as palavras: o helper já ignora ao casar termos de várias palavras e ao achar a "próxima palavra". Se escrever um script próprio sobre a transcrição, faça o mesmo.
- Revise o que o espectador lê ou ouve: nomes, marcas, números, interjeições trocadas. Não "melhore" a fala; legenda e áudio precisam continuar iguais.
- Frase numerada demais ou inexistente é erro (código de saída 1), nunca aplicada em silêncio.
