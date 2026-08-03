"""
Módulo de Reportes (Sección 6 y 10 del PDF): un mini "dashboard" en consola
con los totales de la última semana y el listado de personas registradas.

Uso: python reporte.py
"""
import database


def main():
    database.init_db()
    r = database.reporte_semanal()

    print("=== TABLERO DE CONTROL: Últimos 7 días ===")
    print(f"Total de eventos:     {r['total']}")
    print(f"Accesos permitidos:   {r['permitidos']}")
    print(f"Accesos denegados:    {r['denegados']}")
    print("Por camino (A=reconocido, B=PIN residente, C=visita):")
    for camino, cant in r["por_camino"].items():
        print(f"  Camino {camino}: {cant}")

    print("\n=== Personas registradas ===")
    for p in database.listar_personas():
        negra = " [LISTA NEGRA]" if p["lista_negra"] else ""
        print(f"  #{p['label_lbph']:>3} {p['apellido']}, {p['nombre']} "
              f"- {p['categoria']} - depto {p['depto']}{negra}")


if __name__ == "__main__":
    main()
