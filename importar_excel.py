from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from db import get_supabase

COL_DATA = "Data"
COL_PEDIDO = "Número de pedido JMS"
COL_BASE = "Código da base de entrega"
COL_BASE_NOME = "PDD de Entrega"
COL_E6 = "Tempo trânsito SC Destino->Base Entrega"
COL_E7 = "Tempo médio processamento Base Entrega"
COL_E8 = "Tempo médio Saída para Entrega->Entrega"

GEST_BASE = "Estação No."
GEST_RM = "Responsável da Região"
GEST_COORD = "Coordenador"
GEST_SUP = "Supervisor"
GEST_NOME = "Nome da base"

SEG_BASE = "Código da base"
SEG_CIDADE = "Cidade"

CARTA_PEDIDO = "Número de pedido JMS"
CARTA_CIDADE = "Cidade Destino"

ORLEAN = "ORLEAN DA SILVA DO NASCIMENTO"


def read_excel_fast(path: str | Path, usecols=None) -> pd.DataFrame:
    path = str(path)
    try:
        return pd.read_excel(path, sheet_name=0, usecols=usecols, engine="calamine")
    except Exception:
        return pd.read_excel(path, sheet_name=0, usecols=usecols, engine="openpyxl")


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").astype("Int64")


def normalizar_pedido(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def preparar_gestao(caminho_gestao: str | Path) -> pd.DataFrame:
    cols = [GEST_BASE, GEST_NOME, GEST_RM, GEST_COORD, GEST_SUP]
    gest = read_excel_fast(caminho_gestao, usecols=cols)
    gest[GEST_BASE] = normalizar_codigo(gest[GEST_BASE])
    gest = gest[gest[GEST_RM].astype(str).str.contains("ORLEAN", case=False, na=False)].copy()

    sup = gest[GEST_SUP].fillna("").astype(str).str.strip()
    coord = gest[GEST_COORD].fillna("").astype(str).str.strip()
    gest["S/C"] = sup.where(sup.ne(""), coord)
    gest["R/M"] = gest[GEST_RM].fillna(ORLEAN).astype(str).str.strip()

    gest = gest.dropna(subset=[GEST_BASE]).drop_duplicates(subset=[GEST_BASE], keep="last")
    return gest[[GEST_BASE, GEST_NOME, "R/M", "S/C"]]


def preparar_segmento(caminho_segmento: str | Path | None) -> pd.DataFrame | None:
    if not caminho_segmento:
        return None
    seg = read_excel_fast(caminho_segmento, usecols=[SEG_BASE, SEG_CIDADE])
    seg[SEG_BASE] = normalizar_codigo(seg[SEG_BASE])
    seg[SEG_CIDADE] = seg[SEG_CIDADE].fillna("").astype(str).str.strip()
    seg = seg.dropna(subset=[SEG_BASE])
    seg = seg[seg[SEG_CIDADE].ne("")]
    seg = seg.drop_duplicates(subset=[SEG_BASE], keep="last")
    return seg[[SEG_BASE, SEG_CIDADE]]


def preparar_carta(caminho_carta: str | Path | None) -> pd.DataFrame | None:
    if not caminho_carta:
        return None
    carta = read_excel_fast(caminho_carta, usecols=[CARTA_PEDIDO, CARTA_CIDADE])
    carta["_pedido_key"] = normalizar_pedido(carta[CARTA_PEDIDO])
    carta[CARTA_CIDADE] = carta[CARTA_CIDADE].fillna("").astype(str).str.strip()
    carta = carta[(carta["_pedido_key"] != "") & (carta[CARTA_CIDADE] != "")]
    carta = carta.drop_duplicates(subset=["_pedido_key"], keep="last")
    return carta[["_pedido_key", CARTA_CIDADE]]


def preparar_shipping(
    caminho_shipping: str | Path,
    gestao: pd.DataFrame,
    segmento: pd.DataFrame | None = None,
    carta: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [COL_DATA, COL_PEDIDO, COL_BASE, COL_BASE_NOME, COL_E6, COL_E7, COL_E8]
    ship = read_excel_fast(caminho_shipping, usecols=cols)

    ship[COL_BASE] = normalizar_codigo(ship[COL_BASE])
    ship["_pedido_key"] = normalizar_pedido(ship[COL_PEDIDO])
    ship = ship.merge(
        gestao,
        left_on=COL_BASE,
        right_on=GEST_BASE,
        how="inner",
        suffixes=("", "_gestao"),
    )

    if segmento is not None and not segmento.empty:
        ship = ship.merge(segmento, left_on=COL_BASE, right_on=SEG_BASE, how="left")
    else:
        ship[SEG_CIDADE] = ""

    if ship.empty:
        raise RuntimeError("Nenhum pacote das bases do R/M Orlean foi encontrado no arquivo.")

    ship[COL_DATA] = pd.to_datetime(ship[COL_DATA], errors="coerce").dt.date
    ship = ship.dropna(subset=[COL_DATA, COL_BASE])

    for c in [COL_E6, COL_E7, COL_E8]:
        ship[c] = pd.to_numeric(ship[c], errors="coerce").fillna(0.0)

    ship[COL_BASE_NOME] = ship[COL_BASE_NOME].fillna("").astype(str).str.strip()
    ship[GEST_NOME] = ship[GEST_NOME].fillna("").astype(str).str.strip()
    ship[SEG_CIDADE] = ship[SEG_CIDADE].fillna("").astype(str).str.strip()

    ship["base_final"] = ship[COL_BASE_NOME]
    faltou_nome = ship["base_final"].eq("")
    ship.loc[faltou_nome, "base_final"] = ship.loc[faltou_nome, GEST_NOME]
    ship.loc[ship["base_final"].eq(""), "base_final"] = ship.loc[ship["base_final"].eq(""), COL_BASE].astype(str)

    ship = ship.drop_duplicates(subset=[COL_DATA, COL_BASE, COL_PEDIDO], keep="last")

    agrupado = (
        ship.groupby([COL_DATA, COL_BASE, "base_final", "R/M", "S/C", SEG_CIDADE], dropna=False)
        .agg(
            pacotes=(COL_PEDIDO, "count"),
            soma_e6=(COL_E6, "sum"),
            soma_e7=(COL_E7, "sum"),
            soma_e8=(COL_E8, "sum"),
        )
        .reset_index()
    )
    agrupado["etapa_6_h"] = agrupado["soma_e6"] / agrupado["pacotes"]
    agrupado["etapa_7_h"] = agrupado["soma_e7"] / agrupado["pacotes"]
    agrupado["etapa_8_h"] = agrupado["soma_e8"] / agrupado["pacotes"]
    agrupado["total_6_8_h"] = (agrupado["soma_e6"] + agrupado["soma_e7"] + agrupado["soma_e8"]) / agrupado["pacotes"]

    cidades = pd.DataFrame()
    if carta is not None and not carta.empty:
        detalhe = ship.merge(carta, on="_pedido_key", how="inner")
        detalhe[CARTA_CIDADE] = detalhe[CARTA_CIDADE].fillna("").astype(str).str.strip()
        detalhe = detalhe[detalhe[CARTA_CIDADE].ne("")]
        if not detalhe.empty:
            cidades = (
                detalhe.groupby(
                    [COL_DATA, COL_BASE, "base_final", "R/M", "S/C", SEG_CIDADE, CARTA_CIDADE],
                    dropna=False,
                )
                .agg(
                    pacotes=(COL_PEDIDO, "count"),
                    soma_e8=(COL_E8, "sum"),
                )
                .reset_index()
            )
            cidades["etapa_8_h"] = cidades["soma_e8"] / cidades["pacotes"]

    return agrupado, cidades


def records_para_supabase(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "data": r[COL_DATA].isoformat(),
            "codigo_base": int(r[COL_BASE]),
            "base": str(r["base_final"]),
            "cidade": str(r[SEG_CIDADE] or ""),
            "rm": str(r["R/M"] or ""),
            "sc": str(r["S/C"] or ""),
            "etapa_6_h": round(float(r["etapa_6_h"]), 4),
            "etapa_7_h": round(float(r["etapa_7_h"]), 4),
            "etapa_8_h": round(float(r["etapa_8_h"]), 4),
            "total_6_8_h": round(float(r["total_6_8_h"]), 4),
            "pacotes": int(r["pacotes"]),
        })
    return out


def records_cidades_para_supabase(df: pd.DataFrame) -> list[dict]:
    out = []
    if df.empty:
        return out
    for _, r in df.iterrows():
        out.append({
            "data": r[COL_DATA].isoformat(),
            "codigo_base": int(r[COL_BASE]),
            "base": str(r["base_final"]),
            "cidade_base": str(r[SEG_CIDADE] or ""),
            "cidade_destino": str(r[CARTA_CIDADE] or ""),
            "rm": str(r["R/M"] or ""),
            "sc": str(r["S/C"] or ""),
            "etapa_8_h": round(float(r["etapa_8_h"]), 4),
            "pacotes": int(r["pacotes"]),
        })
    return out


def enviar_em_lotes(records: list[dict], tabela: str, on_conflict: str, lote: int = 500) -> None:
    supabase = get_supabase()
    for i in range(0, len(records), lote):
        supabase.table(tabela).upsert(records[i:i + lote], on_conflict=on_conflict).execute()


def resumo(df: pd.DataFrame, cidades: pd.DataFrame) -> None:
    pacotes = int(df["pacotes"].sum())
    s6 = float((df["etapa_6_h"] * df["pacotes"]).sum())
    s7 = float((df["etapa_7_h"] * df["pacotes"]).sum())
    s8 = float((df["etapa_8_h"] * df["pacotes"]).sum())
    datas = sorted(str(x) for x in df[COL_DATA].unique())

    print("=" * 70)
    print("IMPORTAÇÃO SHIPPING TIME - J&T")
    print("=" * 70)
    print(f"Datas:                       {', '.join(datas)}")
    print(f"Bases do Orlean com volume: {df[COL_BASE].nunique():,}")
    print(f"Total de pacotes:            {pacotes:,}")
    print(f"Etapa 6 média:               {s6 / pacotes:.2f} h")
    print(f"Etapa 7 média:               {s7 / pacotes:.2f} h")
    print(f"Etapa 8 média:               {s8 / pacotes:.2f} h")
    print(f"Shipping 6+7+8:              {(s6+s7+s8) / pacotes:.2f} h")
    print(f"Cidades-base mapeadas:       {df[SEG_CIDADE].fillna('').astype(str).str.strip().ne('').sum():,} bases")
    if not cidades.empty:
        print(f"Cidades destino mapeadas:    {cidades[CARTA_CIDADE].nunique():,}")
        print(f"Pacotes cruzados com carta:  {int(cidades['pacotes'].sum()):,}")
    else:
        print("Cidades destino mapeadas:    0 (carta de porte não encontrada/sem match)")
    print("=" * 70)


def localizar_arquivos() -> tuple[list[Path], Path, Path | None, Path | None]:
    pasta = Path.cwd()
    arquivos = [p for p in pasta.glob("*.xlsx") if not p.name.startswith("~$")]

    gestoes = sorted(
        [p for p in arquivos if "gestão de colaboradores" in p.name.casefold() or "gestao de colaboradores" in p.name.casefold()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not gestoes:
        raise FileNotFoundError("Não encontrei o arquivo 'Gestão de colaboradores.xlsx' na pasta atual.")
    gestao = gestoes[0]

    segmentos = sorted(
        [p for p in arquivos if "segundo segmento" in p.name.casefold()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    segmento = segmentos[0] if segmentos else None

    cartas = sorted(
        [p for p in arquivos if "carta de porte" in p.name.casefold()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    carta = cartas[0] if cartas else None

    shipping = sorted(
        [
            p for p in arquivos
            if ("全网时效分析" in p.name or "shipping time" in p.name.casefold() or "shipping_time" in p.name.casefold())
            and p not in {gestao, segmento, carta}
        ],
        key=lambda p: p.name.casefold(),
    )
    if not shipping:
        raise FileNotFoundError("Não encontrei nenhum arquivo de Shipping Time na pasta atual.")

    return shipping, gestao, segmento, carta


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa Shipping Time das bases do R/M Orlean")
    parser.add_argument("shipping", nargs="?", help="Arquivo Excel Shipping Time exportado do JMS")
    parser.add_argument("gestao", nargs="?", help="Arquivo Gestão de colaboradores")
    parser.add_argument("--segmento", default=None, help="Arquivo Segundo Segmento para mapear cidades-base")
    parser.add_argument("--carta", default=None, help="Arquivo Exportar carta de porte de entrega para mapear cidade destino")
    parser.add_argument("--dry-run", action="store_true", help="Valida e calcula sem enviar ao Supabase")
    args = parser.parse_args()

    shipping_auto, gestao_auto, segmento_auto, carta_auto = localizar_arquivos()
    shipping_files = [Path(args.shipping)] if args.shipping else shipping_auto
    gestao_path = Path(args.gestao) if args.gestao else gestao_auto
    segmento_path = Path(args.segmento) if args.segmento else segmento_auto
    carta_path = Path(args.carta) if args.carta else carta_auto

    print("=" * 70)
    print("ARQUIVOS LOCALIZADOS")
    print("=" * 70)
    print(f"Gestão:            {gestao_path.name}")
    print(f"Segundo Segmento:  {segmento_path.name if segmento_path else 'NÃO ENCONTRADO'}")
    print(f"Carta de porte:     {carta_path.name if carta_path else 'NÃO ENCONTRADA'}")
    print(f"Shipping Time:     {len(shipping_files)} arquivo(s)")
    for arq in shipping_files:
        print(f"  - {arq.name}")
    print("=" * 70)

    gestao = preparar_gestao(gestao_path)
    segmento = preparar_segmento(segmento_path) if segmento_path else None
    carta = preparar_carta(carta_path) if carta_path else None

    dfs: list[pd.DataFrame] = []
    dfs_cidades: list[pd.DataFrame] = []
    for caminho in shipping_files:
        print(f"\nProcessando: {caminho.name}")
        base_df, cidade_df = preparar_shipping(caminho, gestao, segmento, carta)
        dfs.append(base_df)
        if not cidade_df.empty:
            dfs_cidades.append(cidade_df)

    df = pd.concat(dfs, ignore_index=True)
    df = (
        df.sort_values([COL_DATA, COL_BASE])
        .drop_duplicates(subset=[COL_DATA, COL_BASE], keep="last")
        .reset_index(drop=True)
    )

    cidades = pd.concat(dfs_cidades, ignore_index=True) if dfs_cidades else pd.DataFrame()
    if not cidades.empty:
        cidades = (
            cidades.sort_values([COL_DATA, COL_BASE, CARTA_CIDADE])
            .drop_duplicates(subset=[COL_DATA, COL_BASE, CARTA_CIDADE], keep="last")
            .reset_index(drop=True)
        )

    resumo(df, cidades)

    if args.dry_run:
        print("DRY-RUN: nada foi enviado ao Supabase.")
        return

    records = records_para_supabase(df)
    enviar_em_lotes(records, "shipping_time_diario", "data,codigo_base")
    print(f"OK: {len(records)} registros de base/data enviados para shipping_time_diario.")

    city_records = records_cidades_para_supabase(cidades)
    if city_records:
        try:
            enviar_em_lotes(city_records, "shipping_time_cidade_diario", "data,codigo_base,cidade_destino")
            print(f"OK: {len(city_records)} registros base/cidade enviados para shipping_time_cidade_diario.")
        except Exception as exc:
            print("ATENÇÃO: base principal foi importada, mas o detalhamento por cidade não foi enviado.")
            print("Execute primeiro o SQL do arquivo supabase_shipping_cidades.sql no Supabase.")
            print(f"Detalhe: {exc}")


if __name__ == "__main__":
    main()
