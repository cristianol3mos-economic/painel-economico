"""Coleta de séries nas APIs públicas do Banco Central (SGS) e do IBGE (SIDRA).

Só usa a biblioteca padrão do Python. Qualquer falha vira uma exceção FonteErro;
nunca há dado substituto inventado.
"""

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

USER_AGENT = "painel-indicadores-brasil/1.0 (+https://github.com)"
TENTATIVAS = 3
ESPERA_INICIAL = 5  # segundos; dobra a cada nova tentativa
PRAZO_TOTAL = 120   # segundos por requisição, do início ao fim da leitura


class FonteErro(Exception):
    """Falha ao obter dados de uma fonte oficial."""


def _baixar(url):
    """Lê a URL com prazo TOTAL de PRAZO_TOTAL s (o timeout do urllib vale só por leitura;
    um servidor que responde aos poucos poderia travar o processo indefinidamente)."""
    resultado = {}

    def tarefa():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resultado["corpo"] = resp.read()
        except Exception as e:  # noqa: BLE001 — repassado para a thread principal
            resultado["erro"] = e

    t = threading.Thread(target=tarefa, daemon=True)
    t.start()
    t.join(PRAZO_TOTAL)
    if t.is_alive():
        raise TimeoutError(f"sem resposta completa em {PRAZO_TOTAL}s")
    if "erro" in resultado:
        raise resultado["erro"]
    return resultado["corpo"]


def _get_json(url, aceitar_404=False):
    """GET com novas tentativas para erros transitórios (5xx, timeout)."""
    ultimo_erro = None
    espera = ESPERA_INICIAL
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return json.loads(_baixar(url).decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404 and aceitar_404:
                return None
            ultimo_erro = f"HTTP {e.code} em {url}"
            if e.code < 500 and e.code != 429:
                break  # erro do pedido, não adianta repetir
        except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError) as e:
            ultimo_erro = f"{type(e).__name__}: {e} em {url}"
        if tentativa < TENTATIVAS:
            time.sleep(espera)
            espera *= 2
    raise FonteErro(ultimo_erro)


# ---------------------------------------------------------------- SGS / BCB

def _janelas(inicio, fim, anos=10):
    """Janelas de no máximo 10 anos: a API do SGS recusa (HTTP 406) pedidos maiores para séries diárias."""
    atual = inicio
    while atual <= fim:
        try:
            limite = atual.replace(year=atual.year + anos) - timedelta(days=1)
        except ValueError:  # 29/fev
            limite = atual.replace(year=atual.year + anos, day=28)
        yield atual, min(limite, fim)
        atual = limite + timedelta(days=1)


def _sgs_janela(codigo, ini, fim):
    """Busca uma janela; se o servidor falhar (ex.: HTTP 502 em respostas grandes), divide-a ao meio."""
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
           f"&dataInicial={ini:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}")
    try:
        return _get_json(url, aceitar_404=True) or []  # 404 = janela sem observações
    except FonteErro:
        if (fim - ini).days < 370:
            raise
        meio = ini + (fim - ini) / 2
        return _sgs_janela(codigo, ini, meio) + _sgs_janela(codigo, meio + timedelta(days=1), fim)


def _sgs_linhas(codigo, diaria, hoje):
    if not diaria:
        # Séries mensais/anuais aceitam a série inteira num único pedido
        try:
            return _get_json(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json")
        except FonteErro:
            pass  # tenta de novo em janelas
    linhas = []
    for ini, fim in _janelas(date(1970, 1, 1), hoje):
        linhas += _sgs_janela(codigo, ini, fim)
    return linhas


def buscar_sgs(codigo, hoje=None, diaria=False):
    """Série completa do SGS como lista [(date, float)], ordenada e sem datas futuras."""
    hoje = hoje or date.today()
    pontos = {}
    for linha in _sgs_linhas(codigo, diaria, hoje):
        d, m, a = linha["data"].split("/")
        dia = date(int(a), int(m), int(d))
        valor = linha.get("valor")
        if valor in (None, "") or dia > hoje:
            continue  # a meta Selic (432) traz datas até a próxima reunião do Copom
        pontos[dia] = float(valor)
    if not pontos:
        raise FonteErro(f"SGS {codigo}: nenhuma observação retornada")
    return sorted(pontos.items())


# ---------------------------------------------------------------- SIDRA / IBGE

def buscar_sidra(tabela, variavel, classificacao=None):
    """Série nacional (n1) da tabela SIDRA como lista [(date, float)], com data = 1º dia do mês."""
    url = f"https://apisidra.ibge.gov.br/values/t/{tabela}/n1/all/v/{variavel}/p/all"
    if classificacao:
        url += f"/{classificacao}"
    url += "?formato=json"
    dados = _get_json(url)
    if not isinstance(dados, list) or len(dados) < 2:
        raise FonteErro(f"SIDRA {tabela}/{variavel}: resposta vazia ou inesperada")
    cabecalho = dados[0]
    # A coluna de período é a que tem "Mês (Código)" ou "Trimestre Móvel (Código)" no cabeçalho
    chave_periodo = next((k for k, v in cabecalho.items()
                          if v.endswith("(Código)") and (v.startswith("Mês") or v.startswith("Trimestre"))), None)
    if not chave_periodo:
        raise FonteErro(f"SIDRA {tabela}: coluna de período não encontrada no cabeçalho {cabecalho}")
    pontos = []
    for linha in dados[1:]:
        valor = linha.get("V", "")
        try:
            v = float(valor)
        except ValueError:
            continue  # "...", "-", "X" = sem dado / sigilo
        p = linha[chave_periodo]  # AAAAMM (no trimestre móvel, o último mês do trimestre)
        pontos.append((date(int(p[:4]), int(p[4:6]), 1), v))
    if not pontos:
        raise FonteErro(f"SIDRA {tabela}/{variavel}: nenhuma observação numérica")
    return sorted(pontos)


# ---------------------------------------------------------------- conversões

def para_mensal(pontos, metodo):
    """Agrega observações diárias/anuais em meses. Retorna [("AAAA-MM", valor)]."""
    if metodo == "anual_para_mensal":
        saida = []
        for d, v in pontos:
            for m in range(1, 13):
                saida.append((f"{d.year}-{m:02d}", v))
        return saida
    grupos = {}
    for d, v in pontos:
        grupos.setdefault(f"{d.year}-{d.month:02d}", []).append(v)
    if metodo == "media":
        return [(k, sum(vs) / len(vs)) for k, vs in sorted(grupos.items())]
    if metodo == "ultimo":
        return [(k, vs[-1]) for k, vs in sorted(grupos.items())]
    # série já mensal
    return [(k, vs[-1]) for k, vs in sorted(grupos.items())]


def buscar(ind, hoje=None):
    """Busca um indicador da configuração. Retorna (bruto [(date, v)], mensal [("AAAA-MM", v)])."""
    f = ind["fonte"]
    if f["tipo"] == "sgs":
        bruto = buscar_sgs(f["codigo"], hoje, diaria=f.get("diaria", False))
    elif f["tipo"] == "sidra":
        bruto = buscar_sidra(f["tabela"], f["variavel"], f.get("classificacao"))
    else:
        raise FonteErro(f"tipo de fonte desconhecido: {f['tipo']}")
    if ind.get("inicio_valido"):
        corte = date.fromisoformat(ind["inicio_valido"])
        bruto = [(d, v) for d, v in bruto if d >= corte]
    return bruto, para_mensal(bruto, ind.get("mensal"))
