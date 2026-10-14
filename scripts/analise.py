"""Estatísticas e textos de análise gerados a partir dos dados.

Nenhum número é fixo: todo valor citado nos textos vem das séries baixadas.
Os critérios (limiares) estão nas constantes abaixo.
"""

import math
from datetime import date, timedelta
from statistics import mean, pstdev

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro"]

LIMIAR_TENDENCIA = 0.5   # variação de 6 meses, em desvios-padrão da variação típica de 6 meses
JANELA_TENDENCIA = 6     # meses
JANELA_VOLATILIDADE = 120  # meses usados para medir a variação típica (regime recente)
LIMIAR_DEFASAGEM = 0.2   # correlação mínima (em módulo) para citar uma defasagem
JANELA_CORR = 36         # meses da correlação móvel
MIN_PARES = 36           # mínimo de meses em comum para reportar uma correlação


# ---------------------------------------------------------------- formatação

def num(x, casas=2, sinal=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    s = f"{x:+,.{casas}f}" if sinal else f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def num_var(ind, x):
    """Variação com sinal e unidade: '+5,56 p.p.' ou '−8,30%'."""
    return f"{num(x, 2, True)} p.p." if ind["tipo_variacao"] == "pp" else f"{num(x, 2, True)}%"


def rot_mes(chave):
    """'2026-09' -> 'set/2026'"""
    a, m = chave[:7].split("-")
    return f"{MESES[int(m) - 1]}/{a}"


def rot_data(d):
    """date ou 'AAAA-MM-DD' -> '13/10/2026'; 'AAAA-MM' -> 'set/2026'"""
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return rot_mes(d) if len(d) == 7 else date.fromisoformat(d).strftime("%d/%m/%Y")


def soma_meses(chave, k):
    a, m = int(chave[:4]), int(chave[5:7])
    total = a * 12 + (m - 1) + k
    return f"{total // 12}-{total % 12 + 1:02d}"


def fmt_valor(ind, v):
    casas = 4 if ind["id"] == "dolar" else 2
    u = ind["unidade"]
    if u.startswith("%"):          # "%", "% a.a.", "% do PIB", "% no mês"
        return f"{num(v, casas)}{u}"
    if u == "R$/US$":
        return f"R$ {num(v, casas)}"
    if u.startswith("índice"):
        return f"{num(v, casas)} pontos {u.replace('índice ', '')}"
    return f"{num(v, casas)} {u}"


# ---------------------------------------------------------------- estatística básica

def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def variacao(ind, novo, antigo):
    if novo is None or antigo is None:
        return None
    if ind["tipo_variacao"] == "pp":
        return novo - antigo
    return (novo / antigo - 1) * 100 if antigo else None


def forca(r):
    a = abs(r)
    if a >= 0.7:
        return "forte"
    if a >= 0.4:
        return "moderada"
    if a >= 0.2:
        return "fraca"
    return "praticamente nula"


# ---------------------------------------------------------------- por indicador

def estatisticas(ind, mensal, bruto_recente=None):
    """mensal: [("AAAA-MM", v)]; bruto_recente: [("AAAA-MM-DD", v)] para séries diárias."""
    if not mensal:
        return None
    dic = dict(mensal)
    chaves = [k for k, _ in mensal]
    inicio_media = ind.get("media_desde") or chaves[0]
    janela = [v for k, v in mensal if k >= inicio_media]

    # Valor atual e variação em 12 meses (na frequência original quando a série é diária)
    if bruto_recente:
        data_atual, atual = bruto_recente[-1]
        alvo = date.fromisoformat(data_atual) - timedelta(days=365)
        anteriores = [(d, v) for d, v in bruto_recente if date.fromisoformat(d) <= alvo]
        data_12m, valor_12m = anteriores[-1] if anteriores else (None, None)
    else:
        data_atual, atual = mensal[-1]
        data_12m = soma_meses(data_atual, -12)
        valor_12m = dic.get(data_12m)
    var12 = variacao(ind, atual, valor_12m)

    media = mean(janela)
    dp = pstdev(janela)
    percentil = 100 * sum(1 for v in janela if v < atual) / len(janela)
    k_min = min(mensal, key=lambda kv: kv[1])
    k_max = max(mensal, key=lambda kv: kv[1])

    # Tendência: variação dos últimos 6 meses comparada com a variação típica de 6 meses
    # no regime recente (desvio-padrão das variações mensais dos últimos 10 anos × √6)
    def transf(v):
        return math.log(v) * 100 if ind["tipo_variacao"] == "pct" else v
    ys = [transf(v) for _, v in mensal[-(JANELA_VOLATILIDADE + 1):]]
    difs = [b - a for a, b in zip(ys, ys[1:])]
    sigma = pstdev(difs) if len(difs) > 2 else 0
    v6_ini = mensal[-JANELA_TENDENCIA - 1][1] if len(mensal) > JANELA_TENDENCIA else mensal[0][1]
    var6 = variacao(ind, mensal[-1][1], v6_ini)
    delta6 = transf(mensal[-1][1]) - transf(v6_ini)
    z = delta6 / (sigma * math.sqrt(JANELA_TENDENCIA)) if sigma else 0
    tendencia = "alta" if z > LIMIAR_TENDENCIA else "queda" if z < -LIMIAR_TENDENCIA else "estável"

    # "Maior/menor valor desde ..."
    ult_k, ult_v = mensal[-1]
    marco = None
    anteriores = mensal[:-1]
    if anteriores and ult_v > anteriores[-1][1]:
        prev = [k for k, v in anteriores if v >= ult_v]
        marco = {"tipo": "maior", "desde": prev[-1] if prev else None}
    elif anteriores and ult_v < anteriores[-1][1]:
        prev = [k for k, v in anteriores if v <= ult_v]
        marco = {"tipo": "menor", "desde": prev[-1] if prev else None}

    return {
        "data_atual": data_atual, "atual": atual,
        "data_12m": data_12m, "valor_12m": valor_12m, "var12": var12,
        "media": media, "desvio_padrao": dp, "inicio_media": inicio_media,
        "percentil": percentil,
        "minimo": {"data": k_min[0], "valor": k_min[1]},
        "maximo": {"data": k_max[0], "valor": k_max[1]},
        "tendencia": tendencia, "tendencia_z": z, "var6": var6,
        "ultimo_mes": ult_k, "ultimo_mes_valor": ult_v,
        "marco": marco,
        "inicio": chaves[0], "fim": chaves[-1], "n": len(mensal),
    }


def sazonalidade(mensal):
    """Desvio médio de cada mês do calendário em relação à média do próprio ano (anos completos)."""
    por_ano = {}
    for k, v in mensal:
        por_ano.setdefault(k[:4], {})[int(k[5:7])] = v
    desvios = {m: [] for m in range(1, 13)}
    for ano, meses in por_ano.items():
        if len(meses) == 12:
            mu = mean(meses.values())
            for m, v in meses.items():
                desvios[m].append(v - mu)
    medias = {m: mean(d) for m, d in desvios.items() if d}
    if len(medias) < 12:
        return None
    alto = max(medias, key=medias.get)
    baixo = min(medias, key=medias.get)
    return {"mes_alto": alto, "desvio_alto": medias[alto], "mes_baixo": baixo, "desvio_baixo": medias[baixo],
            "anos": sum(1 for m in por_ano.values() if len(m) == 12)}


def juro_real(selic_m, ipca_m):
    """Juro real ex-post: Selic (meta, fim do mês) descontada do IPCA acumulado em 12 meses."""
    i = dict(ipca_m)
    return [(k, ((1 + s / 100) / (1 + i[k] / 100) - 1) * 100) for k, s in selic_m if k in i]


def texto_indicador(ind, s, ctx):
    partes = []
    var_txt = (f", {num_var(ind, s['var12'])} em relação a 12 meses antes ({rot_data(s['data_12m'])})"
               if s["var12"] is not None else "")
    partes.append(f"O dado mais recente ({rot_data(s['data_atual'])}) é {fmt_valor(ind, s['atual'])}{var_txt}.")

    dif = s["atual"] - s["media"]
    if s["desvio_padrao"] and abs(dif) < 0.1 * s["desvio_padrao"]:
        pos = "praticamente igual à"
    else:
        pos = "acima da" if dif > 0 else "abaixo da"
    partes.append(f"O valor está {pos} média histórica de {fmt_valor(ind, s['media'])} (desde {rot_mes(s['inicio_media'])}) "
                  f"e supera {num(s['percentil'], 0)}% dos meses da série nesse período.")

    tend = {"alta": "alta", "queda": "queda", "estável": "estabilidade"}[s["tendencia"]]
    partes.append(f"Nos últimos seis meses a tendência é de {tend} ({num_var(ind, s['var6'])} desde {rot_mes(soma_meses(s['ultimo_mes'], -JANELA_TENDENCIA))}).")

    m = s["marco"]
    if m:
        if m["desde"] is None:
            partes.append(f"O dado de {rot_mes(s['ultimo_mes'])} é o {m['tipo']} de toda a série.")
        elif (int(s["ultimo_mes"][:4]) * 12 + int(s["ultimo_mes"][5:7])) - (int(m["desde"][:4]) * 12 + int(m["desde"][5:7])) >= 12:
            partes.append(f"É o {m['tipo']} valor desde {rot_mes(m['desde'])}.")

    partes.extend(_interpretacao(ind, s, ctx))
    if ind.get("nota_media"):
        partes.append(ind["nota_media"])
    return " ".join(partes)


def _interpretacao(ind, s, ctx):
    i = ind["id"]
    out = []
    if i == "selic" and ctx.get("juro_real"):
        jr = ctx["juro_real"]
        k, v = jr[-1]
        media_jr = mean(x for _, x in jr)
        lado = "acima" if v > media_jr else "abaixo"
        out.append(f"Descontada a inflação de 12 meses, o juro real ex-post em {rot_mes(k)} era de {num(v)}% a.a., "
                   f"{lado} da média de {num(media_jr)}% desde {rot_mes(jr[0][0])}.")
        out.append("Juro real acima da média indica política monetária mais restritiva, que tende a desacelerar crédito, consumo e inflação."
                   if v > media_jr else
                   "Juro real abaixo da média indica política monetária menos restritiva, que tende a estimular crédito e atividade.")
    elif i == "ipca12" and ctx.get("meta"):
        ano, meta = ctx["meta"]
        d = s["atual"] - meta
        lado = "acima" if d > 0 else "abaixo" if d < 0 else "igual à"
        out.append(f"A meta de inflação para {ano} é {num(meta)}%: a inflação de 12 meses está {num(abs(d))} p.p. {lado} dela."
                   if d else f"A inflação de 12 meses está exatamente na meta de {num(meta)}% para {ano}.")
        if d > 0 and s["tendencia"] == "alta":
            out.append("Inflação acima da meta e em alta costuma levar o Banco Central a manter ou elevar os juros.")
        elif d > 0 and s["tendencia"] == "queda":
            out.append("A inflação segue acima da meta, mas em trajetória de queda, o que pode abrir espaço para cortes de juros se continuar.")
        elif d <= 0 and s["tendencia"] != "alta":
            out.append("Inflação na meta ou abaixo dela, sem tendência de alta, reduz a pressão por juros altos.")
    elif i == "dolar" and s["var12"] is not None:
        if s["var12"] > 0:
            out.append(f"Em 12 meses o real se desvalorizou {num(s['var12'])}% frente ao dólar; câmbio mais caro encarece importados e pode pressionar a inflação.")
        else:
            out.append(f"Em 12 meses o real se valorizou {num(-s['var12'])}% frente ao dólar, o que alivia o preço de produtos e insumos importados.")
    elif i in ("dbgg", "dlsp") and s["var12"] is not None:
        verbo = "subiu" if s["var12"] > 0 else "caiu"
        out.append(f"Em 12 meses a dívida {verbo} {num(abs(s['var12']))} p.p. do PIB.")
        if i == "dlsp" and ctx.get("dbgg_atual"):
            k, v = ctx["dbgg_atual"]
            out.append(f"A diferença em relação à dívida bruta ({num(v)}% do PIB em {rot_mes(k)}) se deve aos ativos do setor público, "
                       "principalmente as reservas internacionais, que são descontados na dívida líquida.")
        elif s["atual"] > s["media"]:
            out.append("Com a dívida acima da média histórica, as contas públicas ficam mais sensíveis a juros altos e a crescimento baixo.")
    elif i == "uci":
        if s["atual"] > s["media"]:
            out.append("Uso acima da média indica pouca ociosidade na indústria, situação historicamente associada a pressões de preços e a mais investimento.")
        else:
            out.append("Uso abaixo da média indica ociosidade na indústria, o que reduz pressões inflacionárias vindas do setor.")
    elif i == "producao":
        mx = s["maximo"]
        queda = (s["ultimo_mes_valor"] / mx["valor"] - 1) * 100
        if mx["data"] == s["ultimo_mes"]:
            out.append("O índice está no maior nível de toda a série.")
        else:
            out.append(f"O índice está {num(abs(queda))}% abaixo do pico da série, registrado em {rot_mes(mx['data'])}.")
    elif i == "desemprego":
        sz = ctx.get("sazonalidade")
        if sz:
            out.append(f"A série não tem ajuste sazonal: nos {sz['anos']} anos completos, a taxa ficou em média "
                       f"{num(sz['desvio_alto'], 1, True)} p.p. em {MESES_LONGOS[sz['mes_alto'] - 1]} (trimestre terminado nesse mês) e "
                       f"{num(sz['desvio_baixo'], 1, True)} p.p. em {MESES_LONGOS[sz['mes_baixo'] - 1]}, em relação à média do ano. "
                       "Por isso a comparação com 12 meses antes é a mais confiável, e a tendência de seis meses pode refletir apenas a época do ano.")
        if s["var12"] is not None:
            out.append("O desemprego está menor do que há um ano." if s["var12"] < 0 else
                       "O desemprego está maior do que há um ano." if s["var12"] > 0 else "O desemprego está igual ao de um ano atrás.")
    return out


# ---------------------------------------------------------------- relações

def transformar(mensal, t):
    if not t:
        return list(mensal)
    d = dict(mensal)
    out = []
    for k, v in mensal:
        ant = d.get(soma_meses(k, -12))
        if ant is None:
            continue
        if t == "dif12":
            out.append((k, v - ant))
        elif t == "var12_pct" and ant:
            out.append((k, (v / ant - 1) * 100))
    return out


def relacao(cfg, series, nomes):
    a_ser = transformar(series[cfg["a"]], cfg.get("a_transformacao"))
    b_ser = transformar(series[cfg["b"]], cfg.get("b_transformacao"))
    da, db = dict(a_ser), dict(b_ser)
    comuns = sorted(set(da) & set(db))
    if len(comuns) < MIN_PARES:
        return None
    r_total = pearson([da[k] for k in comuns], [db[k] for k in comuns])
    ult = comuns[-JANELA_CORR:]
    r_recente = pearson([da[k] for k in ult], [db[k] for k in ult])

    movel = []
    for i in range(JANELA_CORR - 1, len(comuns)):
        jan = comuns[i - JANELA_CORR + 1:i + 1]
        r = pearson([da[k] for k in jan], [db[k] for k in jan])
        if r is not None:
            movel.append((comuns[i], r))

    # Defasagens: k > 0 => A no mês t comparado com B no mês t+k (A antecede B)
    defs = []
    for k in range(-cfg["defasagem_max"], cfg["defasagem_max"] + 1):
        pares = [(da[t], db[soma_meses(t, k)]) for t in da if soma_meses(t, k) in db]
        if len(pares) >= MIN_PARES:
            r = pearson([p[0] for p in pares], [p[1] for p in pares])
            if r is not None:
                defs.append({"k": k, "r": r, "n": len(pares)})
    melhor = max(defs, key=lambda x: abs(x["r"])) if defs else None

    rot_a = cfg.get("a_rotulo") or nomes[cfg["a"]]   # rótulos dos gráficos
    rot_b = cfg.get("b_rotulo") or nomes[cfg["b"]]
    na = cfg.get("a_texto") or rot_a                 # forma usada no meio das frases
    nb = cfg.get("b_texto") or rot_b
    def sentido(r):
        if abs(r) < 0.2:
            return "sem relação linear relevante entre as séries."
        return ("as duas séries tendem a se mover na mesma direção." if r > 0
                else "as séries tendem a se mover em direções opostas.")

    txt = [f"Entre {rot_mes(comuns[0])} e {rot_mes(comuns[-1])} ({len(comuns)} meses), a correlação entre "
           f"{na} e {nb} é {num(r_total)}: {forca(r_total)}, {sentido(r_total)}"]
    if r_recente is not None:
        if abs(r_recente) > abs(r_total) + 0.1:
            comp = "mais forte do que no período todo"
        elif abs(r_recente) < abs(r_total) - 0.1:
            comp = "mais fraca do que no período todo"
        else:
            comp = "de intensidade parecida com a do período todo"
        inverteu = (r_recente > 0) != (r_total > 0) and min(abs(r_recente), abs(r_total)) >= 0.2
        txt.append(f"Nos últimos {JANELA_CORR} meses a correlação é {num(r_recente)}, {comp}"
                   + (", e com o sinal invertido." if inverteu else "."))
    if melhor:
        no_limite = abs(melhor["k"]) == cfg["defasagem_max"]
        limite = f" (é o limite testado, de {cfg['defasagem_max']} meses; a defasagem real pode ser maior)" if no_limite else ""
        if abs(melhor["r"]) < LIMIAR_DEFASAGEM:
            txt.append(f"Nenhuma defasagem testada, de até {cfg['defasagem_max']} meses em qualquer direção, mostra associação relevante.")
        elif melhor["k"] == 0:
            txt.append("A associação é mais intensa no mesmo mês do que com qualquer defasagem testada.")
        elif melhor["k"] > 0:
            txt.append(f"A associação mais intensa ({num(melhor['r'])}) aparece ao comparar {na} com {nb} "
                       f"{melhor['k']} meses depois{limite}. Isso sugere que {na} antecede {nb}.")
        else:
            txt.append(f"A associação mais intensa ({num(melhor['r'])}) aparece ao comparar {nb} com {na} "
                       f"{-melhor['k']} meses depois{limite}. Isso sugere que {nb} antecede {na}.")
    if movel:
        mn = min(movel, key=lambda x: x[1])
        mx = max(movel, key=lambda x: x[1])
        txt.append(f"A correlação móvel de {JANELA_CORR} meses oscilou entre {num(mn[1])} (em {rot_mes(mn[0])}) e "
                   f"{num(mx[1])} (em {rot_mes(mx[0])})"
                   + (", ou seja, a relação mudou bastante ao longo do tempo." if mx[1] - mn[1] > 0.8 else "."))
    if cfg["id"] == "juros_inflacao" and r_total > 0:
        txt.append("Uma correlação positiva no mesmo mês costuma refletir a reação do Banco Central à inflação (juros sobem depois que a inflação sobe); "
                   "o efeito dos juros sobre os preços atua com defasagem.")
    txt.append("Correlação não implica causalidade: outros fatores (choques externos, política fiscal, câmbio) afetam as duas séries.")

    return {
        "id": cfg["id"], "titulo": cfg["titulo"], "pergunta": cfg["pergunta"],
        "a": cfg["a"], "b": cfg["b"], "a_rotulo": rot_a, "b_rotulo": rot_b,
        "inicio": comuns[0], "fim": comuns[-1], "n": len(comuns),
        "r_total": r_total, "r_recente": r_recente, "melhor_defasagem": melhor, "defasagens": defs,
        "serie_a": [[k, round(da[k], 4)] for k in comuns],
        "serie_b": [[k, round(db[k], 4)] for k in comuns],
        "corr_movel": [[k, round(r, 4)] for k, r in movel],
        "texto": " ".join(txt),
    }


# ---------------------------------------------------------------- orquestração

def analisar(config, dados):
    inds = {i["id"]: i for i in config["indicadores"]}
    series = {i: [tuple(p) for p in d["serie"]] for i, d in dados["indicadores"].items() if d.get("serie")}
    nomes = {i: inds[i]["nome_curto"] for i in inds}

    ctx = {}
    if "selic" in series and "ipca12" in series:
        ctx["juro_real"] = juro_real(series["selic"], series["ipca12"])
    if "meta_inflacao" in series and "ipca12" in series:
        ano_ipca = series["ipca12"][-1][0][:4]
        metas = {k[:4]: v for k, v in series["meta_inflacao"]}
        if ano_ipca in metas:
            ctx["meta"] = (ano_ipca, metas[ano_ipca])
    if "dbgg" in series:
        ctx["dbgg_atual"] = series["dbgg"][-1]
    if "desemprego" in series:
        ctx["sazonalidade"] = sazonalidade(series["desemprego"])

    saida = {"indicadores": {}, "relacoes": [], "juro_real": [[k, round(v, 4)] for k, v in ctx.get("juro_real", [])]}
    for i, ind in inds.items():
        if i not in series:
            continue
        bruto = dados["indicadores"][i].get("bruto_recente")
        s = estatisticas(ind, series[i], [tuple(p) for p in bruto] if bruto else None)
        s["texto"] = texto_indicador(ind, s, ctx) if ind.get("card") else ""
        saida["indicadores"][i] = s

    for rel in config["relacoes"]:
        if rel["a"] in series and rel["b"] in series:
            r = relacao(rel, series, nomes)
            if r:
                saida["relacoes"].append(r)

    saida["panorama"] = panorama(saida["indicadores"], ctx)
    return saida


def panorama(st, ctx):
    def t(i, nome, fem=False):
        if i not in st:
            return None
        tend = st[i]["tendencia"]
        palavra = {"alta": "em alta", "queda": "em queda", "estável": "estável" if not fem else "estável"}[tend]
        return f"{nome} {palavra}"
    itens = [t("selic", "Selic"), t("ipca12", "inflação", True), t("dolar", "dólar"), t("dbgg", "dívida bruta", True),
             t("uci", "uso da capacidade industrial"), t("producao", "produção industrial", True), t("desemprego", "desemprego")]
    itens = [x for x in itens if x]
    if not itens:
        return ""
    frase = "Tendência dos últimos seis meses: " + ", ".join(itens[:-1]) + (" e " if len(itens) > 1 else "") + itens[-1] + "."
    if ctx.get("meta") and "ipca12" in st:
        ano, meta = ctx["meta"]
        d = st["ipca12"]["atual"] - meta
        frase += f" A inflação de 12 meses está {num(abs(d))} p.p. {'acima' if d > 0 else 'abaixo'} da meta de {ano}." if d else ""
    if ctx.get("juro_real"):
        k, v = ctx["juro_real"][-1]
        frase += f" O juro real ex-post é de {num(v)}% a.a. ({rot_mes(k)})."
    return frase
