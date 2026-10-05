"""
Normalización del nombre de país (jugadores.nacionalidad, equipos.pais) a
español, con un nombre canónico por país.

Por qué existe este módulo: se detectó que "nacionalidad" tenía mezcla de
idiomas y grafías según el origen del dato - acb.com siempre da el nombre
en español (confirmado), la API de Euroliga/EuroCup siempre lo da en
inglés (confirmado), y las altas manuales antiguas por CSV (anteriores al
scraper de ficha de ACB) se escribieron a mano con lo que tocara en cada
momento ("Croata"/"Croacia"/"Croatia" para el mismo país). Este módulo da
un único nombre canónico en español para cada variante conocida.

nombre_pais_es() admite tanto el nombre en inglés de la API de Euroliga
como las grafías en español ya usadas en este proyecto (para poder
normalizar lo que ya hay guardado, no solo lo nuevo). Si no reconoce un
valor, lo deja tal cual y avisa por print - para que un país nuevo que
aparezca se note en vez de perderse en silencio.
"""

# Clave: cualquier variante vista (inglés de la API de Euroliga, u otra
# grafía en español ya usada en este proyecto) en minúsculas sin tildes
# no es necesario - se compara tal cual, pero se listan las variantes
# literales encontradas. Valor: nombre canónico en español.
_CANONICO: dict[str, str] = {
    # España
    "Spain": "España", "España": "España",
    # Alemania
    "Germany": "Alemania", "Alemania": "Alemania",
    # Francia
    "France": "Francia", "Francia": "Francia",
    # Italia
    "Italy": "Italia", "Italia": "Italia",
    # Estados Unidos
    "United States of America": "Estados Unidos", "USA": "Estados Unidos",
    "EE.UU.": "Estados Unidos", "Estados Unidos": "Estados Unidos",
    # Reino Unido
    "United Kingdom": "Reino Unido", "Reino Unido": "Reino Unido",
    # Croacia
    "Croatia": "Croacia", "Croata": "Croacia", "Croacia": "Croacia",
    # Serbia / Bosnia / Montenegro / Eslovenia / Macedonia del Norte
    "Serbia": "Serbia",
    "Bosnia and Herzegovina": "Bosnia y Herzegovina", "Bosnia y Herzegovina": "Bosnia y Herzegovina",
    "Montenegro": "Montenegro",
    "Slovenia": "Eslovenia", "Eslovenia": "Eslovenia",
    "North Macedonia": "Macedonia del Norte", "Macedonia del Norte": "Macedonia del Norte",
    # Grecia / Turquía
    "Greece": "Grecia", "Grecia": "Grecia",
    "Turkiye": "Turquía", "Turkey": "Turquía", "Turquía": "Turquía",
    # Países bálticos
    "Latvia": "Letonia", "Letonia": "Letonia",
    "Lithuania": "Lituania", "Lituania": "Lituania",
    "Estonia": "Estonia",
    # Europa central/este
    "Poland": "Polonia", "Polonia": "Polonia",
    "Czech Republic": "República Checa", "República Checa": "República Checa",
    "Slovakia": "Eslovaquia", "Eslovaquia": "Eslovaquia",
    "Hungary": "Hungría", "Hungría": "Hungría",
    "Romania": "Rumanía", "Rumanía": "Rumanía",
    "Bulgaria": "Bulgaria",
    "Ukraine": "Ucrania", "Ucrania": "Ucrania",
    "Belarus": "Bielorrusia", "Bielorrusia": "Bielorrusia",
    "Moldova": "Moldavia", "Moldavia": "Moldavia",
    "Russia": "Rusia", "Rusia": "Rusia", "Russian Federation": "Rusia",
    "Armenia": "Armenia", "Georgia": "Georgia", "Azerbaijan": "Azerbaiyán", "Azerbaiyán": "Azerbaiyán",
    "Kosovo": "Kosovo",
    # Europa occidental/norte
    "Belgium": "Bélgica", "Bélgica": "Bélgica",
    "Netherlands": "Países Bajos", "Países Bajos": "Países Bajos",
    "Switzerland": "Suiza", "Suiza": "Suiza",
    "Austria": "Austria",
    "Portugal": "Portugal",
    "Ireland": "Irlanda", "Irlanda": "Irlanda",
    "Denmark": "Dinamarca", "Dinamarca": "Dinamarca",
    "Sweden": "Suecia", "Suecia": "Suecia",
    "Norway": "Noruega", "Noruega": "Noruega",
    "Finland": "Finlandia", "Finlandia": "Finlandia",
    "Iceland": "Islandia", "Islandia": "Islandia",
    "Luxembourg": "Luxemburgo", "Malta": "Malta", "Cyprus": "Chipre",
    "Monaco": "Mónaco", "Andorra": "Andorra", "San Marino": "San Marino", "Liechtenstein": "Liechtenstein",
    # Israel
    "Israel": "Israel",
    # África
    "Angola": "Angola", "Cameroon": "Camerún", "Congo": "Congo",
    "Gabon": "Gabón", "Gambia": "Gambia", "Guinea": "Guinea",
    "Mali": "Mali", "Nigeria": "Nigeria", "Senegal": "Senegal",
    "South Africa": "Sudáfrica", "Sudáfrica": "Sudáfrica",
    "South Sudan": "Sudán del Sur", "Sudan": "Sudán",
    "Cabo Verde": "Cabo Verde", "Egypt": "Egipto", "Tunisia": "Túnez", "Morocco": "Marruecos",
    "Ivory Coast": "Costa de Marfil", "DR Congo": "República Democrática del Congo",
    "Ethiopia": "Etiopía", "Kenya": "Kenia", "Ghana": "Ghana", "Tanzania": "Tanzania",
    "Zambia": "Zambia", "Zimbabwe": "Zimbabue", "Mozambique": "Mozambique",
    "Guinea-Bissau": "Guinea-Bisáu", "Equatorial Guinea": "Guinea Ecuatorial",
    "Sierra Leone": "Sierra Leona", "Burkina Faso": "Burkina Faso", "Niger": "Níger",
    "Chad": "Chad", "Libya": "Libia", "Algeria": "Argelia",
    # América
    "Argentina": "Argentina", "Brazil": "Brasil", "Canada": "Canadá", "Canadá": "Canadá",
    "Chile": "Chile", "Mexico": "México", "Uruguay": "Uruguay",
    "Dominican Republic": "República Dominicana", "República Dominicana": "República Dominicana",
    "Cuba": "Cuba", "Jamaica": "Jamaica", "Bahamas": "Bahamas", "Barbados": "Barbados",
    "Antigua and Barbuda": "Antigua y Barbuda", "Panama": "Panamá",
    "Puerto Rico": "Puerto Rico", "Venezuela": "Venezuela", "Colombia": "Colombia",
    "Bolivia": "Bolivia", "Paraguay": "Paraguay", "Ecuador": "Ecuador", "Peru": "Perú",
    "Guatemala": "Guatemala", "Honduras": "Honduras", "El Salvador": "El Salvador",
    "Nicaragua": "Nicaragua", "Costa Rica": "Costa Rica", "Haiti": "Haití",
    "Trinidad and Tobago": "Trinidad y Tobago",
    # Oceanía / Asia
    "Australia": "Australia", "New Zealand": "Nueva Zelanda",
    "China": "China", "Japan": "Japón", "South Korea": "Corea del Sur", "Philippines": "Filipinas",
    "United Arab Emirates": "Emiratos Árabes Unidos", "Emiratos Árabes Unidos": "Emiratos Árabes Unidos",
    "Saudi Arabia": "Arabia Saudí", "Qatar": "Catar", "Lebanon": "Líbano", "Jordan": "Jordania",
}


def nombre_pais_es(valor: str | None) -> str | None:
    """Devuelve el nombre canónico en español de un país a partir de
    cualquier variante conocida (inglés de la API de Euroliga, u otra
    grafía en español ya vista en este proyecto). Si no se reconoce, se
    deja tal cual (no se pierde el dato) y se avisa por print."""
    if not valor:
        return valor
    canonico = _CANONICO.get(valor)
    if canonico is None:
        print(f"  [aviso] país '{valor}' no está en el catálogo de scraping/paises.py - se deja tal cual.")
        return valor
    return canonico
