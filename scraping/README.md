# Scraping de estadísticas y trayectoria (fuente: acb.com)

Confirmado sobre un jugador real (Luka Bozic, slug `luka-bozic-30003420`,
`editionId=90`):

- `https://acb.com/es/liga/jugadores/<slug>/temporada?editionId=<id>`
  Tabla con una fila por temporada + "Totales"/"Promedios" de carrera al
  final. Un único request trae el historial completo (no hace falta
  repetir por temporada). `estadisticas.py` la parsea con `pandas.read_html`
  (funciona a partir de la estructura real de `<table>`/`colspan`, no de
  nombres de clase CSS).

- `https://acb.com/es/liga/jugadores/<slug>/trayectoria?editionId=<id>`
  No es una tabla — es texto repetido "AAAA - AAAA" seguido del nombre del
  equipo. `trayectoria.py` lo busca por patrón de texto en vez de por
  selector CSS. Un único request trae el historial completo.

- El slug de acb.com termina en el ID numérico interno del jugador
  (`luka-bozic-30003420` -> `30003420`). `actualizar_jugador.py` lo guarda
  en `jugadores.id_externo_acb`, por si algún día hace falta volver a
  consultar la misma ficha sin tener que buscar el slug de nuevo.

## Confirmado con ejecución real contra acb.com

Probado el 2026-10-02 sobre Luka Bozic (`jugador_id` existente,
`luka-bozic-30003420`): 2 temporadas y 2 etapas de trayectoria guardadas
correctamente, con valores coincidentes con los promedios publicados en
su ficha (p. ej. 2025-2026: 34 PJ, 16,2 puntos, 6,6 rebotes, 3,1
asistencias, 24,3 de valoración).

acb.com repite en la página de temporadas una tabla-plantilla vacía antes
de la tabla real con los datos (misma cabecera, 0 filas). Por eso
`_localizar_tabla_temporadas()` en `estadisticas.py` no elige la tabla por
número de columnas, sino por tener una fila "Totales" en la primera
columna — es robusto tanto a la tabla duplicada como a un cambio en el
número de columnas. Si algún día la página cambia y el número de columnas
real no coincide con la lista `COLUMNAS`, la función imprime un aviso con
la cabecera real detectada por pandas en vez de guardar datos mal
mapeados o fallar con un error críptico.

## Cosas a saber

- La tabla de temporadas da **promedios por partido** para casi todo
  (puntos, rebotes, asistencias, tiros Con/Int, "5i", mates...), no
  totales de temporada — la única excepción confirmada son "Par"
  (partidos jugados) y "V"/"D" (victorias/derrotas, cuya suma coincide
  con "Par"). Todos los campos `_totales`/`_convertidos`/`_intentados` en
  `estadisticas_temporada` que no sean esos se calculan como
  `promedio × partidos_jugados` redondeado — son una estimación, no el
  dato exacto de la fuente (se avisa de esto también en la ficha del
  jugador).
- La columna "5i" se guarda en `partidos_titular` (estimado igual que el
  resto) bajo la hipótesis de que es la frecuencia de quinteto inicial
  por partido — no se ha podido confirmar al 100% qué mide exactamente.
- `guardar_trayectoria()` no comprueba duplicados: ejecutarlo dos veces
  para el mismo jugador añade filas repetidas.
- Los equipos se crean automáticamente por nombre (`obtener_o_crear_equipo`
  en `db/conexion.py`) si no existen todavía.
- Lo que **no** cubre este scraper: partidos individuales (la página solo
  da promedios de temporada, no hay boxscore por partido).

## Totales de carrera ("Totales"/"Promedios")

Las dos filas finales de la tabla de temporadas (el acumulado de toda la
carrera del jugador en esa competición) se capturan por separado con
`parsear_carrera()`/`scrapear_carrera()` y se guardan en
`estadisticas_carrera` con `guardar_estadisticas_carrera()`. A diferencia
de las temporadas sueltas, aquí **no se estima nada**: son los valores
reales que publica acb.com — "Totales" son sumas reales de toda la
carrera, "Promedios" el promedio real por partido de toda la carrera.

Confirmado con datos reales (Luka Bozic, 66 partidos en ACB): acb.com usa
el punto como separador de miles en estos agregados (p. ej. "1.260" de
valoración = 1260, no 1,26) — `_a_numero()` ya lo tiene en cuenta.

**acb.com no es consistente con el separador decimal, incluso dentro de
la misma columna**: comprobado con `scraping/diagnosticar_5i.py` que, en
la columna "5i", las filas de temporada llegan como texto con PUNTO
decimal (`'0.9'`, `'0.5'`) mientras que la fila "Promedios" llega con
COMA (`'0,7'`) y "Totales" como entero sin separador (`'48'`) — las tres
en la misma columna, en el mismo `read_html()`. `_a_numero()` distingue
miles de decimales por la FORMA del texto (grupos de exactamente 3
dígitos tras el punto y sin parte decimal = miles; cualquier otra cosa
con punto o coma = decimal), no por la fila o columna de origen, así que
cubre las tres variantes a la vez. Si aparecen más inconsistencias así,
`scraping/diagnosticar_5i.py <slug>` imprime el valor crudo y el tipo
python de cada fila de esa columna para investigarlo igual.

`scrapear_pagina_temporadas()` descarga la página una sola vez y devuelve
`(temporadas, carrera)` juntos, para no duplicar la petición a acb.com;
`actualizar_jugador.py` ya lo usa así.

## editionId y jugadores recién llegados a la liga

Confirmado el 2026-10-03 con Guillem Jou (`guillem-jou-20210815`), fichaje
reciente del Leyma Coruña con historial previo en ACB (BAXI Manresa,
ICL Manresa): con `editionId=90` (edición/temporada actual, 2026-2027) la
tabla de temporadas viene **completamente vacía** (6 filas, todo `NaN`,
sin fila "Totales") - no es un fallo del scraper, es la propia página de
acb.com la que está así (comprobado trayendo el HTML real). Con
`editionId=89` (temporada anterior) la misma URL/jugador sí trae el
historial completo: 9 temporadas reales y 139 partidos con Totales/
Promedios.

Conclusión: `editionId` filtra por la edición cuya tabla se puede ver, y
acb.com solo "activa" el historial completo bajo la edición actual una
vez el jugador ha disputado algún partido oficial en ella. Para un
fichaje reciente que aún no ha jugado esta temporada:
- Con `editionId` de la temporada pasada se recupera su historial previo
  (si lo tiene).
- Con `editionId=90` (el actual, por defecto) seguirá devolviendo 0
  temporadas/0 carrera hasta que acb.com publique sus primeros partidos
  de esta edición - momento en el que SÍ debería aparecer el historial
  completo bajo `editionId=90`, como ya se confirmó con Luka Bozic.
- Un jugador sin ninguna temporada previa en ACB (debutante, ej. un
  fichaje extranjero) da 0/0 con cualquier `editionId` hasta que juegue.

Por eso `scraping/alta_masiva.py` y `scraping/actualizar_jugador.py`
aceptan `--edition-id`: para un jugador recién llegado conviene lanzar
una vez con la edición anterior (para rellenar su historial) y, más
adelante en la temporada, repetir con la edición actual (por defecto) -
los `ON CONFLICT ... DO UPDATE` ya existentes hacen que repetirlo no
duplique nada.

Si algún día hace falta investigar esto para otro jugador,
`scraping/diagnosticar_temporada.py <slug_acb> [--edition-id]` descarga la
página y muestra cuántas tablas encuentra pandas, su forma, y si alguna
tiene fila "Totales" - útil para distinguir "la página está vacía" de
"ha cambiado la estructura y hay que tocar `COLUMNAS`".

## Automatizar toda la plantilla de un equipo (o toda la liga)

Confirmado el 2026-10-03: cada equipo tiene una página de plantilla en
`https://acb.com/es/liga/equipos/equipo-<id>/plantilla` que lista a todos
sus jugadores actuales con su slug - el texto antes del id no importa
(`equipo-657` funciona igual que `leyma-coruna-657`), solo el número
final. Los 18 IDs de la temporada 2026-2027 están en
`scraping/equipos.py` (`EQUIPOS_ACB`).

Esa misma página es una app Next.js y mete en el HTML, además de la
plantilla real, un widget de jugadores de OTROS equipos (líderes de los
últimos partidos) - `scraping/equipos.py` (`parsear_plantilla`) acota la
búsqueda a la tarjeta con clase CSS que contiene "ResumenPlantillaCard"
para no mezclar ambas cosas (ver `scraping/diagnosticar_plantilla.py` si
hiciera falta volver a investigar la estructura).

El cuerpo técnico (entrenadores) **no** se puede scrapear con
`requests`/BeautifulSoup, y se investigó a fondo el porqué (2026-10-03)
antes de rendirse:
- Con un navegador real (probado vía el puente al PC del usuario) la
  sección "CUERPO TÉCNICO" SÍ aparece en el texto de la página, y no hay
  ninguna llamada a una API aparte - es la propia página.
- Se descartaron dos hipótesis razonables para replicar eso con
  `requests`: (1) cabeceras de navegador real en vez de un User-Agent de
  bot (`scraping/base_scraper.py` ya las usa) - no cambió nada; (2) una
  sesión "calentada" visitando antes la página de Resumen del equipo
  para coger cookies - el sitio no puso ninguna cookie, tampoco cambió
  nada. El HTML que ve `requests` es, carácter a carácter, casi idéntico
  con o sin esos cambios.
- Conclusión: el contenido depende de algo que solo ocurre en la
  ejecución real de JavaScript en el navegador (no de cabeceras ni de
  cookies), así que haría falta un navegador completo (Selenium/
  Playwright) para verlo - mucho más pesado y frágil de lo que compensa
  para ~18-50 personas que cambian poco en la temporada.

Por eso los entrenadores se dan de alta a mano por CSV con
`scraping/alta_entrenadores.py` (tabla `entrenadores`, separada de
`jugadores`) en vez de con scraping automático. Si en el futuro alguien
quiere retomar la idea de automatizarlo, que sepa que ya se descartaron
cabeceras y cookies como causa - habría que ir directo a un navegador
real (Selenium/Playwright) o buscar si acb.com publica esta información
en algún otro sitio más fácil de leer.

El alta de jugadores por equipo reutiliza `buscar_o_crear_jugador()` de
`db/conexion.py` (compartida con `scraping/alta_masiva.py`), que busca
por nombre+apellidos SIN distinguir mayúsculas/minúsculas (`COLLATE
NOCASE`) para no duplicar un jugador que ya se dio de alta a mano con
otra capitalización (ej. "Verge-jr" vs "Verge-Jr").

## Uso

```bash
python -m scraping.actualizar_jugador <jugador_id> <slug_acb> [--edition-id 90]
# ejemplo:
python -m scraping.actualizar_jugador 1 luka-bozic-30003420

# jugador recién llegado con historial en una edición anterior:
python -m scraping.actualizar_jugador 5 guillem-jou-20210815 --edition-id 89

# diagnóstico si un jugador da 0 temporadas y no se sabe por qué:
python -m scraping.diagnosticar_temporada guillem-jou-20210815 --edition-id 90

# un equipo entero (crea los jugadores que falten y actualiza todos):
python -m scraping.actualizar_equipo 657

# toda la liga ACB (los 18 equipos):
python -m scraping.actualizar_equipo --liga

# diagnóstico si la plantilla de un equipo no se detecta bien:
python -m scraping.diagnosticar_plantilla 657 "nombre a buscar"

# alta manual de entrenadores (cuerpo técnico) desde un CSV:
python -m scraping.alta_entrenadores scraping/entrenadores_coruna.csv

# Euroliga/EuroCup - un solo club o toda la competición:
python -m scraping.actualizar_euroleague euroliga 2026 --club MAD
python -m scraping.actualizar_euroleague euroliga 2026
python -m scraping.actualizar_euroleague eurocup 2026
```

## Euroliga y EuroCup (scraping/euroleague_api.py, scraping/actualizar_euroleague.py)

Confirmado el 2026-10-03 contra la API real (`https://api-live.euroleague.net`),
no contra documentación de terceros (el documento que sirvió de punto de
partida para esta investigación tenía la URL de ejemplo equivocada - no
fiarse de él sin verificar en vivo):

- Es una API REST con JSON real, **sin falta de API key** para estos
  endpoints de lectura (a diferencia de lo que insinúa el swagger de
  `/v3/`, que es un namespace distinto y vacío). Mucho más simple que
  acb.com: no hace falta mirar HTML en ningún momento.
- `GET /v2/competitions/{E|U}/seasons/{E2026|U2026}/clubs` -> lista de
  clubes con `country` ya incluido (Alemania, Turquía, España, Serbia...).
  Euroliga = código "E" (18 equipos), EuroCup = código "U" (20 equipos).
  El código de temporada es letra+año de inicio: la 2026-2027 es "E2026"/
  "U2026".
- `GET /v2/.../clubs/{clubCode}/people` -> la plantilla COMPLETA de un
  club esa temporada: jugadores y cuerpo técnico en la misma llamada
  (campo `type`: "J"=Jugador, "E"=Entrenador, "A"=Entrenador Ayudante;
  también aparecen médicos/utilleros con otros códigos, que se
  descartan). Por eso aquí, a diferencia de ACB, **el cuerpo técnico SÍ
  se puede automatizar** - no hace falta alta manual por CSV.
- Cada persona trae nombre completo en formato "APELLIDOS, Nombre"
  (ej. "LLULL, SERGIO"), nacionalidad, altura/peso en cm/kg (¡Euroliga sí
  da el peso, a diferencia de acb.com!), fecha de nacimiento, dorsal y
  fechas de alta/baja en el club esa temporada. `height`/`weight` vienen
  a 0 cuando no hay dato real (se trata como `None`, no como un 0
  literal).
- La posición (`positionName`) solo tiene 3 valores en inglés (Guard/
  Forward/Center) frente a los 5 en español del catálogo `posiciones`
  (Base/Escolta/Alero/Ala-pívot/Pívot) tomados de acb.com - no hay
  correspondencia fiable 1:1, así que **`actualizar_euroleague.py` no
  toca la posición** del jugador.
- El `club` que devuelve `/people` NO trae `country` (solo code/name/...)
  - el país hay que sacarlo de la llamada a `/clubs` y pasarlo aparte
  (ver `obtener_clubes` en `scraping/euroleague_api.py`).
- Un jugador que juega ACB y Euroliga/EuroCup la misma temporada queda
  como UNA sola fila en `jugadores` (se busca/crea por nombre+apellidos,
  igual que en el flujo de ACB - `db.conexion.buscar_o_crear_jugador`).
  El id externo de cada fuente se guarda en una columna separada
  (`id_externo_acb` / `id_externo_euroleague`) para no pisarse entre
  sí. El "equipo" sí es una fila distinta por competición (p.ej. "Real
  Madrid"/ACB y "Real Madrid"/Euroliga son dos filas de `equipos`), así
  que las trayectorias de cada competición no se mezclan.
- **Pendiente, no implementado todavía:** estadísticas de partido/
  temporada/carrera de Euroliga o EuroCup (solo se trae roster, datos
  personales y trayectoria) - requeriría investigar otro endpoint
  distinto al de `/people`.
