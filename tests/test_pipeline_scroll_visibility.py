"""The Pipeline controls must remain reachable in a small window."""

from pathlib import Path
import subprocess
import sys


def test_pipeline_overflow_keeps_scrollbar_and_run_button_visible():
    script = '''
import sys
from tkinter import ttk
sys.path.insert(0, 'halbach_coils')
from gui.main_window import CoilGenApp
app = CoilGenApp()
app.geometry('960x640')
app.language_var.set('es')
app._on_language_changed()
app.notebook.select(app.pipeline_panel)
app.pipeline_panel.roi_ellipsoidal_var.set(True)
app.pipeline_panel._toggle_roi()
app.pipeline_panel.coilgen_advanced.expanded.set(True)
app.pipeline_panel.coilgen_advanced._toggle()
app.update()
errors = []
def check():
    try:
        panel = app.pipeline_panel
        canvas = panel._ctrl_canvas
        scrollbar, = [w for w in panel._controls_shell.winfo_children()
                      if isinstance(w, ttk.Scrollbar)]
        assert canvas.bbox('all')[3] > canvas.winfo_height(), (canvas.bbox('all'), canvas.winfo_height())
        assert scrollbar.winfo_ismapped(), (scrollbar.winfo_manager(), canvas.bbox('all'), canvas.winfo_height())
        assert scrollbar.winfo_width() >= scrollbar.winfo_reqwidth(), (scrollbar.winfo_width(), scrollbar.winfo_reqwidth())
        canvas.yview_moveto(1)
        app.update_idletasks()
        choice = panel._step_choices[-1]
        assert choice.winfo_rooty() >= canvas.winfo_rooty()
        assert choice.winfo_rooty() + choice.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
        assert panel.run_btn.winfo_ismapped()
        assert panel.run_btn.winfo_rooty() + panel.run_btn.winfo_height() <= app.winfo_rooty() + app.winfo_height()
        for control in panel._step_choices:
            assert control.winfo_width() >= control.winfo_reqwidth()
    except BaseException as exc:
        errors.append(exc)
    finally:
        app.destroy()
app.after(500, check)
app.mainloop()
if errors:
    raise errors[0]
'''
    result = subprocess.run([sys.executable, '-c', script],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
