import json, os, re, sys, unicodedata, urllib.parse, urllib.request
from pathlib import Path

ESTADO = Path("estado_busca.json")
# palavras (inteiras) que descartam o resultado; some as suas em "excluir" no produtos.json
EXCLUIR_PADRAO = ["capa", "capinha", "pelicula", "case", "carregador", "cabo", "suporte", "usado", "usada",
                  "seminovo", "recondicionado", "vitrine", "peca", "replica", "kit"]


def limpa(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def buscar(q):
    qs = urllib.parse.urlencode({"engine": "google_shopping", "q": q, "gl": "br", "hl": "pt-br",
                                 "api_key": os.environ["SERPAPI_KEY"]})
    with urllib.request.urlopen("https://serpapi.com/search.json?" + qs, timeout=60) as r:
        return json.load(r).get("shopping_results", [])


def validos(res, prod):
    exc = {limpa(w).strip() for w in EXCLUIR_PADRAO + prod.get("excluir", [])}
    inc = limpa(prod["busca"]).split()
    saida = []
    for r in res:
        p, t = r.get("extracted_price"), limpa(r.get("title", ""))
        if not p or p < prod.get("min", 0) or r.get("second_hand_condition"):
            continue
        if any(w not in t.replace(" ", "") for w in inc) or exc & set(t.split()):
            continue
        saida.append(r)
    return sorted(saida, key=lambda r: r["extracted_price"])


def avisar(texto):
    dados = urllib.parse.urlencode({"chat_id": os.environ["TG_CHAT"], "text": texto}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage", dados, timeout=20)


def main():
    produtos = json.loads(Path("produtos.json").read_text(encoding="utf-8"))
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    for prod in produtos:
        nome, alvo = prod["nome"], prod.get("alvo")
        try:
            res = buscar(prod["busca"])
        except Exception as e:
            print("FALHOU", nome, e)
            continue
        ok = validos(res, prod)
        print(f"{nome}: {len(res)} resultados, {len(ok)} válidos")
        if not ok:
            continue
        melhor = ok[0]
        p, loja = melhor["extracted_price"], melhor.get("source", "?")
        ant = estado.get(nome, {})
        abaixo_alvo = alvo and p <= alvo and p < ant.get("avisado", float("inf"))
        queda = "min" in ant and p <= ant["min"] * 0.95
        if abaixo_alvo or queda:
            linhas = [("🎯 Bateu o alvo: " if abaixo_alvo else "📉 Queda de 5%+: ") + nome,
                      f"{loja}: {brl(p)}", melhor.get("title", "")]
            if alvo:
                linhas.append(f"Seu alvo: {brl(alvo)}")
            if "min" in ant:
                linhas.append(f"Menor preço visto antes: {brl(ant['min'])}")
            outros = [f"{r.get('source', '?')}: {brl(r['extracted_price'])}" for r in ok[1:4]]
            if outros:
                linhas.append("Também: " + " | ".join(outros))
            linhas.append(melhor.get("product_link") or melhor.get("link", ""))
            try:
                avisar("\n".join(linhas))
            except Exception as e:
                print("ALERTA NÃO ENVIADO", nome, e)
                continue  # não grava estado: tenta de novo na próxima rodada
            ant["avisado"] = p
        estado[nome] = {**ant, "min": min(p, ant.get("min", p))}
        print("OK", nome, loja, brl(p))
    ESTADO.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")


def teste():
    res = [
        {"title": "Capa iPhone 18 Pro Max 256GB", "extracted_price": 49.9, "source": "A"},
        {"title": "Apple iPhone 18 Pro Max 256 GB Prateado", "extracted_price": 10599, "source": "Carrefour"},
        {"title": "Apple iPhone 18 Pro Max 256GB", "extracted_price": 10999, "source": "Magalu"},
        {"title": "iPhone 18 Pro Max 256GB Seminovo", "extracted_price": 8000, "source": "B"},
        {"title": "iPhone 18 Pro Max 256GB", "extracted_price": 7000, "source": "C", "second_hand_condition": "refurbished"},
        {"title": "Apple iPhone 18 Pro 256GB", "extracted_price": 9000, "source": "D"},
        {"title": "iPhone 18 Pro Max 256GB capacidade", "extracted_price": 11500, "source": "E"},
    ]
    ok = validos(res, {"busca": "iphone 18 pro max 256gb", "min": 6000})
    assert [r["source"] for r in ok] == ["Carrefour", "Magalu", "E"], ok
    assert brl(10599) == "R$ 10.599,00"
    print("testes ok")


if __name__ == "__main__":
    teste() if "--teste" in sys.argv else main()
