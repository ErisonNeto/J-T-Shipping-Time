from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

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

ORLEAN = "ORLEAN DA SILVA DO NASCIMENTO"


def read_excel_fast(path: str | Path, usecols=None) -> pd.DataFrame:
    path = str(path)
    try:
        return pd.read_excel(path, sheet_name=0, usecols=usecols, engine="calamine")
    except Exception:
        return pd.read_excel(path, sheet_name=0, usecols=usecols, engine="openpyxl")


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").astype("Int64")


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


def preparar_shipping(caminho_shipping: str | Path, gestao: pd.DataFrame) -> pd.DataFrame:
    cols = [COL_DATA, COL_PEDIDO, COL_BASE, COL_BASE_NOME, COL_E6, COL_E7, COL_E8]
    ship = read_excel_fast(caminho_shipping, usecols=cols)

    ship[COL_BASE] = normalizar_codigo(ship[COL_BASE])
    ship = ship.merge(
        gestao,
        left_on=COL_BASE,
        right_on=GEST_BASE,
        how="inner",
        suffixes=("", "_gestao"),
    )

    if ship.empty:
        raise RuntimeError("Nenhum pacote das bases do R/M Orlean foi encontrado no arquivo.")

    ship[COL_DATA] = pd.to_datetime(ship[COL_DATA], errors="coerce").dt.date
    ship = ship.dropna(subset=[COL_DATA, COL_BASE])

    # Regra informada: soma de AM/AP/AQ dividida pelo total de pacotes.
    # Portanto vazios entram como 0 no somatório, mas continuam no denominador.
    for c in [COL_E6, COL_E7, COL_E8]:
        ship[c] = pd.to_numeric(ship[c], errors="coerce").fillna(0.0)

    ship["base_final"] = (
        ship[COL_BASE_NOME]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    faltou_nome = ship["base_final"].eq("")
    ship.loc[faltou_nome, "base_final"] = (
        ship.loc[faltou_nome, GEST_NOME].fillna("").astype(str).str.strip()
    )
    ship.loc[ship["base_final"].eq(""), "base_final"] = ship.loc[
        ship["base_final"].eq(""), COL_BASE
    ].astype(str)

    # Um pedido por linha é o padrão, mas removemos duplicata do mesmo pedido/data/base por segurança.
    ship = ship.drop_duplicates(subset=[COL_DATA, COL_BASE, COL_PEDIDO], keep="last")

    agrupado = (
        ship.groupby([COL_DATA, COL_BASE, "base_final", "R/M", "S/C"], dropna=False)
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
    agrupado["total_6_8_h"] = (
        agrupado["soma_e6"] + agrupado["soma_e7"] + agrupado["soma_e8"]
    ) / agrupado["pacotes"]

    return agrupado


def records_para_supabase(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        out.append(
            {
                "data": r[COL_DATA].isoformat(),
                "codigo_base": int(r[COL_BASE]),
                "base": str(r["base_final"]),
                "rm": str(r["R/M"] or ""),
                "sc": str(r["S/C"] or ""),
                "etapa_6_h": round(float(r["etapa_6_h"]), 4),
                "etapa_7_h": round(float(r["etapa_7_h"]), 4),
                "etapa_8_h": round(float(r["etapa_8_h"]), 4),
                "total_6_8_h": round(float(r["total_6_8_h"]), 4),
                "pacotes": int(r["pacotes"]),
            }
        )
    return out


def enviar_em_lotes(records: list[dict], lote: int = 500) -> None:
    supabase = get_supabase()
    for i in range(0, len(records), lote):
        parte = records[i : i + lote]
        (
            supabase.table("shipping_time_diario")
            .upsert(parte, on_conflict="data,codigo_base")
            .execute()
        )


def resumo(df: pd.DataFrame) -> None:
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
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa Shipping Time das bases do R/M Orlean")
    parser.add_argument("shipping", help="Arquivo Excel Shipping Time exportado do JMS")
    parser.add_argument("gestao", help="Arquivo Gestão de colaboradores")
    parser.add_argument("--dry-run", action="store_true", help="Valida e calcula sem enviar ao Supabase")
    args = parser.parse_args()

    gestao = preparar_gestao(args.gestao)
    df = preparar_shipping(args.shipping, gestao)
    resumo(df)

    if args.dry_run:
        print("DRY-RUN: nada foi enviado ao Supabase.")
        return

    records = records_para_supabase(df)
    enviar_em_lotes(records)
    print(f"OK: {len(records)} registros de base/data enviados para shipping_time_diario.")


if __name__ == "__main__":
    main()
