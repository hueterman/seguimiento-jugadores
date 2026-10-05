"""
Aplicación Flask de formularios manuales: jugadores, equipos, lesiones y
datos económicos. Estructura básica — sin autenticación ni estilos avanzados.
"""
from flask import Flask

from formularios.routes import routes


def _num(valor, decimales: int = 1) -> str:
    """Formatea un número para la plantilla: '-' si es None, sin decimales
    si es un entero exacto (66.0 -> '66'), con los decimales pedidos si no
    (19.1 -> '19.1'). Evita el '66.0' feo de columnas REAL que guardan
    tanto enteros como decimales."""
    if valor is None:
        return "-"
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if numero == int(numero):
        return str(int(numero))
    return f"{numero:.{decimales}f}"


def crear_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(routes)
    app.jinja_env.filters["num"] = _num
    return app


if __name__ == "__main__":
    crear_app().run(debug=True, port=5500)
