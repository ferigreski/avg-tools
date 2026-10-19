"""Resumen mensual y acumulado de ventas diarias."""

import pandas as pd


def resumir_ventas(ventas: list[dict]) -> pd.DataFrame:
    """Suma ventas por año y mes y calcula el acumulado cronológico.

    Cada diccionario debe contener ``fecha`` (AAAA-MM-DD) y ``venta``.
    Solo incluye meses con ventas registradas.
    """
    if not ventas:
        return pd.DataFrame(columns=["mes", "total_ventas", "total_acumulado"])

    datos = pd.DataFrame(ventas)
    datos["fecha"] = pd.to_datetime(datos["fecha"], format="%Y-%m-%d", errors="raise")
    datos["venta"] = pd.to_numeric(datos["venta"], errors="raise")
    if datos[["fecha", "venta"]].isna().any().any():
        raise ValueError("Cada venta debe tener una fecha y un importe válidos.")

    resumen = (
        datos.groupby(datos["fecha"].dt.to_period("M"), sort=True)["venta"]
        .sum()
        .rename_axis("mes")
        .reset_index(name="total_ventas")
    )
    resumen["total_acumulado"] = resumen["total_ventas"].cumsum()
    return resumen


def main() -> None:
    ventas = [
        {"fecha": "2026-03-02", "venta": 300},
        {"fecha": "2026-01-05", "venta": 100},
        {"fecha": "2026-02-10", "venta": 200},
        {"fecha": "2026-01-20", "venta": 150},
        {"fecha": "2026-03-15", "venta": 50},
        {"fecha": "2026-02-25", "venta": 75},
    ]
    print(resumir_ventas(ventas).to_string(index=False))


if __name__ == "__main__":
    main()
