# Cruces de GX/GY: investigación y corrección del 24 de octubre de 2026

El lote original terminaba GZ y fallaba en GX, con cuatro zonas de interferencia
entre ramas del mismo conductor. Las separaciones entre ejes eran 1,51227,
0,0167387, 0,0154803 y 0,000282678 mm para un cable circular de 2 mm.

## Qué cambió

La comparación con Git encontró comprobaciones nuevas en los cambios locales de
`halbach_coils/coilgen/overlap.py` y `final_field.py`: distancias entre segmentos
3D y rechazo obligatorio del conductor final. El desplazamiento de cruces en
`pyCoilGen/sub_functions/shift_return_paths.py` conservaba la selección histórica;
su último cambio anterior solo añadía metadatos de diagnóstico. El nuevo control
hacía obligatorio detener un diseño con contactos que antes podía continuar.

La advertencia permitía aceptar el resultado, pero el control final volvía a
rechazar los mismos contactos después de generar los terminales. Las cuatro
interferencias ya existían en la bobina original; los terminales no las creaban.

## Causa y corrección

El motor elegía independientemente qué rama desplazar en cada cruce. Al suavizar
esa selección mediante una convolución, una rampa alcanzaba cruces vecinos y
desplazaba también la rama que debía permanecer afuera. En el peor contacto,
las dos ramas estaban prácticamente en el mismo radio, 63,293 mm.

Ahora, si la selección original deja un cruce sin separación nominal suficiente,
se agrupan los segmentos cuyos suavizados interactúan y se asignan conjuntamente
las dos capas radiales. Cada cruce exige capas opuestas. Se elige la orientación
más cercana a la selección anterior, manteniendo el desplazamiento y el suavizado
solicitados. Las rutas que ya estaban separadas conservan la selección anterior.

Si ese conjunto de restricciones no admite dos capas, no se introduce una tercera
ni se declara resuelto el cruce. Las distancias físicas 3D siguen comprobándose
después del barrido y de los terminales. Una interferencia medida que aún quede
detiene el pipeline antes de los terminales, con un mensaje explícito, sin ofrecer
la continuación que después iba a fallar.

## Reproducción con los parámetros originales

Se ejecutó el lote completo en un directorio nuevo, con B0=+Y, ROI de radios
50 mm, altura 170 mm, malla 200 × 10, cable de 2 mm, deformación de surco A=2/B=1,
gap de cruce cero, corte de interconexión 1 mm y suavizado `[7,7,7]` en los tres
ejes. Orden interior a exterior: Z, X, Y; radio ancla interior completo 53 mm y
separación radial de gradientes completos 0,3 mm.

| Eje | Radio exterior del molde | Tikhonov | Niveles |
| --- | ---: | ---: | ---: |
| Z | 59,0 mm | 20000 | 3 |
| X | 67,3 mm | 20000 | 12 |
| Y | 75,6 mm | 10000 | 12 |

El lote terminó, incluidos los terminales, los moldes, las marcas B0 y los
encajes. El ensamblador comprobó los tres conductores, los soportes y la ROI.
Los STL de moldes y conductores GX/GY se recargaron: cada uno tiene un solo
cuerpo, cierre, orientación consistente y volumen positivo. Los moldes finales
usan mm y los STL de conductor usan m.

| Resultado final | GX | GY |
| --- | ---: | ---: |
| Distancia mínima entre segmentos no locales | 3,81456 mm | 3,25712 mm |
| Longitud de conductor | 8,32624 m | 8,43396 m |
| Pendiente simulada | 1,59502 mT/(m·A) | 1,15251 mT/(m·A) |
| Error máximo relativo a amplitud objetivo en ROI | 8,64146 % | 6,35282 % |
| R analítica | 0,0445254 Ω | 0,0451015 Ω |
| R FastHenry | 0,0445247 Ω | 0,0451008 Ω |
| L FastHenry | 18,0697 µH | 17,6880 µH |

La distancia utiliza segmentos exactos y la misma exclusión de vecindad por arco
que el control del conductor final. GZ conservó sus parámetros y resultados.
La modificación del trazado requiere recalcular el campo; se guardaron las
métricas finales nuevas, sin reutilizar las de la bobina anterior.

También se comprobó una alternativa con corte 3 mm y suavizado `[1,1,3]` para
GX/GY: completaba el lote aun con la selección antigua. La corrección del motor
permite conservar los parámetros originales en el caso investigado.

## Pruebas y archivos

La suite completa aprobó **436 pruebas**, sin omisiones. Las dos advertencias de
deprecación provienen de fixtures antiguos de SciPy. `pip check` pasó y el comando
de ayuda del pipeline se ejecutó correctamente.

`tests/test_shift_return_paths.py` cubre interacción de rampas, restricciones que
no admiten dos capas, conservación de rutas separadas y la geometría exacta del
GX que fallaba. El fixture `test_data/gx_crossing_ramps.npz` contiene solo malla y
trayectorias numéricas, sin objetos Python serializados ni rutas de la máquina.
`tests/test_pipeline_collision_decision.py` cubre el rechazo anticipado de una
interferencia física medida, en español e inglés.

La salida local `Gx_Gy_reparado_20261024` contiene `Resumen_lote.txt`,
`lote.json`, los presets por eje, `Conjunto/`, la figura antes/después,
`verificacion_exportados.json` y una copia de este informe y de los logs.
