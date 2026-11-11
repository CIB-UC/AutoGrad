"""Design selected concentric gradients in one cancellable calculation."""

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
        self._actual_b0_markers = None
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

        dimensions = ttk.LabelFrame(left, text='Gradient dimensions [mm]', padding=8)
        dimensions.pack(fill='x', pady=(0, 4))
        self.length_vars = {}
        self.outer_radius_vars = {}
        self.cable_vars = {}
        self.groove_height_vars = {}
        self.groove_width_vars = {}
        self._dimension_entries = {axis: [] for axis in 'xyz'}
        for col, axis in enumerate('xyz', 1):
            ttk.Label(dimensions, text='G' + axis.upper()).grid(row=0, column=col)
        dimension_fields = (
            ('Length', self.length_vars, ('200',) * 3),
            ('Mold outer radius', self.outer_radius_vars, ('64.3', '72.6', '56')),
            ('Real cable diameter', self.cable_vars, ('2',) * 3),
            ('Groove height', self.groove_height_vars, ('4',) * 3),
            ('Groove width', self.groove_width_vars, ('2',) * 3),
        )
        for row, (label, variables, defaults) in enumerate(dimension_fields, 1):
            ttk.Label(dimensions, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8))
            for col, axis in enumerate('xyz', 1):
                var = variables[axis] = tk.StringVar(self, value=defaults[col - 1])
                entry = ttk.Entry(dimensions, textvariable=var, width=7)
                entry.grid(row=row, column=col, padx=3, pady=2)
                self._dimension_entries[axis].append(entry)

        shared = ttk.LabelFrame(left, text='Shared dimensions', padding=8)
        shared.pack(fill='x', pady=(0, 4))
        shared.columnconfigure(1, weight=1)
        ttk.Label(shared, text='Conductor material:').grid(row=0, column=0, sticky='w', pady=3)
        self.material_var = tk.StringVar(self, value='Cu')
        material = ttk.Combobox(shared, textvariable=self.material_var,
                                values=[*CONDUCTOR_MATERIAL_RESISTIVITY, 'Custom'],
                                state='readonly', width=13)
        material.grid(row=0, column=1, sticky='e')
        material.bind('<<ComboboxSelected>>', self._on_material_changed)
        self.resistivity_var = self._entry(shared, 1, 'Resistivity [ohm.m]:', '1.68e-8')
        self.b0_markers_var = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(shared, text='Add aligned B₀ marks to selected gradients',
                        variable=self.b0_markers_var).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=4)
        self.reassign_crossings_var = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(shared, text='Reassign nearby crossings between radial layers',
                        variable=self.reassign_crossings_var).grid(
            row=3, column=0, columnspan=2, sticky='w', pady=4)

        roi_frame = ttk.LabelFrame(left, text='ROI per gradient [mm]', padding=8)
        roi_frame.pack(fill='x', pady=4)
        for col, label in enumerate(('Gradient', 'Rx', 'Ry', 'Rz')):
            ttk.Label(roi_frame, text=label).grid(row=0, column=col, padx=3, pady=3)
        self.roi_vars = {}
        self.roi_spherical_vars = {}
        self.roi_entries = {}
        for row, axis in enumerate('xyz', 1):
            ttk.Label(roi_frame, text='G' + axis.upper()).grid(row=row, column=0, padx=3)
            self.roi_vars[axis] = {}
            self.roi_entries[axis] = {}
            self.roi_spherical_vars[axis] = tk.BooleanVar(self, value=False)
            for col, dimension in enumerate('xyz', 1):
                var = tk.StringVar(self, value='20')
                self.roi_vars[axis][dimension] = var
                entry = ttk.Entry(roi_frame, textvariable=var, width=8)
                entry.grid(row=row, column=col, padx=3, pady=3)
                self.roi_entries[axis][dimension] = entry
            ttk.Checkbutton(roi_frame, text='Spherical', variable=self.roi_spherical_vars[axis],
                            command=self._update_roi_entries).grid(row=row, column=4, padx=3)

        layers = ttk.LabelFrame(left, text='Layers: inner to outer', padding=8)
        layers.pack(fill='x', pady=4)
        for col, label in enumerate(('Axis', 'Layer gap [mm]', 'Tikhonov', 'Levels')):
            ttk.Label(layers, text=label).grid(row=1, column=col, padx=3, pady=3)
        self.layer_gap_vars = {}
        self.tikhonov_vars = {}
        self.levels_vars = {}
        self.radius_labels = {}
        self._layer_rows = {}
        self.enabled_vars = {}
        for row, axis in enumerate('xyz', 2):
            self.enabled_vars[axis] = tk.BooleanVar(self, value=True)
            label = ttk.Checkbutton(layers, text='G' + axis.upper(),
                                    variable=self.enabled_vars[axis])
            label.grid(row=row, column=0, padx=3, pady=3)
            self._layer_rows[axis] = [label]
            self.layer_gap_vars[axis] = tk.StringVar(self, value='0')
            self.tikhonov_vars[axis] = tk.StringVar(self, value='2500')
            self.levels_vars[axis] = tk.StringVar(self, value='10')
            for col, var in enumerate((self.layer_gap_vars[axis], self.tikhonov_vars[axis],
                                       self.levels_vars[axis]), 1):
                entry = ttk.Entry(layers, textvariable=var, width=8)
                entry.grid(row=row, column=col, padx=3, pady=3)
                self._layer_rows[axis].append(entry)
        for row, axis in enumerate('xyz', 5):
            label = ttk.Label(layers, wraplength=430, justify='left')
            label.grid(row=row, column=0, columnspan=4, sticky='w', pady=2)
            self.radius_labels[axis] = label
        self.total_radius_label = ttk.Label(layers, wraplength=430, justify='left')
        self.total_radius_label.grid(row=8, column=0, columnspan=4, sticky='w', pady=(6, 0))

        keys = ttk.LabelFrame(left, text='Assembly keys', padding=8)
        keys.pack(fill='x', pady=4)
        self.keys_var = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(keys, text='Generate anti-rotation keys', variable=self.keys_var).pack(anchor='w')
        self.key_dimensions = ttk.Frame(keys)
        self.key_dimensions.pack(fill='x')
        self.key_length_var = self._entry(self.key_dimensions, 0, 'Key axial length [mm]:', '4')
        self.key_width_var = self._entry(self.key_dimensions, 1, 'Key width [mm]:', '4')
        self.fit_clearance_var = self._entry(self.key_dimensions, 2, 'Key clearance per side [mm]:', '0.3')
        ttk.Label(keys, text='Keys share the physical X/Y/Z frame. The gradients are never rotated to fit.',
                  wraplength=430, justify='left').pack(fill='x', pady=(4, 0))

        self.parallel_gradients_var = tk.BooleanVar(self, value=False)
        self.parallel_gradients_check = ttk.Checkbutton(
            left, text='Generate gradients simultaneously (one process each)',
            variable=self.parallel_gradients_var)
        self.parallel_gradients_check.pack(anchor='w', pady=6)
        self.coilgen_advanced = AdvancedControls(left, root=self.root, on_change=self._schedule_preview)
        self.coilgen_advanced.pack(fill='x', pady=4)
        bar = ttk.Frame(controls)
        bar.pack(side='bottom', fill='x', pady=6)
        self.run_btn = ttk.Button(bar, text='Design selected gradients', command=self._on_run)
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
        roi_visibility = ttk.Frame(previews)
        roi_visibility.pack(fill='x', pady=3)
        ttk.Label(roi_visibility, text='Show ROI:').pack(side='left')
        self.roi_visible_vars = {}
        for axis in 'xyz':
            self.roi_visible_vars[axis] = tk.BooleanVar(self, value=True)
            tk.Checkbutton(roi_visibility, text='G' + axis.upper(),
                           fg=_COLORS[axis], selectcolor='white',
                           variable=self.roi_visible_vars[axis],
                           command=self._schedule_preview).pack(side='left', padx=3)
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

        variables = [self.keys_var, self.b0_markers_var,
                     self.material_var, self.resistivity_var,
                     self.key_length_var, self.key_width_var, self.fit_clearance_var,
                     *(var for values in self.roi_vars.values() for var in values.values()),
                     *self.roi_spherical_vars.values(),
                     *(var for _, fields, _ in dimension_fields for var in fields.values()),
                     *self.layer_gap_vars.values(),
                     *self.tikhonov_vars.values(), *self.levels_vars.values(),
                     *self.enabled_vars.values()]
        for variable in variables:
            variable.trace_add('write', self._schedule_preview)
        self._preview_variables = variables
        self._bind_scroll(left, canvas)
        tips = [
            (self._entries[str(self.fit_clearance_var)], 'Extra space on each side of the key and at the axial stop. With 0.3 mm, a 4 mm key fits a 4.6 mm wide slot with a 0.3 mm axial gap. Adjust for your printer and material.'),
        ]
        for axis, widgets in self._layer_rows.items():
            tips.append((self._dimension_entries[axis][0], 'The winding is centered at Z = 0 and uses this length before applying the winding length factor. All molds use the longest selected length.'))
            tips.append((self._dimension_entries[axis][1], 'Radius of the outer plastic surface, as in Pipeline. The mold radii determine the nesting order.'))
            tips.append((widgets[1], 'Radial gap between cable crossings within this gradient. It contributes to this mold thickness.'))
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
        cfg.winding.reassign_crossing_layers = self.reassign_crossings_var.get()
        cfg.fasthenry.material = self.material_var.get()
        cfg.fasthenry.specific_conductivity = float(self.resistivity_var.get())
        if not math.isfinite(cfg.fasthenry.specific_conductivity) or cfg.fasthenry.specific_conductivity <= 0:
            raise ValueError(self.root.tr('Resistivity must be a positive number.'))
        self.coilgen_advanced.apply_to(cfg)
        return cfg

    def _build_cfg(self):
        """Construct one validated backend batch description; GUI lengths are mm."""
        from halbach_coils.coilgen.batch import BatchConfig, build_layer_configs
        selected = tuple(axis for axis in 'xyz' if self.enabled_vars[axis].get())
        if not selected:
            raise ValueError('Select at least one gradient (X, Y or Z), without duplicates.')
        if self._missing_main_values():
            raise ValueError(self.root.tr('Complete the required design fields before running.'))
        base = self._base_config()
        key_values = ((float(self.key_length_var.get()) / 1000,
                       float(self.key_width_var.get()) / 1000,
                       float(self.fit_clearance_var.get()) / 1000)
                      if self.keys_var.get() and len(selected) > 1 else (.004, .004, .0003))
        cfg = BatchConfig(
            base=base,
            axis_order=selected,
            outer_radii=tuple(float(self.outer_radius_vars[axis].get()) / 1000
                              if axis in selected else None for axis in 'xyz'),
            gradient_lengths=tuple(float(self.length_vars[axis].get()) / 1000
                                   if axis in selected else base.cylinder.height for axis in 'xyz'),
            roi_dimensions=tuple(
                tuple(float(self.roi_vars[axis]['x' if self.roi_spherical_vars[axis].get() else dim].get()) / 1000
                      for dim in 'xyz')
                if axis in selected else None for axis in 'xyz'),
            conductor_widths=tuple(float(self.cable_vars[axis].get()) / 1000
                                   if axis in selected else base.wire.conductor_width for axis in 'xyz'),
            groove_dimensions=tuple(
                (float(self.groove_height_vars[axis].get()) / 1000,
                 float(self.groove_width_vars[axis].get()) / 1000)
                if axis in selected else None for axis in 'xyz'),
            layer_gaps=tuple(float(self.layer_gap_vars[axis].get()) / 1000
                             if axis in selected else base.winding.layer_gap_mm for axis in 'xyz'),
            tikhonov_factors=tuple(float(self.tikhonov_vars[axis].get())
                                   if axis in selected else base.tikhonov_factor for axis in 'xyz'),
            num_levels=tuple(int(self.levels_vars[axis].get())
                             if axis in selected else base.num_levels for axis in 'xyz'),
            include_keys=self.keys_var.get() and len(selected) > 1,
            include_b0_markers=self.b0_markers_var.get(),
            parallel_gradients=self.parallel_gradients_var.get(),
            key_length=key_values[0],
            key_width=key_values[1],
            fit_clearance=key_values[2],
            output_dir=self.get_output_dir(),
        )
        cfg.axis_order = tuple(layer.gradient_axis for layer in build_layer_configs(cfg))
        return cfg

    def _missing_main_values(self):
        variables = [self.material_var, self.resistivity_var]
        selected = [axis for axis in 'xyz' if self.enabled_vars[axis].get()]
        for axis in selected:
            variables.extend(self.roi_vars[axis][dim] for dim in
                             ('x' if self.roi_spherical_vars[axis].get() else 'xyz'))
            variables.extend((self.length_vars[axis], self.outer_radius_vars[axis], self.cable_vars[axis],
                              self.groove_height_vars[axis], self.groove_width_vars[axis], self.layer_gap_vars[axis],
                              self.tikhonov_vars[axis], self.levels_vars[axis]))
        if self.keys_var.get() and len(selected) > 1:
            variables.extend((self.key_length_var, self.key_width_var, self.fit_clearance_var))
        return any(not variable.get().strip() for variable in variables)

    def _update_roi_entries(self):
        for axis in 'xyz':
            for dim in 'yz':
                self.roi_entries[axis][dim].configure(
                    state='disabled' if self.roi_spherical_vars[axis].get() else 'normal')

    def _schedule_preview(self, *_args):
        if self._preview_pending is not None:
            self.after_cancel(self._preview_pending)
        self._preview_pending = self.after(250, self._redraw_preview)

    def _preview_signature(self):
        return tuple(variable.get() for variable in self._preview_variables) + (
            self.root.b0_var.get(),
            *(variable.get() for variable in self.coilgen_advanced.variables.values()),
        )

    def _clear_preview(self, message, color):
        self._last_layers = None
        self.ax3d.clear()
        self.radial_ax.clear()
        for axis, label in self.radius_labels.items():
            if self.enabled_vars[axis].get():
                label.configure(text='')
        self.total_radius_label.configure(text='')
        self.preview_notice.configure(text=self.root.tr(message), foreground=color)
        self.figure_canvas.draw_idle()

    def _redraw_preview(self):
        if self._preview_pending is not None:
            self.after_cancel(self._preview_pending)
        self._preview_pending = None
        if not hasattr(self, 'ax3d'):
            return
        selected_count = sum(var.get() for var in self.enabled_vars.values())
        for axis in 'xyz':
            for entry in (*self._layer_rows[axis][1:], *self._dimension_entries[axis]):
                entry.configure(state='normal' if self.enabled_vars[axis].get() else 'disabled')
            if not self.enabled_vars[axis].get():
                self.radius_labels[axis].configure(
                    text=self.root.tr('{axis}: excluded from batch', axis='G'+axis.upper()))
        for child in self.key_dimensions.winfo_children():
            child.configure(state='normal' if self.keys_var.get() and selected_count > 1 else 'disabled')
        if selected_count and self._missing_main_values():
            self._clear_preview('Enter the design values to see the preview.', '#666666')
            return
        try:
            from halbach_coils.coilgen.batch import build_layer_configs
            cfg = self._build_cfg()
            layers = build_layer_configs(cfg)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            self._clear_preview(str(exc), '#a32323')
            return
        self._last_layers = layers
        displayed_axes = (*cfg.axis_order, *(axis for axis in 'xyz' if axis not in cfg.axis_order))
        for row, axis in enumerate(displayed_axes, 2):
            for widget in self._layer_rows[axis]:
                widget.grid_configure(row=row)
            self.radius_labels[axis].grid_configure(row=row + 3)
        # Filled in with the same backend dimensions used to export the molds.
        try:
            self._draw_geometry(cfg, layers)
        except (ValueError, RuntimeError) as exc:
            self._clear_preview(str(exc), '#a32323')

    def _draw_geometry(self, batch, layers):
        from halbach_coils.coilgen.batch import gradient_radial_bounds, mold_radial_gap
        ax, section = self.ax3d, self.radial_ax
        elev, azim = ax.elev, ax.azim
        ax.clear()
        section.clear()
        theta = np.linspace(0, 2 * math.pi, 73)
        height = layers[0].cylinder.height * 1000
        for cfg in layers:
            axis = cfg.gradient_axis
            inner, outer = cfg.shell_inner_radius * 1000, cfg.shell_outer_radius * 1000
            color = _COLORS[axis]
            section.add_patch(Wedge((0, 0), outer, 0, 360, width=outer-inner,
                                    facecolor=color, edgecolor='#454545', linewidth=.6, alpha=.7))
            t, z = np.meshgrid(theta, [-height/2, height/2])
            ax.plot_surface(outer*np.cos(t), outer*np.sin(t), z, color=color, alpha=.18,
                            linewidth=0, antialiased=True)
            design_radius = cfg.cylinder_design_radius * 1000
            winding_half = height * cfg.cylinder.mesh_length_factor / 2
            if self.coilgen_advanced.expanded.get():
                refinement = 2 ** cfg.advanced.iteration_num_mesh_refinement
                mesh_theta, mesh_z = np.meshgrid(
                    np.linspace(0, 2*math.pi, min(cfg.cylinder.n_circ*refinement+1, 61)),
                    np.linspace(-winding_half, winding_half, min(cfg.cylinder.n_long*refinement+1, 31)))
                ax.plot_wireframe(design_radius*np.cos(mesh_theta), design_radius*np.sin(mesh_theta), mesh_z,
                                  color=color, alpha=.25, linewidth=.4)
            for end in (-winding_half, winding_half):
                ax.plot(design_radius*np.cos(theta), design_radius*np.sin(theta), np.full_like(theta, end),
                        color=color, linestyle=':', linewidth=1)
            for end in (-height/2, height/2):
                for radius in (inner, outer):
                    ax.plot(radius*np.cos(theta), radius*np.sin(theta), np.full_like(theta, end),
                            color=color, linewidth=1)
            self.radius_labels[axis].configure(text=self.root.tr(
                '{axis}: gradient {gradient_inner:.2f}–{gradient_outer:.2f} mm\nMold {inner:.2f}–{outer:.2f} mm · wall {wall:.2f} mm\nReal cable Ø {diameter:.2f} mm · Groove {height:.2f} × {width:.2f} mm',
                gradient_inner=gradient_radial_bounds(cfg)[0]*1000,
                gradient_outer=gradient_radial_bounds(cfg)[1]*1000,
                axis='G'+axis.upper(), inner=inner, outer=outer,
                wall=cfg.shell_wall_thickness * 1000,
                diameter=cfg.wire.conductor_width * 1000,
                height=cfg.groove_radial_height * 1000,
                width=cfg.groove_tangential_width * 1000))
            gradient_inner, gradient_outer = gradient_radial_bounds(cfg)
            section.add_patch(Wedge((0, 0), gradient_outer*1000, 0, 360,
                                    width=(gradient_outer-gradient_inner)*1000,
                                    facecolor=color, alpha=.16, edgecolor=color, linestyle=':', linewidth=.7))
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
        if batch.include_b0_markers:
            self._draw_b0_marks(batch, layers, height)
        u, v = np.meshgrid(np.linspace(0, 2*math.pi, 30), np.linspace(0, math.pi, 17))
        for cfg in layers:
            if not self.roi_visible_vars[cfg.gradient_axis].get():
                continue
            rx, ry, rz = (getattr(cfg.target, 'r'+axis)*1000 for axis in 'xyz')
            surface = ax.plot_surface(rx*np.cos(u)*np.sin(v), ry*np.sin(u)*np.sin(v), rz*np.cos(v),
                                      color=_COLORS[cfg.gradient_axis], alpha=.18, linewidth=0)
            surface.set_gid('roi-' + cfg.gradient_axis)
        outer = max(cfg.shell_outer_radius for cfg in layers)*1000
        wire_outer = max(gradient_radial_bounds(cfg)[1] for cfg in layers)*1000
        self.total_radius_label.configure(text=self.root.tr(
            'Maximum mold radius: {mold:.2f} mm. Total radius including cable: {cable:.2f} mm.',
            mold=outer, cable=wire_outer))
        full_outer = max(gradient_radial_bounds(cfg)[1] for cfg in layers)*1000
        section.set_xlim(-full_outer*1.12, full_outer*1.12)
        section.set_ylim(-full_outer*1.12, full_outer*1.12)
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
        notice += '\n' + self.root.tr(
            'Shared mold length: {length:.2f} mm. Dotted rings mark the winding mesh ends.',
            length=height)
        if len(layers) > 1:
            gaps = ' · '.join(f'{inner.axis_label} → {outer.axis_label} {1000 * max(0, mold_radial_gap(inner, outer)):.2f} mm'
                              for inner, outer in zip(layers, layers[1:]))
            notice += '\n' + self.root.tr('Mold gaps: {gaps}', gaps=gaps)
        if batch.include_keys:
            notice += '\n' + self.root.tr(
                'Key clearance: {clearance:.2f} mm per side and at the axial stop.',
                clearance=batch.fit_clearance * 1000)
            notice += '\n' + self.root.tr(
                'Final key positions verified against the conductors.' if actual_keys else
                'Key positions are preliminary; the final design selects a clear location for each key.')
        if batch.include_b0_markers:
            notice += '\n' + self.root.tr(
                'B₀ marks share one azimuth. Final placement is checked against grooves and keys.')
        self.preview_notice.configure(text=notice, foreground='')
        self.figure_canvas.draw_idle()

    def _draw_b0_marks(self, batch, layers, height):
        from halbach_coils.coilgen.shell_marker import marker_dimensions, marker_radial_direction

        radial, transverse = marker_radial_direction(layers[0])
        actual = (self._actual_b0_markers is not None
                  and self._preview_signature() == getattr(self, '_running_signature', None))
        if actual and self._actual_b0_markers.get('enabled'):
            radial = np.asarray(self._actual_b0_markers['radial_direction'])
        tangent = np.cross([0., 0., 1.], radial)
        for cfg in layers:
            inner, outer = cfg.shell_inner_radius * 1000, cfg.shell_outer_radius * 1000
            length, width, depth = marker_dimensions(inner, outer, height)
            radial_center = (inner + outer) / 2 if transverse else outer - depth / 2
            radial_length = length if transverse else depth
            corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
            points = ((radial_center + corners[:, :1] * radial_length / 2) * radial[:2]
                      + corners[:, 1:] * width / 2 * tangent[:2])
            self.radial_ax.add_patch(Polygon(
                points, facecolor='#334f66', edgecolor='#18334e', linewidth=.5,
                gid='b0-marker-' + cfg.gradient_axis))
            for end, inward in ((-height/2, 1), (height/2, -1)):
                if transverse:
                    vertices = np.column_stack((points, np.full(4, end)))
                else:
                    z_center = end + inward * .75 * length
                    vertices = (outer * radial + corners[:, :1] * width / 2 * tangent
                                + np.column_stack((np.zeros((4, 2)),
                                                   z_center + corners[:, 1] * length / 2)))
                self.ax3d.add_collection3d(Poly3DCollection(
                    [vertices], facecolors='#334f66', edgecolors='#18334e', linewidths=.5))

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
        self._actual_b0_markers = None
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
        if event in ('complete', 'needs_revision'):
            # The last 10% belongs to assembly validation and key generation.
            self.progress['value'] = 90 * float(value) / len(self._running_order)

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
        axes = getattr(result, 'layer_axes', ()) or self._running_order
        outcomes = tuple(zip(axes, result.layers))
        for axis, outcome in outcomes:
            if outcome.field_plots:
                self._plots[axis] = outcome.field_plots
                self.result_buttons[axis].configure(state='normal')
        if not result.completed:
            issues = [f'G{axis.upper()}: {outcome.message}' for axis, outcome in outcomes
                      if getattr(outcome, 'needs_revision', False)]
            message = self.root.tr(
                'The set is incomplete. Completed layers were kept in:\n{path}', path=result.output_dir)
            if issues:
                message += '\n\n' + '\n\n'.join(issues)
            if result.message:
                message += '\n\n' + result.message
            messagebox.showwarning(self.root.tr('Batch design'), message, parent=self.root)
            return
        self._actual_interfaces = (result.assembly or {}).get('interfaces')
        self._actual_b0_markers = (result.assembly or {}).get('b0_markers')
        self._redraw_preview()
        message = self.root.tr('Done.\nResults in:\n{path}', path=result.output_dir)
        for axis, outcome in outcomes:
            electrical = electrical_result_text(outcome.metrics_path, self.root.tr)
            if electrical:
                message += '\n\nG'+axis.upper()+': '+electrical
        messagebox.showinfo(self.root.tr('Batch design'), message, parent=self.root)

    def _set_running(self, running):
        self.run_btn.configure(state='disabled' if running else 'normal')
        self.parallel_gradients_check.configure(state='disabled' if running else 'normal')
        for row in self._layer_rows.values():
            row[0].configure(state='disabled' if running else 'normal')
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
