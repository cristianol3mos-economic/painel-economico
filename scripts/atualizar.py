"""Baixa todas as séries, recalcula a análise e grava os arquivos que o site lê.

Uso:  python scripts/atualizar.py
Saída: docs/data/dados.json, docs/data/analise.json, docs/data/indicadores_mensais.csv,
       docs/data/bruto/<id>.csv (séries na frequência original)
Código de saída 1 se alguma fonte falhou (os dados anteriores daquele indicador são mantidos e marcados).
"""

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analise import analisar  # noqa: E402
from fontes import FonteErro, buscar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config" / "indicadores.json"
SAIDA = RAIZ / "docs" / "data"
DIAS_RECENTES = 400  # observações diárias guardadas para calcular a variação em 12 meses


def agora_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def carregar_anterior():
    arq = SAIDA / "dados.json"
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    return {"indicadores": {}}


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    anterior = carregar_anterior()
    (SAIDA / "bruto").mkdir(parents=True, exist_ok=True)

    dados = {"gerado_em": agora_iso(), "indicadores": {}, "erros": [],
             "periodos_marcantes": config["periodos_marcantes"]}
    hoje = date.today()

    for ind in config["indicadores"]:
        i = ind["id"]
        meta = {k: ind[k] for k in ("nome", "nome_curto", "grupo", "unidade", "tipo_variacao", "fonte_nome",
                                     "fonte_url", "nome_oficial", "descricao", "card") if k in ind}
        meta["notas"] = [n for n in (ind.get("nota_inicio"), ind.get("nota_media")) if n]
        meta["fonte"] = ind["fonte"]
        print(f"→ {i}: {ind['fonte_nome']} ... ", end="", flush=True)
        try:
            bruto, mensal = buscar(ind, hoje)
            ant = anterior["indicadores"].get(i, {}).get("serie") or []
            if ant and len(mensal) < 0.9 * len(ant):
                raise FonteErro(f"a fonte devolveu {len(mensal)} meses, bem menos que os {len(ant)} da versão anterior "
                                "(resposta possivelmente incompleta)")
            entrada = dict(meta, status="ok", erro=None, atualizado_em=agora_iso(),
                           ultima_observacao=bruto[-1][0].isoformat(),
                           serie=[[k, round(v, 4)] for k, v in mensal])
            if ind["fonte"].get("diaria"):
                corte = bruto[-1][0] - timedelta(days=DIAS_RECENTES)
                entrada["bruto_recente"] = [[d.isoformat(), v] for d, v in bruto if d >= corte]
                with open(SAIDA / "bruto" / f"{i}.csv", "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["data", f"{i} ({ind['unidade']})"])
                    for d, v in bruto:
                        w.writerow([d.isoformat(), f"{v}".replace(".", ",")])
            print(f"ok ({len(mensal)} meses, último dado {bruto[-1][0]:%d/%m/%Y})")
        except Exception as e:  # noqa: BLE001 — qualquer falha é registrada, nunca mascarada
            msg = f"{type(e).__name__}: {e}"
            print(f"FALHOU — {msg}")
            ant = anterior["indicadores"].get(i)
            if ant and ant.get("serie"):
                entrada = dict(ant, **meta, status="erro", erro=msg)
            else:
                entrada = dict(meta, status="erro", erro=msg, atualizado_em=None, serie=[])
            dados["erros"].append({"indicador": i, "fonte": ind["fonte_nome"], "erro": msg})
        dados["indicadores"][i] = entrada

    print("→ calculando análise ...", flush=True)
    analise = analisar(config, dados)
    analise["gerado_em"] = dados["gerado_em"]

    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SAIDA / "analise.json").write_text(json.dumps(analise, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    escrever_csv_mensal(dados)

    if dados["erros"]:
        print("\nATENÇÃO — fontes com falha (dados anteriores mantidos e sinalizados no site):")
        for e in dados["erros"]:
            print(f"  - {e['indicador']} ({e['fonte']}): {e['erro']}")
        return 1
    print("\nTudo atualizado.")
    return 0


def escrever_csv_mensal(dados):
    ids = [i for i, d in dados["indicadores"].items() if d.get("serie")]
    tabela = {}
    for i in ids:
        for k, v in dados["indicadores"][i]["serie"]:
            tabela.setdefault(k, {})[i] = v
    with open(SAIDA / "indicadores_mensais.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["mes"] + [f"{dados['indicadores'][i]['nome_curto']} ({dados['indicadores'][i]['unidade']})" for i in ids])
        for k in sorted(tabela):
            w.writerow([k] + [("" if tabela[k].get(i) is None else f"{tabela[k][i]}".replace(".", ",")) for i in ids])


if __name__ == "__main__":
    sys.exit(main())
