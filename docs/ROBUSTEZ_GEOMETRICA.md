# Recuperación de interferencias y estados de la interfaz

Implementación y comprobación del 24 de octubre de 2026.

## Comportamiento

La separación del cable circular se comprueba siempre, tanto en el barrido como
en el pipeline. Desactivar los mensajes de solapamiento solo reduce el log; no
desactiva la comprobación física.

Después de conectar y desplazar los cruces, y de depurar la trayectoria antes
del barrido sólido, el motor intenta separar vueltas vecinas que siguen
demasiado próximas. El ajuste mantiene radios de las capas, altura disponible,
orden de la trayectoria y cantidad de niveles. No cambia Tikhonov, ROI ni
dimensiones del conjunto. Las trayectorias que ya pasan la comprobación quedan
sin ajuste.

La reparación intenta primero desplazamientos locales suaves sobre las capas
cilíndricas, con un máximo de medio diámetro de cable por estación. Si varias
vueltas consecutivas siguen apretadas, resuelve sus restricciones conjuntamente
con una transformación axial cúbica suave y monótona. Esta segunda etapa conserva
XY exactamente y la altura disponible, limita su desplazamiento a dos diámetros
de cable y mantiene la derivada de la transformación entre 0,5 y 1,5. El ajuste
mínimo se obtiene por programación lineal y se vuelve a medir con distancias
exactas entre segmentos; la aproximación del optimizador no certifica el resultado.
Las dos etapas comparten 24 iteraciones y un presupuesto de 20 segundos.
Buscan un pequeño margen sobre el diámetro real. El margen de
búsqueda no amplía la vecindad local excluida de la comprobación física. Los
cruces que necesitan otro trazado o una asignación distinta de capas conservan
su diagnóstico.

También se eliminan cortes repetidos cuando el plano de corte coincide con un
vértice de una espira. El código anterior mezclaba filas y columnas al quitar
duplicados y podía normalizar una dirección de longitud cero. Los puntos UV,
XYZ e índices de segmento se deduplican juntos antes de elegir los dos cortes.

Solo se aplica una trayectoria reparada si pasa la comprobación completa y
puede proyectarse en la malla para actualizar sus coordenadas UV y normales.
Si no alcanza la separación dentro de los límites, se conserva la trayectoria
original. El campo, la longitud, la resistencia, los terminales y el molde se
calculan sobre la trayectoria que realmente se exporta. El conductor final y
el ensamblaje mantienen sus comprobaciones independientes.

## Resultados que necesitan revisión

Una interferencia conocida o la imposibilidad de generar terminales válidos
devuelve `PipelineResult.needs_revision`, con mensaje y archivos conservados.
La interfaz muestra un aviso y el trabajo queda parcial. No se intenta tallar
un molde usando un conductor que haya fallado la comprobación.

En un lote, ese eje se registra como `needs_revision` y los otros ejes siguen
calculándose. El conjunto no se ensambla mientras quede un eje sin geometría
válida. Las interferencias de ensamblaje y la falta de un lugar válido para
los encajes también quedan como un resultado para revisar, conservando las
capas completas. Los errores inesperados del programa y la cancelación siguen
teniendo sus estados propios.

Cada ejecución guarda `Diagnostico/*_geometry.json`: resultado de comprobación,
separación requerida, contactos, intentos y desplazamiento aplicado.
`Resumen.txt` enlaza ese diagnóstico y muestra el ajuste máximo.

## Barrido de Tikhonov

Cada fila y CSV incluye `Geometry_status`, número de zonas de contacto y enlace
al informe. Los estados son `valid`, `interference`, `failed` y `unchecked`.
Solo las filas válidas y con métricas finitas pueden recomendarse por pendiente
o error. La pasada fina respeta los límites de Tikhonov solicitados.

Si no se encuentra una geometría válida, se guardan todos los intentos y se
devuelven recomendaciones vacías. La interfaz conserva la tabla, informa el
resultado y sugiere revisar espacio, niveles o rango. Un CSV anterior que no
registre la comprobación aparece como no verificado y no puede aplicarse como
una recomendación validada. La comprobación del barrido corresponde al bobinado;
los terminales y el conjunto se comprueban durante el pipeline completo.

## Reproducción del fallo GY de 20 niveles

Se repitió el lote original con B0=+Y, altura 170 mm, ROI de radios 50 mm,
diámetro de cable 2 mm, surco A=2/B=1, corte 1 mm y suavizado `[7,7,7]`.
Se conservaron el radio ancla de 55 mm, el gap de gradientes de 0,3 mm,
los niveles Z/X/Y de 3/20/20 y Tikhonov Z/X/Y de 10000/28480/38495.

| GY | Resultado |
| --- | ---: |
| Radio exterior del molde | 77,6 mm |
| Separación mínima inicial entre ramas | 1,870983 mm |
| Pares de segmentos con contacto inicial | 38, agrupados en dos zonas |
| Separación mínima final, incluidos terminales | 2,025412 mm |
| Ajuste máximo aplicado | 0,235670 mm |
| Iteraciones | 7 |
| Longitud final | 15,743051 m |
| Pendiente simulada final | 2,558515 mT/(m·A) |
| R analítica / FastHenry | 0,08418764 / 0,084186 Ω |
| L FastHenry | 73,81750 µH |

GZ y GX no necesitaron la nueva separación de vueltas. Los tres ejes terminaron
y el ensamblaje pasó sus controles. Se recargaron los STL finales: moldes en mm,
cerrados, orientación consistente, un cuerpo y volumen positivo. Se comprobó
el hash de cada conductor final y se verificó otra vez su trayectoria guardada.

En aquella comprobación se guardaron resultados en `ahorasi_robusto_20261024`, con presets,
conductores, moldes, conjunto, gráficos, informes y logs. Estas son comprobaciones
CAD y resultados simulados; la geometría y los errores de campo se reportan por
separado. Ningún algoritmo garantiza que cualquier combinación de diámetro,
espacio y niveles admita un bobinado: el estado de revisión cubre ese caso.

## Pruebas

La suite de aquella etapa aprobó **463 pruebas**, sin omisiones. `pip check` no encontró
incompatibilidades y el comando de ayuda del pipeline se ejecutó correctamente.
Las dos advertencias de deprecación corresponden a fixtures antiguos de SciPy.

La verificación general de la versión preparada para publicar se registra en
[VALIDACION.md](VALIDACION.md); incluye las regresiones añadidas posteriormente.

Se añadieron regresiones del GY real, conservación de radios y límites de altura,
cilindros rotados, actualización UV, agotamiento de límites, reversión de un
intento incompleto y conservación de trayectorias que ya eran válidas. También
se probaron recomendaciones del barrido, ausencia de resultados válidos, CSV
anteriores, continuidad de otros ejes, estados parciales y controles de la
interfaz en inglés y español.

## Segundo caso: GY a 69,6 mm, cadena de vueltas próximas

El nuevo lote usa radio ancla de 51 mm y cable de 1 mm para GZ. Los moldes
Z/X/Y quedan en radios exteriores de 54/61,3/69,6 mm. Se conservan los niveles
3/24/20 y Tikhonov 10000/28480/38495. Por tanto, el GY tiene menos radio que
el caso anterior validado a 77,6 mm; sus parámetros eléctricos no garantizan
la misma separación entre vueltas en ese nuevo espacio.

El log mostraba dos defectos distintos. El corte duplicado en un vértice
producía la división por cero de `find_group_cut_position`. Además, cuatro
regiones del bobinado contenían una cadena de vueltas demasiado próximas.
La reparación local anterior agotaba su presupuesto y revertía al original:
prolongarla hasta 120 iteraciones tampoco alcanzó la separación requerida.
Corregir solo el corte duplicado tampoco resolvía la interferencia.

La versión anterior del detector revisaba algunos cruces proyectados y su
asignación de capa. La comprobación actual mide las distancias 3D del cable
circular también entre vueltas sin un cruce proyectado. Por eso un cálculo
que antes terminaba podía estar dejando estos contactos sin detectar.

Se repitió el lote completo con sus parámetros y la nueva recuperación
conjunta. La comparación de los JSON de configuración de los tres ejes coincide
con la ejecución del usuario, dentro del redondeo numérico de SI.

| GY a 69,6 mm | Resultado |
| --- | ---: |
| Separación mínima inicial | 1,718620 mm |
| Separación mínima final, incluidos terminales | 2,038990 mm |
| Desplazamiento axial máximo | 3,388272 mm |
| Radios y altura disponible | Conservados |
| Iteraciones | 12 locales y 1 resolución conjunta |
| Niveles y Tikhonov | 20 / 38495, conservados |
| Longitud final | 15,588987 m |
| Pendiente simulada final | 3,285959 mT/(m·A) |
| Error medio final respecto al objetivo | 1,358205 % |
| R analítica / FastHenry | 0,08336376 / 0,0833619 Ω |
| L FastHenry | 75,10458 µH |

GZ, GX y GY terminaron, incluyendo terminales, moldes y encajes. Se recargaron
los nueve STL finales (tres conductores, tres moldes individuales y tres moldes
del conjunto): un cuerpo, cerrados, orientación coherente, volumen positivo y
dimensiones/unidades correctas. Se verificaron los hashes de los conductores,
sus trayectorias finales y los 18 controles del ensamblaje.

La nueva ejecución se guarda en `Gx_Gy_robusto_20261024_v2`. Incluye los presets,
los informes por eje y `Diagnostico/verificacion_exportados.json`. Se añadieron
regresiones de los cortes en vértices (incluida la costura), la cadena real de
vueltas, conservación exacta de XY, monotonía axial, límites de recuperación y
los parámetros de los puntos de mínima distancia entre segmentos.

## Recuperación de interconexiones en lotes sin Z

El lote X/Y con cable de 1,5 mm, 22 niveles y GY a 65,8 mm produjo contactos
entre ramas de la misma capa: el mínimo registrado fue 0,000535 mm. La separación
local devolvía `crossing_requires_different_routing` sin volver a intentar las
interconexiones. Este caso requiere cambiar el trazado, además de separar vueltas.

Cuando el primer trazado no pasa la comprobación física, el motor ahora conserva
los contornos y reconstruye únicamente las interconexiones y los desplazamientos.
En modo de corte automático prueba el otro lado y anchos de apertura de al menos
dos y tres diámetros, hasta cinco alternativas distintas. Un lado de corte
explícitamente solicitado se respeta. Los intentos parten de grupos independientes,
sin repetir la optimización del stream function ni modificar Tikhonov, niveles,
radio, altura o diámetro del cable.

Solo se acepta un candidato si todas sus trayectorias pasan de nuevo el control
físico 3D. La evaluación de campo y la exportación se hacen después sobre las
partes seleccionadas. Si ningún intento pasa, se conserva el primer resultado y
su diagnóstico, con el historial completo. El JSON geométrico registra bajo
`routing_recovery` los cortes solicitados, cada intento y la selección efectiva.

Para esta modificación se ejecutaron únicamente tres pruebas puntuales de
recuperación, independencia de los intentos, conservación de resultados y respeto
del lado solicitado: las tres aprobaron. Por petición del usuario, no se volvió a
ejecutar el lote completo ni la suite general; la prueba del lote queda en manos
del usuario.

## Corrección comprobada de los cruces de GY de 22 niveles

El siguiente log confirmó que las cinco alternativas de corte se ejecutaron y
ninguna resolvió esa trayectoria. Se añade una recuperación espacial antes de
esos reintentos: puede desplazar ramas radialmente dentro del intervalo radial
que ya ocupa el conductor. La separación anterior solo permitía movimientos
tangenciales y rechazaba directamente las intersecciones casi coincidentes.
Se mantienen los límites axiales, el orden de la trayectoria y sus estaciones.
Cada intento fallido se revierte al original.

El cálculo de distancias durante la recuperación examina los segmentos afectados
y sus vecinos contra la trayectoria completa. Antes de aceptar el resultado se
realiza otra comprobación global exacta, independiente del conjunto activo. Esto
evita repetir la búsqueda global en cada iteración y no reduce la validación final.

La trayectoria del log (GY, Tk=38495, 22 niveles, cable de 1,5 mm, radio de diseño
65,8 mm) se guarda como fixture portátil `gy_crossing_22_levels.npz`. La prueba
puntual sobre esa geometría produjo:

| Medida | Resultado |
| --- | ---: |
| Pares de segmentos inicialmente en contacto | 38 |
| Separación mínima inicial | 0,000535163 mm |
| Separación mínima después del ajuste | 1,515095 mm |
| Separación requerida | 1,5 mm |
| Desplazamiento máximo aplicado | 1,810955 mm |
| Iteraciones | 155 |
| Tiempo medido del ajuste | 2,31 segundos |
| Contactos en la comprobación global final | 0 |

El intervalo radial y la altura disponible se conservan. También se comprobó
la trayectoria con las normales cilíndricas analíticas: cero contactos y un
mínimo de 1,515034 mm. La actualización UV y la aplicación del ajuste en la etapa
previa al barrido sólido aprobaron una regresión con la geometría del fallo.

Los candidatos de recuperación de cortes que todavía fueran necesarios se
comprueban antes de construir su sólido. El candidato aceptado conserva la
trayectoria ya depurada; no se recortan estaciones una segunda vez. En cilindros
generados, el desplazamiento de retornos utiliza las normales radiales conocidas
sin buscar un triángulo UV por cada estación. Se corrige además el final exclusivo
de una rebanada al elegir cortes esféricos, que descartaba candidatos de una sola
estación y producía los avisos de medias vacías.

Se ejecutaron **9 pruebas puntuales, todas aprobadas en 7,52 segundos**, que
incluyen la geometría real, conservación de envolvente y altura, equivalencia de
distancias activas/globales, agotamiento de presupuesto, actualización UV,
finalización selectiva del sólido y cortes de una estación. No se repitió el lote
completo ni la suite general; terminales, moldes y ensamblaje quedan para la prueba
del usuario.

## Cierre del bobinado incluido en la comprobación física

El siguiente lote X/Y completó la separación anterior, pero falló al evaluar el
conductor con terminales. El barrido sólido une siempre su última sección con la
primera. Las comprobaciones previas recorrían únicamente los segmentos entre
estaciones consecutivas y omitían esa unión. Además, inferían el cierre según la
distancia entre los extremos: en este caso están a 3,130792 mm, más que el diámetro
del cable. La trayectoria final con terminales sí recuperaba el segmento omitido.

La referencia real de GY se conserva en `tests/test_data/gy_closing_segment.npz`,
con los dos terminales originales y los índices del corte. Contiene cuatro pares
en interferencia, todos contra el cierre, con un mínimo de 0,119348 mm. Por ello
el informe previo declaraba cero contactos y la etapa siguiente lo rechazaba.

La reparación ahora representa explícitamente el cierre antes de ajustar el
bobinado. Conserva el número original de estaciones para que la trayectoria y las
secciones del sólido sigan correspondiendo. La selección de rutas y el control
independiente de los bobinados barridos comprueban también ese mismo segmento.
Las trayectorias finales entre terminales siguen comprobándose como abiertas.

Sobre esa referencia, la recuperación necesitó cinco iteraciones y un ajuste
máximo de 1,418352 mm dentro de los límites radiales y axiales existentes. La
trayectoria corregida, reconstruida con los mismos terminales y el mismo corte,
tuvo cero interferencias y una separación mínima de 1,515034 mm para cable de
1,5 mm. También aprobó la recuperación de la trayectoria anterior de 22 niveles,
esta vez comprobando su cierre en la integración previa al barrido.

Se ejecutaron **18 pruebas puntuales, todas aprobadas en 17,63 segundos**: cierre
real, reconstrucción con terminales guardados, controles independientes,
recuperación espacial, actualización UV, reintentos y diagnósticos de cruces.
No se ejecutaron el lote completo, nuevos STL, los moldes ni el ensamblaje.
