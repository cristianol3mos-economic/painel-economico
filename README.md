# Indicadores Econômicos do Brasil

Painel estático (GitHub Pages) com juros, inflação, câmbio, dívida pública, indústria e desemprego,
atualizado todo dia pelo GitHub Actions a partir das APIs oficiais do Banco Central (SGS) e do IBGE (SIDRA).

## Séries usadas (códigos conferidos na fonte em 14/10/2026)

| Indicador | Fonte | Código | Início |
|---|---|---|---|
| Selic – meta Copom (% a.a.) | BCB/SGS | 432 (diária) | mar/1999 |
| IPCA acumulado 12 meses (%) | BCB/SGS (dado do IBGE) | 13522 | dez/1980 |
| IPCA mensal (%) | BCB/SGS | 433 | jan/1980 |
| Meta de inflação (%) | BCB/SGS | 13521 (anual) | — |
| Dólar PTAX venda (R$/US$) | BCB/SGS | 1 (diária) | jul/1994* |
| Dívida Bruta do Governo Geral (% PIB) | BCB/SGS | 13762 | dez/2006 |
| Dívida Líquida do Setor Público (% PIB) | BCB/SGS | 4513 | dez/2001 |
| Utilização da capacidade – ind. transformação (FGV, dessaz.) | BCB/SGS | 28561 | jan/2001 |
| Utilização da capacidade – ind. transformação (FGV, original) | BCB/SGS | 24352 | jan/2001 |
| Produção industrial – Indústria geral, com ajuste (2022=100) | IBGE/SIDRA | tab. 8888, var. 12607, c544/129314 | jan/2002 |
| Produção industrial – Indústria geral, sem ajuste | IBGE/SIDRA | tab. 8888, var. 12606, c544/129314 | jan/2002 |
| Taxa de desocupação – PNAD Contínua (%) | IBGE/SIDRA | tab. 6381, var. 4099 | mar/2012 |

\* A série 1 começa em 1984, mas antes do Plano Real os valores estão em moedas antigas, sem conversão.

**Utilização da capacidade:** o IBGE não publica essa série. A da CNI no SGS (1341) parou em 2006,
e os dados atuais da CNI não têm API pública estável. Por isso o painel usa a série da FGV republicada pelo BCB.

## Estrutura

```
config/indicadores.json   códigos das séries, períodos marcantes e relações analisadas
scripts/fontes.py         coleta (SGS em janelas de 10 anos, SIDRA, novas tentativas)
scripts/analise.py        estatísticas, correlações e textos gerados a partir dos dados
scripts/atualizar.py      executa tudo e grava docs/data/
docs/                     site (index.html, assets/, data/)
.github/workflows/        atualização diária + publicação no Pages
```

Só usa a biblioteca padrão do Python (3.9+). Para rodar localmente:

```bash
python scripts/atualizar.py
python -m http.server -d docs 8000
```

## Publicar

1. Crie um repositório no GitHub e envie estes arquivos para a branch `main`.
2. Em **Settings → Pages**, em *Build and deployment → Source*, escolha **GitHub Actions**.
3. Em **Actions**, abra "Atualizar dados e publicar painel" e clique em **Run workflow**.
   Depois disso ele roda sozinho todo dia às 9h (horário de Brasília).

Se alguma fonte falhar, o site mostra um aviso, mantém os últimos dados válidos daquele indicador
(nunca substitui por outra fonte) e o workflow termina com erro, o que faz o GitHub enviar um e-mail.
