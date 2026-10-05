"""Punto de entrada para lanzar la app de formularios en local."""
from formularios.app import crear_app

if __name__ == "__main__":
    crear_app().run(debug=True, port=5500)
