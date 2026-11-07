"""Resolution-independent orbital illustration for the PSOBB desktop launcher.

Only standard-library Canvas primitives are used; this scene has no animation,
network requests, external assets or dependencies on the game runtime.
"""

import math
import tkinter as tk


class OrbitalScene(tk.Canvas):
    """A quiet navigation view of Ragol, sized to its containing hero panel."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("bg", "#101f32")
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("borderwidth", 0)
        kwargs.setdefault("takefocus", 0)
        kwargs.setdefault("width", 400)
        kwargs.setdefault("height", 260)
        super().__init__(parent, **kwargs)
        self._redraw_id = None
        self.bind("<Configure>", self._schedule_draw)
        self.bind("<Destroy>", self._cancel_draw, add="+")

    def _schedule_draw(self, _event=None):
        if self._redraw_id is not None:
            self.after_cancel(self._redraw_id)
        self._redraw_id = self.after_idle(self._draw)

    def _cancel_draw(self, event):
        if event.widget is self and self._redraw_id is not None:
            self.after_cancel(self._redraw_id)
            self._redraw_id = None

    @staticmethod
    def _blend(a, b, amount):
        amount = max(0.0, min(1.0, amount))
        rgb_a = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
        rgb_b = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(rgb_a, rgb_b))

    def _draw(self):
        self._redraw_id = None
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        scale = min(w / 390, h / 260)
        cx, cy = w * .51, h * .48
        radius = min(h * .325, w * .238)

        def line(points, color, width=1, **options):
            self.create_line(*points, fill=color, width=width, **options)

        # Deterministic pinprick stars: no timer or random flicker.
        stars = ((.08, .19), (.14, .60), (.22, .09), (.31, .84), (.40, .13),
                 (.62, .08), (.75, .19), (.89, .36), (.91, .69), (.78, .87),
                 (.60, .92), (.08, .85), (.96, .11), (.83, .53), (.17, .36))
        for index, (sx, sy) in enumerate(stars):
            x, y = sx * w, sy * h
            color = "#54748c" if index % 4 else "#99bec9"
            self.create_oval(x - .7, y - .7, x + .7, y + .7, fill=color, outline="")
            if index in (3, 6, 12):
                line((x - 3, y, x + 3, y), "#32576c")
                line((x, y - 3, x, y + 3), "#32576c")

        # The small vertical instrument scale anchors the illustration to the UI.
        gx = w - max(12, 20 * scale)
        for i in range(17):
            y = h * .22 + i * h * .033
            tick = 7 if i % 4 == 0 else 3
            line((gx - tick, y, gx, y), "#2b485d")

        tilt = -.34

        def orbit_point(angle, a=1.72, b=.56):
            x, y = math.cos(angle) * radius * a, math.sin(angle) * radius * b
            return (cx + x * math.cos(tilt) - y * math.sin(tilt),
                    cy + x * math.sin(tilt) + y * math.cos(tilt))

        def orbit_arc(start, stop, color, width=1, a=1.72, b=.56):
            points = []
            for i in range(81):
                points.extend(orbit_point(start + (stop - start) * i / 80, a, b))
            line(points, color, width, smooth=True)

        orbit_arc(math.pi, 2 * math.pi, "#294a63", a=1.84, b=.65)
        orbit_arc(math.pi, 2 * math.pi, "#416980")
        # Broken navigation arc behind the atmospheric rim.
        self.create_arc(cx - radius * 1.18, cy - radius * 1.18,
                        cx + radius * 1.18, cy + radius * 1.18,
                        start=28, extent=134, style="arc", outline="#2d586d", width=1)
        for i in range(8):
            angle = math.radians(34 + i * 16)
            r1, r2 = radius * 1.18, radius * (1.23 if i % 2 else 1.26)
            line((cx + math.cos(angle) * r1, cy - math.sin(angle) * r1,
                  cx + math.cos(angle) * r2, cy - math.sin(angle) * r2), "#3d7082")

        # A subtle atmospheric glow gives the planet depth against the navy panel.
        for offset, color in ((5, "#163346"), (3, "#205368"), (1.3, "#4b9cac")):
            r = radius + offset * scale
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")

        def project(latitude, longitude):
            return (cx + radius * math.cos(latitude) * math.sin(longitude),
                    cy - radius * math.sin(latitude))

        # Smooth sphere built from a lit latitude/longitude mesh. The light comes
        # from upper left; the day/night shading is deterministic at every size.
        rows, columns = 30, 40
        for row in range(rows):
            lat0 = -.5 * math.pi + row * math.pi / rows
            lat1 = -.5 * math.pi + (row + 1) * math.pi / rows
            lat = (lat0 + lat1) / 2
            for column in range(columns):
                lon0 = -.5 * math.pi + column * math.pi / columns
                lon1 = -.5 * math.pi + (column + 1) * math.pi / columns
                lon = (lon0 + lon1) / 2
                nx = math.cos(lat) * math.sin(lon)
                ny = math.sin(lat)
                nz = math.cos(lat) * math.cos(lon)
                light = max(0, -.61 * nx + .46 * ny + .64 * nz)
                color = self._blend("#10283d", "#327d96", light ** 1.5)
                points = (*project(lat0, lon0), *project(lat0, lon1),
                          *project(lat1, lon1), *project(lat1, lon0))
                self.create_polygon(points, fill=color, outline=color)

        # Abstract continental shelves, intentionally cartographic rather than a
        # real-world map; all coordinates sit on the front hemisphere of Ragol.
        landmasses = (
            ((.78, -.48), (.65, -.79), (.42, -.90), (.29, -.65), (.34, -.40),
             (.12, -.33), (.04, -.06), (.19, .10), (.38, -.05), (.59, -.11)),
            ((.08, .24), (-.10, .08), (-.28, .25), (-.39, .14), (-.58, .33),
             (-.68, .58), (-.44, .73), (-.22, .56), (-.10, .60)),
            ((.63, .50), (.56, .78), (.39, .88), (.29, .70), (.37, .54)),
        )
        for points, color in zip(landmasses, ("#3c8594", "#286579", "#327689")):
            flat = []
            for lat, lon in points:
                flat.extend(project(lat, lon))
            self.create_polygon(flat, fill=color, outline="", smooth=True, splinesteps=14)

        # Very fine latitude and meridian lines, with half the front grid omitted
        # so the planet retains a calm shaded surface instead of a wireframe ball.
        for latitude in (-.56, -.18, .23, .62):
            points = []
            for step in range(35):
                points.extend(project(latitude, -1.40 + step * 2.80 / 34))
            line(points, "#377386", smooth=True)
        for longitude in (-.86, -.38, .12, .65):
            points = []
            for step in range(45):
                points.extend(project(-1.34 + step * 2.68 / 44, longitude))
            line(points, "#397b8c", smooth=True)
        self.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                        start=58, extent=112, style="arc", outline="#8ac9ce", width=1.2)

        orbit_arc(0, math.pi, "#4a7f92")
        orbit_arc(.1, math.pi - .14, "#244b64", a=1.84, b=.65)
        orbit_arc(.21, 1.02, "#79c8cb", width=1.3)

        # Pioneer signal: a small diamond, a forward heading and local readout.
        sx, sy = orbit_point(.36)
        unit = max(3, 4 * scale)
        self.create_polygon(sx, sy - unit, sx + unit, sy, sx, sy + unit,
                            sx - unit, sy, fill="#b8eeea", outline="")
        self.create_oval(sx - unit * 2.2, sy - unit * 2.2,
                         sx + unit * 2.2, sy + unit * 2.2,
                         outline="#406e83", width=1)
        line((sx + 11 * scale, sy, sx + 28 * scale, sy), "#7cbabb")

        label_x, label_y = max(20, cx - radius * .98), h - 27 * scale
        line((label_x, label_y - 13 * scale, label_x + 24 * scale, label_y - 13 * scale), "#63dbd3")
        self.create_text(label_x, label_y, anchor="w", text="R A G O L",
                         fill="#a5c5ce", font=("Segoe UI", max(8, round(9 * scale)), "bold"))
        if w >= 330:
            self.create_text(label_x + 105 * scale, label_y, anchor="w", text="01 / 02 / 04",
                             fill="#638197", font=("Consolas", max(8, round(8 * scale))))


if __name__ == "__main__":
    root = tk.Tk()
    root.title("OrbitalScene preview")
    root.geometry("430x280")
    OrbitalScene(root).pack(fill="both", expand=True)
    root.mainloop()
