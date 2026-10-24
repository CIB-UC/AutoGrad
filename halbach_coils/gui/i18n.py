"""Small, dependency-free localisation helper for the Tkinter interface.

English strings are the source strings used in the code.  Keeping one source
language makes untranslated text obvious and lets contributors add another
language by extending :data:`TRANSLATIONS` without changing the widgets.
"""

from __future__ import annotations

from collections.abc import Iterator
import tkinter as tk


DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "es": "Español"}


TRANSLATIONS: dict[str, dict[str, str]] = {
    "es": {
        'Design needs revision': 'El diseño necesita revisión',
        'Diagnostic files kept in:\n{path}': 'Archivos de diagnóstico conservados en:\n{path}',
        'Winding geometry': 'Geometría del bobinado',
        'Wire clear': 'Cable sin interferencias',
        'Turns too close': 'Vueltas demasiado juntas',
        'Calculation failed': 'Falló el cálculo',
        'Unverified': 'Sin verificar',
        'needs_revision': 'necesita revisión',
        'This winding has not passed the wire clearance check. Run a new sweep or select a valid row.':
            'Este bobinado no ha pasado la comprobación de separación del cable. Ejecute otro barrido o seleccione una fila válida.',
        'No winding without interference was found. Try fewer levels, more winding space or another parameter range. All attempts were kept in:\n{path}':
            'No se encontró un bobinado sin interferencias. Pruebe menos niveles, más espacio de bobinado u otro rango de parámetros. Todos los intentos se conservaron en:\n{path}',
        "pyCoilGen - MRI gradient coil design": "pyCoilGen - Diseño de bobinas de gradiente MRI",
        "Settings": "Configuración",
        "Final conductor — FastHenry R: {resistance} Ω | L: {inductance} µH": "Conductor final — FastHenry R: {resistance} Ω | L: {inductance} µH",
        "Final conductor — FastHenry: {status}. {reason}": "Conductor final — FastHenry: {status}. {reason}",
        "unavailable": "no disponible",
        "disabled": "desactivado",
        "failed": "falló",
        "Language": "Idioma",
        "Output directory:": "Directorio de salida:",
        "Browse...": "Examinar...",
        "Tikhonov sweep": "Barrido Tikhonov",
        "Batch design": "Diseño en lote",
        "Design selected gradients": "Diseñar gradientes seleccionados",
        "Add aligned B₀ marks to selected gradients": "Añadir marcas B₀ alineadas a los gradientes seleccionados",
        "Select the gradients to generate. Radii and keys are recalculated for the selected set.":
            "Selecciona los gradientes que se generarán. Los radios y encajes se recalculan para el conjunto seleccionado.",
        "{axis}: excluded from batch": "{axis}: excluido del lote",
        "Select at least one gradient (X, Y or Z), without duplicates.":
            "Selecciona al menos un gradiente (X, Y o Z), sin repetir ejes.",
        "Generate gradients simultaneously (one process each)":
            "Generar gradientes en simultáneo (un proceso por gradiente)",
        "Shared dimensions": "Dimensiones compartidas",
        "Inner gradient radius": "Radio interior del gradiente",
        "Outer gradient radius": "Radio exterior del gradiente",
        "Radii and gap include the complete gradient: mold, cable and groove. Plastic faces are shown separately.":
            "Los radios y el gap incluyen el gradiente completo: molde, cable y ranura. Las caras de plástico se muestran aparte.",
        "Use the inner radius of the innermost complete gradient, or the outer radius of the outermost complete gradient, including cable and groove.":
            "Usa el radio interior del gradiente completo más interno o el exterior del más externo, incluyendo cable y ranura.",
        "Gap = inner radius of the outer gradient minus outer radius of the inner gradient, including cable and groove. The crossing gap within each gradient is separate.":
            "Gap = radio interno del gradiente exterior menos radio externo del interior, incluyendo cable y ranura. El gap de cruces dentro de cada gradiente es independiente.",
        "{axis}: gradient {gradient_inner:.2f}–{gradient_outer:.2f} mm\nMold {inner:.2f}–{outer:.2f} mm; wall {wall:.2f} mm; groove {height:.2f} × {width:.2f} mm":
            "{axis}: gradiente {gradient_inner:.2f}–{gradient_outer:.2f} mm\nMolde {inner:.2f}–{outer:.2f} mm; grosor {wall:.2f} mm; ranura {height:.2f} × {width:.2f} mm",
        "Separation between complete gradients: {gap:.2f} mm.":
            "Separación entre gradientes completos: {gap:.2f} mm.",
        "Inner mold radius": "Radio interior del conjunto",
        "Outer mold radius": "Radio exterior del conjunto",
        "Reference radius [mm]:": "Radio de referencia [mm]:",
        "Gap between gradients [mm]:": "Separación entre gradientes [mm]:",
        "Cable Ø [mm]": "Ø cable [mm]",
        "Layer gap [mm]": "Gap capas [mm]",
        "One reference radius fixes the set. Cable dimensions and crossings determine each mold thickness.":
            "Un radio de referencia define el conjunto. El cable y sus cruces determinan el grosor de cada molde.",
        "Use the inner radius of the innermost mold, or the outer radius of the outermost mold. All other radii are calculated.":
            "Usa el radio interior del molde más interno o el radio exterior del molde más externo. Los demás radios se calculan.",
        "Clearance between neighboring mold bodies. This is separate from the crossing gap inside each gradient.":
            "Separación entre los cuerpos de moldes vecinos. Es independiente del gap de cruces dentro de cada gradiente.",
        "A multiplies each cable diameter to set the radial groove height. B sets the tangential groove width.":
            "A multiplica el diámetro de cada cable para definir la altura radial del surco. B define su ancho tangencial.",
        "Radial gap between cable crossings within this gradient. It contributes to this mold thickness.":
            "Separación radial entre los cruces de cable dentro de este gradiente. Se incluye en el grosor del molde.",
        "{axis}: mold {inner:.2f}–{outer:.2f} mm; wall {wall:.2f} mm\nGroove {height:.2f} × {width:.2f} mm; cable envelope {wire_inner:.2f}–{wire_outer:.2f} mm":
            "{axis}: molde {inner:.2f}–{outer:.2f} mm; grosor {wall:.2f} mm\nSurco {height:.2f} × {width:.2f} mm; envolvente {wire_inner:.2f}–{wire_outer:.2f} mm",
        "Suggested gap without radial overlap: {gap:.2f} mm.":
            "Separación sugerida sin solapar las envolventes: {gap:.2f} mm.",
        "Cable envelopes overlap radially. The final 3D check verifies the actual conductor clearance.":
            "Las envolventes de los cables se solapan radialmente. La comprobación 3D final verifica la separación real.",
        "Final key positions verified against the conductors.":
            "Posiciones finales de los encajes comprobadas con los conductores.",
        "Key positions are preliminary; the final design selects a clear location for each key.":
            "Los encajes son preliminares; el diseño final selecciona una ubicación libre para cada encaje.",
        "Free inner radius [mm]:": "Radio interior libre [mm]:",
        "Radial assembly clearance [mm]:": "Holgura radial entre bobinas [mm]:",
        "ROI Rx [mm]:": "ROI Rx [mm]:",
        "ROI Ry [mm]:": "ROI Ry [mm]:",
        "ROI Rz [mm]:": "ROI Rz [mm]:",
        "Layers: inner to outer": "Capas: de adentro hacia afuera",
        "Layer order:": "Orden de las capas:",
        "Automatic radii": "Radios automáticos",
        "Set three outer radii": "Definir tres radios externos",
        "Rext [mm]": "Rext [mm]",
        "Tikhonov": "Tikhonov",
        "Axis": "Eje",
        "Levels": "Niveles",
        "Automatic spacing reserves clearance for the cable and its crossings, including the portions outside the mold.":
            "La separación automática reserva holgura para el cable y sus cruces, incluidas las partes que sobresalen del molde.",
        "Assembly keys": "Encajes de montaje",
        "Generate anti-rotation keys": "Generar encajes que impidan la rotación",
        "Key axial length [mm]:": "Largo axial del encaje [mm]:",
        "Key width [mm]:": "Ancho del encaje [mm]:",
        "Key clearance per side [mm]:": "Holgura del encaje por lado [mm]:",
        "Extra space on each side of the key and at the axial stop. With 0.3 mm, a 4 mm key fits a 4.6 mm wide slot with a 0.3 mm axial gap. Adjust for your printer and material.":
            "Espacio adicional a cada lado de la pestaña y en el tope axial. Con 0,3 mm, una pestaña de 4 mm entra en una ranura de 4,6 mm de ancho con 0,3 mm de margen axial. Ajusta según tu impresora y material.",
        "Key clearance: {clearance:.2f} mm per side and at the axial stop.":
            "Holgura del encaje: {clearance:.2f} mm por lado y en el tope axial.",
        "Keys share the physical X/Y/Z frame. The gradients are never rotated to fit.":
            "Los encajes comparten la referencia física X/Y/Z. Los gradientes conservan su orientación al ensamblarse.",
        "Design Gx, Gy and Gz": "Diseñar Gx, Gy y Gz",
        "Concentric assembly preview": "Vista previa del conjunto concéntrico",
        "Field results:": "Resultados del campo:",
        "Radial section": "Corte radial",
        "Assembly: Z longitudinal": "Conjunto: Z longitudinal",
        "Maximum mold radius: {mold:.2f} mm. Total radius including cable: {cable:.2f} mm.":
            "Radio máximo del molde: {mold:.2f} mm. Radio total incluido el cable: {cable:.2f} mm.",
        "{axis}: mold {inner:.2f}–{outer:.2f}; cable {wire_inner:.2f}–{wire_outer:.2f} mm":
            "{axis}: molde {inner:.2f}–{outer:.2f}; cable {wire_inner:.2f}–{wire_outer:.2f} mm",
        "Inner to outer: {order}. B₀ {direction}. Preview shows dimensions; grooves require a design run.":
            "De adentro hacia afuera: {order}. B₀ {direction}. La vista muestra dimensiones; los surcos se calculan al diseñar.",
        "Batch: {axis} — {event}": "Lote: {axis} — {event}",
        "start": "iniciando",
        "complete": "completo",
        "The set is incomplete. Completed layers were kept in:\n{path}":
            "El conjunto está incompleto. Las capas terminadas se conservaron en:\n{path}",
        "Partial results in:\n{path}": "Resultados parciales en:\n{path}",
        "Select output directory": "Seleccionar directorio de salida",
        "Full pipeline": "Pipeline completo",
        "Gradient axis:": "Eje gradiente:",
        "Cylinder outer radius [mm]:": "Radio externo del cilindro [mm]:",
        "Cylinder height [mm]:": "Altura del cilindro [mm]:",
        "Ellipsoidal ROI (independent Rx, Ry, Rz)": "ROI elipsoidal (Rx, Ry, Rz independientes)",
        "ROI radius [mm]:": "Radio ROI [mm]:",
        "Levels (turns):": "Niveles (vueltas):",
        "Conductor diameter [mm]:": "Diámetro del conductor [mm]:",
        "Real cable diameter [mm]:": "Diámetro real del cable [mm]:",
        "Groove deformation A:": "Deformación del surco A:",
        "Groove deformation B:": "Deformación del surco B:",
        "Groove radial height [mm]:": "Altura radial del surco [mm]:",
        "Groove height [mm]:": "Altura del surco [mm]:",
        "Groove width [mm]:": "Ancho del surco [mm]:",
        "Cable and groove dimensions must be positive.": "Las dimensiones del cable y del surco deben ser positivas.",
        "Section A:": "Sección A:",
        "Section B:": "Sección B:",
        "Section N:": "Sección N:",
        "Conductor material:": "Material del conductor:",
        "Resistivity [ohm.m]:": "Resistividad [ohm.m]:",
        "Autogenerated hollow cylinder (1 piece)": "Cilindro hueco autogenerado (1 pieza)",
        "Custom printable STL (2 halves)": "STL personalizado para impresión (2 mitades)",
        "STL pair (assets/shells):": "Par STL (assets/shells):",
        "Radial trim (% cable height):": "Recorte radial (% alto del cable):",
        "Gap between layers [mm]:": "Separación entre capas [mm]:",
        "Add B₀ orientation marks to the shell": "Agregar marcas de orientación de B₀ al molde",
        "Add aligned B₀ marks to all three gradients": "Agregar marcas alineadas de B₀ a los tres gradientes",
        "B₀ marks share one azimuth. Final placement is checked against grooves and keys.":
            "Las marcas de B₀ comparten una posición angular. Su ubicación final se comprueba con los surcos y encajes.",
        "Presets": "Presets",
        "Save preset...": "Guardar preset...",
        "Load preset...": "Cargar preset...",
        "Save preset": "Guardar preset",
        "Load preset": "Cargar preset",
        "Preset saved": "Preset guardado",
        "Preset saved to:\n{path}": "Preset guardado en:\n{path}",
        "Invalid preset": "Preset inválido",
        "Steps": "Pasos",
        "Gradient (pyCoilGen)": "Gradiente (pyCoilGen)",
        "Advanced leads": "Leads avanzados",
        "Show advanced lead parameters": "Mostrar parámetros avanzados de leads",
        "Run pipeline": "Ejecutar pipeline",
        "Stop": "Detener",
        "Stopping...": "Deteniendo...",
        "Cylinder radial section": "Corte radial del cilindro",
        "3D view: shell + ROI": "Vista 3D: carcasa + ROI",
        "Pipeline output": "Salida del pipeline",
        "Clear": "Limpiar",
        "Standalone (one step)": "Standalone (un paso)",
        "Action:": "Acción:",
        "Axis (for wire):": "Eje (para wire):",
        "Levels (wire):": "Niveles (wire):",
        "Outer radius [mm]:": "Radio externo [mm]:",
        "Files": "Archivos",
        "Input STL:": "STL de entrada:",
        "Run step": "Ejecutar paso",
        "Select STL": "Seleccionar STL",
        "All files": "Todos los archivos",
        "Axis:": "Eje:",
        "Height [mm]:": "Altura [mm]:",
        "Levels:": "Niveles:",
        "Coarse points:": "Puntos gruesos:",
        "Fine adjustment": "Ajuste fino",
        "Simultaneous processes:": "Procesos simultáneos:",
        "1 = sequential": "1 = secuencial",
        "Processes must be an integer between 1 and {maximum}.":
            "La cantidad de procesos debe ser un entero entre 1 y {maximum}.",
        "Run sweep": "Ejecutar barrido",
        "Load previous CSV...": "Cargar CSV anterior...",
        "Use selected in Pipeline": "Usar selección en Pipeline",
        "Load previous sweep": "Cargar barrido anterior",
        "Invalid sweep": "Barrido inválido",
        "No sweep result selected": "No hay resultado de barrido seleccionado",
        "Select one result row first.": "Seleccione primero una fila de resultados.",
        "Results": "Resultados",
        "Phase": "Fase",
        "Slope": "Pendiente",
        "Mean error": "Error medio",
        "Missing directory": "Falta directorio",
        "Select an output directory first.": "Seleccione primero un directorio de salida.",
        "Invalid parameters": "Parámetros inválidos",
        "Failed: {error}": "Falló: {error}",
        "Done.\n{payload}": "Listo.\n{payload}",
        "No STL pair is selected in assets/shells.": "No hay un par STL seleccionado en assets/shells.",
        "Select a valid wire STL.": "Seleccione un STL de wire válido.",
        "Select a valid with-leads STL.": "Seleccione un STL with-leads válido.",
        "\n\nAreas with 3 or more cables: {count}. Maximum at one location: {maximum} cables.": "\n\nZonas con 3 o más cables: {count}. Máximo en un mismo lugar: {maximum} cables.",
        "Sweep": "Barrido",
        "Sweep complete": "Barrido completo",
        "Best slope: tk={tk} ({value:.4g} mT/(m.A))\nLowest error: tk={error_tk} ({error:.4g} %)\nCSV: {path}": "Mejor pendiente: tk={tk} ({value:.4g} mT/(m.A))\nMenor error: tk={error_tk} ({error:.4g} %)\nCSV: {path}",
        "No STL pairs in assets/shells (g_Na.stl + g_Nb.stl)": "Sin pares STL en assets/shells (g_Na.stl + g_Nb.stl)",
        "From STL: Rext {outer:.2f} mm  |  Rint {inner:.2f} mm  |  Height {height:.1f} mm": "Del STL: Rext {outer:.2f} mm  |  Rint {inner:.2f} mm  |  Altura {height:.1f} mm",
        "Could not measure the STL: {error}": "No se pudo medir el STL: {error}",
        "Invalid input": "Entradas inválidas",
        "Invalid geometry": "Geometría inválida",
        "Resistivity must be a positive number.": "La resistividad debe ser un número positivo.",
        "ROI outside / colliding with shell": "ROI fuera / colisionando con la carcasa",
        "Alert: {details}": "Alerta: {details}",
        "ROI inside bore (no collision)": "ROI dentro del bore (sin colisión)",
        "Thickness: {value:.2f} mm": "Grosor: {value:.2f} mm",
        "Trim: {value:.0f}%": "Recorte: {value:.0f}%",
        "● Cable Ø {value:.2f} mm": "● Cable Ø {value:.2f} mm",
        "No STL pair is selected. Place g_Na.stl / g_Nb.stl halves in assets/shells.": "No hay un par STL seleccionado. Coloque las mitades g_Na.stl / g_Nb.stl en assets/shells.",
        "The cylinder outer radius must be greater than cable semi-axis A.": "El radio externo del cilindro debe ser mayor que el semieje A del cable.",
        "The radius, cable height, and layer gap leave the autogenerated cylinder with no usable radial thickness.": "La combinación de radio, alto del cable y separación de capas deja el cilindro autogenerado sin espesor radial útil.",
        "The custom STL has Rint >= Rext; check the halves in assets/shells.": "El STL personalizado tiene Rint >= Rext; revise las mitades en assets/shells.",
        "Cable collision": "Colisión de cables",
        "Result discarded": "Resultado descartado",
        "The result was discarded, so leads and shell were not run.\n\nThe cable generated by pyCoilGen was kept for diagnosis at:\n{path}": "Se descartó el resultado y no se ejecutaron leads ni shell.\n\nEl cable generado por pyCoilGen se conserva para diagnóstico en:\n{path}",
        "Done.\nResults in:\n{path}": "Listo.\nResultados en:\n{path}",
        "Open field plots...": "Abrir gráficos del campo...",
        "Stopped. Partial output files were kept.": "Detenido. Se conservaron los archivos parciales.",
        "Field data": "Datos del campo",
        "Mesh and ROI preview use reduced samples.": "Vista de malla y ROI con muestreo reducido.",
    },
}


from halbach_coils.coilgen.field_plots import FIELD_PLOT_TRANSLATIONS_ES
TRANSLATIONS['es'].update(FIELD_PLOT_TRANSLATIONS_ES)


class Localizer:
    """Translate source strings and refresh ordinary Tk ``text`` options."""

    def __init__(self, language: str = DEFAULT_LANGUAGE):
        self.language = language

    def set_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported GUI language: {language}")
        self.language = language

    def translate(self, source: str, **values) -> str:
        template = TRANSLATIONS.get(self.language, {}).get(source, source)
        return template.format(**values) if values else template

    def refresh_widget_tree(self, root: tk.Misc) -> None:
        for widget in _walk_widgets(root):
            try:
                current = widget.cget("text")
            except (tk.TclError, AttributeError):
                continue
            if not hasattr(widget, "_i18n_source_text"):
                widget._i18n_source_text = current
            widget.configure(text=self.translate(widget._i18n_source_text))


def _walk_widgets(root: tk.Misc) -> Iterator[tk.Misc]:
    yield root
    for child in root.winfo_children():
        yield from _walk_widgets(child)
