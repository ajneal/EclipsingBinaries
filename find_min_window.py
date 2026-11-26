# -*- coding: utf-8 -*-
"""
The Find Minimum window: step through the nights of a light curve, set the
boundaries around an eclipse with the a and d keys, and save each time of
minimum to a file O-C Plotting can read.

The calculations are in find_min.py; this file is only the window.

Author: Kyle Koeller
Created: 10/10/2026
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import star_file, time_systems
from .find_min import (DEFAULT_NPAIRS, DEFAULT_ORDER, DEFAULT_RESOLUTION, MinimumError, MinimumFile,
                       draw_night, guess_boundaries, load_nights, measure_minimum, minimum_file_name)

CONTROLS_TEXT = ('CONTROLS'+'\n'+
                 'Left bound:\tA'+'\n'+
                 'Right Bound:\tD'+'\n'+
                 'Next night:\tN'+'\n'+
                 'Previous night:\tP'+'\n'+
                 'Save minimum:\tEnter'+'\n'+
                 'Zoom:\t\tScrl wheel')
"""
HELP_TEXT = ("Point at the plot and press A to put the left boundary (>|) there, or D for the right "
             "one (|<). Keep both on the sides of the eclipse rather than out on the flat parts. "
             "Shaded points aren't used: dark grey is outside the boundaries, light grey is past "
             "where the fit's pairs reach. Drag the plot, or use the scrollbar under it, to slide "
             "along continuous data. n and p change night, Enter saves the minimum, and the "
             "scroll wheel or the toolbar zooms.")
"""

HELP_TEXT_2 = ('INSTRUCTIONS\n'
               'Mouse over to the desired left bound and press A, then mouse over to the '
               'right bound and press D. The left and right bounds should be on the left '
               'and right sides of a minimum, respectively.')

SHADE_INFO = ('SHADED AREA INFO\n'
              'The inside white region indicates which points are used, while the light gray '
              'region indicates excess bound which isn\'t being used. The dark gray indicates points '
              'outside of the specified range.')
import textwrap

autowrap=lambda text,width=70: '\n'.join(textwrap.wrap(text,width=width))


class DepressTooltipLabel:
    def __init__(self, parent, text, tooltip_text):
        self.tooltip_window = None
        self.tooltip_text = tooltip_text

        # Create the label with a raised border so the depressed state is visible
        self.label = tk.Label(
            parent,
            text=text,
            relief="raised",
            borderwidth=2,
            padx=10,
            pady=5,
            bg="#f0f0f0"
        )

        # Bind hover events for the tooltip
        self.label.bind("<Enter>", self.on_enter)
        self.label.bind("<Leave>", self.on_leave)

        # Bind click events for the depressed effect
        # self.label.bind("<ButtonPress-1>", self.on_press)
        # self.label.bind("<ButtonRelease-1>", self.on_release)

    def on_enter(self, event):
        # Optional: Uncomment the line below to depress on hover instead of click
        self.label.config(relief="sunken", bg="#e0e0e0")
        self.show_tooltip()

    def on_leave(self, event):
        self.label.config(relief="raised", bg="#f0f0f0")
        self.hide_tooltip()

    # def on_press(self, event):
        # self.label.config(relief="sunken", bg="#d9d9d9")

    # def on_release(self, event):
        # self.label.config(relief="raised", bg="#f0f0f0")

    def show_tooltip(self):
        if self.tooltip_window:
            return
        # Position tooltip slightly below and to the right of the label
        x = self.label.winfo_rootx() - 150
        y = self.label.winfo_rooty() + self.label.winfo_height() + 5

        self.tooltip_window = tk.Toplevel(self.label)
        self.tooltip_window.wm_overrideredirect(True)  # Remove window borders
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        tip_label = tk.Label(
            self.tooltip_window,
            text=self.tooltip_text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
            justify='left'
        )
        tip_label.pack()

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class ToolTip(object):

    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text):
        "Display text in tooltip window"
        self.text = text
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 57
        y = y + cy + self.widget.winfo_rooty() +27
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                      background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                      padx=6,pady=3)
                      # font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        # self.linger_delay = 1000
        self.tipwindow = None
        if tw:
            tw.destroy()

def CreateToolTip(widget, text):
    toolTip = ToolTip(widget)
    def enter(event):
        toolTip.showtip(text)
    def leave(event):
        toolTip.hidetip()
    widget.bind('<Enter>', enter)
    widget.bind('<Leave>', leave)

# How far past the view the points are drawn, as a fraction of the view's width either side.
# Sliding further than that draws the plot again around the new view.
DRAW_MARGIN = 1.0


def _style(widget, name, fallback):
    """Use one of the main window's button styles when it exists (it doesn't when run on its own)."""
    try:
        widget.tk.call("ttk::style", "layout", name)
        return name
    except tk.TclError:
        return fallback


class MinimumFinderWindow(tk.Toplevel):
    """
    Interactive window for measuring times of minimum.

    :param master: parent Tk window
    :param files: light curve files, one per filter
    :param labels: filter name for each file (B, V, R...)
    :param output_folder: where the minimum files are saved
    :param obj_name: used in the minimum file names
    :param log: function for progress messages, such as the main window's log
    :param time_system: one of time_systems.SYSTEMS to use, or None to go by the files
    """

    def __init__(self, master, files, labels, output_folder, obj_name, log=print,
                 order=DEFAULT_ORDER, resolution=DEFAULT_RESOLUTION, npairs=DEFAULT_NPAIRS,
                 time_system=None):
        super().__init__(master)
        self.log = log
        self.output_folder = Path(output_folder)
        self.obj_name = obj_name
        notes = []
        try:
            self.nights = load_nights(files, labels, notes=notes, time_system=time_system)
        except Exception:
            self.destroy()
            raise
        for note in notes:
            log(note)
        if not self.nights:
            self.destroy()
            raise MinimumError("The light curve files have no observations in them.")
        self.time_system = self.nights[0].time_system
        self.time_name = time_systems.describe(self.time_system)
        if self.time_system is None:
            log("The light curve files don't say which time system their times are in, so the "
                "minima are saved without one. Choose a time system to have them labelled.")
        self.labels = list(dict.fromkeys(b for night in self.nights for b in night.bands))
        self.order, self.resolution, self.npairs = order, resolution, npairs
        self.current = 0
        self.boundaries = {}       # night index: (lb, rb), so each night keeps its own
        self.views = {}            # night index: (left, right) of the plot, once it's been moved
        self._ylims = {}           # night index: (bottom, top), once it's been zoomed
        self._drawn = None         # the stretch of time the points are drawn for
        self._drag = None          # (pointer x, view) while dragging the plot
        self.minimum = None
        self._files = {}           # filter combination: MinimumFile

        self.title(f"Find Minimum: {obj_name}" if obj_name else "Find Minimum")
        self.geometry("1100x760") #1100x760
        self.minsize(860, 600)
        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.show_night(0)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self):
        accent = _style(self, "Accent.TButton", "TButton")
        secondary = _style(self, "Secondary.TButton", "TButton")
        
        # ===== night frame ======
        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Button(top, text="< Previous Night", command=lambda: self.step(-1), style=secondary).pack(side="left")
        self.night_var = tk.StringVar(master=self)
        self.night_picker = ttk.Combobox(top, textvariable=self.night_var, state="readonly", width=46,
                                         values=[n.describe() for n in self.nights])
        self.night_picker.pack(side="left", padx=8)
        self.night_picker.bind("<<ComboboxSelected>>",
                               lambda _e: self.show_night(self.night_picker.current()))
        ttk.Button(top, text="Next Night >", command=lambda: self.step(1), style=secondary).pack(side="left")

        
        # ===== info frame ======
        info = ttk.Frame(self, padding=(12, 0, 12, 0))
        # info = CollapsibleFrame(ttk.Frame(self, padding=(12, 0, 12, 4)))
        info.pack(fill='x')
        
        # == sep line ===
        sep_line = ttk.Frame(self)
        sep_line.pack(fill='x')
        ttk.Separator(sep_line, orient="horizontal").pack(fill="x", padx=8,anchor='w')
        
        # ===== settings frame ======
        settings = ttk.Frame(self, padding=(12, 10, 12, 10)) # (left,top,right,bottom)
        settings.pack(fill="x")
        
        
        
        # === connect label ===
        self.connect_var = tk.BooleanVar(master=self, value=True)
        connect_label = ttk.Checkbutton(settings, text="Connect points", variable=self.connect_var,
                        command=self.redraw)
        connect_label.pack(side="left", padx=(0, 12))
        CreateToolTip(connect_label,text=autowrap('Connect points for visual aid. Has no effect on the calculations.',width=25))
        
        # === polynomial label ===
        self.poly_var = tk.BooleanVar(master=self, value=False)
        self.poly_check = ttk.Checkbutton(settings, text="Draw polynomial", variable=self.poly_var,
                                          command=self._poly_toggled)
        CreateToolTip(self.poly_check,text=autowrap('Draw a polynomial that fits points in range. Currently has no effect on results, but future developments may use it.',width=25))
        self.poly_check.pack(side="left", padx=(0, 8))
        # The polynomial is only a guide for the eye, so its order is only shown when it's drawn
        self.order_frame = ttk.Frame(settings)
        self.order_var = self._spin(self.order_frame, "Polynomial order:", self.order, 2, 9)
        CreateToolTip(self.order_frame,text=autowrap('Order of fitted polynomial. Has no effect on results currently.',width=25))
        
        # === pairs label ===
        self.pairs_frame = ttk.Frame(settings)
        self.pairs_frame.pack(side='left',padx=(0,8))
        self.pairs_var = self._spin(self.pairs_frame, "Pairs (K):", self.npairs, 5, 60)
        CreateToolTip(self.pairs_frame,text=autowrap('Number of pairs that are linearly interolated to compute S, represented as K in the plot. Ideally, this value is close to the number of pairs in rnage, however, '
                                                     'this primarily effects the absolute size of S, not the shape of S. Since the error is calculated using the shape of S, the number of pairs has minimal effect on the results.'
                                                     ,width=50))
        
        # === resolution frame ===
        self.resolution_frame = ttk.Frame(settings)
        self.resolution_frame.pack(side='left',padx=(0,8))
        self.resolution_var = self._spin(self.resolution_frame, "Trial times", self.resolution, 50, 1000, step=50)
        CreateToolTip(self.resolution_frame,text=autowrap('Number of trial minimums used to find the best initial minimum. A parabola is fit around the trial with the smallest S value to refine the search. ' 
                                                          'The parabola\'s coefficients are used in calculating the minimum and error.',width=50))
        # === filter boxes and labels ===
        filter_label = ttk.Label(settings, text="Filters:")
        filter_label.pack(side="left", padx=(24, 4))
        self.band_vars = {}
        for label in self.labels:
            var = tk.BooleanVar(master=self, value=True)
            ttk.Checkbutton(settings, text=label, variable=var, command=self._bands_changed).pack(side="left")
            # ttk.Checkbutton(filter_label, text=label, variable=var, command=self._bands_changed).pack(side="left")
            self.band_vars[label] = var
    
        CreateToolTip(filter_label,text=autowrap('Choose which filters are curruently being used in analysis. It\'s recommended to select and fit one filter at a time unless necessary. '
                                        'Each filter will have its own saved minimum file.',width=40))
        # original help
        # ttk.Label(settings, text=HELP_TEXT, wraplength=520, foreground="#5b6675").pack(side="left", padx=(16, 0))
        
        # / === end settings /


        control_label = ttk.Label(info, text=CONTROLS_TEXT, wraplength=520, foreground="black")
        control_label.pack(side="left", padx=(16, 16),anchor='nw')

        help_label = ttk.Label(info, text=HELP_TEXT_2, wraplength=300, foreground="#000000")
        help_label.pack(side="left", padx=(16, 0),anchor='nw')

        shade_label = ttk.Label(info, text=SHADE_INFO, wraplength=300, foreground="#000000")
        shade_label.pack(side="left", padx=(16, 0),anchor='nw')
        
        DepressTooltipLabel(top, "More Info", autowrap("GUI and implementation created by Kyle Koeller. Current algorithm is a modification of the Kwee & van Woerden method (1956) by Alec Neal. More options coming soon.",width=30)).label.pack(anchor='ne')
        
        

        body = ttk.Frame(self, padding=(12, 0, 12, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        plot_frame = ttk.Frame(body,borderwidth=2,relief='solid')
        plot_frame.grid(row=0, column=0, sticky="nsew")
        # Constrained layout sizes the margins to the labels actually drawn, so the plots
        # fill the window instead of sitting inside matplotlib's fixed default margins
        self.figure = Figure(figsize=(7, 5.5),layout='constrained')
        self.figure.get_layout_engine().set(w_pad=0.06, h_pad=0.06, hspace=0.02)
        grid = self.figure.add_gridspec(2, 1, height_ratios=[1, 3])
        self.ax_s = self.figure.add_subplot(grid[0])
        self.ax_lc = self.figure.add_subplot(grid[1])
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side="bottom", fill="x")
        # Slides the plot along continuous data; only shown when there's more than fits
        self.scrollbar = ttk.Scrollbar(plot_frame, orient="horizontal", command=self._on_scrollbar)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("key_press_event", self._on_key)
        # The boundaries are set with keys, so the plot takes the keyboard as soon as the
        # pointer is over it rather than only after a click
        self.canvas.get_tk_widget().bind("<Enter>", lambda _e: self.canvas.get_tk_widget().focus_set(), add="+")
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        side = ttk.Frame(body, padding=(14, 0, 7, 0), width=320)
        side.grid(row=0, column=1, sticky="ns")
        # A bold copy of the system font; a ("TkDefaultFont", size) tuple would look for a
        # font family by that name and fall back to something else on each platform
        self.heading_font = tkfont.nametofont("TkDefaultFont").copy()
        self.heading_font.configure(weight="bold", size=abs(self.heading_font.cget("size")) + 1)
        ttk.Label(side, text="Time of minimum", font=self.heading_font).pack(anchor="w")
        self.result_var = tk.StringVar(master=self, value="")
        self.result_label = ttk.Label(side, textvariable=self.result_var, wraplength=300, justify="left")
        self.result_label.pack(anchor="w", pady=(4, 8))
        self.save_button = ttk.Button(side, text="Save Minimum", command=self.save_minimum, style=accent)
        self.save_button.pack(anchor="w")

        ttk.Separator(side).pack(fill="x", pady=12)
        self.file_var = tk.StringVar(master=self)
        ttk.Label(side, textvariable=self.file_var, wraplength=300, justify="left").pack(anchor="w")
        # ttk doesn't size table rows to the font, so they clip on scaled Windows displays
        linespace = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        ttk.Style(self).configure("Minima.Treeview", rowheight=int(linespace * 1.4))
        columns = ("hjd", "points", "error")
        self.table = ttk.Treeview(side, columns=columns, show="headings", height=12, selectmode="browse",
                                  style="Minima.Treeview")
        for col, text, width in (("hjd", self.time_name, 130), ("points", "Points", 60), ("error", "Error", 100)):
            self.table.heading(col, text=text)
            self.table.column(col, width=width, anchor="e")
        self.table.pack(fill="both", expand=True, pady=(6, 6))
        buttons = ttk.Frame(side)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Remove Selected", command=self.remove_selected, style=secondary).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy, style=secondary).pack(side="right")

    def _spin(self, parent, text, value, low, high, step=1):
        ttk.Label(parent, text=f"{text}:").pack(side="left")
        var = tk.IntVar(master=self, value=value)
        spin = ttk.Spinbox(parent, from_=low, to=high, increment=step, textvariable=var, width=5,
                           command=self.remeasure)
        spin.pack(side="left", padx=(4, 14))
        spin.bind("<Return>", lambda _e: self.remeasure())
        spin.bind("<FocusOut>", lambda _e: self.remeasure())
        return var

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def selected_labels(self):
        return tuple(label for label, var in self.band_vars.items() if var.get())

    def minimum_file(self):
        """The saved minima for the filters currently ticked."""
        labels = self.selected_labels()
        if labels not in self._files:
            name = minimum_file_name(self.obj_name, labels, self.time_system)
            self._files[labels] = MinimumFile(self.output_folder / name)
        return self._files[labels]

    def _settings(self):
        try:
            return (max(2, int(self.order_var.get())), max(5, int(self.pairs_var.get())),
                    max(20, int(self.resolution_var.get())))
        except (tk.TclError, ValueError):
            return self.order, self.npairs, self.resolution

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def show_night(self, index):
        self.current = max(0, min(index, len(self.nights) - 1))
        night = self.nights[self.current]
        self.night_picker.current(self.current)
        if self.current not in self.boundaries:
            self.boundaries[self.current] = guess_boundaries(night, self.selected_labels() or None)
        self.remeasure()

    def step(self, delta):
        self.show_night(self.current + delta)

    def set_boundary(self, which, x):
        """Move one boundary to x. If that puts it past the other boundary, the other one
        moves along with it and keeps the same spacing, so the pair can be carried over to
        another eclipse with a single key."""
        lb, rb = self.boundaries[self.current]
        width = rb - lb
        if which == "left":
            lb = x
            if lb >= rb:
                rb = lb + width
        else:
            rb = x
            if rb <= lb:
                lb = rb - width
        self.boundaries[self.current] = (lb, rb)
        self.remeasure()

    def _poly_toggled(self):
        if self.poly_var.get():
            self.order_frame.pack(side="left", after=self.poly_check)
        else:
            self.order_frame.pack_forget()
        self.redraw()

    def _bands_changed(self):
        if not self.selected_labels():
            self.result_var.set("Tick at least one filter.")
        self.remeasure()

    def remeasure(self):
        night = self.nights[self.current]
        labels = self.selected_labels()
        lb, rb = self.boundaries[self.current]
        order, npairs, resolution = self._settings()
        self.minimum = None
        message = ""
        if labels:
            try:
                self.minimum = measure_minimum(night, lb, rb, labels=labels, order=order,
                                               resolution=resolution, npairs=npairs)
            except MinimumError as e:
                message = str(e)
        else:
            message = "Tick at least one filter."
        if self.minimum is not None and self.minimum.error is None:
            # A time came out, but too few points for an error, so it can't be saved
            message = (f"Only {self.minimum.n_points} points between the boundaries: too few for an "
                       "error estimate, so this minimum can't be saved. Widen the boundaries.")
        self._message = message
        self._show_result(message)
        self._refresh_table()
        self.redraw()

    def redraw(self):
        """Draw the current night again, keeping the measurement and where the plot is."""
        night = self.nights[self.current]
        lb, rb = self.boundaries[self.current]
        view = self._view()
        if view is None:
            self._drawn = None
        else:
            width = view[1] - view[0]
            self._drawn = (view[0] - DRAW_MARGIN * width, view[1] + DRAW_MARGIN * width)
        draw_night(self.ax_s, self.ax_lc, night, lb, rb, self.minimum, labels=self.selected_labels(),
                   connect=self.connect_var.get(), show_poly=self.poly_var.get(),
                   message=getattr(self, "_message", ""), time_range=self._drawn)
        if view is not None:
            self.ax_lc.set_xlim(*view)
        if self.current in self._ylims:
            self.ax_lc.set_ylim(*self._ylims[self.current])
        self._update_scrollbar()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Sliding along the data
    #
    # A piece of continuous data holds the whole stretch, but opens on its own
    # 1.25 days. Dragging the plot or moving the scrollbar slides that view, so
    # an eclipse cut off at the edge of a piece can be brought into view whole.
    # ------------------------------------------------------------------
    def _view(self):
        """Where the light curve plot is: the night's own view until it's been moved, or None for all of it."""
        if self.current in self.views:
            return self.views[self.current]
        view = self.nights[self.current].view
        if view is None:
            return None
        pad = 0.02 * (view[1] - view[0])
        return view[0] - pad, view[1] + pad

    def set_view(self, left, right):
        """Move the plot to show left to right, staying within reach of the data."""
        lo, hi = self.nights[self.current].extent
        width = right - left
        edge = 0.05 * width
        if width < (hi - lo) + 2 * edge:
            left = min(max(left, lo - edge), hi + edge - width)
            right = left + width
        self.views[self.current] = (left, right)
        if self._drawn is not None and (left < self._drawn[0] or right > self._drawn[1]):
            self.redraw()          # slid past the points that are drawn
            return
        self.ax_lc.set_xlim(left, right)
        self._update_scrollbar()
        self.canvas.draw_idle()

    def _update_scrollbar(self):
        lo, hi = self.nights[self.current].extent
        left, right = self.ax_lc.get_xlim()
        total = hi - lo
        if total <= 0 or (right - left) >= 0.98 * total:
            self.scrollbar.pack_forget()
            return
        if not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="bottom", fill="x", before=self.canvas.get_tk_widget())
        first = min(max((left - lo) / total, 0.0), 1.0)
        last = min(max((right - lo) / total, first), 1.0)
        self.scrollbar.set(first, last)

    def _on_scrollbar(self, action, amount, unit=None):
        """The scrollbar's arrows, trough and thumb."""
        lo, hi = self.nights[self.current].extent
        left, right = self.ax_lc.get_xlim()
        width = right - left
        if action == "moveto":
            left = lo + float(amount) * (hi - lo)
        elif action == "scroll":
            left += int(amount) * width * (0.9 if unit == "pages" else 0.1)
        self.set_view(left, left + width)

    def _show_result(self, message):
        m = self.minimum
        if m is None:
            self.result_var.set(message)
            self.result_label.configure(foreground="#b3261e")
            self.save_button.state(["disabled"])
            return
        error = f"± {m.error:.6f}" if m.error is not None else "(no error estimate: widen the boundaries)"
        self.result_var.set(f"{self.time_name} {m.hjd:.6f} {error}\n"
                            f"{m.n_points} points in {', '.join(m.labels)} between the boundaries, "
                            f"{self._points_used(m)} used by the fit\n"
                            f"K = {self._settings()[1]}, R² = {m.kwee.R2:.5f}")
        self.result_label.configure(foreground="#1b2430" if m.error is not None else "#b3261e")
        self.save_button.state(["!disabled"] if m.error is not None else ["disabled"])

    def _points_used(self, m):
        """How many points fall where the fit's pairs reach, the same distance either side of the minimum."""
        t = self.nights[self.current].points(m.labels)[0]
        start, end = m.kwee.used_range
        return int(((t >= max(m.lb, start)) & (t <= min(m.rb, end))).sum())

    def save_minimum(self):
        if self.minimum is None:
            return
        target = self.minimum_file()
        try:
            replaced = target.add(self.minimum)
        except (MinimumError, OSError) as e:
            self.result_var.set(str(e))
            self.result_label.configure(foreground="#b3261e")
            return
        verb = "Replaced the earlier minimum with" if replaced else "Saved minimum"
        self.log(f"{verb} {self.time_name} {self.minimum.hjd:.6f} ± {self.minimum.error:.6f} in {target.path}")
        star_file.record(self.obj_name, "minima", files=[target.path], write_callback=self.log,
                         time_system=self.time_system)
        self._refresh_table()

    def remove_selected(self):
        selection = self.table.selection()
        if not selection:
            return
        index = self.table.index(selection[0])
        target = self.minimum_file()
        removed = target.entries[index][0]
        target.remove(index)
        self.log(f"Removed minimum {self.time_name} {removed:.6f} from {target.path}")
        self._refresh_table()

    def _refresh_table(self):
        self.table.delete(*self.table.get_children())
        if not self.selected_labels():
            self.file_var.set("")
            return
        target = self.minimum_file()
        self.file_var.set(f"Saved in {target.path.name} ({len(target.entries)}):")
        for t, n, err in target.entries:
            self.table.insert("", "end", values=(f"{t:.6f}", n, f"{err:.6f}"))

    # ------------------------------------------------------------------
    # Mouse and keys on the plot
    # ------------------------------------------------------------------
    def _on_key(self, event):
        if event.key in ("a", "d") and event.inaxes is self.ax_lc and event.xdata is not None:
            self.set_boundary("left" if event.key == "a" else "right", event.xdata)
        elif event.key == "n":
            self.step(1)
        elif event.key == "p":
            self.step(-1)
        elif event.key == "enter":
            self.save_minimum()

    def _on_press(self, event):
        """Start dragging the light curve plot sideways, unless the toolbar is zooming or panning."""
        if event.button == 1 and event.inaxes is self.ax_lc and not self.toolbar.mode:
            self._drag = (event.x, self.ax_lc.get_xlim(), self.ax_lc.get_window_extent().width)

    def _on_motion(self, event):
        if self._drag is None or event.x is None:
            return
        start_x, (left, right), width_px = self._drag
        shift = -(event.x - start_x) * (right - left) / max(width_px, 1.0)
        self.set_view(left + shift, right + shift)

    def _on_release(self, _event):
        self._drag = None

    def _on_scroll(self, event):
        """Scroll over the light curve to zoom in and out around the pointer."""
        if event.inaxes is not self.ax_lc or event.xdata is None:
            return
        # A trackpad sends many small scroll events, a wheel a few big ones, so
        # zoom by how far it scrolled rather than a fixed amount per event
        step = max(-5.0, min(5.0, float(getattr(event, "step", 1 if event.button == "up" else -1))))
        scale = 0.8 ** step
        x0, x1 = self.ax_lc.get_xlim()
        y0, y1 = self.ax_lc.get_ylim()
        self._ylims[self.current] = (event.ydata - (event.ydata - y0) * scale,
                                     event.ydata + (y1 - event.ydata) * scale)
        self.ax_lc.set_ylim(*self._ylims[self.current])
        self.set_view(event.xdata - (event.xdata - x0) * scale, event.xdata + (x1 - event.xdata) * scale)


def run_standalone(files, labels, output_folder, obj_name, time_system=None):
    """Open the window without the main app, for python -m EclipsingBinaries.find_min."""
    root = tk.Tk()
    root.withdraw()
    try:
        window = MinimumFinderWindow(root, files, labels, output_folder, obj_name, time_system=time_system)
    except MinimumError as e:
        print(f"Error: {e}", file=sys.stderr)
        root.destroy()
        return 1
    # Closing the window ends the event loop; the hidden root is destroyed after it
    window.protocol("WM_DELETE_WINDOW", root.quit)
    window.bind("<Destroy>", lambda e: root.quit() if e.widget is window else None)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass
    return 0
