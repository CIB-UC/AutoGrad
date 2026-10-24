"""Persist and plot the final wire field without opening a GUI from a worker.

The NPZ contains only numeric arrays and strings, so results can be reopened
without unpickling a pyCoilGen solution. Coordinates and field vectors use the
physical STL frame. Fields are projected on the *signed* B0 direction and are
shown for one ampere, including the target's original amplitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable

import numpy as np


PLOT_KINDS = ("comparison", "linearity", "spatial", "contours")
PLOT_LABELS = {
    "comparison": "Objective and generated field",
    "linearity": "Linearity and residual",
    "spatial": "Spatial field and target error",
    "contours": "Generated field contours",
}

# Registered by gui.i18n; kept with these figures so all captions stay together.
FIELD_PLOT_TRANSLATIONS_ES = {
    "Field results": "Resultados del campo",
    "Objective and generated field": "Campo objetivo y generado",
    "Linearity and residual": "Linealidad y residuo",
    "Spatial field and target error": "Campo espacial y error respecto al objetivo",
    "Generated field contours": "Curvas de nivel del campo generado",
    "Generated gradient: {slope:.4g} mT/m/A": "Gradiente generado: {slope:.4g} mT/m/A",
    "{plane} plane | {axis} = {position:.3g} mm":
        "Plano {plane} | {axis} = {position:.3g} mm",
    "Central physical slices; linear interpolation inside the sampled ROI only.":
        "Cortes físicos centrales; interpolación lineal solo dentro de la ROI muestreada.",
    "Insufficient ROI samples for this plane.": "Muestreo insuficiente de la ROI para este plano.",
    "Uniform field in this plane: {value:.4g} mT/A":
        "Campo uniforme en este plano: {value:.4g} mT/A",
    "Objective at 1 A": "Objetivo a 1 A",
    "Generated wire field at 1 A": "Campo generado por el cable a 1 A",
    "Linear fit": "Ajuste lineal",
    "Position {axis} [mm]": "Posición {axis} [mm]",
    "Field parallel to B0 [mT/A]": "Campo paralelo a B0 [mT/A]",
    "Residual to linear fit [mT/A]": "Residuo del ajuste lineal [mT/A]",
    "Generated minus objective [mT/A]": "Generado menos objetivo [mT/A]",
    "Generated field": "Campo generado",
    "Error relative to objective": "Error respecto al objetivo",
    "Gradient G{axis} | B0 {direction}": "Gradiente G{axis} | B0 {direction}",
    "Residual RMS: {rms:.4g} mT/A": "RMS del residuo: {rms:.4g} mT/A",
    "Sampled ROI points; no interpolation. Physical axes match the STL viewer.":
        "Puntos muestreados de la ROI; sin interpolación. Ejes físicos iguales a los del visor STL.",
    "Both curves use 1 A; the objective amplitude is not rescaled to the generated field.":
        "Ambas curvas usan 1 A; la amplitud objetivo se conserva sin ajustarla al campo generado.",
    "Field plots:": "Gráficos del campo:",
    "Open saved field results...": "Abrir resultados de campo guardados...",
    "Select saved field results": "Seleccionar resultados de campo guardados",
    "Field result data": "Datos de resultados del campo",
    "Cannot open field results": "No se pueden abrir los resultados del campo",
    "View:": "Vista:",
    'Final conductor with leads; external supply/return wires excluded.':
        'Conductor final con terminales; sin cables externos de alimentación y retorno.',
}


def _translate(tr: Callable | None, source: str, **values) -> str:
    return tr(source, **values) if tr else source.format(**values)


def _b0_vector(direction: str) -> np.ndarray:
    direction = direction.strip().lower()
    if len(direction) == 1:
        direction = "+" + direction
    if direction not in ("+x", "-x", "+y", "-y", "+z", "-z"):
        raise ValueError("B0 direction must be one of +/-x, +/-y, +/-z")
    vector = np.zeros(3)
    vector["xyz".index(direction[1])] = -1.0 if direction[0] == "-" else 1.0
    return vector


@dataclass
class FieldPlotData:
    """Physical ROI samples and signed B-parallel values, in m and mT/A."""

    coords_m: np.ndarray
    generated_mT_per_A: np.ndarray
    target_mT_per_A: np.ndarray
    gradient_axis: str
    b0_direction: str
    project_name: str = "gradient"
    circuit_stage: str = 'coilgen'

    def __post_init__(self):
        self.coords_m = np.asarray(self.coords_m, dtype=float)
        self.generated_mT_per_A = np.asarray(self.generated_mT_per_A, dtype=float)
        self.target_mT_per_A = np.asarray(self.target_mT_per_A, dtype=float)
        self.gradient_axis = str(self.gradient_axis).lower()
        self.b0_direction = str(self.b0_direction).lower()
        if len(self.b0_direction) == 1:
            self.b0_direction = "+" + self.b0_direction
        _b0_vector(self.b0_direction)
        if self.gradient_axis not in ("x", "y", "z"):
            raise ValueError("Gradient axis must be x, y or z")
        if self.coords_m.ndim != 2 or self.coords_m.shape[0] != 3:
            raise ValueError("Field coordinates must have shape (3, N)")
        n = self.coords_m.shape[1]
        if n < 2 or self.generated_mT_per_A.shape != (n,) or self.target_mT_per_A.shape != (n,):
            raise ValueError("At least two matching coordinate, target and field samples are required")
        if not all(np.all(np.isfinite(a)) for a in (
            self.coords_m, self.generated_mT_per_A, self.target_mT_per_A,
        )):
            raise ValueError("Field results contain non-finite samples")
        if np.ptp(self.gradient_coords_m) == 0:
            raise ValueError("The ROI must span the gradient axis")

    @property
    def gradient_coords_m(self) -> np.ndarray:
        return self.coords_m["xyz".index(self.gradient_axis)]

    def linearity(self) -> tuple[float, np.ndarray, np.ndarray, float]:
        """Return slope [mT/(m A)], fit, residual [mT/A], and residual RMS."""
        coords = self.gradient_coords_m
        # Center first to avoid loss of precision for an off-center ROI.
        centered = coords - np.mean(coords)
        field = self.generated_mT_per_A
        slope = float(np.dot(centered, field - field.mean()) / np.dot(centered, centered))
        fit = slope * centered + field.mean()
        residual = field - fit
        rms = float(np.sqrt(np.mean(residual ** 2)))
        return slope, fit, residual, rms

    @cached_property
    def contour_slices(self) -> tuple[dict, ...]:
        """Interpolate physical XY/XZ/YZ sections without extrapolating.

        The scalar is the saved signed B-parallel field per ampere, never
        B/position (which is undefined at the center). A fit supplies the
        gradient efficiency separately. Saved older results use this same
        path, so no new coil solve or NPZ format is needed.
        """
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import QhullError

        points = self.coords_m.T
        lower, upper = points.min(axis=0), points.max(axis=0)
        span = upper - lower
        scale = np.where(span > 0, span, 1.0)
        origin = (lower + upper) / 2
        # Use the physical origin for centered ROIs. For off-center saved
        # ROIs that exclude zero, choose the midpoint along that coordinate.
        centers = np.where((lower <= 0) & (upper >= 0), 0.0, origin)
        slices = []
        for horizontal, vertical, normal in ((0, 1, 2), (0, 2, 1), (1, 2, 0)):
            x, y = np.meshgrid(np.linspace(lower[horizontal], upper[horizontal], 101),
                               np.linspace(lower[vertical], upper[vertical], 101))
            query = np.tile(centers, (x.size, 1))
            query[:, horizontal], query[:, vertical] = x.ravel(), y.ravel()
            slices.append(dict(horizontal=horizontal, vertical=vertical, normal=normal,
                               position=centers[normal], x_mm=x * 1000, y_mm=y * 1000,
                               query=(query - origin) / scale, values=None))

        # Spherical ROI sampling repeats the center, poles and azimuth seam.
        # Merge coincident points at relative 1e-12 resolution before meshing.
        normalized, inverse = np.unique(np.round((points - origin) / scale, 12),
                                        axis=0, return_inverse=True)
        values = (np.bincount(inverse, weights=self.generated_mT_per_A)
                  / np.bincount(inverse))
        mean = normalized.mean(axis=0)
        _, singular, directions = np.linalg.svd(normalized - mean, full_matrices=False)
        rank = int(np.count_nonzero(singular > max(float(singular[0]), 1.0) * 1e-10))
        if rank >= 2:
            basis = directions[:rank].T
            try:
                interpolate = LinearNDInterpolator((normalized - mean) @ basis, values)
                for section in slices:
                    query = section['query'] - mean
                    projected = query @ basis
                    field = np.asarray(interpolate(projected), dtype=float)
                    # For planar archives, reject points outside that plane
                    # instead of projecting them into an invented 3D field.
                    outside = np.linalg.norm(query - projected @ basis.T, axis=1) > 1e-9
                    field[outside] = np.nan
                    section['values'] = np.ma.masked_invalid(field.reshape(section['x_mm'].shape))
            except (QhullError, ValueError):
                # A sparse/degenerate archive can still show its other plots.
                pass
        for section in slices:
            del section['query']
        return tuple(slices)


def field_data_from_solution(solution, gradient_axis: str,
                             b0_direction: str = "+y",
                             project_name: str = "gradient") -> FieldPlotData:
    """Extract the final connected-wire field and the target at one ampere."""
    coords = np.asarray(solution.target_field.coords, dtype=float)
    generated = np.asarray(solution.solution_errors.combined_field_layout_per1Amp, dtype=float)
    target = np.asarray(solution.solution_errors.target_field_1A.b, dtype=float)
    if generated.shape != coords.shape or target.shape != coords.shape:
        raise ValueError("Solution field vectors must match physical coordinates (3, N)")
    b0 = _b0_vector(b0_direction)
    return FieldPlotData(coords, b0 @ generated * 1000.0, b0 @ target * 1000.0,
                         gradient_axis, b0_direction, project_name)


def load_field_data(path: str | Path) -> FieldPlotData:
    """Load a saved result with pickle disabled and validate its sample arrays."""
    with np.load(path, allow_pickle=False) as archive:
        if int(archive["format_version"]) not in (1, 2):
            raise ValueError("Unsupported field result format")
        return FieldPlotData(
            coords_m=archive["coords_m"],
            generated_mT_per_A=archive["generated_mT_per_A"],
            target_mT_per_A=archive["target_mT_per_A"],
            gradient_axis=str(archive["gradient_axis"].item()),
            b0_direction=str(archive["b0_direction"].item()),
            project_name=str(archive["project_name"].item()),
            circuit_stage=str(archive['circuit_stage'].item()) if 'circuit_stage' in archive else 'coilgen',
        )


def draw_field_figure(figure, data: FieldPlotData, kind: str,
                      tr: Callable | None = None):
    """Draw into a Figure shared by the PNG exporter and the Tk viewer."""
    if kind not in PLOT_KINDS:
        raise ValueError(f"Unknown field plot: {kind}")
    figure.clear()
    text = lambda source, **values: _translate(tr, source, **values)
    heading = text("Gradient G{axis} | B0 {direction}",
                   axis=data.gradient_axis.upper(), direction=data.b0_direction.upper())
    slope, fit, residual, rms = data.linearity()
    efficiency = text("Generated gradient: {slope:.4g} mT/m/A", slope=slope)
    figure.suptitle(f"{text(PLOT_LABELS[kind])}\n{heading}\n{efficiency}", fontsize=14)
    if data.circuit_stage == 'final':
        figure.text(0.5, 0.85, text('Final conductor with leads; external supply/return wires excluded.'),
                    ha='center', fontsize=9, color='#555555')
    coord_mm = data.gradient_coords_m * 1000.0
    order = np.argsort(coord_mm)
    field = data.generated_mT_per_A
    target = data.target_mT_per_A

    if kind == "comparison":
        ax = figure.add_subplot(111)
        ax.plot(coord_mm[order], target[order], color="#c24b3b", linewidth=2,
                label=text("Objective at 1 A"))
        ax.scatter(coord_mm, field, s=12, alpha=0.55, color="#2378a6",
                   label=text("Generated wire field at 1 A"), rasterized=True)
        ax.set_xlabel(text("Position {axis} [mm]", axis=data.gradient_axis.upper()))
        ax.set_ylabel(text("Field parallel to B0 [mT/A]"))
        ax.legend()
        ax.grid(alpha=0.3, linestyle=":")
        figure.text(0.5, 0.025,
                    text("Both curves use 1 A; the objective amplitude is not rescaled to the generated field."),
                    ha="center", fontsize=9)
        figure.subplots_adjust(left=0.12, right=0.97, bottom=0.16, top=0.80)
    elif kind == "linearity":
        ax = figure.add_subplot(211)
        residual_ax = figure.add_subplot(212, sharex=ax)
        ax.scatter(coord_mm, field, s=12, alpha=0.55, color="#2378a6",
                   label=text("Generated wire field at 1 A"), rasterized=True)
        ax.plot(coord_mm[order], fit[order], color="#c24b3b", linewidth=2,
                label=text("Linear fit"))
        ax.set_ylabel(text("Field parallel to B0 [mT/A]"))
        ax.legend(loc="best")
        residual_ax.scatter(coord_mm, residual, s=12, alpha=0.55, color="#2378a6",
                            rasterized=True)
        residual_ax.axhline(0, color="#555555", linewidth=1)
        residual_ax.set_xlabel(text("Position {axis} [mm]", axis=data.gradient_axis.upper()))
        residual_ax.set_ylabel(text("Residual to linear fit [mT/A]"))
        ax.grid(alpha=0.3, linestyle=":")
        residual_ax.grid(alpha=0.3, linestyle=":")
        figure.text(0.5, 0.025, text("Residual RMS: {rms:.4g} mT/A", rms=rms),
                    ha="center", fontsize=10)
        figure.subplots_adjust(left=0.14, right=0.97, bottom=0.15, top=0.80, hspace=0.3)
    elif kind == "spatial":
        from matplotlib.colors import Normalize

        coords_mm = data.coords_m * 1000.0
        b0 = _b0_vector(data.b0_direction)
        spans = np.ptp(coords_mm, axis=1)
        from .plot_arrows import ViewScaledArrow
        center = coords_mm.mean(axis=1)
        for index, (values, caption, colorbar_label) in enumerate((
            (field, "Generated field", "Field parallel to B0 [mT/A]"),
            (field - target, "Error relative to objective", "Generated minus objective [mT/A]"),
        ), 1):
            ax = figure.add_subplot(1, 2, index, projection="3d")
            limit = float(max(np.max(np.abs(values)), 1e-12))
            cloud = ax.scatter(*coords_mm, c=values, s=9, cmap="coolwarm",
                               norm=Normalize(-limit, limit), alpha=0.8,
                               rasterized=True)
            ViewScaledArrow(ax, center, b0, fraction=.25, label='B0',
                            color='#343434', linewidth=2)
            ax.set_title(text(caption), fontsize=11)
            ax.set_xlabel("X [mm]")
            ax.set_ylabel("Y [mm]")
            ax.set_zlabel("Z [mm]")
            ax.set_box_aspect(np.maximum(spans, max(spans.max() * 0.05, 1.0)))
            colorbar = figure.colorbar(cloud, ax=ax, fraction=0.035, pad=0.12,
                                      shrink=0.7)
            colorbar.set_label(text(colorbar_label), fontsize=9)
            colorbar.ax.tick_params(labelsize=8)
        figure.text(0.5, 0.025,
                    text("Sampled ROI points; no interpolation. Physical axes match the STL viewer."),
                    ha="center", fontsize=9)
        figure.subplots_adjust(left=0.02, right=0.88, bottom=0.1, top=0.80, wspace=0.42)
    else:
        from matplotlib.cm import ScalarMappable
        from matplotlib.colors import Normalize

        limit = float(max(np.max(np.abs(field)), 1e-12))
        levels = np.linspace(-limit, limit, 17)
        norm = Normalize(-limit, limit)
        for index, section in enumerate(data.contour_slices, 1):
            ax = figure.add_subplot(1, 3, index)
            horizontal, vertical, normal = (
                section[key] for key in ('horizontal', 'vertical', 'normal'))
            plane = 'XYZ'[horizontal] + 'XYZ'[vertical]
            ax.set_title(text("{plane} plane | {axis} = {position:.3g} mm",
                              plane=plane, axis='XYZ'[normal],
                              position=section['position'] * 1000), fontsize=10)
            ax.set_xlabel(text("Position {axis} [mm]", axis='XYZ'[horizontal]))
            ax.set_ylabel(text("Position {axis} [mm]", axis='XYZ'[vertical]))
            ax.set_aspect('equal', adjustable='box')
            ax.tick_params(labelsize=8)
            if np.ptp(section['x_mm']) > 0:
                ax.set_xlim(float(section['x_mm'].min()), float(section['x_mm'].max()))
            if np.ptp(section['y_mm']) > 0:
                ax.set_ylim(float(section['y_mm'].min()), float(section['y_mm'].max()))
            values = section['values']
            valid = None if values is None else ~np.ma.getmaskarray(values)
            if (valid is None or np.count_nonzero(valid) < 4
                    or np.count_nonzero(np.any(valid, axis=0)) < 2
                    or np.count_nonzero(np.any(valid, axis=1)) < 2
                    or np.ptp(section['x_mm']) == 0 or np.ptp(section['y_mm']) == 0):
                ax.text(.5, .5, text("Insufficient ROI samples for this plane."),
                        ha='center', va='center', transform=ax.transAxes,
                        wrap=True, fontsize=9)
                continue
            ax.contourf(section['x_mm'], section['y_mm'], values, levels=levels,
                        cmap='coolwarm', norm=norm, corner_mask=False)
            low, high = float(values.min()), float(values.max())
            if high - low > max(limit * 1e-8, 1e-12):
                # Equal field increments and colors across the three planes
                # keep transverse variation comparable to the main gradient.
                line_levels = levels[(levels > low) & (levels < high)]
                if line_levels.size:
                    isolines = ax.contour(section['x_mm'], section['y_mm'], values,
                                          levels=line_levels, colors='#303030',
                                          linewidths=.65, corner_mask=False)
                    ax.clabel(isolines, inline=True, fmt='%.3g', fontsize=7)
                if low < 0 < high:
                    ax.contour(section['x_mm'], section['y_mm'], values,
                               levels=[0.0], colors='#202020', linewidths=1.2,
                               corner_mask=False)
            else:
                ax.text(.5, .04, text("Uniform field in this plane: {value:.4g} mT/A",
                                     value=(low + high) / 2),
                        ha='center', va='bottom', transform=ax.transAxes, fontsize=8,
                        bbox=dict(facecolor='white', alpha=.85, edgecolor='none'))
            ax.grid(alpha=.15, linestyle=':')
        colorbar_ax = figure.add_axes((.91, .24, .018, .48))
        colorbar = figure.colorbar(ScalarMappable(norm=norm, cmap='coolwarm'), cax=colorbar_ax)
        colorbar.set_label(text("Field parallel to B0 [mT/A]"), fontsize=9)
        colorbar.ax.tick_params(labelsize=8)
        figure.text(.5, .025,
                    text("Central physical slices; linear interpolation inside the sampled ROI only."),
                    ha='center', fontsize=9)
        figure.subplots_adjust(left=.07, right=.86, bottom=.15, top=.78, wspace=.5)
    return figure


def create_field_figure(data: FieldPlotData, kind: str = "comparison",
                        tr: Callable | None = None):
    """Create an OO matplotlib Figure; never import pyplot or change backends."""
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 7), dpi=100)
    return draw_field_figure(figure, data, kind, tr)


def save_field_plots(solution, output_dir: str | Path, gradient_axis: str,
                     b0_direction: str = "+y", project_name: str = "gradient",
                     tr: Callable | None = None) -> dict:
    """Save reusable data and all PNGs, including when GUI/show_plots is false.

    Safe in a worker: FigureCanvasAgg renders directly without a Tk event loop
    or pyplot.show(). The returned dict is suitable for storing in metrics.
    """
    data = field_data_from_solution(solution, gradient_axis, b0_direction, project_name)
    return save_plot_data(data, output_dir, tr)


def save_plot_data(data: FieldPlotData, output_dir: str | Path,
                   tr: Callable | None = None) -> dict:
    """Save an evaluated circuit, using the same figures as the result viewer."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    project_name = data.project_name
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Stems normally come from paths.unique_stem; disallow path components here.
    if not project_name or "/" in project_name or "\\" in project_name or project_name in (".", ".."):
        raise ValueError("The field result project name must be a filename stem")
    data_path = output / f"{project_name}_field_data.npz"
    np.savez_compressed(
        data_path,
        format_version=np.asarray(2, dtype=np.int64),
        coords_m=data.coords_m,
        generated_mT_per_A=data.generated_mT_per_A,
        target_mT_per_A=data.target_mT_per_A,
        gradient_axis=np.asarray(data.gradient_axis),
        b0_direction=np.asarray(data.b0_direction),
        project_name=np.asarray(data.project_name),
        circuit_stage=np.asarray(data.circuit_stage),
    )
    png_paths = {}
    for kind in PLOT_KINDS:
        figure = create_field_figure(data, kind, tr)
        canvas = FigureCanvasAgg(figure)
        path = output / f"{project_name}_field_{kind}.png"
        canvas.print_figure(str(path), dpi=150, facecolor="white")
        png_paths[kind] = str(path)
        figure.clear()
    return {"data_path": str(data_path), "png_paths": png_paths}
