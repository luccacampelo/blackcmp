import json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ESTADO = Path("estado.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def num(v):
    s = str(v).strip()
    if "," in s:  # formato BR: 1.299,90
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def preco(pagina):
    # 1) JSON-LD (schema.org Product/Offer) — padrão na maioria das lojas
    for bloco in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', pagina, re.S):
        try:
            pilha = [json.loads(bloco)]
        except ValueError:
            continue
        while pilha:
            d = pilha.pop(0)
            if isinstance(d, list):
                pilha += d
            elif isinstance(d, dict):
                for k in ("lowPrice", "price"):
                    if str(d.get(k, "")).strip():
                        try:
                            return num(d[k])
                        except ValueError:
                            pass
                pilha += list(d.values())
    # 2) meta tags de preço
    m = (re.search(r'(?:product:price:amount|itemprop="price")[^>]*content="([\d.,]+)"', pagina)
         or re.search(r'content="([\d.,]+)"[^>]*(?:product:price:amount|itemprop="price")', pagina))
    return num(m.group(1)) if m else None
    # ponytail: sem JS — Shopee e páginas 100% client-side retornam None; upgrade = Playwright


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def avisar(texto):
    token, chat = os.environ["TG_TOKEN"], os.environ["TG_CHAT"]
    dados = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=20)


def main():
    lista = json.loads(Path("lista.json").read_text(encoding="utf-8"))
    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    for prod in lista:
        alvo = prod.get("alvo")
        for url in prod["links"]:
            try:
                p = preco(baixar(url))
            except Exception as e:
                print("FALHOU", url, e)
                continue
            if p is None:
                print("SEM PREÇO", url)
                continue
            ant = estado.get(url)
            loja = urllib.parse.urlparse(url).netloc.replace("www.", "")
            bateu_alvo = alvo and p <= alvo and (not ant or p != ant["ultimo"])
            nova_minima = ant and p < ant["min"]
            if bateu_alvo or nova_minima:
                motivo = "🎯 Bateu o alvo" if bateu_alvo else "📉 Menor preço já visto"
                linhas = [f"{motivo}: {prod['nome']}", f"{loja}: {brl(p)}"]
                if ant:
                    linhas.append(f"Antes: {brl(ant['ultimo'])} | mínima anterior: {brl(ant['min'])}")
                if alvo:
                    linhas.append(f"Seu alvo: {brl(alvo)}")
                linhas.append(url)
                avisar("\n".join(linhas))
            estado[url] = {"ultimo": p, "min": min(p, ant["min"]) if ant else p}
            print("OK", loja, brl(p))
            time.sleep(3)
    ESTADO.write_text(json.dumps(estado, indent=1))


def teste():
    assert preco('<script type="application/ld+json">{"@type":"Product","offers":{"price":"1299.90"}}</script>') == 1299.90
    assert preco('<script type="application/ld+json">[{"offers":[{"lowPrice":"899,50"}]}]</script>') == 899.50
    assert preco('<meta property="product:price:amount" content="1.299,90">') == 1299.90
    assert preco("<html>nada</html>") is None
    assert brl(1299.9) == "R$ 1.299,90"
    print("testes ok")


if __name__ == "__main__":
    teste() if "--teste" in sys.argv else main()
