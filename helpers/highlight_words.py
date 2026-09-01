"""Escolhe os termos que merecem card de destaque, a partir do transcript.

Existe porque escolher palavra-chave a olho é o erro que produziu o vídeo
reprovado em 2026-09-01: sem critério, escolhi o que me pareceu bonito e não o
que o falante estava enfatizando.

O critério vem do ofício (PRP 2026-09-01). A referência destaca **substantivos
concretos, números e nomes próprios** — "62%", "Squats", "3D", "gratuita" —
nunca verbos de ligação ou conectivos. E a cadência é de **1 destaque a cada
8–15 segundos**: mais que isso vira uma segunda legenda, e a regra do ofício é
que texto REFORÇA, não duplica.

O que este helper NÃO faz: escrever o texto do card. Ele propõe candidatos com
o tempo exato em que a palavra é dita; a redação final é decisão editorial.

Uso:
    uv run python helpers/highlight_words.py transcripts/cut.json
    uv run python helpers/highlight_words.py transcripts/cut.json --out highlights.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Cadência de ofício: ~1 a cada 8–15s. Usamos o piso como distância mínima.
MIN_GAP_S = 8.0
# Um destaque tem de caber no card e ser lido num relance.
MAX_CHARS = 18
MIN_CHARS = 3

# Palavras que nunca são destaque: artigos, preposições, conectivos, verbos de
# ligação e muletas. Não é lista de "palavras ruins" — são palavras que não
# carregam o ponto, e destacá-las contradiz a função do card.
VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das",
    "dos", "em", "na", "no", "nas", "nos", "por", "para", "pra", "pro", "com",
    "sem", "sobre", "entre", "ate", "desde", "que", "quem", "qual", "quais",
    "e", "ou", "mas", "porem", "porque", "pois", "se", "como", "quando",
    "onde", "eu", "voce", "ele", "ela", "nos", "eles", "elas", "meu", "minha",
    "seu", "sua", "esse", "essa", "isso", "este", "esta", "isto", "aquele",
    "aquela", "aquilo", "ser", "estar", "ter", "haver", "ir", "vir", "fazer",
    "e", "ee", "eh", "sao", "esta", "estao", "tem", "tinha", "foi", "era",
    "vai", "vou", "muito", "mais", "menos", "ja", "ainda", "so", "tambem",
    "nao", "sim", "bem", "bom", "aqui", "ali", "la", "entao", "dai", "ai",
    "tipo", "assim", "coisa", "gente", "vamos", "acho", "sei", "tudo", "nada",
}


def _norm(s: str) -> str:
    """Minúscula sem acento, para comparar com a lista de vazias."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _score(txt: str, inicio_de_frase: bool) -> tuple[float, str]:
    """Quanto esta palavra merece um card, e por quê.

    A razão importa tanto quanto a nota: quem revisar a proposta precisa saber
    se o helper escolheu por conteúdo ou por acaso. Foi lendo as razões que
    apareceram os dois defeitos da primeira versão — "Pelo" marcado como nome
    próprio (era só início de frase) e "entender" como substantivo (é verbo).
    """
    limpo = txt.strip().strip(".,!?;:—-\"'()")
    n = _norm(limpo)

    if not (MIN_CHARS <= len(limpo) <= MAX_CHARS):
        return 0.0, ""
    if n in VAZIAS:
        return 0.0, ""
    # Infinitivos e gerúndios: verbos não carregam o ponto, carregam a ação.
    # A referência destaca COISAS ("Squats", "3D", "62%"), não ações.
    if n.endswith(("ar", "er", "ir", "ando", "endo", "indo")) and len(n) > 4:
        return 0.0, ""

    # Números e percentuais: o destaque mais forte da referência ("62%", "2.4K").
    if re.search(r"\d", limpo):
        return 3.0, "número"
    # Nome próprio: maiúscula no MEIO da frase. No início não diz nada —
    # toda frase começa assim.
    if limpo[0].isupper() and not inicio_de_frase:
        return 2.2, "nome próprio"
    # Termo técnico/estrangeiro: consoante rara em português, ou sigla.
    if re.search(r"[kwy]", n) or (limpo.isupper() and len(limpo) > 1):
        return 2.0, "termo técnico"
    # Palavra longa costuma ser substantivo com carga semântica.
    if len(limpo) >= 8:
        return 1.5, "substantivo longo"
    if len(limpo) >= 6:
        return 1.0, "substantivo"
    return 0.4, "genérico"


def escolher(transcript: Path, max_n: int | None, gap: float) -> dict:
    d = json.loads(transcript.read_text(encoding="utf-8"))
    palavras = [w for w in d.get("words", []) if w.get("text", "").strip()]
    if not palavras:
        return {"ok": False, "reason": "transcript sem palavras", "highlights": []}

    dur = float(palavras[-1].get("end", 0))
    cands = []
    inicio = True   # a primeira palavra sempre abre frase
    for i, w in enumerate(palavras):
        nota, razao = _score(w["text"], inicio)
        # A próxima abre frase se esta terminou com pontuação final, ou se veio
        # uma pausa longa — que na fala é o mesmo que ponto.
        prox_pausa = (float(palavras[i + 1]["start"]) - float(w.get("end", 0))
                      if i + 1 < len(palavras) else 0)
        inicio = w["text"].strip().endswith((".", "!", "?")) or prox_pausa > 0.7
        if nota <= 0:
            continue
        cands.append({
            "text": w["text"].strip().strip(".,!?;:—-\"'()"),
            "at": round(float(w["start"]), 2),
            "score": nota,
            "why": razao,
        })

    # Ordena por nota e vai aceitando, respeitando a distância mínima. É isso
    # que impede o helper de despejar cinco destaques na mesma frase só porque
    # ela é rica em substantivos.
    cands.sort(key=lambda c: (-c["score"], c["at"]))
    aceitos: list[dict] = []
    vistos: set[str] = set()
    for c in cands:
        # A mesma palavra duas vezes não é destaque, é repetição — e chama
        # atenção para o erro em vez do conteúdo.
        if _norm(c["text"]) in vistos:
            continue
        if all(abs(c["at"] - a["at"]) >= gap for a in aceitos):
            aceitos.append(c)
            vistos.add(_norm(c["text"]))
        if max_n and len(aceitos) >= max_n:
            break
    aceitos.sort(key=lambda c: c["at"])

    esperado = max(1, int(dur // 12))  # ~1 a cada 12s, meio da faixa de ofício
    return {
        "ok": bool(aceitos),
        "reason": (f"{len(aceitos)} destaque(s) em {dur:.0f}s "
                   f"(cadência de ofício sugere ~{esperado})"),
        "duration_s": round(dur, 1),
        "highlights": [{"text": c["text"], "at": c["at"], "dur": 3.2,
                        "why": c["why"]} for c in aceitos],
        # A redação do card é decisão editorial, e a regra do ofício é dura:
        # **texto reforça, não duplica**. Repetir no card a palavra que a
        # legenda já mostra torna uma das camadas ruído — verificado em still,
        # com "movimento" duas vezes na tela.
        #
        # O que fazer com estes candidatos: use o termo como GANCHO e escreva
        # no card o que ele significa. "movimento" → "CÂMERA EM MOVIMENTO";
        # "estranho" → "não ficou natural". O `at` é o que importa aqui — é o
        # instante em que o ponto é feito.
        "nota_editorial": (
            "Estes são os MOMENTOS a destacar, não o texto final do card. "
            "Reescreva cada um: o card deve dizer o que a palavra significa, "
            "não repeti-la — a legenda já a mostra."),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("transcript", type=Path)
    ap.add_argument("--max", type=int, default=None,
                    help="teto de destaques; sem isto, a cadência decide")
    ap.add_argument("--gap", type=float, default=MIN_GAP_S,
                    help=f"distância mínima entre destaques (default {MIN_GAP_S}s)")
    ap.add_argument("--out", type=Path, help="grava o bloco highlights em JSON")
    args = ap.parse_args()

    r = escolher(args.transcript, args.max, args.gap)
    if args.out and r["ok"]:
        args.out.write_text(json.dumps(
            {"enabled": True,
             "items": [{k: v for k, v in h.items() if k != "why"}
                       for h in r["highlights"]]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        r["out"] = str(args.out)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if not r["ok"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
