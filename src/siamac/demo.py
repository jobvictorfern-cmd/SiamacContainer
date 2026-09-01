"""Roda a portaria inteira em simulação e mede o que a fusão ganha.

    python -m siamac.demo --events 2000

A pergunta que este script responde é a premissa central do plano: *três
câmeras votando valem mais do que a melhor câmera sozinha?* Ele mede as duas
configurações sobre exatamente os mesmos eventos e imprime a diferença,
incluindo o número que mais importa — o **erro silencioso**, o código errado
que o sistema aceitou sem avisar ninguém.
"""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict

from .cameras import (
    CONDITIONS,
    PROJECT_CAMERAS,
    SimulatedCamera,
    pick_condition,
    px_per_char,
)
from .fusion import Decision, fuse
from .iso6346 import EQUIPMENT_CATEGORIES, check_digit
from .ocr.simulated import SimulatedOcr, error_rate_for
from .pipeline import Pipeline, PipelineConfig

OWNER_PREFIXES = [
    "MSC", "MAE", "CMA", "HLC", "OOL", "EGH", "COS", "EVE",
    "TGH", "TCN", "SUD", "APL", "ONE", "YML", "ZIM", "TRL",
]


def random_code(rng: random.Random) -> str:
    owner = rng.choice(OWNER_PREFIXES)
    category = rng.choice(sorted(EQUIPMENT_CATEGORIES))
    serial = f"{rng.randrange(1_000_000):06d}"
    body = f"{owner}{category}{serial}"
    return f"{body}{check_digit(body)}"


def _bar(frac: float, width: int = 26) -> str:
    filled = round(frac * width)
    return "█" * filled + "·" * (width - filled)


def build_cameras(side_dist: float, side_offset: float, rear_dist: float):
    """Monta o arranjo com a geometria pedida, mantendo a óptica de cada modelo."""
    from dataclasses import replace

    specs = []
    for spec in PROJECT_CAMERAS:
        if spec.name == "rear":
            specs.append(replace(spec, distance_m=rear_dist))
        else:
            specs.append(replace(spec, distance_m=side_dist, offset_m=side_offset))
    return specs


def run(
    events: int,
    seed: int,
    verbose: int,
    *,
    side_dist: float,
    side_offset: float,
    rear_dist: float,
) -> int:
    rng = random.Random(seed)
    specs = build_cameras(side_dist, side_offset, rear_dist)
    cameras = [SimulatedCamera(s) for s in specs]
    ocr = SimulatedOcr(seed=seed)
    config = PipelineConfig()
    pipe = Pipeline(cameras, ocr, config=config, rng=rng)

    print("\n\033[1mSiamacContainer — simulação da portaria\033[0m")
    print(f"{events} eventos · semente {seed}\n")

    print("  \033[2mCâmera    projeção   dist.   desloc.   px/caractere   erro/caractere\033[0m")
    for spec in specs:
        px = px_per_char(spec)
        print(
            f"  {spec.name:<9} {spec.projection:<10} "
            f"{spec.distance_m:>4.1f}m   {spec.offset_m:>5.1f}m   "
            f"{px:>9.1f} px   {error_rate_for(px) * 100:>10.1f}%"
        )

    stats: dict[str, Counter] = {"fusion": Counter(), "rear_only": Counter()}
    by_condition: dict[str, Counter] = defaultdict(Counter)
    wrong_examples: list[tuple[str, str, str]] = []

    for _ in range(events):
        truth = random_code(rng)
        cond = pick_condition(rng)
        processed = pipe.process(truth=truth, condition=cond, persist=False)

        by_condition[cond[0]]["total"] += 1

        for label, result in (
            ("fusion", processed.fusion),
            (
                "rear_only",
                fuse(
                    [r for r in processed.reads if r.camera == "rear"],
                    min_confidence=config.min_confidence,
                    min_agreement=0.0,
                    # Linha de base: mede o reconhecedor numa câmera só, sem a
                    # política que manda leitura sem árbitro para revisão.
                    require_multi_camera=False,
                ),
            ),
        ):
            s = stats[label]
            s["total"] += 1
            accepted = result.decision is Decision.AUTO_ACCEPT
            correct = result.code == truth

            if accepted and correct:
                s["auto_ok"] += 1
                if label == "fusion":
                    by_condition[cond[0]]["auto_ok"] += 1
            elif accepted and not correct:
                s["silent_error"] += 1
                if label == "fusion":
                    by_condition[cond[0]]["silent_error"] += 1
                    if len(wrong_examples) < 6:
                        wrong_examples.append(
                            (truth, result.code, ", ".join(
                                f"{c}={t}" for c, t in result.per_camera.items()
                            ))
                        )
            else:
                s["review"] += 1
                if correct:
                    s["review_but_right"] += 1
                if label == "fusion":
                    by_condition[cond[0]]["review"] += 1

    # ------------------------------------------------------------------
    print("\n\033[1m  Resultado\033[0m")
    print("  \033[2m                        auto-aceite correto   erro silencioso   revisão\033[0m")
    for label, title in (("rear_only", "só a 4K do fundo"), ("fusion", "as 3 câmeras")):
        s = stats[label]
        t = s["total"] or 1
        auto = s["auto_ok"] / t
        silent = s["silent_error"] / t
        review = s["review"] / t
        mark = "\033[1m" if label == "fusion" else ""
        end = "\033[0m" if label == "fusion" else ""
        print(
            f"  {mark}{title:<22}{auto * 100:>10.1f}%{silent * 100:>18.2f}%"
            f"{review * 100:>10.1f}%{end}"
        )

    f, r = stats["fusion"], stats["rear_only"]
    t = f["total"] or 1
    d_auto = (f["auto_ok"] - r["auto_ok"]) / t * 100
    d_silent = (f["silent_error"] - r["silent_error"]) / t * 100
    print(
        f"\n  \033[1mGanho da fusão:\033[0m auto-aceite {d_auto:+.1f} pp · "
        f"erro silencioso {d_silent:+.2f} pp"
    )

    kpi = f["silent_error"] / t * 100
    verdict = "\033[32mdentro\033[0m" if kpi <= 0.5 else "\033[31mACIMA\033[0m"
    print(f"  KPI crítico (erro silencioso ≤ 0,50%): {kpi:.2f}% — {verdict}")

    # ------------------------------------------------------------------
    print("\n\033[1m  Auto-aceite por condição de luz\033[0m")
    for name, _diff, _w in sorted(CONDITIONS, key=lambda c: -c[2]):
        c = by_condition.get(name)
        if not c or not c["total"]:
            continue
        frac = c["auto_ok"] / c["total"]
        print(
            f"  {name:<24} {_bar(frac)} {frac * 100:>5.1f}%   "
            f"\033[2m({c['total']} eventos, {c['silent_error']} erro silencioso)\033[0m"
        )

    if verbose and wrong_examples:
        print("\n\033[1m  Erros silenciosos — o que passou\033[0m")
        for truth, got, per_cam in wrong_examples:
            print(f"  esperado {truth}  ·  aceito \033[31m{got}\033[0m")
            print(f"    \033[2m{per_cam}\033[0m")

    print()
    return 0 if kpi <= 0.5 else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="siamac-demo", description=__doc__)
    ap.add_argument("--events", type=int, default=2000, help="quantos eventos simular")
    ap.add_argument("--seed", type=int, default=7, help="semente, para reprodutibilidade")
    ap.add_argument("-v", "--verbose", action="count", default=0)
    ap.add_argument("--side-dist", type=float, default=3.5,
                    metavar="M", help="distância das laterais até a face (m)")
    ap.add_argument("--side-offset", type=float, default=2.0,
                    metavar="M", help="deslocamento longitudinal até o código (m)")
    ap.add_argument("--rear-dist", type=float, default=6.0,
                    metavar="M", help="distância da 4K até as portas (m)")
    args = ap.parse_args()
    return run(
        args.events, args.seed, args.verbose,
        side_dist=args.side_dist,
        side_offset=args.side_offset,
        rear_dist=args.rear_dist,
    )


if __name__ == "__main__":
    raise SystemExit(main())
