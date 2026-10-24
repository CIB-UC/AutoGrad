# Diseño en lote y encajes

Este documento describe el diseño y las verificaciones históricas del lote.
Los apartados de verificación registran los parámetros de cada ejecución;
no garantizan que esos mismos diseños pasen las comprobaciones de versiones
posteriores. La [validación del 21 de octubre](VALIDACION.md) documenta las
colisiones detectadas con la comprobación actual y un conjunto alternativo.

La pestaña **Diseño en lote** sustituye a Standalone. Ejecuta los tres diseños
en secuencia y conserva los cálculos de campo, leads, FastHenry y molde del
Pipeline existente. El conjunto usa XYZ físicos, Z longitudinal y un mismo B₀.

## Dimensiones

Se introduce **un radio de referencia**: el radio interior del gradiente completo
más interno o el radio exterior del más externo, incluyendo cable y ranuras.
Al cambiar de modo se
conserva inicialmente la geometría; después se puede editar ese radio.

Cada eje tiene diámetro de cable, gap de cruce entre sus capas, Tikhonov y
número de niveles. Los factores comunes A/B multiplican el diámetro para
obtener altura radial y anchura tangencial de la ranura. El grosor de cada
molde se calcula con la fórmula del Pipeline:

`pared = 2 × altura_radial_ranura + gap_capas − 2 × margen_radial`

`margen_radial = fracción_de_recorte × altura_radial_ranura`

El **gap entre gradientes** es `Rint_exterior − Rext_interior`, usando la
envolvente completa del gradiente (plástico, cable y ranura). Se calculan los
seis radios de gradiente y se muestran aparte los del molde. El cable que
sobresale del plástico se incluye en el grosor del gradiente; no consume el
gap introducido. Se admite gap cero y se rechazan valores negativos antes
de ejecutar. La comprobación CAD final sigue revisando leads y encajes reales.
Los radios son envolventes nominales; gap cero representa contacto teórico.
Se conserva la revisión de la geometría final discretizada.

Por defecto: altura 170 mm, radio interno del gradiente 26,5 mm, cable 2 mm,
factores A=2/B=1, gap de capas 0 mm y gap entre gradientes 0,3 mm. Los radios
interior/exterior completos son Gz 26,5/34,5 mm, Gx 34,8/42,8 mm y Gy 43,1/51,1 mm.
Los radios del plástico son 28,5/32,5; 36,8/40,8 y 45,1/49,1 mm. Tikhonov inicial 2500 y 12
niveles por eje; estos valores son puntos de partida, no una optimización del
set completo ni de su acoplamiento mutuo.

Los STL de referencia usan X longitudinal y se interpretaron mediante
`(X_nuevo,Y_nuevo,Z_nuevo)=(Y_STL,Z_STL,X_STL)`. Su orden es Gz → Gx → Gy.
Sus radios de plástico medidos son 26,5/29,5, 30,5/33,5 y 34,5/37,5 mm.
Estas medidas no especifican por sí solas el espacio ocupado por cable fuera
del plástico. Los archivos adjuntos se usan como referencia geométrica;
los sólidos nuevos se generan desde los resultados actuales.

## Encajes

Cada pareja de moldes tiene una pestaña en el interior y una ranura en el
exterior, abiertas desde −Z. Ancho y longitud iniciales: 4 mm. La ranura
tiene por defecto 0,3 mm adicionales por cada lado tangencial y 0,3 mm en el
tope axial: para una pestaña de 4 mm, el ancho de la ranura es 4,6 mm y su
largo útil 4,3 mm. **Holgura del encaje por lado** permite ajustar ese valor;
la vista previa y los STL usan la misma holgura. El valor inicial depende de
la precisión de la impresora y del material: conviene comprobarlo en una
muestra pequeña antes de imprimir el conjunto completo
([guía de tolerancias de Prusa](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135)).
El extremo de la pestaña sigue el radio externo del receptor. Las posiciones
preferidas son 202,5° y 180°, medidas de +X hacia +Y. Si una posición corta
un conductor o interfiere con el otro encaje, se buscan otras posiciones sin
girar las bobinas. El alojamiento de antena no se genera.

El tope limita el avance hacia +Z y los encajes evitan el giro relativo;
se puede retirar cada pieza hacia −Z. No se añade un cierre elástico ni una
retención axial en ambas direcciones. Las holguras son geométricas: conviene
probarlas en una muestra con la impresora y material que se utilizarán.

Antes de publicar el conjunto se comprueban los conductores finales entre
sí, cada conductor contra los otros moldes, los moldes entre sí y la ROI
compartida. Se comprueban de nuevo los STL ya serializados, cerrados y de
una pieza. Los booleanos del conjunto conservan doble precisión hasta esa
exportación. La tolerancia de intersección está registrada en `encajes.json`.
La ROI de la comprobación CAD es un elipsoide circunscrito conservador;
el cálculo electromagnético mantiene la ROI original.

## Resultados y cancelación

`Resumen_lote.txt` y `lote.json` muestran el estado y dimensiones del lote.
Cada carpeta numerada conserva la organización del Pipeline. Al terminar,
los botones Gx/Gy/Gz abren sus gráficos finales y muestran los valores de
FastHenry. Los tres STL de montaje están en `Conjunto/`, junto con
`Gradientes.glb` y `encajes.json`. STL en milímetros; GLB en metros, sin
rotaciones añadidas a las coordenadas físicas.

Solo se publica `Conjunto/` tras completar todas las comprobaciones. Un fallo,
descarte o Stop conserva los diseños individuales y marca el lote incompleto.
Stop termina el proceso de trabajo y sus procesos dependientes, y actualiza
tanto el marcador del trabajo como el manifiesto y resumen del lote.

## Verificación de la versión inicial

Se generaron los tres diseños de las dimensiones iniciales, incluido el
conductor final con sus dos terminales. FastHenry instalado devolvió:

| Gradiente | R [Ω] | L [µH] |
| --- | ---: | ---: |
| Gz | 0,0190474 | 5,68220 |
| Gx | 0,0362015 | 14,73924 |
| Gy | 0,0379879 | 18,24711 |

Los valores corresponden a cada circuito individual, sin los cables externos
de alimentación y retorno. No incluyen la inductancia mutua entre gradientes.

El conjunto exportado pasó las 18 comprobaciones de intersección: conductores
entre sí y contra ROI, moldes entre sí y contra ROI, y cada conductor contra
los moldes de los otros ejes. Los tres STL recargados son sólidos cerrados,
con orientación consistente y una sola pieza. Las posiciones finales fueron
202,5° y 180°, con las holguras de 0,1 mm previstas.

Esta prueba detectó además dos casos de pérdida de precisión al exportar STL
en Gx/Gy. La exportación conserva doble precisión durante los booleanos y
repara localmente las aristas que colapsan al guardar, las láminas CAD de
volumen exactamente cero y las caras collineales. La validación del archivo
guardado sigue siendo obligatoria. No se activa la voxelización para estos
casos. Stop también se comprobó con un proceso real de lote: 0,041 segundos
hasta terminar y manifiesto/resumen marcados como cancelados.

La suite completa pasó **336 pruebas**. La ejecución nueva desde la interfaz
del proyecto principal, mediante `WorkerRunner` y un proceso Windows real,
terminó los tres gradientes en 490,4 segundos y obtuvo los mismos R/L de la
tabla. Se verificaron los tres botones de gráficos, el estado completo del
trabajo y los tres STL finales. Los resultados locales están en
`halbach_coils/resultados/verificacion_lote_final_20261015/`, con
`verificacion.json`, `Vista_conjunto.png` y el informe CAD de `Conjunto/`.

Sobre los STL finales también se comprobó cada interfaz desplazando copias
en memoria: girar ±1° o avanzar 1 mm hacia +Z provoca colisión con el encaje;
la posición original y la extracción 1 mm hacia −Z no provocan intersección.
Esto verifica el bloqueo de giro en ambos sentidos y el tope axial descrito.

## Corrección de la definición del gap

La primera versión medía el gap entre paredes de plástico. El caso guardado
en `Desktop/test` (radio de referencia 50 mm, cable 2 mm y gap 2 mm) tenía
ranuras Gz/Gx superpuestas 254,246 mm³ y Gx/Gy 235,759 mm³. El STL empleado
en ese chequeo es la envolvente de ranura, no un cable circular de 2 mm.
Incluso las trayectorias nominales del cable circular quedaban prácticamente
en contacto. El chequeo detectaba una incoherencia real en la dimensión que
la interfaz llamaba separación entre gradientes.

Desde el formato 2 de `lote.json`, radio de referencia y gap se aplican al
gradiente completo. Para los mismos 50 mm y gap 2 mm, los radios completos
son 50/58, 60/68 y 70/78 mm; los moldes son 52/56, 62/66 y 72/76 mm.
No se alteran las bobinas de resultados anteriores, las fórmulas del Pipeline
individual ni la validación CAD. Para usar la nueva separación hay que
generar un lote nuevo, pues cambian los radios del cálculo electromagnético.

La comprobación entre cables usa ahora sus trayectorias finales verificadas
por hash y el diámetro circular real, con distancias exactas entre segmentos.
El STL de ranuras deformadas se sigue usando para las comprobaciones de molde
y encajes. Esto evita interpretar un cruce entre herramientas de sustracción
fuera del plástico como si fuera necesariamente un cruce entre cables.

Se repitió desde la interfaz el caso de radio 50 mm, gap 2 mm, ROI 30 mm,
Tikhonov 2500 y 12 niveles en cada eje. Terminó en 297,4 segundos, con los
tres moldes cerrados, encajes validados y FastHenry correcto en los tres ejes.
Los resultados están en `halbach_coils/resultados/verificacion_lote_gap_20261015/`.
La suite final pasó 343 pruebas. Se volvieron a comprobar los 18 chequeos
del conjunto exportado usando el cable circular real y los moldes con encajes.

## Corrección de la exportación del conjunto

El lote con radio interior completo 30 mm, gap 2 mm, cable 2 mm y ROI 20 mm
terminaba los tres diseños individuales, pero fallaba al exportar los encajes.
La conversión a CAD acepta ahora los buffers de vértices de solo lectura que
devuelve `to_mesh64()`, creando memoria editable cuando hace falta.

Además, se reparan las caras que se vuelven collineales únicamente al redondear
las coordenadas al float32 del STL. Se divide la cara vecina usando el vértice
existente antes de retirar la cara degenerada, conservando las coordenadas
redondeadas y evitando abrir una fisura. Se mantienen las comprobaciones de
cierre, orientación, caras degeneradas e interferencia de los archivos finales.

Con los archivos reales de ese lote se completó únicamente el conjunto, sin
recalcular bobinas ni FastHenry: los 81 archivos individuales conservaron su
SHA-256 y el conjunto pasó sus 18 comprobaciones. La suite completa pasó
348 pruebas, incluidas las regresiones de buffers de solo lectura y de caras
que se vuelven collineales al exportar STL.
