# Validación y límites

Este resumen conserva los hallazgos del informe local del **21 de octubre de
2026**. Los resultados numéricos de esa fecha son históricos: en la preparación
para GitHub del **24 de octubre de 2026** se ejecutó la suite automatizada;
no se repitieron las simulaciones completas ni FastHenry real.

Las correcciones posteriores de cruces, recuperación de trayectorias y estados
parciales se documentan en [CRUCES_Y_VALIDACION.md](CRUCES_Y_VALIDACION.md) y
[ROBUSTEZ_GEOMETRICA.md](ROBUSTEZ_GEOMETRICA.md). Sus resultados y configuraciones
corresponden a campañas distintas de las tablas históricas de este resumen.

## Verificación automatizada actual

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

La revisión final de publicación del 24 de octubre obtuvo **475 pruebas aprobadas**,
sin omisiones, en una copia limpia de la distribución en Windows con Python
3.11.9. `pip check` no encontró incompatibilidades. Las dos
advertencias de deprecación proceden de fixtures antiguos que referencian
`scipy.io.matlab.mio5_params`. El rango de Python declarado en el paquete no
implica que esta revisión haya repetido pruebas en todas sus versiones.

La suite cubre motor, marcos B₀, parámetros, unidades, métricas, terminales,
colisiones, exportación/recarga STL, lotes, marcas B₀, interfaz y cancelación.
No equivale a una medición física ni a una validación de todos los parámetros.

El cambio de nombre a **AutoGrad** es posterior a esa ejecución general. Se
verificaron de nuevo las pruebas existentes de interfaz, los títulos en inglés
y español, la ayuda de terminal y el inicio de `AutoGrad.bat` en modo de
verificación. La lógica de diseño y cálculo no cambió con el nombre.

## Hallazgos de la revisión del 21 de octubre

- La comprobación de cable utiliza distancias entre segmentos 3D no locales y
  el diámetro circular real. El surco de fabricación no define el área eléctrica
  ni sustituye al cable en esa comprobación. El conductor final se revisa de
  nuevo después de generar ambos terminales.
- Algunos diseños de partida presentaban contactos reales, incluidos Gx con
  Tikhonov 2500 y 10000. Una optimización de campo terminada no garantiza que el
  bobinado o su ensamblaje sean realizables.
- La selección `advanced.connection_cut_side=auto/low/high` se transmite al motor;
  `auto` conserva el comportamiento histórico. El corte, la rampa y la
  significancia de contornos pueden cambiar la geometría y el campo resultante.
- Se verificó el tallado de ambas mitades STL en m y mm, recargando los archivos
  serializados. Para cilindros automáticos, se conserva el cuerpo conectado
  que une ambos extremos axiales; se rechazan casos ambiguos. Esta selección
  no se aplica a mitades CAD aportadas por el usuario.
- La convención eléctrica es `R = ρL/A`, con ρ en Ω·m y `σ = 1/ρ` en S/m.
  `specific_conductivity` es un nombre heredado para **resistividad**. La sección
  real del cable y la holgura del surco se registran por separado.

## Conjunto simulado que pasó la comprobación geométrica

Se obtuvieron tres bobinas con terminales, tres soportes y dos encajes. Los
resultados por eje se coordinaron mediante el ensamblador de producción; los
intentos fallidos previos no se contaron como lotes completos.

La configuración compartía B₀=+Y, altura 170 mm, radios de ROI 20 mm, referencia
interior 26,5 mm, cable de 2 mm y separación nominal de gradientes 0,3 mm. Los
parámetros particulares fueron:

| Eje | Tikhonov | Niveles | Significancia mínima | Corte | Rampa | Plano de corte | Holgura adicional de surco por lado |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| X | 2500 | 12 | 5 % | 3 mm | [1,1,3] | nearest | 0 mm |
| Y | 2500 | 6 | 15 % | 3 mm | [1,1,3] | B0 | 0,1 mm |
| Z | 2500 | 6 | 5 % | 1 mm | [7,7,7] | nearest | 0,1 mm |

Los dos encajes se ubicaron a 202,5° y 180°, con 0,3 mm de holgura por lado y
en el tope axial. Las 18 comprobaciones del ensamblador no detectaron
intersecciones entre conductores, ROI y soportes. Se recargaron los tres STL
finales y se comprobó cierre, orientación y un único cuerpo de volumen positivo.
La escena GLB conservó sus tres geometrías y dimensiones.

| Eje | Longitud final | Pendiente simulada mT/(m·A) | Error máximo respecto a amplitud objetivo en ROI | R analítica | R FastHenry |
| --- | ---: | ---: | ---: | ---: | ---: |
| X | 6,883981758 m | 4,518582 | 3,211 % | 0,03681282276 Ω | 0,0368128 Ω |
| Y | 3,174224907 m | 1,289057 | 1,554 % | 0,01697450443 Ω | 0,0169745 Ω |
| Z | 2,017418089 m | 1,250204 | **16,057 %** | 0,01078835726 Ω | 0,0107884 Ω |

FastHenry real se ejecutó a 1 Hz con las trayectorias completas y sección
cuadrada de igual área. El acuerdo con `ρL/A` comprueba esa extracción eléctrica;
no demuestra por sí mismo ausencia de interferencias ni equivalencia de sección
a frecuencias altas. El modelo no incluye retorno externo ni inductancia mutua.

## Alcance y evidencia local

La validez geométrica de ese conjunto **no certifica su linealidad física**:
Gz conserva un error máximo simulado del 16,057 % en la ROI. No se midieron
campo, resistencia, inductancia ni ajuste de piezas fabricadas. Tampoco se
certificó el radio de doblado de todo el bobinado; el planificador de terminales
sí mantuvo su restricción de 6 mm para el caso documentado.

Los archivos de esa campaña permanecen localmente en
`experiments/comparacion_pycoilgen/`: `VALIDACION_ACTUAL.md`, `results.json` y
`validation/assembly_final/`, con los presets y artefactos de cada eje. Estos
scripts, checkpoints y resultados no forman parte de la distribución limpia.
Este resumen no pretende permitir reproducir exactamente aquella campaña sin
sus presets y artefactos. Para una verificación nueva, guardar la configuración
y todo el directorio de salida del programa y comparar sus métricas finales.
