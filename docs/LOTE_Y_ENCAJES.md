# Diseño en lote y encajes

La pestaña **Diseño en lote** sustituye a Standalone. Ejecuta los tres diseños
en secuencia y conserva los cálculos de campo, leads, FastHenry y molde del
Pipeline existente. El conjunto usa XYZ físicos, Z longitudinal y un mismo B₀.

## Dimensiones

Se introduce **un radio de referencia**: el radio interior del molde más
interno o el radio exterior del molde más externo. Al cambiar de modo se
conserva inicialmente la geometría; después se puede editar ese radio.

Cada eje tiene diámetro de cable, gap de cruce entre sus capas, Tikhonov y
número de niveles. Los factores comunes A/B multiplican el diámetro para
obtener altura radial y anchura tangencial de la ranura. El grosor de cada
molde se calcula con la fórmula del Pipeline:

`pared = 2 × altura_radial_ranura + gap_capas − 2 × margen_radial`

`margen_radial = fracción_de_recorte × altura_radial_ranura`

El **gap entre gradientes** se mide entre paredes de moldes. Se calculan los
seis radios y se muestran por separado las envolventes de cable. Estas pueden
sobresalir de las paredes: un gap pequeño exige comprobar las trayectorias
reales en tres dimensiones. La sugerencia conservadora que aparece en el
visor no modifica la separación elegida.

Por defecto: altura 170 mm, radio interno del molde 26,5 mm, cable 2 mm,
factores A=2/B=1, gap de capas 0 mm y gap entre gradientes 4,3 mm. Los radios
interior/exterior son Gz 26,5/30,5 mm, Gx 34,8/38,8 mm y Gy 43,1/47,1 mm.
El radio máximo estimado del cable es 49,1 mm. Tikhonov inicial 2500 y 12
niveles por eje; estos valores son puntos de partida, no una optimización del
set completo ni de su acoplamiento mutuo.

Los STL de referencia usan X longitudinal y se interpretaron mediante
`(X_nuevo,Y_nuevo,Z_nuevo)=(Y_STL,Z_STL,X_STL)`. Su orden es Gz → Gx → Gy.
Con cable de 1,5 mm, los mismos factores A/B, gap de capas 0 y gap entre
gradientes 1 mm, el cálculo reproduce sus radios 26,5/29,5, 30,5/33,5 y
34,5/37,5 mm. Los archivos adjuntos se usan como referencia geométrica;
los sólidos nuevos se generan desde los resultados actuales.

## Encajes

Cada pareja de moldes tiene una pestaña en el interior y una ranura en el
exterior, abiertas desde −Z. Ancho y longitud iniciales: 4 mm. La ranura
tiene 0,1 mm adicional por cada lado tangencial y 0,1 mm en el tope axial.
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

## Verificación real

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
