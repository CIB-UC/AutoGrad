# Publicación de AutoGrad en CIB-UC

Destino: [CIB-UC/Gradients-PyCoilGen](https://github.com/CIB-UC/Gradients-PyCoilGen).
La versión anterior se publicó el 24 de octubre de 2026, en el commit `01c8408`.
El cambio de nombre a AutoGrad se prepara como una actualización y requiere una
nueva autorización antes de subirlo.

## Estado preparado

- `origin` conserva el repositorio original de la copia de trabajo.
- `cib-uc` apunta al repositorio de destino.
- `release/github-ready` contiene una instantánea de la versión actual, incluidos
  los cambios de código que estaban pendientes y sus pruebas, junto con la
  documentación revisada.
- La actualización parte de la versión publicada en `cib-uc/main`, conserva su
  historial y permite un push normal.
- El índice y la rama activa de trabajo se conservan. La rama lista
  para publicar se crea con un índice independiente; los cambios locales siguen
  disponibles para continuar el trabajo habitual.

La instantánea incluye código, pruebas, fixtures, licencias y entradas STL.
Excluye entornos, resultados, experimentos locales, ZIP duplicado, scripts
obsoletos y notas de recuperación de una máquina. Esos archivos permanecen en
el disco. El historial local de desarrollo con resultados de simulación no es
ancestro de esta rama y no se envía al publicar únicamente esta referencia.

## Revisar y subir

Desde esta copia de trabajo se puede revisar la rama sin cambiar la rama activa:

```powershell
git remote -v
git log --oneline cib-uc/main..release/github-ready
git diff --stat cib-uc/main..release/github-ready
git ls-tree -r --name-only release/github-ready
```

Para publicar la versión preparada directamente en `main`:

```powershell
git fetch cib-uc main
git push --dry-run cib-uc release/github-ready:main
git push cib-uc release/github-ready:main
```

El último comando sube los archivos a GitHub y requiere tus credenciales de
colaborador. Si `main` está protegida, publicar una rama y abrir un pull request
desde GitHub:

```powershell
git push -u cib-uc release/github-ready
```

Si otra persona añadió commits a `main` después de preparar la instantánea, el
push directo puede rechazarse. Conservar sus cambios y actualizar/revisar la
rama antes de reintentar; no forzar el push ni publicar todas las ramas locales.

La rama preparada es una instantánea: cambios posteriores en los archivos no
se incorporan automáticamente. Comparar y actualizarla antes de subir si se
continúa desarrollando después de esta revisión.

## Comprobar la distribución

La revisión del 24 de octubre de 2026 obtuvo **475 pruebas aprobadas** en una
copia limpia de la versión previa al cambio de nombre, usando el entorno existente. `pip check`
no encontró incompatibilidades; la ayuda del pipeline y del barrido se ejecutó
correctamente. Esto comprueba que las pruebas no dependan de archivos locales
excluidos, sin sustituir una instalación nueva en otro equipo.

También se revisaron los enlaces Markdown, excepciones de `.gitignore`, tamaños
y presencia de archivos locales. El commit utiliza la identidad Git configurada
del mantenedor. La subida efectiva requiere su autorización.

Para una instalación independiente después de subir, clonar el repositorio en
otra carpeta y seguir el [inicio rápido](../README.md). Un clone nuevo tendrá
como `origin` el repositorio de CIB-UC y no incluirá el material local excluido.
