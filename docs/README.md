# Documentación técnica de AutoGrad

La instalación y los comandos vigentes están en el [README principal](../README.md).
Los detalles de la interfaz, las marcas B₀ y las entradas STL están en el
[README de la aplicación](../halbach_coils/README.md).

| Documento | Contenido |
| --- | --- |
| [B0_FRAME.md](B0_FRAME.md) | Marco XYZ físico, componente firmada, signos y compatibilidad con diseños anteriores. |
| [VALIDACION.md](VALIDACION.md) | Alcance de las pruebas, hallazgos recientes y límites del conjunto simulado. |
| [CRUCES_Y_VALIDACION.md](CRUCES_Y_VALIDACION.md) | Corrección de rampas de cruce y reproducción del lote GX/GY con los parámetros originales. |
| [ROBUSTEZ_GEOMETRICA.md](ROBUSTEZ_GEOMETRICA.md) | Separación automática de vueltas, barrido con validación geométrica y recuperación de resultados inviables. |
| [LOTE_Y_ENCAJES.md](LOTE_Y_ENCAJES.md) | Radios completos y de plástico, separación de gradientes, encajes y verificaciones históricas. |
| [SALIDAS_Y_FASTHENRY.md](SALIDAS_Y_FASTHENRY.md) | Organización de resultados y métricas antes y después de los terminales. |
| [CIERRE_GZ_Y_CANCELACION.md](CIERRE_GZ_Y_CANCELACION.md) | Verificación histórica del trazado Gz y del cierre de procesos FastHenry. |
| [PUBLICACION.md](PUBLICACION.md) | Rama local preparada y comandos para subirla al repositorio de CIB-UC. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Convenciones, archivos versionables y comprobaciones para cambios futuros. |
| [Datos del motor](../data/README.md) | Entradas reutilizables y fixtures binarios incluidos. |

Los informes fechados registran una versión, configuración y ejecución concretas.
Sus conteos de pruebas y valores eléctricos son evidencia histórica; no son
predicciones para todos los diseños ni sustituyen una ejecución actual. Las
mediciones físicas deben distinguirse de simulaciones y comprobaciones CAD.

Los resultados voluminosos, scripts experimentales y notas de recuperación de
una máquina se conservan localmente y se excluyen de la rama de publicación.
