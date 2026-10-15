"""Design three concentric gradients in one cancellable calculation."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Wedge, Polygon
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from coilgen.config import CONDUCTOR_MATERIAL_RESISTIVITY, Config
from halbach_coils.coilgen.plot_arrows import ViewScaledArrow
from .advanced_controls import AdvancedControls, _HoverHelp
from .field_viewer import electrical_result_text
from .plot_controls import enable_3d_zoom
from .runner import JobCancelled, WorkerRunner


_COLORS = {'x': '#b46ed7', 'y': '#dcbe46', 'z': '#50b9d2'}


class BatchPanel(ttk.Frame):
    def __init__(self, master, get_output_dir, set_output_dir, root):
        super().__init__(master)
        self.root = root
        self.get_output_dir = get_output_dir
        self.set_output_dir = set_output_dir
        self.runner = None
        self._preview_pending = None
        self._plots = {}
        self._tooltips = []
        self._entries = {}
        self._last_layers = None
        self._actual_interfaces = None
        self._build()
        self.bind('<Destroy>', self._on_destroy, add='+')

    def _build(self):
        split = ttk.Panedwindow(self, orient='horizontal')
        split.pack(fill='both', expand=True, padx=6, pady=4)
        controls = ttk.Frame(split)
        split.add(controls, weight=2)
        controls_body = ttk.Frame(controls)
        controls_body.pack(fill='both', expand=True)
        canvas = tk.Canvas(controls_body, highlightthickness=0, width=470)
        scroll = ttk.Scrollbar(controls_body, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        left = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=left, anchor='nw')
        left.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))

        shared = ttk.LabelFrame(left, text='Shared dimensions', padding=8)
        shared.pack(fill='x', pady=(0, 4))
        shared.columnconfigure(1, weight=1)
        self.height_var = self._entry(shared, 0, 'Height [mm]:', '170')
        radius_modes = ttk.Frame(shared)
        radius_modes.grid(row=1, column=0, columnspan=2, sticky='w', pady=4)
        self.radius_mode_var = tk.StringVar(self, value='inner')
        self._radius_mode = 'inner'
        ttk.Radiobutton(radius_modes, text='Inner mold radius', variable=self.radius_mode_var,
                        value='inner').pack(side='left')
        ttk.Radiobutton(radius_modes, text='Outer mold radius', variable=self.radius_mode_var,
                        value='outer').pack(side='left', padx=8)
        self.anchor_radius_var = self._entry(shared, 2, 'Reference radius [mm]:', '26.5')
        self.radial_gap_var = self._entry(shared, 3, 'Gap between gradients [mm]:', '4.3')
        self.roi_vars = {}
        for row, axis in enumerate('xyz', 4):
            self.roi_vars[axis] = self._entry(shared, row, f'ROI R{axis} [mm]:', '20')
        self.a_var = self._entry(shared, 7, 'Groove deformation A:', '2')
        self.b_var = self._entry(shared, 8, 'Groove deformation B:', '1')
        ttk.Label(shared, text='Conductor material:').grid(row=9, column=0, sticky='w', pady=3)
        self.material_var = tk.StringVar(self, value='Cu')
        material = ttk.Combobox(shared, textvariable=self.material_var,
                                values=[*CONDUCTOR_MATERIAL_RESISTIVITY, 'Custom'],
                                state='readonly', width=13)
        material.grid(row=9, column=1, sticky='e')
        material.bind('<<ComboboxSelected>>', self._on_material_changed)
        self.resistivity_var = self._entry(shared, 10, 'Resistivity [ohm.m]:', '1.68e-8')

        layers = ttk.LabelFrame(left, text='Layers: inner to outer', padding=8)
        layers.pack(fill='x', pady=4)
        ttk.Label(layers, text='Layer order:').grid(row=0, column=0, sticky='w', pady=4)
        self.order_var = tk.StringVar(self, value='Z, X, Y')
        ttk.Combobox(layers, textvariable=self.order_var, state='readonly', width=16,
                     values=['Y, Z, X', 'Y, X, Z', 'X, Y, Z', 'X, Z, Y', 'Z, X, Y', 'Z, Y, X']).grid(
                         row=0, column=1, columnspan=3, sticky='w')
        for col, label in enumerate(('Axis', 'Cable Ø [mm]', 'Layer gap [mm]', 'Tikhonov', 'Levels')):
            ttk.Label(layers, text=label).grid(row=1, column=col, padx=3, pady=3)
        self.cable_vars = {}
        self.layer_gap_vars = {}
        self.tikhonov_vars = {}
        self.levels_vars = {}
        self.radius_labels = {}
        self._layer_rows = {}
        for row, axis in enumerate('xyz', 2):
            label = ttk.Label(layers, text='G' + axis.upper(), foreground=_COLORS[axis])
            label.grid(row=row, column=0, padx=3, pady=3)
            self._layer_rows[axis] = [label]
            self.cable_vars[axis] = tk.StringVar(self, value='2')
            self.layer_gap_vars[axis] = tk.StringVar(self, value='0')
            self.tikhonov_vars[axis] = tk.StringVar(self, value='2500')
            self.levels_vars[axis] = tk.StringVar(self, value='12')
            for col, var in enumerate((self.cable_vars[axis], self.layer_gap_vars[axis], self.tikhonov_vars[axis],
                                       self.levels_vars[axis]), 1):
                entry = ttk.Entry(layers, textvariable=var, width=8)
                entry.grid(row=row, column=col, padx=3, pady=3)
                self._layer_rows[axis].append(entry)
        for row, axis in enumerate('xyz', 5):
            label = ttk.Label(layers, wraplength=430, justify='left')
            label.grid(row=row, column=0, columnspan=5, sticky='w', pady=2)
            self.radius_labels[axis] = label
        self.radius_note = ttk.Label(layers, text='One reference radius fixes the set. Cable dimensions and crossings determine each mold thickness.',
                         wraplength=430, justify='left')
        self.radius_note.grid(row=8, column=0, columnspan=5, sticky='w', pady=(6, 0))
        self.total_radius_label = ttk.Label(layers, wraplength=430, justify='left')
        self.total_radius_label.grid(row=9, column=0, columnspan=5, sticky='w', pady=(6, 0))

        keys = ttk.LabelFrame(left, text='Assembly keys', padding=8)
        keys.pack(fill='x', pady=4)
        self.keys_var = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(keys, text='Generate anti-rotation keys', variable=self.keys_var).pack(anchor='w')
        self.key_dimensions = ttk.Frame(keys)
        self.key_dimensions.pack(fill='x')
        self.key_length_var = self._entry(self.key_dimensions, 0, 'Key axial length [mm]:', '4')
        self.key_width_var = self._entry(self.key_dimensions, 1, 'Key width [mm]:', '4')
        self.fit_clearance_var = self._entry(self.key_dimensions, 2, 'Key clearance per side [mm]:', '0.1')
        ttk.Label(keys, text='Keys share the physical X/Y/Z frame. The gradients are never rotated to fit.',
                  wraplength=430, justify='left').pack(fill='x', pady=(4, 0))

        self.coilgen_advanced = AdvancedControls(left, root=self.root, on_change=self._schedule_preview)
        self.coilgen_advanced.pack(fill='x', pady=4)
        bar = ttk.Frame(controls)
        bar.pack(side='bottom', fill='x', pady=6)
        self.run_btn = ttk.Button(bar, text='Design Gx, Gy and Gz', command=self._on_run)
        self.run_btn.pack(side='left')
        self.stop_btn = ttk.Button(bar, text='Stop', command=self._on_stop)
        self.progress = ttk.Progressbar(bar, mode='determinate', maximum=100, length=100)
        self.progress.pack(side='left', fill='x', expand=True, padx=8)
        self.phase_var = tk.StringVar(self)
        ttk.Label(controls, textvariable=self.phase_var, wraplength=430).pack(side='bottom', fill='x')

        right = ttk.Panedwindow(split, orient='vertical')
        split.add(right, weight=3)
        previews = ttk.LabelFrame(right, text='Concentric assembly preview', padding=4)
        right.add(previews, weight=3)
        self.figure = Figure(figsize=(7, 5), dpi=100)
        self.radial_ax = self.figure.add_subplot(121)
        self.ax3d = self.figure.add_subplot(122, projection='3d')
        self.figure.subplots_adjust(left=.07, right=.98, top=.92, bottom=.1, wspace=.12)
        self.figure_canvas = FigureCanvasTkAgg(self.figure, master=previews)
        self.figure_canvas.get_tk_widget().pack(fill='both', expand=True)
        enable_3d_zoom(self.figure_canvas)
        self.preview_notice = ttk.Label(previews, wraplength=650, justify='left')
        self.preview_notice.pack(fill='x')
        results = ttk.Frame(previews)
        results.pack(fill='x', pady=3)
        ttk.Label(results, text='Field results:').pack(side='left')
        self.result_buttons = {}
        for axis in 'xyz':
            button = ttk.Button(results, text='G' + axis.upper(), width=5, state='disabled',
                                command=lambda a=axis: self.root.show_field_plots(self._plots[a]))
            button.pack(side='left', padx=3)
            self.result_buttons[axis] = button
        log = ttk.LabelFrame(right, text='Log', padding=4)
        right.add(log, weight=1)
        self.log_text = tk.Text(log, height=7, wrap='word')
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scroll = ttk.Scrollbar(log, command=self.log_text.yview)
        log_scroll.pack(side='right', fill='y')
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.runner = WorkerRunner(self.log_text, self.progress, self.root)

        variables = [self.height_var, self.anchor_radius_var, self.radial_gap_var,
                     self.a_var, self.b_var, self.order_var, self.keys_var,
                     self.material_var, self.resistivity_var,
                     self.key_length_var, self.key_width_var, self.fit_clearance_var,
                     *self.roi_vars.values(), *self.cable_vars.values(), *self.layer_gap_vars.values(),
                     *self.tikhonov_vars.values(), *self.levels_vars.values()]
        for variable in variables:
            variable.trace_add('write', self._schedule_preview)
        self._preview_variables = variables + [self.radius_mode_var]
        self.radius_mode_var.trace_add('write', self._on_radius_mode_changed)
        self._bind_scroll(left, canvas)
        tips = [
            (self._entries[str(self.anchor_radius_var)], 'Use the inner radius of the innermost mold, or the outer radius of the outermost mold. All other radii are calculated.'),
            (self._entries[str(self.radial_gap_var)], 'Clearance between neighboring mold bodies. This is separate from the crossing gap inside each gradient.'),
            (self._entries[str(self.a_var)], 'A multiplies each cable diameter to set the radial groove height. B sets the tangential groove width.'),
            (self._entries[str(self.b_var)], 'A multiplies each cable diameter to set the radial groove height. B sets the tangential groove width.'),
        ]
        for widgets in self._layer_rows.values():
            tips.append((widgets[2], 'Radial gap between cable crossings within this gradient. It contributes to this mold thickness.'))
        for widget, source in tips:
            self._tooltips.append(_HoverHelp(widget, lambda text=source: self.root.tr(text)))
        self._redraw_preview()

    def _entry(self, parent, row, label, value):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=3)
        variable = tk.StringVar(self, value=value)
        entry = ttk.Entry(parent, textvariable=variable, width=14)
        entry.grid(row=row, column=1, sticky='e', padx=3)
        self._entries[str(variable)] = entry
        return variable

    @staticmethod
    def _bind_scroll(widget, canvas):
        def scroll(event):
            canvas.yview_scroll(int(-event.delta / 120), 'units')
            return 'break'
        widget.bind('<MouseWheel>', scroll)
        for child in widget.winfo_children():
            BatchPanel._bind_scroll(child, canvas)

    def _on_material_changed(self, _event=None):
        resistivity = CONDUCTOR_MATERIAL_RESISTIVITY.get(self.material_var.get())
        if resistivity is not None:
            self.resistivity_var.set(f'{resistivity:.3g}')

    def _base_config(self):
        cfg = Config(gradient_axis='x', b0_direction=self.root.b0_var.get(), show_plots=False)
        cfg.cylinder.height = float(self.height_var.get()) / 1000
        cfg.target.rx, cfg.target.ry, cfg.target.rz = (
            float(self.roi_vars[axis].get()) / 1000 for axis in 'xyz')
        cfg.wire.cross_section_a_frac = float(self.a_var.get())
        cfg.wire.cross_section_b_frac = float(self.b_var.get())
        cfg.fasthenry.material = self.material_var.get()
        cfg.fasthenry.specific_conductivity = float(self.resistivity_var.get())
        if not math.isfinite(cfg.fasthenry.specific_conductivity) or cfg.fasthenry.specific_conductivity <= 0:
            raise ValueError(self.root.tr('Resistivity must be a positive number.'))
        self.coilgen_advanced.apply_to(cfg)
        return cfg

    def _build_cfg(self):
        """Construct one validated backend batch description; GUI lengths are mm."""
        from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs
        key_values = ((float(self.key_length_var.get()) / 1000,
                       float(self.key_width_var.get()) / 1000,
                       float(self.fit_clearance_var.get()) / 1000)
                      if self.keys_var.get() else (.004, .004, .0001))
        cfg = BatchConfig(
            base=self._base_config(),
            anchor_radius=float(self.anchor_radius_var.get()) / 1000,
            radius_mode=self.radius_mode_var.get(),
            axis_order=tuple(part.strip().lower() for part in self.order_var.get().split(',')),
            radial_gap=float(self.radial_gap_var.get()) / 1000,
            conductor_widths=tuple(float(self.cable_vars[axis].get()) / 1000 for axis in 'xyz'),
            layer_gaps=tuple(float(self.layer_gap_vars[axis].get()) / 1000 for axis in 'xyz'),
            tikhonov_factors=tuple(float(self.tikhonov_vars[axis].get()) for axis in 'xyz'),
            num_levels=tuple(int(self.levels_vars[axis].get()) for axis in 'xyz'),
            include_keys=self.keys_var.get(),
            key_length=key_values[0],
            key_width=key_values[1],
            fit_clearance=key_values[2],
            output_dir=self.get_output_dir(),
        )
        build_layer_configs(cfg)
        return cfg

    def _schedule_preview(self, *_args):
        if self._preview_pending is not None:
            self.after_cancel(self._preview_pending)
        self._preview_pending = self.after(250, self._redraw_preview)

    def _on_radius_mode_changed(self, *_args):
        mode = self.radius_mode_var.get()
        if mode != self._radius_mode and self._last_layers:
            value = (self._last_layers[0].shell_inner_radius if mode == 'inner'
                     else self._last_layers[-1].shell_outer_radius)
            self.anchor_radius_var.set(f'{value * 1000:.7g}')
        self._radius_mode = mode
        self._schedule_preview()

    def _preview_signature(self):
        return tuple(variable.get() for variable in self._preview_variables) + (
            self.root.b0_var.get(),
            *(variable.get() for variable in self.coilgen_advanced.variables.values()),
        )

    def _redraw_preview(self):
        if self._preview_pending is not None:
            self.after_cancel(self._preview_pending)
        self._preview_pending = None
        if not hasattr(self, 'ax3d'):
            return
        for child in self.key_dimensions.winfo_children():
            child.configure(state='normal' if self.keys_var.get() else 'disabled')
        try:
            from halbach_coils.coilgen.batch import build_layer_configs
            cfg = self._build_cfg()
            layers = build_layer_configs(cfg)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            self.preview_notice.configure(text=self.root.tr(str(exc)), foreground='#a32323')
            return
        for row, axis in enumerate(cfg.axis_order, 2):
            for widget in self._layer_rows[axis]:
                widget.grid_configure(row=row)
            self.radius_labels[axis].grid_configure(row=row+3)
        self._last_layers = layers
        # Filled in with the same backend dimensions used to export the molds.
        try:
            self._draw_geometry(cfg, layers)
        except (ValueError, RuntimeError) as exc:
            self.preview_notice.configure(text=self.root.tr(str(exc)), foreground='#a32323')

    def _draw_geometry(self, batch, layers):
        ax, section = self.ax3d, self.radial_ax
        elev, azim = ax.elev, ax.azim
        ax.clear()
        section.clear()
        theta = np.linspace(0, 2 * math.pi, 73)
        height = batch.base.cylinder.height * 1000
        for cfg in layers:
            axis = cfg.gradient_axis
            inner, outer = cfg.shell_inner_radius * 1000, cfg.shell_outer_radius * 1000
            color = _COLORS[axis]
            section.add_patch(Wedge((0, 0), outer, 0, 360, width=outer-inner,
                                    facecolor=color, edgecolor='#454545', linewidth=.6, alpha=.7))
            t, z = np.meshgrid(theta, [-height/2, height/2])
            ax.plot_surface(outer*np.cos(t), outer*np.sin(t), z, color=color, alpha=.18,
                            linewidth=0, antialiased=True)
            if self.coilgen_advanced.expanded.get():
                refinement = 2 ** cfg.advanced.iteration_num_mesh_refinement
                mesh_theta, mesh_z = np.meshgrid(
                    np.linspace(0, 2*math.pi, min(cfg.cylinder.n_circ*refinement+1, 61)),
                    np.linspace(-height/2, height/2, min(cfg.cylinder.n_long*refinement+1, 31)))
                design_radius = cfg.cylinder_design_radius*1000
                ax.plot_wireframe(design_radius*np.cos(mesh_theta), design_radius*np.sin(mesh_theta),
                                  mesh_z*cfg.cylinder.mesh_length_factor,
                                  color=color, alpha=.25, linewidth=.4)
            for end in (-height/2, height/2):
                for radius in (inner, outer):
                    ax.plot(radius*np.cos(theta), radius*np.sin(theta), np.full_like(theta, end),
                            color=color, linewidth=1)
            self.radius_labels[axis].configure(text=self.root.tr(
                '{axis}: mold {inner:.2f}–{outer:.2f} mm; wall {wall:.2f} mm\nGroove {height:.2f} × {width:.2f} mm; cable envelope {wire_inner:.2f}–{wire_outer:.2f} mm',
                axis='G'+axis.upper(), inner=inner, outer=outer,
                wall=cfg.shell_wall_thickness * 1000,
                height=cfg.groove_radial_height * 1000,
                width=cfg.groove_tangential_width * 1000,
                wire_inner=cfg.estimated_wire_inner_radius * 1000,
                wire_outer=cfg.estimated_wire_outer_radius * 1000))
            section.add_patch(Wedge((0, 0), cfg.estimated_wire_outer_radius*1000, 0, 360,
                                    width=(cfg.estimated_wire_outer_radius-cfg.estimated_wire_inner_radius)*1000,
                                    facecolor='none', edgecolor=color, linestyle=':', linewidth=.7))
        from halbach_coils.coilgen.assembly import nominal_key_pairs, key_pair_meshes
        actual_keys = (self._actual_interfaces is not None
                       and self._preview_signature() == getattr(self, '_running_signature', None))
        if actual_keys:
            by_axis = {cfg.gradient_axis: cfg for cfg in layers}
            key_pairs = []
            for interface in self._actual_interfaces:
                male, female = key_pair_meshes(batch, by_axis[interface['inner_axis']],
                                               by_axis[interface['outer_axis']], interface['angle_deg'])
                key_pairs.append({**interface, 'male_mm': male, 'female_mm': female})
        else:
            key_pairs = nominal_key_pairs(batch, layers)
        from scipy.spatial import ConvexHull
        for pair in key_pairs:
            color = _COLORS[pair['inner_axis']]
            for name, fill in (('female_mm', False), ('male_mm', True)):
                mesh = pair[name]
                points = np.unique(mesh.vertices[:, :2], axis=0)
                polygon = points[ConvexHull(points).vertices]
                section.add_patch(Polygon(polygon, closed=True, facecolor=color if fill else 'none',
                                          edgecolor='#383838', linewidth=.8,
                                          linestyle='-' if fill else '--', alpha=.9))
                ax.add_collection3d(Poly3DCollection(mesh.triangles, facecolors=color,
                                                     edgecolors='#555555', linewidths=.3,
                                                     alpha=.85 if fill else .08))
        rx, ry, rz = (getattr(batch.base.target, 'r'+axis)*1000 for axis in 'xyz')
        u, v = np.meshgrid(np.linspace(0, 2*math.pi, 30), np.linspace(0, math.pi, 17))
        ax.plot_surface(rx*np.cos(u)*np.sin(v), ry*np.sin(u)*np.sin(v), rz*np.cos(v),
                        color='#2f80ed', alpha=.22, linewidth=0)
        outer = max(cfg.shell_outer_radius for cfg in layers)*1000
        wire_outer = max(cfg.estimated_wire_outer_radius for cfg in layers)*1000
        self.total_radius_label.configure(text=self.root.tr(
            'Maximum mold radius: {mold:.2f} mm. Total radius including cable: {cable:.2f} mm.',
            mold=outer, cable=wire_outer))
        section.set_xlim(-outer*1.12, outer*1.12)
        section.set_ylim(-outer*1.12, outer*1.12)
        section.set_aspect('equal')
        section.set_xlabel('X [mm]', fontsize=8)
        section.set_ylabel('Y [mm]', fontsize=8)
        section.set_title(self.root.tr('Radial section'), fontsize=9)
        section.tick_params(labelsize=7)
        lim = max(outer, height/2)*1.15
        for setter in (ax.set_xlim3d, ax.set_ylim3d, ax.set_zlim3d):
            setter(-lim, lim)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel('X [mm]', fontsize=8)
        ax.set_ylabel('Y [mm]', fontsize=8)
        ax.set_zlabel('Z [mm]', fontsize=8)
        ax.tick_params(labelsize=7)
        for index, color in enumerate(('#d32f2f', '#2e7d32', '#1565c0')):
            ViewScaledArrow(ax, [0, 0, 0], np.eye(3)[index], fraction=.425,
                            label='+'+'XYZ'[index], color=color)
        ViewScaledArrow(ax, [0, 0, 0], batch.base.b0_vector, fraction=.28,
                        label='B₀ '+batch.base.b0_direction.upper(), color='#a000a8')
        ax.set_title(self.root.tr('Assembly: Z longitudinal'), fontsize=9)
        order = ' → '.join('G'+axis.upper() for axis in batch.axis_order)
        notice = self.root.tr(
            'Inner to outer: {order}. B₀ {direction}. Preview shows dimensions; grooves require a design run.',
            order=order, direction=batch.base.b0_direction.upper())
        minimum_gap = max(
            inner.estimated_wire_outer_radius - inner.shell_outer_radius
            + outer.shell_inner_radius - outer.estimated_wire_inner_radius
            for inner, outer in zip(layers, layers[1:])) + .0003
        notice += '\n' + self.root.tr('Suggested gap without radial overlap: {gap:.2f} mm.', gap=minimum_gap * 1000)
        overlap = any(inner.estimated_wire_outer_radius > outer.estimated_wire_inner_radius
                      for inner, outer in zip(layers, layers[1:]))
        if overlap:
            notice += '\n' + self.root.tr('Cable envelopes overlap radially. The final 3D check verifies the actual conductor clearance.')
        if batch.include_keys:
            notice += '\n' + self.root.tr(
                'Final key positions verified against the conductors.' if actual_keys else
                'Key positions are preliminary; the final design selects a clear location for each key.')
        self.preview_notice.configure(text=notice, foreground='#9c6515' if overlap else '')
        self.figure_canvas.draw_idle()

    def _on_run(self):
        if not self.get_output_dir():
            messagebox.showwarning(self.root.tr('Missing directory'),
                                   self.root.tr('Select an output directory first.'), parent=self.root)
            return
        try:
            cfg = self._build_cfg()
            from halbach_coils.coilgen.assembly import nominal_key_pairs
            nominal_key_pairs(cfg)
        except (ValueError, RuntimeError, ZeroDivisionError, OverflowError) as exc:
            messagebox.showerror(self.root.tr('Invalid parameters'), self.root.tr(str(exc)), parent=self.root)
            return
        self._plots = {}
        self._actual_interfaces = None
        self._running_order = cfg.axis_order
        self._running_cfg = cfg
        self._running_signature = self._preview_signature()
        for button in self.result_buttons.values():
            button.configure(state='disabled')
        self.runner.run_job('batch', cfg,
                            extra={'question_language': self.root.language_var.get()},
                            ask_user=self._ask_user, on_done=self._on_done,
                            on_progress=self._on_progress)

    def _ask_user(self, question):
        return messagebox.askyesno(self.root.tr('Cable collision'), question,
                                   icon=messagebox.WARNING, default=messagebox.NO, parent=self.root)

    def _on_progress(self, phase, value, event, row=None):
        axis = 'G'+row['axis'].upper() if row and 'axis' in row else phase
        self.phase_var.set(self.root.tr('Batch: {axis} — {event}', axis=axis, event=self.root.tr(event)))
        if event == 'complete':
            # The last 10% belongs to assembly validation and key generation.
            self.progress['value'] = 90 * float(value) / 3

    def _on_done(self, result, error):
        if isinstance(error, JobCancelled):
            self.runner.log(self.root.tr('Stopped. Partial output files were kept.')+'\n')
            return
        if error is not None:
            messagebox.showerror(self.root.tr('Batch design'), self.root.tr('Failed: {error}', error=error)
                                 + '\n\n' + self.root.tr('Partial results in:\n{path}',
                                                        path=self._running_cfg.output_dir),
                                 parent=self.root)
            return
        outcomes = tuple(zip(self._running_order, result.layers))
        for axis, outcome in outcomes:
            if outcome.field_plots:
                self._plots[axis] = outcome.field_plots
                self.result_buttons[axis].configure(state='normal')
        if not result.completed:
            messagebox.showwarning(self.root.tr('Batch design'), self.root.tr(
                'The set is incomplete. Completed layers were kept in:\n{path}', path=result.output_dir),
                parent=self.root)
            return
        self._actual_interfaces = (result.assembly or {}).get('interfaces')
        self._redraw_preview()
        message = self.root.tr('Done.\nResults in:\n{path}', path=result.output_dir)
        for axis, outcome in outcomes:
            electrical = electrical_result_text(outcome.metrics_path, self.root.tr)
            if electrical:
                message += '\n\nG'+axis.upper()+': '+electrical
        messagebox.showinfo(self.root.tr('Batch design'), message, parent=self.root)

    def _set_running(self, running):
        self.run_btn.configure(state='disabled' if running else 'normal')
        if running:
            self.stop_btn.configure(state='normal', text=self.root.tr('Stop'))
            if not self.stop_btn.winfo_ismapped():
                self.stop_btn.pack(side='left', before=self.progress, padx=6)
        else:
            self.stop_btn.pack_forget()

    def _on_stop(self):
        self.runner.request_stop()
        self.stop_btn.configure(state='disabled', text=self.root.tr('Stopping...'))

    def retranslate(self):
        self.coilgen_advanced.retranslate()
        self._redraw_preview()

    def _on_destroy(self, event):
        if event.widget is self and self._preview_pending is not None:
            self.after_cancel(self._preview_pending)
            self._preview_pending = None
