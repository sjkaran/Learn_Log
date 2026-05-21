"""
LearnLog — A minimal learning journal for students.
Pure Python stdlib: tkinter + sqlite3. No pip installs needed.
Run: python learning_journal.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import re
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME   = "LearnLog"
DB_PATH      = Path.home() / ".learnlog" / "journal.db"
DRAFT_PATH   = Path.home() / ".learnlog" / "draft.tmp"
WIN_W, WIN_H = 900, 620

# ── Palette (dark, ink-on-paper feel) ─────────────────────────────────────────
C = {
    "bg":        "#0f0f0f",
    "panel":     "#374246",
    "border":    "#5D526F",
    "accent":    "#c8f060",   # lime-green — the "highlight" pen
    "accent2":   "#60c8f0",   # sky-blue accent
    "text":      "#e8e8e8",
    "muted":     "#666666",
    "tag_bg":    "#1e2a10",
    "tag_fg":    "#c8f060",
    "entry_bg":  "#131313",
    "hover":     "#1f1f1f",
    "danger":    "#f06060",
    "streak":    "#f0a060",
}

FONT_MONO  = ("Courier New", 11)
FONT_BODY  = ("Georgia", 11)
FONT_TITLE = ("Georgia", 20, "bold")
FONT_LABEL = ("Courier New", 9)
FONT_TAG   = ("Courier New", 9, "bold")

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            created   TEXT NOT NULL,
            topic     TEXT NOT NULL DEFAULT '',
            body      TEXT NOT NULL,
            mood      TEXT NOT NULL DEFAULT '🟢',
            code_mode INTEGER NOT NULL DEFAULT 0
        )
    """)
    # migrate existing DBs that lack code_mode column
    cols = [r[1] for r in con.execute("PRAGMA table_info(entries)").fetchall()]
    if "code_mode" not in cols:
        con.execute("ALTER TABLE entries ADD COLUMN code_mode INTEGER NOT NULL DEFAULT 0")
    con.commit()
    return con

def db_add(con, topic, body, mood, code_mode=0):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    con.execute("INSERT INTO entries (created, topic, body, mood, code_mode) VALUES (?,?,?,?,?)",
                (ts, topic.strip(), body.strip(), mood, int(code_mode)))
    con.commit()

def db_search(con, query="", topic_filter=""):
    q = f"%{query}%"
    t = f"%{topic_filter}%"
    rows = con.execute("""
        SELECT * FROM entries
        WHERE (body LIKE ? OR topic LIKE ?)
          AND topic LIKE ?
        ORDER BY created DESC
    """, (q, q, t)).fetchall()
    return rows

def db_delete(con, entry_id):
    con.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    con.commit()

def db_all_topics(con):
    rows = con.execute("SELECT DISTINCT topic FROM entries WHERE topic != '' ORDER BY topic").fetchall()
    topics = []
    for r in rows:
        for tag in [t.strip() for t in r["topic"].split(",")]:
            if tag and tag not in topics:
                topics.append(tag)
    return sorted(topics)

def db_streak(con):
    rows = con.execute("SELECT DISTINCT date(created) as d FROM entries ORDER BY d DESC").fetchall()
    if not rows:
        return 0
    days = [date.fromisoformat(r["d"]) for r in rows]
    today = date.today()
    streak = 0
    check = today
    for d in days:
        if d == check or (streak == 0 and d == today - timedelta(days=1)):
            if streak == 0 and d != today:
                check = today - timedelta(days=1)
            if d == check:
                streak += 1
                check -= timedelta(days=1)
            else:
                break
        elif d < check:
            break
    return streak

def db_total(con):
    return con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

def db_export(con, path):
    rows = con.execute("SELECT * FROM entries ORDER BY created DESC").fetchall()
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"LearnLog Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n\n")
        for r in rows:
            f.write(f"[{r['created']}]  {r['mood']}  Topics: {r['topic']}\n")
            f.write("-" * 40 + "\n")
            f.write(r["body"] + "\n\n")

def draft_save(topic, body, mood, code_mode):
    """Write current editor state to a temp file for crash recovery."""
    try:
        import json
        DRAFT_PATH.write_text(json.dumps({
            "topic": topic, "body": body, "mood": mood, "code_mode": code_mode
        }), encoding="utf-8")
    except Exception:
        pass

def draft_load():
    """Return saved draft dict or None."""
    try:
        import json
        if DRAFT_PATH.exists():
            return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

def draft_clear():
    try:
        if DRAFT_PATH.exists():
            DRAFT_PATH.unlink()
    except Exception:
        pass


def styled_btn(parent, text, cmd, color=None, small=False):
    fg = color or C["accent"]
    f  = FONT_LABEL if small else FONT_MONO
    b  = tk.Label(parent, text=text, fg=fg, bg=C["panel"],
                  font=f, cursor="hand2", padx=8, pady=3)
    b.bind("<Button-1>", lambda e: cmd())
    b.bind("<Enter>",  lambda e: b.config(bg=C["hover"]))
    b.bind("<Leave>",  lambda e: b.config(bg=C["panel"]))
    return b

def tag_chip(parent, text):
    lbl = tk.Label(parent, text=f" {text} ", fg=C["tag_fg"], bg=C["tag_bg"],
                   font=FONT_TAG, padx=2, pady=1, relief="flat")
    return lbl

def sep(parent, pady=4):
    tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", pady=pady)

# ── Main Application ──────────────────────────────────────────────────────────
class LearnLog(tk.Tk):
    def __init__(self):
        super().__init__()
        self.con = init_db()
        self.title(APP_NAME)
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.minsize(760, 520)
        self.configure(bg=C["bg"])
        self.resizable(True, True)

        self._selected_id = None
        self._mood        = tk.StringVar(value="🟢")
        self._code_mode   = False

        self._build_layout()
        self._refresh_list()
        self._update_stats()
        self._check_draft_recovery()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_layout(self):
        # Top bar
        bar = tk.Frame(self, bg=C["panel"], height=48)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        tk.Label(bar, text=APP_NAME, fg=C["accent"], bg=C["panel"],
                 font=FONT_TITLE).pack(side="left", padx=18, pady=8)

        # Stats in top bar
        self._lbl_streak = tk.Label(bar, text="", fg=C["streak"], bg=C["panel"], font=FONT_LABEL)
        self._lbl_streak.pack(side="left", padx=12)
        self._lbl_total  = tk.Label(bar, text="", fg=C["muted"],  bg=C["panel"], font=FONT_LABEL)
        self._lbl_total.pack(side="left", padx=4)

        # Export button
        styled_btn(bar, "[ export ]", self._export, color=C["muted"], small=True).pack(side="right", padx=14)

        # Body: left list + right editor
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True)

        self._build_sidebar(body)
        self._build_editor(body)

    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=C["panel"], width=280)
        side.pack(fill="y", side="left")
        side.pack_propagate(False)

        # Search
        sf = tk.Frame(side, bg=C["panel"])
        sf.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(sf, text="SEARCH", fg=C["muted"], bg=C["panel"], font=FONT_LABEL).pack(anchor="w")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_list())
        se = tk.Entry(sf, textvariable=self._search_var, bg=C["entry_bg"], fg=C["text"],
                      insertbackground=C["accent"], relief="flat", font=FONT_MONO,
                      highlightthickness=1, highlightcolor=C["accent"],
                      highlightbackground=C["border"])
        se.pack(fill="x", pady=(2, 0), ipady=5)

        # Topic filter
        tf = tk.Frame(side, bg=C["panel"])
        tf.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(tf, text="TOPIC FILTER", fg=C["muted"], bg=C["panel"], font=FONT_LABEL).pack(anchor="w")
        self._topic_var = tk.StringVar(value="")
        self._topic_combo = ttk.Combobox(tf, textvariable=self._topic_var,
                                         font=FONT_MONO, state="readonly")
        self._topic_combo.pack(fill="x", pady=(2, 0))
        self._topic_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        sep(side)

        # Entry list
        tk.Label(side, text="ENTRIES", fg=C["muted"], bg=C["panel"],
                 font=FONT_LABEL).pack(anchor="w", padx=10)

        list_frame = tk.Frame(side, bg=C["panel"])
        list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        scroll = tk.Scrollbar(list_frame, bg=C["border"], troughcolor=C["bg"],
                              activebackground=C["accent"], relief="flat", width=6)
        scroll.pack(side="right", fill="y")

        self._listbox = tk.Listbox(list_frame, bg=C["panel"], fg=C["text"],
                                   selectbackground=C["border"], selectforeground=C["accent"],
                                   font=FONT_MONO, relief="flat", bd=0,
                                   activestyle="none", yscrollcommand=scroll.set)
        self._listbox.pack(fill="both", expand=True)
        scroll.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._entries = []

        sep(side, pady=0)
        styled_btn(side, "[ + new entry ]", self._new_entry).pack(pady=8)

    def _build_editor(self, parent):
        ed = tk.Frame(parent, bg=C["bg"])
        ed.pack(fill="both", expand=True, side="left")

        # Meta row: date (auto), topic input, mood
        meta = tk.Frame(ed, bg=C["bg"])
        meta.pack(fill="x", padx=18, pady=(14, 0))

        self._lbl_date = tk.Label(meta, text="", fg=C["muted"], bg=C["bg"], font=FONT_LABEL)
        self._lbl_date.pack(side="left")

        # Mood picker
        mood_frame = tk.Frame(meta, bg=C["bg"])
        mood_frame.pack(side="right")
        tk.Label(mood_frame, text="mood ", fg=C["muted"], bg=C["bg"], font=FONT_LABEL).pack(side="left")
        for emoji in ["🟢", "🟡", "🔴", "⚡", "🔥"]:
            rb = tk.Radiobutton(mood_frame, text=emoji, variable=self._mood, value=emoji,
                                bg=C["bg"], fg=C["text"], selectcolor=C["bg"],
                                activebackground=C["bg"], font=("TkDefaultFont", 12),
                                relief="flat", bd=0)
            rb.pack(side="left", padx=2)

        # Topic row
        tr = tk.Frame(ed, bg=C["bg"])
        tr.pack(fill="x", padx=18, pady=(6, 0))
        tk.Label(tr, text="topics: ", fg=C["muted"], bg=C["bg"], font=FONT_LABEL).pack(side="left")
        self._topic_entry = tk.Entry(tr, bg=C["entry_bg"], fg=C["accent"],
                                     insertbackground=C["accent"], relief="flat",
                                     font=FONT_MONO, width=40,
                                     highlightthickness=1, highlightcolor=C["accent"],
                                     highlightbackground=C["border"])
        self._topic_entry.pack(side="left", ipady=4, padx=(0, 8))
        tk.Label(tr, text="comma-separated", fg=C["muted"], bg=C["bg"], font=FONT_LABEL).pack(side="left")

        sep(ed, pady=6)

        # Body text area
        ta_frame = tk.Frame(ed, bg=C["bg"])
        ta_frame.pack(fill="both", expand=True, padx=18)

        ta_scroll = tk.Scrollbar(ta_frame, bg=C["border"], troughcolor=C["bg"],
                                 activebackground=C["accent"], relief="flat", width=6)
        ta_scroll.pack(side="right", fill="y")

        self._text = tk.Text(ta_frame, bg=C["entry_bg"], fg=C["text"],
                             insertbackground=C["accent"], relief="flat", bd=0,
                             font=FONT_BODY, wrap="word", padx=14, pady=12,
                             spacing1=2, spacing3=4,
                             yscrollcommand=ta_scroll.set,
                             highlightthickness=1, highlightcolor=C["accent"],
                             highlightbackground=C["border"])
        self._text.pack(fill="both", expand=True)
        ta_scroll.config(command=self._text.yview)

        # Placeholder behaviour
        self._placeholder = "Start writing what you learned today…"
        self._text.insert("1.0", self._placeholder)
        self._text.config(fg=C["muted"])
        self._text.bind("<FocusIn>",  self._clear_placeholder)
        self._text.bind("<FocusOut>", self._restore_placeholder)

        # Bottom bar
        bot = tk.Frame(ed, bg=C["panel"])
        bot.pack(fill="x", side="bottom")

        self._lbl_chars = tk.Label(bot, text="", fg=C["muted"], bg=C["panel"], font=FONT_LABEL)
        self._lbl_chars.pack(side="left", padx=14, pady=8)

        # Code mode toggle
        self._btn_code = tk.Label(bot, text="[ </> ]", fg=C["tag_fg"], bg=C["tag_bg"],
                                  font=FONT_LABEL, cursor="hand2", padx=8, pady=3)
        self._btn_code.pack(side="left", padx=2)
        self._btn_code.bind("<Button-1>", lambda e: self._toggle_code_mode())
        self._btn_code.bind("<Enter>", lambda e: self._btn_code.config(bg=C["hover"]))
        self._btn_code.bind("<Leave>", lambda e: self._btn_code.config(bg=C["panel"]))

        self._text.bind("<KeyRelease>", self._on_keyrelease)

        styled_btn(bot, "[ delete ]", self._delete_entry, color=C["text"], small=True).pack(side="right", padx=6, pady=8)
        styled_btn(bot, "[ save entry ]", self._save_entry, color=C["accent"]).pack(side="right", padx=6, pady=8)

        self._set_date_label()

    # ── Placeholder ───────────────────────────────────────────────────────────
    def _clear_placeholder(self, e=None):
        if self._text.get("1.0", "end-1c") == self._placeholder:
            self._text.delete("1.0", "end")
            self._text.config(fg=C["text"])

    def _restore_placeholder(self, e=None):
        if not self._text.get("1.0", "end-1c").strip():
            self._text.insert("1.0", self._placeholder)
            self._text.config(fg=C["muted"])

    def _on_keyrelease(self, e=None):
        body = self._text.get("1.0", "end-1c")
        if body != self._placeholder:
            wc = len(body.split())
            self._lbl_chars.config(text=f"{wc} words")
            # crash recovery — persist draft on every keystroke
            if not self._selected_id:
                draft_save(
                    self._topic_entry.get(),
                    body,
                    self._mood.get(),
                    self._code_mode
                )

    # ── Date label ────────────────────────────────────────────────────────────
    def _set_date_label(self, ts=None):
        if ts is None:
            ts = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self._lbl_date.config(text=ts)

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _update_stats(self):
        streak = db_streak(self.con)
        total  = db_total(self.con)
        flame  = "🔥" if streak >= 3 else "📅"
        self._lbl_streak.config(text=f"{flame} {streak}-day streak")
        self._lbl_total.config(text=f"  |  {total} entries total")

        # Refresh topic combo
        topics = [""] + db_all_topics(self.con)
        self._topic_combo["values"] = topics

    # ── List ──────────────────────────────────────────────────────────────────
    def _refresh_list(self):
        q = self._search_var.get().strip()
        t = self._topic_var.get().strip()
        self._entries = db_search(self.con, q, t)

        self._listbox.delete(0, "end")
        # _index_map[listbox_line] = entry row  OR  None (date header)
        self._index_map = {}

        today     = date.today()
        yesterday = today - timedelta(days=1)
        last_date = None
        lb_idx    = 0

        for row in self._entries:
            row_date = date.fromisoformat(row["created"][:10])

            # ── Date header ───────────────────────────────────────────────
            if row_date != last_date:
                last_date = row_date
                if row_date == today:
                    label = "─── Today ─────────────────────"
                elif row_date == yesterday:
                    label = "─── Yesterday ─────────────────"
                else:
                    label = f"─── {row_date.strftime('%d %b %Y')} ─────────────"
                self._listbox.insert("end", label)
                self._listbox.itemconfig(lb_idx, fg=C["muted"], selectbackground=C["panel"],
                                         selectforeground=C["muted"])
                self._index_map[lb_idx] = None   # header → not selectable
                lb_idx += 1

            # ── Entry row ─────────────────────────────────────────────────
            mood_part  = row["mood"]
            time_part  = row["created"][11:16]           # HH:MM
            topic_part = row["topic"]
            if len(topic_part) > 18:
                topic_part = topic_part[:17] + "…"
            entry_label = f"  {mood_part} {time_part}  {topic_part}"
            self._listbox.insert("end", entry_label)
            self._index_map[lb_idx] = row
            lb_idx += 1

    # ── Code mode ─────────────────────────────────────────────────────────────
    def _toggle_code_mode(self):
        self._code_mode = not self._code_mode
        self._apply_code_mode()

    def _apply_code_mode(self):
        if self._code_mode:
            self._text.config(font=("Courier New", 11), tabs=("4c",))
            self._btn_code.config(fg=C["accent2"])
        else:
            self._text.config(font=FONT_BODY, tabs=(""))
            self._btn_code.config(fg=C["muted"])

    # ── Crash recovery ────────────────────────────────────────────────────────
    def _check_draft_recovery(self):
        draft = draft_load()
        if not draft or not draft.get("body", "").strip():
            return
        restore = messagebox.askyesno(
            APP_NAME,
            "⚡ Unsaved draft found from last session.\n\nRestore it?"
        )
        if restore:
            self._selected_id = None
            self._topic_entry.delete(0, "end")
            self._topic_entry.insert(0, draft.get("topic", ""))
            self._mood.set(draft.get("mood", "🟢"))
            self._code_mode = bool(draft.get("code_mode", False))
            self._apply_code_mode()
            self._text.config(fg=C["text"])
            self._text.delete("1.0", "end")
            self._text.insert("1.0", draft["body"])
            wc = len(draft["body"].split())
            self._lbl_chars.config(text=f"{wc} words")
        draft_clear()

    def _autosave(self):
        """Silently save the current editor state before switching entries."""
        body  = self._text.get("1.0", "end-1c").strip()
        topic = self._topic_entry.get().strip()
        mood  = self._mood.get()
        if not body or body == self._placeholder:
            return
        if self._selected_id:
            self.con.execute(
                "UPDATE entries SET topic=?, body=?, mood=?, code_mode=? WHERE id=?",
                (topic, body, mood, int(self._code_mode), self._selected_id)
            )
            self.con.commit()
        else:
            db_add(self.con, topic, body, mood, self._code_mode)
            draft_clear()
        self._refresh_list()
        self._update_stats()

    def _on_select(self, e=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        row = self._index_map.get(sel[0])
        if row is None:           # clicked a date header — deselect
            self._listbox.selection_clear(0, "end")
            return
        self._autosave()
        self._selected_id = row["id"]
        self._set_date_label(row["created"])
        self._topic_entry.delete(0, "end")
        self._topic_entry.insert(0, row["topic"])
        self._mood.set(row["mood"])
        self._code_mode = bool(row["code_mode"])
        self._apply_code_mode()
        self._text.config(fg=C["text"])
        self._text.delete("1.0", "end")
        self._text.insert("1.0", row["body"])
        wc = len(row["body"].split())
        self._lbl_chars.config(text=f"{wc} words")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _new_entry(self):
        self._autosave()
        self._selected_id = None
        self._set_date_label()
        self._topic_entry.delete(0, "end")
        self._mood.set("🟢")
        self._code_mode = False
        self._apply_code_mode()
        self._text.config(fg=C["muted"])
        self._text.delete("1.0", "end")
        self._text.insert("1.0", self._placeholder)
        self._lbl_chars.config(text="")
        self._listbox.selection_clear(0, "end")
        self._text.focus_set()
        self._clear_placeholder()

    def _save_entry(self):
        body  = self._text.get("1.0", "end-1c").strip()
        topic = self._topic_entry.get().strip()
        mood  = self._mood.get()

        if not body or body == self._placeholder:
            messagebox.showwarning(APP_NAME, "Nothing to save — write something first.")
            return

        if self._selected_id:
            self.con.execute(
                "UPDATE entries SET topic=?, body=?, mood=?, code_mode=? WHERE id=?",
                (topic, body, mood, int(self._code_mode), self._selected_id)
            )
            self.con.commit()
        else:
            db_add(self.con, topic, body, mood, self._code_mode)
            self._selected_id = None
            draft_clear()

        self._refresh_list()
        self._update_stats()
        self._flash_saved()

    def _delete_entry(self):
        if not self._selected_id:
            messagebox.showinfo(APP_NAME, "Select an entry to delete.")
            return
        if messagebox.askyesno(APP_NAME, "Delete this entry permanently?"):
            db_delete(self.con, self._selected_id)
            self._new_entry()
            self._refresh_list()
            self._update_stats()

    def _export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile=f"learnlog_{date.today()}.txt"
        )
        if path:
            db_export(self.con, path)
            messagebox.showinfo(APP_NAME, f"Exported to:\n{path}")

    def _flash_saved(self):
        orig = self._lbl_chars.cget("text")
        self._lbl_chars.config(text="✓ saved", fg=C["accent"])
        self.after(1400, lambda: self._lbl_chars.config(
            text=orig, fg=C["muted"]))

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def on_close(self):
        self.con.close()
        self.destroy()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = LearnLog()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()