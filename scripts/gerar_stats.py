"""
Gera os cards de estatísticas do perfil (img/stats/stats.svg e img/stats/langs.svg)
usando a API GraphQL do GitHub. Roda no GitHub Actions (.github/workflows/stats.yml).

Uso local:  GITHUB_TOKEN=<token> python scripts/gerar_stats.py
"""

import json
import os
import urllib.request
from html import escape
from pathlib import Path

USUARIO = os.environ.get("GH_USER", "Caua-Sampaio")
TOKEN = os.environ.get("STATS_TOKEN") or os.environ["GITHUB_TOKEN"]

# Peso do tamanho do código (bytes) e da quantidade de repositórios em que a linguagem aparece.
# 1 e 0 = só tamanho (um repositório grande domina). 0.5 e 0.5 = equilibrado.
PESO_TAMANHO = float(os.environ.get("PESO_TAMANHO", "0.5"))
PESO_QUANTIDADE = float(os.environ.get("PESO_QUANTIDADE", "0.5"))

# Linguagens que não devem aparecer no card (ex.: "Jupyter Notebook", "C++")
IGNORAR = {l.strip() for l in os.environ.get("IGNORAR_LINGUAGENS", "").split(",") if l.strip()}
SAIDA = Path(__file__).resolve().parent.parent / "img" / "stats"

# Tema escuro (mesmas cores do card de sequência)
FUNDO = "#151515"
TITULO = "#FFFFFF"
TEXTO = "#9F9F9F"
DESTAQUE = "#FB8C00"
FONTE = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"

CONSULTA = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) {
      totalCount
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def consultar(cursor=None):
    corpo = json.dumps({"query": CONSULTA, "variables": {"login": USUARIO, "cursor": cursor}})
    requisicao = urllib.request.Request(
        "https://api.github.com/graphql",
        data=corpo.encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(requisicao) as resposta:
        dados = json.load(resposta)
    if "errors" in dados:
        raise SystemExit(f"Erro da API do GitHub: {dados['errors']}")
    return dados["data"]["user"]


def coletar():
    usuario = consultar()
    repositorios = list(usuario["repositories"]["nodes"])
    pagina = usuario["repositories"]["pageInfo"]
    while pagina["hasNextPage"]:
        proxima = consultar(pagina["endCursor"])["repositories"]
        repositorios += proxima["nodes"]
        pagina = proxima["pageInfo"]

    linguagens = {}
    for repo in repositorios:
        for aresta in repo["languages"]["edges"]:
            nome = aresta["node"]["name"]
            if nome in IGNORAR:
                continue
            atual = linguagens.setdefault(nome, {"bytes": 0, "repos": 0, "cor": aresta["node"]["color"] or "#858585"})
            atual["bytes"] += aresta["size"]
            atual["repos"] += 1

    for info in linguagens.values():
        info["tamanho"] = (info["bytes"] ** PESO_TAMANHO) * (info["repos"] ** PESO_QUANTIDADE)

    contribuicoes = usuario["contributionsCollection"]
    return {
        "nome": usuario["name"] or USUARIO,
        "estrelas": sum(r["stargazerCount"] for r in repositorios),
        "commits": contribuicoes["totalCommitContributions"] + contribuicoes["restrictedContributionsCount"],
        "prs": usuario["pullRequests"]["totalCount"],
        "issues": usuario["issues"]["totalCount"],
        "contribuiu": usuario["repositoriesContributedTo"]["totalCount"],
        "linguagens": linguagens,
    }


def card(largura, altura, titulo, conteudo):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" role="img" aria-label="{escape(titulo)}">
  <style>
    .titulo {{ font: 600 18px {FONTE}; fill: {TITULO}; }}
    .texto  {{ font: 400 14px {FONTE}; fill: {TEXTO}; }}
    .valor  {{ font: 700 14px {FONTE}; fill: {TITULO}; }}
    .lang   {{ font: 400 12px {FONTE}; fill: {TEXTO}; }}
  </style>
  <rect width="{largura}" height="{altura}" rx="4.5" fill="{FUNDO}" />
  <text x="25" y="35" class="titulo">{escape(titulo)}</text>
{conteudo}
</svg>
"""


def card_stats(d):
    linhas = [
        ("Estrelas recebidas", d["estrelas"]),
        ("Commits (último ano)", d["commits"]),
        ("Pull requests", d["prs"]),
        ("Issues", d["issues"]),
        ("Contribuiu em (repos)", d["contribuiu"]),
    ]
    itens = []
    for i, (rotulo, valor) in enumerate(linhas):
        y = 70 + i * 25
        itens.append(
            f'  <circle cx="31" cy="{y - 5}" r="4" fill="{DESTAQUE}" />\n'
            f'  <text x="45" y="{y}" class="texto">{rotulo}:</text>\n'
            f'  <text x="230" y="{y}" class="valor">{valor}</text>'
        )
    return card(400, 195, f"Estatísticas de {d['nome']}", "\n".join(itens))


def card_linguagens(d):
    total = sum(l["tamanho"] for l in d["linguagens"].values()) or 1
    principais = sorted(d["linguagens"].items(), key=lambda kv: kv[1]["tamanho"], reverse=True)[:6]

    barra, x = [], 25.0
    largura_barra = 250
    for nome, info in principais:
        w = info["tamanho"] / total * largura_barra
        barra.append(f'    <rect x="{x:.2f}" y="55" width="{w:.2f}" height="8" fill="{info["cor"]}" />')
        x += w

    legenda = []
    for i, (nome, info) in enumerate(principais):
        coluna, linha = i % 2, i // 2
        lx, ly = 25 + coluna * 130, 95 + linha * 25
        pct = info["tamanho"] / total * 100
        legenda.append(
            f'  <circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{info["cor"]}" />\n'
            f'  <text x="{lx + 16}" y="{ly}" class="lang">{escape(nome)} {pct:.1f}%</text>'
        )

    conteudo = (
        '  <clipPath id="borda"><rect x="25" y="55" width="250" height="8" rx="4" /></clipPath>\n'
        '  <g clip-path="url(#borda)">\n'
        + "\n".join(barra)
        + "\n  </g>\n"
        + "\n".join(legenda)
    )
    return card(300, 195, "Linguagens mais usadas", conteudo)


def main():
    dados = coletar()
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "stats.svg").write_text(card_stats(dados), encoding="utf-8")
    (SAIDA / "langs.svg").write_text(card_linguagens(dados), encoding="utf-8")
    print("Cards gerados em", SAIDA)


if __name__ == "__main__":
    main()
