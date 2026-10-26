from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import get_supabase

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="J&T Shipping Time")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

META_E6 = 25.6
META_E7 = 6.0
META_E8 = 23.4


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


def buscar(data_inicial: str | None = None, data_final: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("shipping_time_diario").select("*")
    if data_inicial:
        q = q.gte("data", data_inicial)
    if data_final:
        q = q.lte("data", data_final)
    return q.execute().data or []


def filtrar(
    rows: list[dict],
    sc: str | None = None,
    cidade: str | None = None,
    base: str | None = None,
) -> list[dict]:
    out = rows
    if sc:
        alvo = sc.strip().casefold()
        out = [r for r in out if (r.get("sc") or "").strip().casefold() == alvo]
    if cidade:
        alvo = cidade.strip().casefold()
        out = [r for r in out if (r.get("cidade") or "").strip().casefold() == alvo]
    if base:
        alvo = base.strip().casefold()
        out = [r for r in out if (r.get("base") or "").strip().casefold() == alvo]
    return out


def validar_periodo(data_inicial: str, data_final: str):
    if data_inicial > data_final:
        raise HTTPException(400, "Data inicial não pode ser maior que a data final")


@app.get("/api/datas")
def datas():
    sb = get_supabase()
    rows = (
        sb.table("shipping_time_diario")
        .select("data")
        .order("data", desc=True)
        .limit(10000)
        .execute()
        .data
        or []
    )
    return sorted({r["data"] for r in rows if r.get("data")}, reverse=True)


@app.get("/api/filtros")
def filtros(data_inicial: str = Query(...), data_final: str = Query(...)):
    validar_periodo(data_inicial, data_final)
    rows = buscar(data_inicial, data_final)
    scs = sorted({(r.get("sc") or "SEM S/C").strip() for r in rows if (r.get("sc") or "").strip()})

    bases_ag: dict[tuple[str, str, str], dict] = {}
    cidades = set()
    for r in rows:
        nome = (r.get("base") or "").strip()
        if not nome:
            continue
        sc = (r.get("sc") or "SEM S/C").strip()
        cidade = (r.get("cidade") or "").strip()
        if cidade:
            cidades.add(cidade)
        key = (nome, sc, cidade)
        a = bases_ag.setdefault(key, {
            "base": nome,
            "codigo_base": r.get("codigo_base"),
            "sc": sc,
            "cidade": cidade,
            "pacotes": 0,
        })
        a["pacotes"] += int(r.get("pacotes") or 0)

    bases = sorted(bases_ag.values(), key=lambda x: (x["base"].casefold(), x["cidade"].casefold()))
    return {"scs": scs, "cidades": sorted(cidades, key=str.casefold), "bases": bases}


@app.get("/api/kpis")
def kpis(
    data_inicial: str = Query(...),
    data_final: str = Query(...),
    sc: str | None = None,
    cidade: str | None = None,
    base: str | None = None,
):
    validar_periodo(data_inicial, data_final)
    rows = filtrar(buscar(data_inicial, data_final), sc=sc, cidade=cidade, base=base)
    if not rows:
        raise HTTPException(404, "Sem dados para os filtros selecionados")

    total_pacotes = sum(int(r.get("pacotes") or 0) for r in rows)
    if total_pacotes == 0:
        raise HTTPException(404, "Seleção sem pacotes")

    s6 = sum(float(r.get("etapa_6_h") or 0) * int(r.get("pacotes") or 0) for r in rows)
    s7 = sum(float(r.get("etapa_7_h") or 0) * int(r.get("pacotes") or 0) for r in rows)
    s8 = sum(float(r.get("etapa_8_h") or 0) * int(r.get("pacotes") or 0) for r in rows)

    e6, e7, e8 = s6 / total_pacotes, s7 / total_pacotes, s8 / total_pacotes
    total_medio = (s6 + s7 + s8) / total_pacotes

    etapas = [
        ("Etapa 6", e6, META_E6),
        ("Etapa 7", e7, META_E7),
        ("Etapa 8", e8, META_E8),
    ]
    gargalo = max(etapas, key=lambda x: (x[1] / x[2]) if x[2] else 0)

    bases_unicas = {(r.get("codigo_base"), r.get("base")) for r in rows}

    return {
        "pacotes": total_pacotes,
        "bases": len(bases_unicas),
        "etapa_6": round(e6, 2),
        "etapa_7": round(e7, 2),
        "etapa_8": round(e8, 2),
        "total_6_8": round(total_medio, 2),
        "gargalo": gargalo[0],
        "gargalo_h": round(gargalo[1], 2),
    }


@app.get("/api/piores-bases")
def piores_bases(
    data_inicial: str = Query(...),
    data_final: str = Query(...),
    etapa: int = Query(..., ge=6, le=8),
    limite: int = Query(0, ge=0, le=500),
    sc: str | None = None,
    cidade: str | None = None,
    base: str | None = None,
):
    validar_periodo(data_inicial, data_final)
    rows = filtrar(buscar(data_inicial, data_final), sc=sc, cidade=cidade, base=base)
    campo = f"etapa_{etapa}_h"

    ag: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        nome = (r.get("base") or "SEM BASE").strip()
        nome_sc = (r.get("sc") or "SEM S/C").strip()
        cidade_nome = (r.get("cidade") or "").strip()
        key = (nome, nome_sc, cidade_nome)
        p = int(r.get("pacotes") or 0)
        a = ag.setdefault(key, {
            "base": nome,
            "codigo_base": r.get("codigo_base"),
            "cidade": cidade_nome,
            "sc": nome_sc,
            "pacotes": 0,
            "soma_ponderada": 0.0,
        })
        a["pacotes"] += p
        a["soma_ponderada"] += float(r.get(campo) or 0) * p

    arr = []
    for a in ag.values():
        p = a["pacotes"]
        horas = a["soma_ponderada"] / p if p else 0
        arr.append({
            "base": a["base"],
            "codigo_base": a["codigo_base"],
            "cidade": a["cidade"],
            "sc": a["sc"],
            "pacotes": p,
            "horas": round(horas, 2),
        })

    arr.sort(key=lambda x: (x["horas"], x["pacotes"]), reverse=True)
    return arr if limite == 0 else arr[:limite]


@app.get("/api/piores-sc")
def piores_sc(
    data_inicial: str = Query(...),
    data_final: str = Query(...),
    limite: int = Query(0, ge=0, le=500),
    sc: str | None = None,
    cidade: str | None = None,
    base: str | None = None,
):
    validar_periodo(data_inicial, data_final)
    rows = filtrar(buscar(data_inicial, data_final), sc=sc, cidade=cidade, base=base)
    ag: dict[str, dict] = {}
    for r in rows:
        nome_sc = (r.get("sc") or "SEM S/C").strip()
        p = int(r.get("pacotes") or 0)
        a = ag.setdefault(nome_sc, {"sc": nome_sc, "pacotes": 0, "bases_set": set(), "s6": 0.0, "s7": 0.0, "s8": 0.0})
        a["pacotes"] += p
        a["bases_set"].add((r.get("codigo_base"), r.get("base")))
        a["s6"] += float(r.get("etapa_6_h") or 0) * p
        a["s7"] += float(r.get("etapa_7_h") or 0) * p
        a["s8"] += float(r.get("etapa_8_h") or 0) * p

    out = []
    for a in ag.values():
        p = a["pacotes"] or 1
        e6, e7, e8 = a["s6"] / p, a["s7"] / p, a["s8"] / p
        out.append({
            "sc": a["sc"],
            "bases": len(a["bases_set"]),
            "pacotes": a["pacotes"],
            "etapa_6": round(e6, 2),
            "etapa_7": round(e7, 2),
            "etapa_8": round(e8, 2),
            "total": round(e6 + e7 + e8, 2),
        })
    out.sort(key=lambda x: (x["total"], x["pacotes"]), reverse=True)
    return out if limite == 0 else out[:limite]


@app.get("/api/evolutivo")
def evolutivo(
    data_inicial: str = Query(...),
    data_final: str = Query(...),
    sc: str | None = None,
    cidade: str | None = None,
    base: str | None = None,
):
    validar_periodo(data_inicial, data_final)
    rows = filtrar(buscar(data_inicial, data_final), sc=sc, cidade=cidade, base=base)
    por_data: dict[str, dict] = {}
    for r in rows:
        d = r.get("data")
        p = int(r.get("pacotes") or 0)
        a = por_data.setdefault(d, {"data": d, "pacotes": 0, "s6": 0.0, "s7": 0.0, "s8": 0.0})
        a["pacotes"] += p
        a["s6"] += float(r.get("etapa_6_h") or 0) * p
        a["s7"] += float(r.get("etapa_7_h") or 0) * p
        a["s8"] += float(r.get("etapa_8_h") or 0) * p

    out = []
    for a in por_data.values():
        p = a["pacotes"] or 1
        e6, e7, e8 = a["s6"] / p, a["s7"] / p, a["s8"] / p
        out.append({
            "data": a["data"],
            "pacotes": a["pacotes"],
            "etapa_6": round(e6, 2),
            "etapa_7": round(e7, 2),
            "etapa_8": round(e8, 2),
            "total": round(e6 + e7 + e8, 2),
        })
    return sorted(out, key=lambda x: x["data"])
