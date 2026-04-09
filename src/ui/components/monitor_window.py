from __future__ import annotations

import json
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from ..adapters.runtime_monitor_adapter import MonitorEventRecord, MonitorSnapshot
from ..helpers.monitor_helper_service import MonitorHelperResult, MonitorHelperService
from ..helpers.monitor_settings_store import (
    MonitorActionSettings,
    MonitorSettings,
    MonitorSettingsStore,
)


@dataclass(frozen=True, slots=True)
class MonitorContext:
    label: str
    text: str
    context_type: str
    full_text: str
    selection_text: str = ""


class MonitorWindow:
    """Tkinter operator window for grouped runtime monitoring."""

    _BACKGROUND = "#071525"
    _PANEL = "#0f2740"
    _PANEL_ALT = "#12304d"
    _TEXT = "#d6f4ff"
    _CYAN = "#33d8ff"
    _YELLOW = "#ffd166"
    _ERROR = "#ff6b6b"

    def __init__(
        self,
        helper_service: MonitorHelperService,
        settings_store: MonitorSettingsStore,
    ) -> None:
        self._helper_service = helper_service
        self._settings_store = settings_store
        self._settings = settings_store.load()
        self._root: tk.Tk | None = None
        self._snapshot_provider: Callable[[], MonitorSnapshot] | None = None
        self._treeviews: dict[str, ttk.Treeview] = {}
        self._event_index: dict[str, MonitorEventRecord] = {}
        self._registry_labels: dict[str, tk.Label] = {}
        self._status_label: tk.Label | None = None
        self._detail_text: tk.Text | None = None
        self._log_text: tk.Text | None = None
        self._notebook: ttk.Notebook | None = None
        self._context_menu: tk.Menu | None = None
        self._pending_context: MonitorContext | None = None
        self._widget_groups: dict[str, str] = {}
        self._last_popup_xy: tuple[int, int] | None = None
        self._active_modal: tk.Toplevel | None = None
        self._available_models: list[str] = []

    def run(
        self,
        *,
        title: str,
        snapshot_provider: Callable[[], MonitorSnapshot],
        refresh_ms: int = 1000,
    ) -> int:
        self._snapshot_provider = snapshot_provider
        root = tk.Tk()
        self._root = root
        root.title(title)
        root.geometry("1420x900")
        root.configure(background=self._BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        self._configure_styles()
        self._build_layout()
        self._refresh(refresh_ms=refresh_ms)
        root.mainloop()
        return 0

    def _configure_styles(self) -> None:
        assert self._root is not None
        style = ttk.Style(self._root)
        style.theme_use("clam")
        style.configure(
            "Monitor.TNotebook",
            background=self._BACKGROUND,
            borderwidth=0,
        )
        style.configure(
            "Monitor.TNotebook.Tab",
            background=self._PANEL,
            foreground=self._CYAN,
            padding=(10, 6),
        )
        style.map(
            "Monitor.TNotebook.Tab",
            background=[("selected", self._PANEL_ALT)],
            foreground=[("selected", self._YELLOW)],
        )
        style.configure(
            "Monitor.Treeview",
            background=self._PANEL,
            fieldbackground=self._PANEL,
            foreground=self._TEXT,
            rowheight=22,
            borderwidth=0,
        )
        style.configure(
            "Monitor.Treeview.Heading",
            background=self._PANEL_ALT,
            foreground=self._YELLOW,
            relief="flat",
        )
        style.map(
            "Monitor.Treeview",
            background=[("selected", self._PANEL_ALT)],
            foreground=[("selected", self._YELLOW)],
        )

    def _build_layout(self) -> None:
        assert self._root is not None
        self._context_menu = tk.Menu(self._root, tearoff=0, bg=self._PANEL, fg=self._TEXT)
        self._context_menu.add_command(label="Summarize", command=self._open_summarize_modal)
        self._context_menu.add_command(label="Ask About", command=self._open_ask_modal)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Settings", command=self._open_settings_modal)

        top_frame = tk.Frame(self._root, bg=self._BACKGROUND)
        top_frame.pack(fill="x", padx=12, pady=(12, 6))

        title_label = tk.Label(
            top_frame,
            text="UsefulHELPER MCP Monitor",
            bg=self._BACKGROUND,
            fg=self._CYAN,
            font=("Consolas", 18, "bold"),
        )
        title_label.pack(anchor="w")

        registry_frame = tk.Frame(self._root, bg=self._BACKGROUND)
        registry_frame.pack(fill="x", padx=12, pady=(0, 8))
        for group in ("requests", "workspace", "execution", "inference", "memory", "other"):
            label = tk.Label(
                registry_frame,
                text=f"{group}: idle",
                bg=self._PANEL,
                fg=self._TEXT,
                font=("Consolas", 10),
                padx=10,
                pady=8,
                relief="ridge",
                bd=1,
            )
            label.pack(side="left", padx=(0, 8))
            self._registry_labels[group] = label

        main_pane = tk.PanedWindow(
            self._root,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            bg=self._BACKGROUND,
            bd=0,
        )
        main_pane.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        left_frame = tk.Frame(main_pane, bg=self._BACKGROUND)
        right_frame = tk.Frame(main_pane, bg=self._BACKGROUND)
        main_pane.add(left_frame, stretch="always", minsize=760)
        main_pane.add(right_frame, minsize=540)

        notebook = ttk.Notebook(left_frame, style="Monitor.TNotebook")
        notebook.pack(fill="both", expand=True)
        self._notebook = notebook
        for group in ("requests", "workspace", "execution", "inference", "memory", "other"):
            tab = tk.Frame(notebook, bg=self._BACKGROUND)
            notebook.add(tab, text=group.title())
            tree = ttk.Treeview(
                tab,
                columns=("time", "action", "summary"),
                show="headings",
                style="Monitor.Treeview",
            )
            tree.heading("time", text="Time")
            tree.heading("action", text="Action")
            tree.heading("summary", text="Summary")
            tree.column("time", width=90, stretch=False)
            tree.column("action", width=220, stretch=False)
            tree.column("summary", width=420, stretch=True)
            tree.pack(fill="both", expand=True)
            tree.bind("<<TreeviewSelect>>", self._on_select_event)
            tree.bind("<Button-3>", self._on_tree_right_click)
            self._treeviews[group] = tree
            self._widget_groups[str(tree)] = group

        detail_header = tk.Label(
            right_frame,
            text="Selected Event Detail",
            bg=self._BACKGROUND,
            fg=self._YELLOW,
            anchor="w",
            font=("Consolas", 12, "bold"),
        )
        detail_header.pack(fill="x", pady=(0, 6))
        self._detail_text = tk.Text(
            right_frame,
            bg=self._PANEL,
            fg=self._TEXT,
            insertbackground=self._YELLOW,
            wrap="word",
            font=("Consolas", 10),
        )
        self._detail_text.pack(fill="both", expand=True)
        self._detail_text.bind("<Button-3>", self._on_text_right_click)

        log_header = tk.Label(
            self._root,
            text="App Log Tail",
            bg=self._BACKGROUND,
            fg=self._YELLOW,
            anchor="w",
            font=("Consolas", 12, "bold"),
        )
        log_header.pack(fill="x", padx=12)
        self._log_text = tk.Text(
            self._root,
            height=10,
            bg=self._PANEL,
            fg=self._TEXT,
            insertbackground=self._YELLOW,
            wrap="none",
            font=("Consolas", 9),
        )
        self._log_text.pack(fill="x", padx=12, pady=(4, 8))
        self._log_text.bind("<Button-3>", self._on_text_right_click)

        self._status_label = tk.Label(
            self._root,
            text="Waiting for runtime events...",
            bg=self._BACKGROUND,
            fg=self._CYAN,
            anchor="w",
            font=("Consolas", 10),
        )
        self._status_label.pack(fill="x", padx=12, pady=(0, 12))

    def _refresh(self, *, refresh_ms: int) -> None:
        if self._root is None or self._snapshot_provider is None:
            return
        snapshot = self._snapshot_provider()
        self._apply_snapshot(snapshot)
        self._root.after(refresh_ms, lambda: self._refresh(refresh_ms=refresh_ms))

    def _apply_snapshot(self, snapshot: MonitorSnapshot) -> None:
        selected_event_id = self._current_selection_id()
        self._event_index = {}

        for entry in snapshot.registry:
            label = self._registry_labels[entry.group]
            accent = self._ERROR if entry.last_action.endswith("error") else self._TEXT
            label.configure(
                text=(
                    f"{entry.group}: {entry.recent_count} recent\n"
                    f"{entry.last_action}"
                ),
                fg=accent,
            )

        for group, tree in self._treeviews.items():
            for item in tree.get_children():
                tree.delete(item)
            for record in snapshot.events_by_group.get(group, []):
                item_id = f"{group}:{record.event_id}"
                time_label = self._short_time(record.dispatched_at)
                tree.insert(
                    "",
                    "end",
                    iid=item_id,
                    values=(time_label, record.action, record.summary),
                    tags=("error",) if record.is_error else (),
                )
                if record.is_error:
                    tree.tag_configure("error", foreground=self._ERROR)
                self._event_index[item_id] = record

        if selected_event_id in self._event_index:
            self._show_record(self._event_index[selected_event_id])
            group_name = selected_event_id.split(":", 1)[0]
            self._treeviews[group_name].selection_set(selected_event_id)
        elif self._detail_text is not None:
            self._detail_text.delete("1.0", tk.END)

        if self._log_text is not None:
            self._log_text.delete("1.0", tk.END)
            self._log_text.insert("1.0", "\n".join(snapshot.log_tail))

        if self._status_label is not None:
            latest = snapshot.latest_event_id if snapshot.latest_event_id is not None else "-"
            self._status_label.configure(
                text=(
                    f"total_events={snapshot.total_event_count} "
                    f"latest_event_id={latest} "
                    f"settings={self._settings_store.settings_path.name}"
                )
            )

    def _current_selection_id(self) -> str | None:
        for tree in self._treeviews.values():
            selection = tree.selection()
            if selection:
                return str(selection[0])
        return None

    def _on_select_event(self, event) -> None:  # noqa: ANN001
        tree = event.widget
        selection = tree.selection()
        if not selection:
            return
        record = self._event_index.get(str(selection[0]))
        if record is None:
            return
        self._show_record(record)

    def _show_record(self, record: MonitorEventRecord) -> None:
        if self._detail_text is None:
            return
        payload_text = json.dumps(record.payload, indent=2, sort_keys=True)
        response_text = json.dumps(record.response, indent=2, sort_keys=True)
        detail = "\n".join(
            [
                f"id: {record.event_id}",
                f"time: {record.dispatched_at}",
                f"group: {record.group}",
                f"action: {record.action}",
                f"sender: {record.sender}",
                f"target: {record.target}",
                f"summary: {record.summary}",
                f"is_error: {record.is_error}",
                "",
                "payload:",
                payload_text,
                "",
                "response:",
                response_text,
            ]
        )
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", detail)

    def _on_tree_right_click(self, event) -> None:  # noqa: ANN001
        tree = event.widget
        row_id = tree.identify_row(event.y)
        if row_id:
            tree.selection_set(row_id)
            tree.focus(row_id)
        group = self._widget_groups.get(str(tree), "other")
        self._pending_context = self._build_tree_context(group, tree)
        self._show_context_menu(event)

    def _on_text_right_click(self, event) -> None:  # noqa: ANN001
        widget = event.widget
        label = "detail panel" if widget is self._detail_text else "log panel"
        self._pending_context = self._build_text_context(widget, label)
        self._show_context_menu(event)

    def _show_context_menu(self, event) -> None:  # noqa: ANN001
        if self._context_menu is None:
            return
        self._last_popup_xy = (int(event.x_root), int(event.y_root))
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _build_tree_context(self, group: str, tree: ttk.Treeview) -> MonitorContext:
        selection = tree.selection()
        if selection:
            record = self._event_index.get(str(selection[0]))
            if record is not None:
                detail_text = "\n".join(
                    [
                        f"group: {record.group}",
                        f"time: {record.dispatched_at}",
                        f"action: {record.action}",
                        f"summary: {record.summary}",
                        "",
                        "payload:",
                        json.dumps(record.payload, indent=2, sort_keys=True),
                        "",
                        "response:",
                        json.dumps(record.response, indent=2, sort_keys=True),
                    ]
                )
                return MonitorContext(
                    label=f"{group} selected event",
                    text=detail_text,
                    context_type="event_record",
                    full_text=detail_text,
                    selection_text=detail_text,
                )

        rows: list[str] = []
        for item_id in tree.get_children():
            values = tree.item(item_id, "values")
            if not values:
                continue
            rows.append(" | ".join(str(value) for value in values))
        if not rows:
            rows = [f"No visible rows in {group}."]
        return MonitorContext(
            label=f"{group} panel",
            text="\n".join(rows),
            context_type="event_panel",
            full_text="\n".join(rows),
        )

    def _build_text_context(self, widget: tk.Text, label: str) -> MonitorContext:
        selected_text = self._get_selected_text(widget)
        full_text = widget.get("1.0", tk.END).strip()
        if selected_text.strip():
            return MonitorContext(
                label=f"{label} selected text",
                text=selected_text,
                context_type="log_panel" if widget is self._log_text else "text_panel",
                full_text=full_text,
                selection_text=selected_text,
            )
        return MonitorContext(
            label=label,
            text=full_text,
            context_type="log_panel" if widget is self._log_text else "text_panel",
            full_text=full_text,
        )

    def _get_selected_text(self, widget: tk.Text) -> str:
        try:
            return widget.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def _open_summarize_modal(self) -> None:
        if self._pending_context is None:
            self._pending_context = self._default_context()
        self._open_helper_modal(
            title="Summarize Panel",
            context=self._pending_context,
            action="summarize",
        )

    def _open_ask_modal(self) -> None:
        if self._pending_context is None:
            self._pending_context = self._default_context()
        self._open_helper_modal(
            title="Ask About Panel",
            context=self._pending_context,
            action="ask_about",
        )

    def _default_context(self) -> MonitorContext:
        if self._detail_text is not None:
            text = self._detail_text.get("1.0", tk.END).strip()
            if text:
                return MonitorContext(
                    label="detail panel",
                    text=text,
                    context_type="text_panel",
                    full_text=text,
                )
        if self._log_text is not None:
            log_text = self._log_text.get("1.0", tk.END).strip()
            return MonitorContext(
                label="log panel",
                text=log_text,
                context_type="log_panel",
                full_text=log_text,
            )
        return MonitorContext(
            label="monitor",
            text="No current monitor context.",
            context_type="panel",
            full_text="No current monitor context.",
        )

    def _open_helper_modal(
        self,
        *,
        title: str,
        context: MonitorContext,
        action: str,
    ) -> None:
        if self._root is None:
            return
        self._close_active_modal()
        modal = tk.Toplevel(self._root)
        self._active_modal = modal
        modal.title(title)
        modal.configure(bg=self._BACKGROUND)
        modal.geometry("820x720" if action == "ask_about" else "820x660")
        modal.minsize(720, 560)
        modal.transient(self._root)
        modal.grab_set()
        modal.protocol("WM_DELETE_WINDOW", self._close_active_modal)
        self._position_modal(modal)

        header = tk.Label(
            modal,
            text=f"{title} | {context.label}",
            bg=self._BACKGROUND,
            fg=self._CYAN,
            font=("Consolas", 12, "bold"),
            anchor="w",
        )
        header.pack(fill="x", padx=12, pady=(12, 6))

        body_frame = tk.Frame(modal, bg=self._BACKGROUND)
        body_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        footer_frame = tk.Frame(body_frame, bg=self._BACKGROUND)
        footer_frame.pack(side="bottom", fill="x", pady=(10, 0))

        content_frame = tk.Frame(body_frame, bg=self._BACKGROUND)
        content_frame.pack(side="top", fill="both", expand=True)

        settings = (
            self._settings.summarize
            if action == "summarize"
            else self._settings.ask_about
        )

        controls_frame = tk.Frame(content_frame, bg=self._BACKGROUND)
        controls_frame.pack(fill="x", pady=(0, 8))

        model_label = tk.Label(
            controls_frame,
            text="Model",
            bg=self._BACKGROUND,
            fg=self._YELLOW,
            anchor="w",
            font=("Consolas", 10, "bold"),
        )
        model_label.pack(side="left")

        model_box = ttk.Combobox(
            controls_frame,
            font=("Consolas", 10),
            state="normal",
            width=28,
            values=self._available_models,
        )
        model_box.pack(side="left", padx=(8, 8))
        model_box.set(settings.model)

        refresh_button = tk.Button(
            controls_frame,
            text="Refresh Models",
            bg=self._PANEL_ALT,
            fg=self._YELLOW,
            activebackground=self._PANEL,
            activeforeground=self._YELLOW,
        )
        refresh_button.pack(side="left")

        context_box = tk.Text(
            content_frame,
            height=12,
            bg=self._PANEL,
            fg=self._TEXT,
            wrap="word",
            font=("Consolas", 9),
        )
        context_box.pack(fill="x")
        context_box.insert("1.0", context.text)
        context_box.configure(state="disabled")

        question_box: tk.Text | None = None
        memory_status_label: tk.Label | None = None
        conversation_summary_holder = {"value": ""}
        recent_turns: list[dict[str, str]] = []
        if action == "ask_about":
            question_label = tk.Label(
                content_frame,
                text="Question",
                bg=self._BACKGROUND,
                fg=self._YELLOW,
                anchor="w",
                font=("Consolas", 11, "bold"),
            )
            question_label.pack(fill="x", pady=(10, 4))
            question_box = tk.Text(
                content_frame,
                height=4,
                bg=self._PANEL_ALT,
                fg=self._TEXT,
                insertbackground=self._YELLOW,
                wrap="word",
                font=("Consolas", 10),
            )
            question_box.pack(fill="x")
            memory_status_label = tk.Label(
                content_frame,
                text="Conversation memory: 0 summarized chars | 0 live turns",
                bg=self._BACKGROUND,
                fg=self._CYAN,
                anchor="w",
                font=("Consolas", 9),
            )
            memory_status_label.pack(fill="x", pady=(8, 0))

        status_label = tk.Label(
            content_frame,
            text="Ready.",
            bg=self._BACKGROUND,
            fg=self._CYAN,
            anchor="w",
            font=("Consolas", 10),
        )
        status_label.pack(fill="x", pady=(10, 4))

        result_box = tk.Text(
            content_frame,
            bg=self._PANEL,
            fg=self._TEXT,
            insertbackground=self._YELLOW,
            wrap="word",
            font=("Consolas", 10),
        )
        result_box.pack(fill="both", expand=True)

        def refresh_models() -> None:
            status_label.configure(text="Refreshing model list...", fg=self._YELLOW)
            refresh_button.configure(state="disabled")

            def worker_refresh() -> None:
                try:
                    models = self._helper_service.list_models()
                except Exception as error:  # noqa: BLE001
                    if self._root is not None:
                        self._root.after(
                            0,
                            lambda error=error: (
                                refresh_button.configure(state="normal"),
                                status_label.configure(text=self._format_error(error), fg=self._ERROR),
                            ),
                        )
                    return

                if self._root is not None:
                    self._root.after(
                        0,
                        lambda models=models: self._apply_modal_model_refresh(
                            model_box=model_box,
                            models=models,
                            refresh_button=refresh_button,
                            status_label=status_label,
                            fallback_model=settings.model,
                        ),
                    )

            threading.Thread(target=worker_refresh, daemon=True).start()

        refresh_button.configure(command=refresh_models)

        def run_action() -> None:
            status_label.configure(text="Working with local model...", fg=self._YELLOW)
            result_box.delete("1.0", tk.END)
            question_text = ""
            if question_box is not None:
                question_text = question_box.get("1.0", tk.END).strip()
                if not question_text:
                    status_label.configure(text="Enter a question first.", fg=self._ERROR)
                    return

            effective_settings = MonitorActionSettings(
                model=model_box.get().strip() or settings.model,
                instructions=settings.instructions,
            )
            context_packet = self._helper_service.build_context_packet(
                context_label=context.label,
                context_text=context.text,
                context_type=context.context_type,
                full_visible_text=context.full_text,
                selection_text=context.selection_text,
            )

            def worker() -> None:
                try:
                    if action == "summarize":
                        result = self._helper_service.summarize(
                            context_label=context.label,
                            context_text=context.text,
                            settings=effective_settings,
                            context_packet=context_packet,
                        )
                    else:
                        result = self._helper_service.ask_about(
                            context_label=context.label,
                            context_text=context.text,
                            question=question_text,
                            settings=effective_settings,
                            context_packet=context_packet,
                            conversation_summary=conversation_summary_holder["value"],
                            recent_turns=recent_turns,
                        )
                except Exception as error:  # noqa: BLE001
                    if self._root is not None:
                        error_text = self._format_error(error)
                        self._root.after(
                            0,
                            lambda error_text=error_text: status_label.configure(
                                text=error_text,
                                fg=self._ERROR,
                            ),
                        )
                    return

                if self._root is not None:
                    self._root.after(
                        0,
                        lambda result=result, question_text=question_text: self._apply_helper_result(
                            status_label=status_label,
                            result_box=result_box,
                            result=result,
                            action=action,
                            memory_status_label=memory_status_label,
                            conversation_summary_holder=conversation_summary_holder,
                            recent_turns_ref=recent_turns,
                            question_text=question_text,
                        ),
                    )

            threading.Thread(target=worker, daemon=True).start()

        action_label = "Summarize" if action == "summarize" else "Ask"
        tk.Button(
            footer_frame,
            text=action_label,
            command=run_action,
            bg=self._PANEL_ALT,
            fg=self._YELLOW,
            activebackground=self._PANEL,
            activeforeground=self._YELLOW,
        ).pack(side="left")
        tk.Button(
            footer_frame,
            text="Close",
            command=self._close_active_modal,
            bg=self._PANEL_ALT,
            fg=self._TEXT,
            activebackground=self._PANEL,
            activeforeground=self._TEXT,
        ).pack(side="right")

        refresh_models()
        if action == "summarize":
            run_action()

    def _show_helper_result(
        self,
        *,
        status_label: tk.Label,
        result_box: tk.Text,
        result: MonitorHelperResult,
    ) -> None:
        status_label.configure(
            text=f"Done with {result.model}.",
            fg=self._CYAN,
        )
        result_box.delete("1.0", tk.END)
        footer = (
            f"\n\n[model={result.model} prompt_eval={result.prompt_eval_count} "
            f"eval={result.eval_count} duration={result.total_duration}]"
        )
        result_box.insert("1.0", result.content + footer)

    def _apply_helper_result(
        self,
        *,
        status_label: tk.Label,
        result_box: tk.Text,
        result: MonitorHelperResult,
        action: str,
        memory_status_label: tk.Label | None,
        conversation_summary_holder: dict[str, str],
        recent_turns_ref: list[dict[str, str]],
        question_text: str,
    ) -> None:
        self._show_helper_result(
            status_label=status_label,
            result_box=result_box,
            result=result,
        )
        if action != "ask_about":
            return

        recent_turns_ref.append(
            {
                "question": question_text,
                "answer": result.content,
            }
        )
        summary, turns = self._helper_service.roll_conversation_window(
            conversation_summary=conversation_summary_holder["value"],
            recent_turns=recent_turns_ref,
        )
        conversation_summary_holder["value"] = summary
        recent_turns_ref[:] = turns
        if memory_status_label is not None:
            memory_status_label.configure(
                text=(
                    "Conversation memory: "
                    f"{len(conversation_summary_holder['value'])} summarized chars | "
                    f"{len(recent_turns_ref)} live turns"
                ),
                fg=self._CYAN,
            )

    def _open_settings_modal(self) -> None:
        if self._root is None:
            return
        self._close_active_modal()
        modal = tk.Toplevel(self._root)
        self._active_modal = modal
        modal.title("Monitor Helper Settings")
        modal.configure(bg=self._BACKGROUND)
        modal.geometry("860x620")
        modal.minsize(760, 540)
        modal.transient(self._root)
        modal.grab_set()
        modal.protocol("WM_DELETE_WINDOW", self._close_active_modal)
        self._position_modal(modal)

        header = tk.Label(
            modal,
            text="Monitor Helper Settings",
            bg=self._BACKGROUND,
            fg=self._CYAN,
            font=("Consolas", 13, "bold"),
            anchor="w",
        )
        header.pack(fill="x", padx=12, pady=(12, 8))

        action_inputs: dict[str, tuple[tk.Entry, tk.Text]] = {}
        model_boxes: dict[str, ttk.Combobox] = {}

        controls_frame = tk.Frame(modal, bg=self._BACKGROUND)
        controls_frame.pack(fill="x", padx=12, pady=(0, 8))

        status_label = tk.Label(
            controls_frame,
            text=str(self._settings_store.settings_path),
            bg=self._BACKGROUND,
            fg=self._CYAN,
            anchor="w",
            font=("Consolas", 10),
        )
        status_label.pack(side="left", fill="x", expand=True)

        refresh_button = tk.Button(
            controls_frame,
            text="Refresh Models",
            bg=self._PANEL_ALT,
            fg=self._YELLOW,
            activebackground=self._PANEL,
            activeforeground=self._YELLOW,
        )
        refresh_button.pack(side="right")

        for action_name, action_settings in (
            ("summarize", self._settings.summarize),
            ("ask_about", self._settings.ask_about),
        ):
            frame = tk.Frame(modal, bg=self._PANEL, bd=1, relief="ridge")
            frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

            title = tk.Label(
                frame,
                text=action_name.replace("_", " ").title(),
                bg=self._PANEL,
                fg=self._YELLOW,
                font=("Consolas", 11, "bold"),
                anchor="w",
            )
            title.pack(fill="x", padx=10, pady=(8, 6))

            model_label = tk.Label(
                frame,
                text="Model",
                bg=self._PANEL,
                fg=self._CYAN,
                anchor="w",
                font=("Consolas", 10),
            )
            model_label.pack(fill="x", padx=10)
            model_box = ttk.Combobox(
                frame,
                font=("Consolas", 10),
                state="normal",
            )
            model_box.pack(fill="x", padx=10, pady=(2, 8))
            model_box.set(action_settings.model)
            model_boxes[action_name] = model_box

            instruction_label = tk.Label(
                frame,
                text="Role / Instructions",
                bg=self._PANEL,
                fg=self._CYAN,
                anchor="w",
                font=("Consolas", 10),
            )
            instruction_label.pack(fill="x", padx=10)
            instruction_box = tk.Text(
                frame,
                height=8,
                bg=self._PANEL_ALT,
                fg=self._TEXT,
                insertbackground=self._YELLOW,
                wrap="word",
                font=("Consolas", 10),
            )
            instruction_box.pack(fill="both", expand=True, padx=10, pady=(2, 10))
            instruction_box.insert("1.0", action_settings.instructions)
            action_inputs[action_name] = (model_box, instruction_box)

        button_frame = tk.Frame(modal, bg=self._BACKGROUND)
        button_frame.pack(fill="x", padx=12, pady=(0, 12))

        def refresh_models() -> None:
            status_label.configure(text="Refreshing model list...", fg=self._YELLOW)
            refresh_button.configure(state="disabled")

            def worker() -> None:
                try:
                    models = self._helper_service.list_models()
                except Exception as error:  # noqa: BLE001
                    if self._root is not None:
                        self._root.after(
                            0,
                            lambda: (
                                refresh_button.configure(state="normal"),
                                status_label.configure(text=self._format_error(error), fg=self._ERROR),
                            ),
                        )
                    return

                if self._root is not None:
                    self._root.after(
                        0,
                        lambda models=models: self._apply_model_refresh(
                            model_boxes=model_boxes,
                            models=models,
                            refresh_button=refresh_button,
                            status_label=status_label,
                        ),
                    )

            threading.Thread(target=worker, daemon=True).start()

        refresh_button.configure(command=refresh_models)

        def save_settings() -> None:
            summarize_model, summarize_instructions = action_inputs["summarize"]
            ask_model, ask_instructions = action_inputs["ask_about"]
            new_settings = MonitorSettings(
                summarize=MonitorActionSettings(
                    model=summarize_model.get().strip() or self._settings.summarize.model,
                    instructions=(
                        summarize_instructions.get("1.0", tk.END).strip()
                        or self._settings.summarize.instructions
                    ),
                ),
                ask_about=MonitorActionSettings(
                    model=ask_model.get().strip() or self._settings.ask_about.model,
                    instructions=(
                        ask_instructions.get("1.0", tk.END).strip()
                        or self._settings.ask_about.instructions
                    ),
                ),
            )
            self._settings_store.save(new_settings)
            self._settings = new_settings
            status_label.configure(text=f"Saved to {self._settings_store.settings_path}", fg=self._YELLOW)

        tk.Button(
            button_frame,
            text="Save",
            command=save_settings,
            bg=self._PANEL_ALT,
            fg=self._YELLOW,
            activebackground=self._PANEL,
            activeforeground=self._YELLOW,
        ).pack(side="left")
        tk.Button(
            button_frame,
            text="Close",
            command=self._close_active_modal,
            bg=self._PANEL_ALT,
            fg=self._TEXT,
            activebackground=self._PANEL,
            activeforeground=self._TEXT,
        ).pack(side="right")

        refresh_models()

    def _short_time(self, timestamp: str) -> str:
        if "T" not in timestamp:
            return timestamp[-8:]
        time_part = timestamp.split("T", 1)[1]
        return time_part[:8]

    def _position_modal(self, modal: tk.Toplevel) -> None:
        if self._root is None:
            return
        modal.update_idletasks()
        width = modal.winfo_width()
        height = modal.winfo_height()
        screen_width = modal.winfo_screenwidth()
        screen_height = modal.winfo_screenheight()
        if self._last_popup_xy is None:
            root_x = self._root.winfo_rootx() + 40
            root_y = self._root.winfo_rooty() + 40
        else:
            root_x, root_y = self._last_popup_xy
        x = min(max(root_x + 8, 0), max(screen_width - width - 20, 0))
        y = min(max(root_y + 8, 0), max(screen_height - height - 60, 0))
        modal.geometry(f"+{x}+{y}")

    def _close_active_modal(self) -> None:
        if self._active_modal is not None and self._active_modal.winfo_exists():
            try:
                self._active_modal.grab_release()
            except tk.TclError:
                pass
            self._active_modal.destroy()
        self._active_modal = None

    def _format_error(self, error: Exception) -> str:
        message = str(error).strip()
        if not message or message == "None":
            return f"{error.__class__.__name__}: helper request failed."
        return message

    def _apply_model_refresh(
        self,
        *,
        model_boxes: dict[str, ttk.Combobox],
        models: list[str],
        refresh_button: tk.Button,
        status_label: tk.Label,
    ) -> None:
        self._available_models = list(models)
        for action_name, model_box in model_boxes.items():
            current_value = model_box.get().strip()
            model_box.configure(values=models)
            if current_value:
                model_box.set(current_value)
            elif models:
                fallback = (
                    self._settings.summarize.model
                    if action_name == "summarize"
                    else self._settings.ask_about.model
                )
                model_box.set(fallback if fallback in models else models[0])
        refresh_button.configure(state="normal")
        if models:
            status_label.configure(
                text=f"Loaded {len(models)} local models from Ollama.",
                fg=self._CYAN,
            )
        else:
            status_label.configure(
                text="No local models were returned by Ollama.",
                fg=self._ERROR,
            )

    def _apply_modal_model_refresh(
        self,
        *,
        model_box: ttk.Combobox,
        models: list[str],
        refresh_button: tk.Button,
        status_label: tk.Label,
        fallback_model: str,
    ) -> None:
        self._available_models = list(models)
        current_value = model_box.get().strip()
        model_box.configure(values=models)
        if current_value:
            model_box.set(current_value)
        elif models:
            model_box.set(fallback_model if fallback_model in models else models[0])
        refresh_button.configure(state="normal")
        if models:
            status_label.configure(
                text=f"Loaded {len(models)} local models from Ollama.",
                fg=self._CYAN,
            )
        else:
            status_label.configure(
                text="No local models were returned by Ollama.",
                fg=self._ERROR,
            )
