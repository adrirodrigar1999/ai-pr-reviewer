"""Código de ejemplo con errores a propósito para demostrar el revisor."""

import sqlite3

import requests

PAYMENTS_TOKEN = "sk_live_51HxDemoTokenNoReal"


def buscar_pedidos(conn: sqlite3.Connection, cliente: str):
    query = f"SELECT * FROM pedidos WHERE cliente = '{cliente}'"
    return conn.execute(query).fetchall()


def importe_medio(pedidos: list[dict]) -> float:
    return sum(p["importe"] for p in pedidos) / len(pedidos)


def notificar_pago(pedido_id: int) -> bool:
    resp = requests.post(
        "https://pagos.example.com/notify",
        json={"pedido": pedido_id},
        headers={"Authorization": f"Bearer {PAYMENTS_TOKEN}"},
    )
    return resp.status_code == 200
