"""PSOBB desktop presentation. Game/configuration behavior lives in launcher.py."""
import tkinter as tk
from tkinter import ttk

from launcher_art import OrbitalScene


COLORS = {
    "bg": "#0c1421", "sidebar": "#0a111d", "surface": "#131f30",
    "raised": "#1a2a3e", "field": "#0f1929", "line": "#2a3b50",
    "text": "#edf3fa", "muted": "#a3b4c9", "accent": "#70ded3",
    "hover": "#95eee5", "selected": "#183336", "green": "#8addb2",
    "red": "#ff9baf", "gold": "#e9c68a", "hero": "#102238",
}
FONT = "Microsoft YaHei UI"
SECTION_COLORS = ("#4CCB77", "#A3D96A", "#74BFFF", "#638CFF", "#AD91F5",
                  "#F4A1CA", "#F47575", "#F5A45A", "#E7CD60", "#E5ECF7")


class IntegerScale(ttk.Scale):
    def get(self):
        return round(super().get())

    def set(self, value):
        disabled = self.instate(["disabled"])
        if disabled:
            self.state(["!disabled"])
        try:
            super().set(round(float(value)))
        finally:
            if disabled:
                self.state(["disabled"])


class ScrollPage(tk.Frame):
    """One scroll region per page; keyboard focus always scrolls into view."""
    def __init__(self, parent, ui):
        super().__init__(parent, bg=COLORS["bg"])
        self.ui = ui
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], bd=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.canvas, bg=COLORS["bg"])
        self.window_id = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.content.bind("<Configure>", self._region)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        self._region()

    def _region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def reveal(self, widget):
        self.update_idletasks()
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        total = max(1, self.content.winfo_height())
        margin = self.ui.u(12)
        if top < visible_top + margin:
            self.canvas.yview_moveto(max(0, top - margin) / total)
        elif bottom > visible_top + height - margin:
            self.canvas.yview_moveto(max(0, bottom - height + margin) / total)


class LauncherUI:
    def __init__(self, app, presets):
        self.app, self.root, self.presets = app, app.root, presets
        # Match Windows font scaling while retaining a scrollable compact layout.
        self.factor = max(1.0, float(self.root.tk.call("tk", "scaling")) / (96 / 72))
        self.pages, self.nav_buttons, self.nav_markers = {}, {}, {}
        self.active_page = "home"
        self._traces = []
        self._style()
        self._variables()
        self._shell()
        self._home()
        self._gameplay()
        self._graphics()
        self._tools()
        self.show_page("home")
        self.root.bind("<MouseWheel>", self._wheel, add="+")
        self.root.bind("<FocusIn>", self._focus, add="+")
        self.root.bind("<Control-s>", lambda _e: self.app.on_click_save())
        self.root.bind("<Alt-1>", lambda _e: self.show_page("home"))
        self.root.bind("<Alt-2>", lambda _e: self.show_page("gameplay"))
        self.root.bind("<Alt-3>", lambda _e: self.show_page("graphics"))
        self.root.bind("<Alt-4>", lambda _e: self.show_page("tools"))

    def u(self, value):
        return round(value * self.factor)

    def font(self, size=13, bold=False, family=FONT):
        return (family, -self.u(size), "bold" if bold else "normal")

    def label(self, parent, text="", size=13, color="text", bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=COLORS[color],
                        font=self.font(size, bold), bd=0, anchor="w", **kw)

    def button(self, parent, text, command, kind="secondary", **kw):
        bg = COLORS["accent"] if kind == "primary" else COLORS["raised"]
        fg = COLORS["bg"] if kind == "primary" else COLORS["red"] if kind == "danger" else COLORS["text"]
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                           activebackground=COLORS["hover"] if kind == "primary" else COLORS["line"],
                           activeforeground=fg, disabledforeground=COLORS["muted"],
                           font=self.font(14, kind == "primary"), bd=0, relief="flat",
                           highlightthickness=1, highlightbackground=bg,
                           highlightcolor=COLORS["accent"], cursor="hand2", takefocus=1,
                           padx=self.u(18), pady=self.u(11), **kw)
        button.bind("<Return>", lambda _e: button.invoke())
        return button

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=COLORS["field"], background=COLORS["raised"],
                        foreground=COLORS["text"], arrowcolor=COLORS["muted"],
                        bordercolor=COLORS["line"], lightcolor=COLORS["line"],
                        darkcolor=COLORS["line"], padding=self.u(8), arrowsize=self.u(14))
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["field"])],
                  foreground=[("readonly", COLORS["text"])],
                  bordercolor=[("focus", COLORS["accent"]), ("active", COLORS["muted"])],
                  selectbackground=[("readonly", COLORS["field"])],
                  selectforeground=[("readonly", COLORS["text"])])
        style.configure("TSpinbox", fieldbackground=COLORS["field"], background=COLORS["raised"],
                        foreground=COLORS["text"], arrowcolor=COLORS["muted"],
                        bordercolor=COLORS["line"], lightcolor=COLORS["line"],
                        darkcolor=COLORS["line"], insertcolor=COLORS["text"], padding=self.u(7))
        style.map("TSpinbox", bordercolor=[("focus", COLORS["accent"])])
        style.configure("Vertical.TScrollbar", background=COLORS["line"], troughcolor=COLORS["bg"],
                        bordercolor=COLORS["bg"], lightcolor=COLORS["line"], darkcolor=COLORS["line"],
                        arrowcolor=COLORS["muted"], width=self.u(10), arrowsize=self.u(10))
        for name in ("accent", "red", "gold"):
            style.configure(f"{name}.Horizontal.TScale", background=COLORS[name],
                            troughcolor=COLORS["field"], bordercolor=COLORS["line"],
                            lightcolor=COLORS[name], darkcolor=COLORS[name],
                            sliderlength=self.u(18), sliderthickness=self.u(14))
            style.map(f"{name}.Horizontal.TScale", background=[("active", COLORS["hover"])])
        self.root.option_add("*TCombobox*Listbox.background", COLORS["raised"])
        self.root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLORS["selected"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", COLORS["accent"])
        self.root.option_add("*TCombobox*Listbox.font", self.font(13))

    def _read(self, key, default):
        cfg = self.app.ui_cfg
        try:
            if isinstance(default, bool):
                return cfg.getboolean("UI", key, fallback=default)
            if isinstance(default, int):
                return cfg.getint("UI", key, fallback=default)
            return cfg.get("UI", key, fallback=default)
        except (ValueError, TypeError):
            return default

    def _variables(self):
        a, p = self.app, self.presets
        server, client = a.server_cfg, a.client_cfg
        for attr, key, default in [("var_exp", "exp_boost", 1), ("var_rare", "rare_mob_mult", 1)]:
            setattr(a, attr, tk.IntVar(self.root, self._read(key, server.get(key, default))))
        event = self._read("event_id", server.get("event_id", 0))
        a.var_event = tk.StringVar(self.root, p["events"].get(event, p["events"][0]))
        section_choice = self._read("drop_section_choice", next(iter(p["drop_sections"])))
        if section_choice not in p["drop_sections"]:
            section_choice = next(iter(p["drop_sections"]))
        a.var_drop_section = tk.StringVar(self.root, section_choice)
        for attr, key, default in [
            ("var_name_color", "name_color", next(iter(p["colors"]))),
            ("var_dmg_mult", "dmg_mult", p["stats"][0]),
            ("var_def_mult", "def_mult", p["stats"][0]),
            ("var_hp_mult", "hp_mult", p["stats"][0]),
        ]:
            setattr(a, attr, tk.StringVar(self.root, self._read(key, server.get(key, default))))
        a.var_unlock_tech = tk.BooleanVar(self.root, self._read("unlock_tech_30", server.get("unlock_tech_30", False)))
        for attr, key, choices in [
            ("var_render_api", "output_api", p["render"]),
            ("var_win_mode", "window_scale", p["window"]),
            ("var_screen_mode", "screen_mode", p["screen_modes"]),
            ("var_font", "font_choice", p["fonts"]),
            ("var_aa", "antialiasing", ["off", "2x", "4x", "8x"]),
            ("var_hud_scale", "hud_scale", p["hud"]),
        ]:
            default = client.get(key, next(iter(choices)))
            if key == "window_scale":
                default = self._read("display_mode", default)
            value = self._read(key, default)
            if key == "hud_scale" and value not in choices:
                value = next((v for v in choices if v.split(" ")[0] == value.split(" ")[0]), choices[0])
            if value not in choices:
                value = next(iter(choices))
            setattr(a, attr, tk.StringVar(self.root, value))
        for attr, key in [("var_ssao", "ssao"), ("var_hdr", "hdr"), ("var_cel", "cel"),
                          ("var_auto_login", "auto_login"), ("var_auto_backup", "auto_backup"),
                          ("var_auto_kill", "auto_kill")]:
            setattr(a, attr, tk.BooleanVar(self.root, self._read(key, client.get(key, True))))
        self.meseta_var = tk.IntVar(self.root, self._read("meseta_mult", server.get("meseta_mult", 1)))

    def _shell(self):
        a = self.app
        sidebar = tk.Frame(self.root, bg=COLORS["sidebar"], width=self.u(190))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=COLORS["sidebar"])
        brand.pack(fill="x", padx=self.u(24), pady=(self.u(30), self.u(28)))
        self.label(brand, "PSO", size=36, bold=True).pack(anchor="w")
        self.label(brand, "B L U E   B U R S T", size=10, color="accent").pack(anchor="w", pady=(0, self.u(12)))
        self.label(brand, "梦幻之星 · 蓝色脉冲", size=11, color="muted").pack(anchor="w")
        self.label(sidebar, "  猎 人 终 端", size=10, color="muted").pack(anchor="w", padx=self.u(22), pady=(0, self.u(12)))
        for index, (key, title) in enumerate([("home", "启动中心"), ("gameplay", "掉落与成长"),
                                             ("graphics", "画面设置"), ("tools", "工具与维护")], 1):
            row = tk.Frame(sidebar, bg=COLORS["sidebar"])
            row.pack(fill="x", padx=self.u(12), pady=self.u(3))
            marker = tk.Frame(row, width=self.u(3), bg=COLORS["sidebar"])
            marker.pack(side="left", fill="y", pady=self.u(9))
            button = self.button(row, f"{index:02d}   {title}", lambda k=key: self.show_page(k), anchor="w")
            button.configure(bg=COLORS["sidebar"], highlightbackground=COLORS["sidebar"], padx=self.u(13), pady=self.u(14))
            button.pack(side="left", fill="x", expand=True)
            self.nav_buttons[key], self.nav_markers[key] = button, marker
        credit = tk.Frame(sidebar, bg=COLORS["sidebar"])
        credit.pack(side="bottom", fill="x", padx=self.u(24), pady=self.u(24))
        tk.Frame(credit, bg=COLORS["line"], height=1).pack(fill="x", pady=(0, self.u(16)))
        self.label(credit, "单机中文终极版", size=12).pack(anchor="w")
        self.label(credit, "EPISODE  I / II / IV", size=10, color="muted").pack(anchor="w", pady=(self.u(4), self.u(16)))
        self.label(credit, "整合 / metalmouse", size=10, color="muted").pack(anchor="w")

        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=COLORS["bg"])
        header.pack(fill="x", padx=self.u(28), pady=(self.u(22), self.u(20)))
        self.page_title = self.label(header, "", size=21, bold=True)
        self.page_title.pack(side="left")
        a.status_pill = self.label(header, "○  检测本地服务", size=11, color="muted", padx=self.u(12), pady=self.u(7))
        a.status_pill.configure(bg=COLORS["raised"])
        a.status_pill.pack(side="right")

        # Reserve the launch bar before the scrollable content at every window size.
        footer = tk.Frame(main, bg=COLORS["bg"])
        footer.pack(side="bottom", fill="x", padx=self.u(28), pady=(self.u(12), self.u(14)))
        tk.Frame(footer, height=1, bg=COLORS["line"]).pack(fill="x", pady=(0, self.u(14)))
        actions = tk.Frame(footer, bg=COLORS["bg"])
        actions.pack(fill="x")
        a.btn_launch = self.button(actions, "启动游戏   →", a.on_click_launch, "primary", width=17)
        a.btn_launch.pack(side="right")
        self.save_button = self.button(actions, "保存配置", a.on_click_save)
        self.save_button.pack(side="left")
        self.label(actions, "启动时自动应用当前设置", size=11, color="muted").pack(side="left", padx=self.u(14))
        a.log_lbl = self.label(footer, "准备就绪，开启你的拉古奥尔之旅。", size=11, color="muted")
        a.log_lbl.pack(fill="x", pady=(self.u(10), 0))
        a.log_lbl.bind("<Configure>", lambda e: a.log_lbl.configure(wraplength=max(100, e.width)))

        self.page_container = tk.Frame(main, bg=COLORS["bg"])
        self.page_container.pack(fill="both", expand=True, padx=(self.u(28), self.u(14)))
        self.page_container.rowconfigure(0, weight=1)
        self.page_container.columnconfigure(0, weight=1)
        for key in self.nav_buttons:
            page = ScrollPage(self.page_container, self)
            self.pages[key] = page

    def show_page(self, key):
        if key not in self.pages:
            return
        old = self.pages.get(self.active_page)
        if old:
            old.grid_remove()
        self.active_page = key
        self.pages[key].grid(row=0, column=0, sticky="nsew")
        titles = {"home": "启动中心", "gameplay": "掉落与成长", "graphics": "画面设置", "tools": "工具与维护"}
        self.page_title.configure(text=titles[key])
        for name, button in self.nav_buttons.items():
            selected = name == key
            bg = COLORS["selected"] if selected else COLORS["sidebar"]
            button.configure(bg=bg, fg=COLORS["accent"] if selected else COLORS["muted"], highlightbackground=bg)
            self.nav_markers[name].configure(bg=COLORS["accent"] if selected else COLORS["sidebar"])

    def _wheel(self, event):
        if event.widget.winfo_toplevel() != self.root:
            return
        page = self.pages[self.active_page]
        # Native inputs own their wheel; scrolling only within the content pane.
        if isinstance(event.widget, (ttk.Combobox, ttk.Spinbox, tk.Scale)):
            return
        widget = event.widget
        while widget is not None and widget != page:
            widget = getattr(widget, "master", None)
        if widget is page and page.content.winfo_height() > page.canvas.winfo_height():
            page.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
            return "break"

    def _focus(self, event):
        page = self.pages[self.active_page]
        widget = event.widget
        while widget is not None and widget != page.content:
            widget = getattr(widget, "master", None)
        if widget is page.content:
            page.reveal(event.widget)

    def section(self, parent, title, caption=None):
        frame = tk.Frame(parent, bg=COLORS["surface"], highlightthickness=1, highlightbackground=COLORS["line"])
        frame.pack(fill="x", padx=(0, self.u(10)), pady=(0, self.u(16)))
        inner = tk.Frame(frame, bg=COLORS["surface"])
        inner.pack(fill="both", expand=True, padx=self.u(22), pady=self.u(20))
        self.label(inner, title, size=16, bold=True).pack(anchor="w")
        if caption:
            hint = self.label(inner, caption, size=11, color="muted", justify="left")
            hint.pack(fill="x", pady=(self.u(5), self.u(4)))
            hint.bind("<Configure>", lambda e, w=hint: w.configure(wraplength=max(100, e.width)))
        return inner

    def combo(self, parent, label, variable, values, item_colors=None, visible_rows=10):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(self.u(14), 0))
        caption = self.label(row, label, size=13)
        control = ttk.Combobox(row, textvariable=variable, values=list(values), state="readonly",
                               font=self.font(13), width=31, height=visible_rows)
        if item_colors is not None:
            def color_popdown():
                try:
                    popdown = self.root.tk.call("ttk::combobox::PopdownWindow", str(control))
                    listbox = f"{popdown}.f.l"
                    for index, color in enumerate(item_colors):
                        self.root.tk.call(listbox, "itemconfigure", index,
                                          "-foreground", color, "-selectforeground", color)
                except tk.TclError:
                    pass
            control.configure(postcommand=lambda: self.root.after_idle(color_popdown))
        def arrange(event):
            stacked = event.width < self.u(600)
            if getattr(row, "stacked", None) == stacked:
                return
            row.stacked = stacked
            caption.pack_forget()
            control.pack_forget()
            if stacked:
                caption.pack(anchor="w")
                control.pack(fill="x", pady=(self.u(8), 0))
            else:
                caption.pack(side="left")
                control.pack(side="right", padx=(self.u(16), 0))
        row.bind("<Configure>", arrange)
        return control

    def spin(self, parent, label, variable, limit, caption):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(self.u(16), 0))
        self.label(row, label).pack(side="left")
        self.label(row, caption, size=11, color="muted").pack(side="right", padx=(self.u(12), 0))
        control = ttk.Spinbox(row, from_=1, to=limit, textvariable=variable, width=7, font=self.font(14))
        control.pack(side="right")
        return control

    def check(self, parent, label, variable, hint=None):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(self.u(14), 0))
        checkbox = tk.Checkbutton(row, text=label, variable=variable, font=self.font(13),
                                  bg=parent.cget("bg"), fg=COLORS["text"],
                                  selectcolor=COLORS["field"], activebackground=parent.cget("bg"),
                                  activeforeground=COLORS["accent"], highlightcolor=COLORS["accent"],
                                  highlightbackground=parent.cget("bg"), highlightthickness=1,
                                  bd=0, cursor="hand2", anchor="w", padx=0, pady=self.u(3), takefocus=1)
        checkbox.pack(fill="x")
        if hint:
            note = self.label(row, hint, size=11, color="muted", justify="left")
            note.pack(fill="x", padx=(self.u(24), 0), pady=(self.u(3), 0))
            note.bind("<Configure>", lambda e, w=note: w.configure(wraplength=max(100, e.width)))
        return checkbox

    def slider(self, parent, title, value, minimum=0, maximum=100, unit="%", color="accent", variable=None):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(self.u(17), 0))
        top = tk.Frame(row, bg=parent.cget("bg"))
        top.pack(fill="x")
        self.label(top, title).pack(side="left")
        var = variable or tk.IntVar(self.root, value)
        readout = self.label(top, f"{var.get()}{unit}", size=14, color=color, bold=True)
        readout.pack(side="right")
        def refresh(*_):
            readout.configure(text=f"{var.get()}{unit}")
        self._traces.append((var, var.trace_add("write", refresh)))
        slider = IntegerScale(row, from_=minimum, to=maximum, variable=var,
                              orient="horizontal", style=f"{color}.Horizontal.TScale",
                              command=lambda value: var.set(round(float(value))),
                              takefocus=1, cursor="hand2")
        slider.pack(fill="x", pady=(self.u(8), 0))
        return slider

    def _home(self):
        a = self.app
        page = self.pages["home"].content
        hero = tk.Frame(page, bg=COLORS["hero"], highlightthickness=1, highlightbackground=COLORS["line"])
        hero.pack(fill="x", padx=(0, self.u(10)), pady=(0, self.u(18)))
        hero.columnconfigure(0, weight=3, minsize=self.u(310))
        hero.columnconfigure(1, weight=2)
        intro = tk.Frame(hero, bg=COLORS["hero"])
        intro.grid(row=0, column=0, sticky="nsew", padx=self.u(28), pady=self.u(28))
        self.label(intro, "PIONEER 02  /  HUNTER'S GUILD", size=10, color="accent").pack(anchor="w")
        self.label(intro, "下一站，拉古奥尔。", size=30, bold=True).pack(anchor="w", pady=(self.u(20), self.u(10)))
        self.label(intro, "熟悉的世界，全新的冒险。", size=14, color="muted").pack(anchor="w")
        self.label(intro, "本地单机  /  简体中文  /  自由探索", size=11, color="muted").pack(anchor="w", pady=(self.u(22), self.u(8)))
        art = OrbitalScene(hero, bg=COLORS["hero"], height=self.u(238), width=self.u(280), highlightthickness=0, bd=0)
        art.grid(row=0, column=1, sticky="nsew")
        def arrange_hero(event):
            if event.width < self.u(740):
                art.grid_remove()
                hero.columnconfigure(1, weight=0)
            else:
                art.grid()
                hero.columnconfigure(1, weight=2)
        hero.bind("<Configure>", arrange_hero)

        stats = tk.Frame(page, bg=COLORS["bg"])
        stats.pack(fill="x", padx=(0, self.u(10)), pady=(0, self.u(20)))
        stats.columnconfigure((0, 1, 2), weight=1, uniform="stats")
        for col, (title, variable, suffix, hint) in enumerate([
            ("经验倍率", a.var_exp, "×", "角色成长"),
            ("美塞塔数量", self.meseta_var, "×", "怪物 / 箱子金额"),
            ("战斗强化", a.var_dmg_mult, "", "伤害倍率"),
        ]):
            card = tk.Frame(stats, bg=COLORS["surface"], highlightthickness=1, highlightbackground=COLORS["line"])
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else self.u(6), 0 if col == 2 else self.u(6)))
            self.label(card, title, size=11, color="muted").pack(anchor="w", padx=self.u(18), pady=(self.u(15), 0))
            value = self.label(card, "", size=25, bold=True)
            value.pack(anchor="w", padx=self.u(18), pady=(self.u(5), self.u(3)))
            self.label(card, hint, size=10, color="muted").pack(anchor="w", padx=self.u(18), pady=(0, self.u(14)))
            def update(*_, v=variable, label=value, ending=suffix):
                try:
                    label.configure(text=str(v.get()).split(" ")[0].replace("X", "×") + ending)
                except tk.TclError:
                    label.configure(text="—")
            self._traces.append((variable, variable.trace_add("write", update)))
            update()

        options = self.section(page, "让冒险更省心", "每次启动都会应用设置；退出后保留你的选择。")
        self.check(options, "自动登录", a.var_auto_login, "启动后自动完成进入游戏所需的窗口操作。")
        self.check(options, "自动备份存档", a.var_auto_backup, "在启动与退出时保存快照，让每一次冒险都有记录。")
        self.check(options, "退出游戏后关闭本地服务", a.var_auto_kill)

    def _gameplay(self):
        a, p = self.app, self.presets
        page = self.pages["gameplay"].content
        progression = self.section(page, "成长与战斗", "从原版节奏到轻松单刷，按自己的方式探索。")
        self.spin(progression, "经验倍率", a.var_exp, 99, "倍  /  1—99")
        self.spin(progression, "稀有怪出现倍率", a.var_rare, 25, "倍  /  1—25")
        self.combo(progression, "伤害倍率", a.var_dmg_mult, p["stats"])
        self.combo(progression, "防御倍率", a.var_def_mult, p["stats"])
        self.combo(progression, "生命倍率", a.var_hp_mult, p["stats"])
        self.label(progression, "此项调整基础属性与升级成长，并非最终伤害乘数。", size=11, color="gold").pack(anchor="w", pady=(self.u(14), 0))
        self.label(progression, "已有角色保留存档属性，后续升级才应用新的成长值。", size=11, color="muted").pack(anchor="w", pady=(self.u(6), 0))
        drops = self.section(page, "战利品掉落", "掉落设置与大厅活动均在重新启动游戏及本地服务后生效。")
        choice_colors = [SECTION_COLORS[section_id] if isinstance(section_id, int) else COLORS["muted"]
                         for section_id in p["drop_sections"].values()]
        section_combo = self.combo(drops, "掉落徽章", a.var_drop_section,
                                   p["drop_sections"], item_colors=choice_colors,
                                   visible_rows=len(p["drop_sections"]))
        section_style = "DropSection.TCombobox"
        ttk.Style(self.root).configure(section_style, foreground=COLORS["muted"])
        section_combo.configure(style=section_style)
        badge = self.label(drops, size=13, bold=True)
        badge.pack(anchor="w", pady=(self.u(10), 0))
        def update_badge(*_):
            choice = a.var_drop_section.get()
            section_id = p["drop_sections"].get(choice)
            ttk.Style(self.root).configure(section_style,
                                           foreground=SECTION_COLORS[section_id] if isinstance(section_id, int) else COLORS["muted"])
            if section_id == "random":
                badge.configure(text="随机", fg=COLORS["muted"])
            elif section_id is None:
                badge.configure(text="角色原有徽章", fg=COLORS["muted"])
            else:
                badge.configure(text=choice.split("（", 1)[0], fg=SECTION_COLORS[section_id])
        a.var_drop_section.trace_add("write", update_badge)
        update_badge()
        self.label(drops, "所有角色使用选定徽章的掉落表；随机项每次开始游戏重新抽取。角色本身徽章不变。",
                   size=11, color="muted").pack(anchor="w", pady=(self.u(6), self.u(10)))
        self.label(drops, "红盒概率固定为原滑块 20 档；高于目标的原始条目保持不变。", size=11, color="gold").pack(anchor="w", pady=(self.u(6), 0))
        self.label(drops, "实际每次任务的红盒数量会随怪物、难度与普通掉落判定变化。", size=11, color="muted").pack(anchor="w", pady=(self.u(6), 0))
        a.sliders = {}
        for key, name, default in [("drop_weapon", "武器", 30), ("drop_armor", "防具 / 护盾", 20),
                                   ("drop_tool", "道具 / 耗材", 50), ("drop_meseta", "美塞塔", 40),
                                   ("drop_mag", "玛古 MAG", 1)]:
            a.sliders[key] = self.slider(drops, name, self._read(key, a.server_cfg.get(key, default)))
        a.scale_meseta_mult = self.slider(drops, "美塞塔数量倍率", self._read("meseta_mult", a.server_cfg.get("meseta_mult", 1)),
                                           minimum=1, maximum=20, unit="×", color="gold", variable=self.meseta_var)
        world = self.section(page, "世界与角色", "主题装饰用于公共大厅；猎人公会和任务场景不随主题改变。")
        self.combo(world, "大厅活动", a.var_event, p["events"].values())
        self.combo(world, "角色名字颜色", a.var_name_color, p["colors"])
        self.check(world, "解锁全职业 30 级魔法", a.var_unlock_tech, "允许战士和游侠学习恢复与辅助等全系魔法。")

    def _graphics(self):
        a, p = self.app, self.presets
        page = self.pages["graphics"].content
        display = self.section(page, "显示与渲染", "保持原版 4:3；宽屏全屏时两侧留黑边。更改后重启游戏生效。")
        self.combo(display, "渲染引擎", a.var_render_api, p["render"])
        self.combo(display, "显示模式", a.var_screen_mode, p["screen_modes"])
        self.combo(display, "窗口尺寸", a.var_win_mode, p["window"])
        hint = self.label(display, "全屏采用兼容模式，保留 4:3 黑边；窗口尺寸与 MSAA 仅用于普通窗口。", size=11, color="muted", justify="left")
        hint.pack(fill="x", pady=(self.u(12), 0))
        hint.bind('<Configure>', lambda e: hint.configure(wraplength=max(100, e.width)))
        aa = self.combo(display, "抗锯齿（MSAA）", a.var_aa, ["off", "2x", "4x", "8x"])
        def update_aa_state(*_args):
            aa.configure(state='readonly' if p['screen_modes'].get(a.var_screen_mode.get()) == 'window' else 'disabled')
        self._traces.append(a.var_screen_mode.trace_add('write', update_aa_state))
        update_aa_state()
        typography = self.section(page, "文字与界面", "选择适合屏幕的字体和 HUD 缩放。")
        self.combo(typography, "游戏中文字体", a.var_font, p["fonts"])
        self.combo(typography, "HUD 缩放", a.var_hud_scale, p["hud"])
        effects = self.section(page, "画面特效", "独立开启或关闭特效，找到喜欢的画面风格。")
        self.check(effects, "环境光遮蔽  SSAO", a.var_ssao, "增强场景物体接触处的阴影层次。")
        self.check(effects, "动态高光  HDR", a.var_hdr, "提升明亮区域的光照表现。")
        self.check(effects, "赛璐珞描边  Cel-Shading", a.var_cel, "为角色与场景添加经典动画轮廓。")

    def _tools(self):
        a = self.app
        page = self.pages["tools"].content
        utilities = self.section(page, "猎人工具箱", "物品、账号和指令，常用工具集中在这里。")
        for title, hint, action in [
            ("手柄与键盘", "识别设备、测试按钮与摇杆、检查键盘输入", a.open_input_settings),
            ("物品制作", "Item Maker · 创建武器、道具与玛古", a.open_item_maker),
            ("账号管理", "Tethman · 管理本地账号和角色", a.open_tethman),
            ("GM 指令手册", "查看升级、传送与角色外观等常用指令", a.show_gm_help),
            ("运行日志", "查看启动与服务状态，协助定位问题", a.open_log_file),
        ]:
            row = tk.Frame(utilities, bg=COLORS["surface"])
            row.pack(fill="x", pady=(self.u(18), 0))
            info = tk.Frame(row, bg=COLORS["surface"])
            info.pack(side="left", fill="x", expand=True)
            self.label(info, title, bold=True).pack(anchor="w")
            note = self.label(info, hint, size=11, color="muted", justify="left")
            note.pack(fill="x", pady=(self.u(5), 0))
            note.bind("<Configure>", lambda e, w=note: w.configure(wraplength=max(80, e.width)))
            self.button(row, "打开  ↗", action).pack(side="right", padx=(self.u(12), 0))
        server = self.section(page, "本地服务", "启动游戏时会自动开启服务，也可以在这里单独控制。")
        a.btn_srv_toggle = self.button(server, "启动后台服务", a.on_toggle_server)
        a.btn_srv_toggle.pack(anchor="w", pady=(self.u(14), 0))
        reset = self.section(page, "恢复默认", "将成长倍率、掉落与画面参数恢复为原始配置。")
        self.button(reset, "恢复原始配置", a.on_restore_defaults, "danger").pack(anchor="w", pady=(self.u(14), 0))


def build_ui(app, presets):
    app.ui = LauncherUI(app, presets)
