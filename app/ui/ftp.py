""" Simple FTP client module. """
import subprocess
from collections import namedtuple
from datetime import datetime
from enum import IntEnum
from ftplib import all_errors
from pathlib import Path
from shutil import rmtree
from urllib.parse import urlparse, unquote

from gi.repository import GLib

from app.commons import log, run_task, run_idle
from app.connections import UtfFTP
from app.ui.dialogs import show_dialog, DialogType, get_builder
from app.ui.main_helper import on_popup_menu
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, KeyboardKey, MOD_MASK

File = namedtuple("File", ["icon", "name", "size", "date", "attr", "extra"])


class FtpClientBox(Gtk.HBox):
    """ Simple FTP client base class. """
    ROOT = ".."
    FOLDER = "<Folder>"
    LINK = "<Link>"
    MAX_SIZE = 10485760  # 10 MB file limit
    URI_SEP = "::::"

    class Column(IntEnum):
        ICON = 0
        NAME = 1
        SIZE = 2
        DATE = 3
        ATTR = 4
        EXTRA = 5

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_spacing(2)
        self.set_orientation(Gtk.Orientation.VERTICAL)

        self._app = app
        self._settings = settings
        self._ftp = None
        self._select_enabled = True

        handlers = {"on_connect": self.on_connect,
                    "on_disconnect": self.on_disconnect,
                    "on_ftp_row_activated": self.on_ftp_row_activated,
                    "on_file_row_activated": self.on_file_row_activated,
                    "on_ftp_edit": self.on_ftp_edit,
                    "on_ftp_edited": self.on_ftp_edited,
                    "on_file_edit": self.on_file_edit,
                    "on_file_edited": self.on_file_edited,
                    "on_file_remove": self.on_file_remove,
                    "on_ftp_remove": self.on_ftp_file_remove,
                    "on_file_create_folder": self.on_file_create_folder,
                    "on_ftp_create_folder": self.on_ftp_create_folder,
                    "on_view_drag_begin": self.on_view_drag_begin,
                    "on_ftp_drag_data_get": self.on_ftp_drag_data_get,
                    "on_ftp_drag_data_received": self.on_ftp_drag_data_received,
                    "on_file_drag_data_get": self.on_file_drag_data_get,
                    "on_file_drag_data_received": self.on_file_drag_data_received,
                    "on_view_drag_end": self.on_view_drag_end,
                    "on_view_popup_menu": on_popup_menu,
                    "on_view_key_press": self.on_view_key_press,
                    "on_view_press": self.on_view_press,
                    "on_view_release": self.on_view_release}

        builder = get_builder(UI_RESOURCES_PATH + "ftp.glade", handlers)

        self.add(builder.get_object("main_frame"))
        self._ftp_info_label = builder.get_object("ftp_info_label")
        self._ftp_view = builder.get_object("ftp_view")
        self._ftp_model = builder.get_object("ftp_list_store")
        self._ftp_name_renderer = builder.get_object("ftp_name_column_renderer")
        self._file_view = builder.get_object("file_view")
        self._file_model = builder.get_object("file_list_store")
        self._file_name_renderer = builder.get_object("file_name_column_renderer")
        # Buttons
        self._connect_button = builder.get_object("connect_button")
        disconnect_button = builder.get_object("disconnect_button")
        disconnect_button.bind_property("visible", builder.get_object("ftp_create_folder_menu_item"), "sensitive")
        disconnect_button.bind_property("visible", builder.get_object("ftp_edit_menu_item"), "sensitive")
        disconnect_button.bind_property("visible", builder.get_object("ftp_remove_menu_item"), "sensitive")
        self._connect_button.bind_property("visible", builder.get_object("disconnect_button"), "visible", 4)
        # Force Ctrl
        self._ftp_view.connect("key-press-event", self._app.force_ctrl)
        self._file_view.connect("key-press-event", self._app.force_ctrl)
        # Icons
        theme = Gtk.IconTheme.get_default()
        folder_icon = "folder-symbolic" if settings.is_darwin else "folder"
        self._folder_icon = theme.load_icon(folder_icon, 16, 0) if theme.lookup_icon(folder_icon, 16, 0) else None
        self._link_icon = theme.load_icon("emblem-symbolic-link", 16, 0) if theme.lookup_icon("emblem-symbolic-link",
                                                                                              16, 0) else None
        # Initialization
        self.init_drag_and_drop()
        self.init_ftp()
        self.init_file_data()
        self.show()

    @run_task
    def init_ftp(self):
        GLib.idle_add(self._ftp_model.clear)
        try:
            if self._ftp:
                self._ftp.close()

            self._ftp = UtfFTP(host=self._settings.host, user=self._settings.user, passwd=self._settings.password)
            self._ftp.encoding = "utf-8"
            self.update_ftp_info(self._ftp.getwelcome())
        except all_errors as e:
            self.update_ftp_info(str(e))
            self.on_disconnect()
        else:
            self.init_ftp_data()

    @run_task
    def init_ftp_data(self, path=None):
        if not self._ftp:
            return

        if path:
            try:
                self._ftp.cwd(path)
            except all_errors as e:
                self.update_ftp_info(str(e))

        files = []
        try:
            self._ftp.dir(files.append)
        except all_errors as e:
            log(e)
            self.update_ftp_info(str(e))
            self.on_disconnect()
        else:
            self.append_ftp_data(files)
            GLib.idle_add(self._connect_button.set_visible, False)

    @run_task
    def init_file_data(self, path=None):
        self.append_file_data(Path(path if path else self._settings.data_local_path))

    @run_idle
    def append_file_data(self, path: Path):
        self._file_model.clear()
        self._file_model.append(File(None, self.ROOT, None, None, str(path), "0"))

        try:
            dirs = [p for p in path.iterdir()]
        except OSError as e:
            log(e)
        else:
            for p in dirs:
                is_dir = p.is_dir()
                st = p.stat()
                size = str(st.st_size)
                date = datetime.fromtimestamp(st.st_mtime).strftime("%d-%m-%y %H:%M")
                icon = None
                if is_dir:
                    r_size = self.FOLDER
                    icon = self._folder_icon
                elif p.is_symlink():
                    r_size = self.LINK
                    icon = self._link_icon
                else:
                    r_size = self.get_size_from_bytes(size)

                self._file_model.append(File(icon, p.name, r_size, date, str(p.resolve()), size))

    @run_idle
    def append_ftp_data(self, files):
        self._ftp_model.clear()
        self._ftp_model.append(File(None, self.ROOT, None, None, self._ftp.pwd(), "0"))

        for f in files:
            f_data = f.split()
            f_type = f_data[0][0]
            is_dir = f_type == "d"
            is_link = f_type == "l"
            size = f_data[4]

            icon = None
            if is_dir:
                r_size = self.FOLDER
                icon = self._folder_icon
            elif is_link:
                r_size = self.LINK
                icon = self._link_icon
            else:
                r_size = self.get_size_from_bytes(size)

            date = "{}, {}  {}".format(f_data[5], f_data[6], f_data[7])
            self._ftp_model.append(File(icon, " ".join(f_data[8:]), r_size, date, f_data[0], size))

    def on_connect(self, item=None):
        self.init_ftp()

    def on_disconnect(self, item=None):
        if self._ftp:
            self._ftp.close()
        self._connect_button.set_visible(True)
        GLib.idle_add(self._ftp_model.clear)

    def on_ftp_row_activated(self, view, path, column):
        row = self._ftp_model[path][:]
        f_path = row[self.Column.NAME]
        size = row[self.Column.SIZE]

        if size == self.FOLDER or f_path == self.ROOT:
            self.init_ftp_data(f_path)
        else:
            b_size = row[self.Column.EXTRA]
            if b_size.isdigit() and int(b_size) > self.MAX_SIZE:
                self._app.show_error_dialog("The file size is too large!")
            else:
                self.open_ftp_file(f_path)

    def on_file_row_activated(self, view, path, column):
        row = self._file_model[path][:]
        path = Path(row[self.Column.ATTR])
        if row[self.Column.SIZE] == self.FOLDER:
            self.init_file_data(path)
        elif row[self.Column.NAME] == self.ROOT:
            self.init_file_data(path.parent)
        else:
            self.open_file(row[self.Column.ATTR])

    @run_task
    def open_file(self, path):
        GLib.idle_add(self._file_view.set_sensitive, False)
        try:
            cmd = ["open" if self._settings.is_darwin else "xdg-open", path]
            subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        finally:
            GLib.idle_add(self._file_view.set_sensitive, True)

    @run_task
    def open_ftp_file(self, f_path):
        is_darwin = self._settings.is_darwin
        GLib.idle_add(self._ftp_view.set_sensitive, False)

        try:
            import tempfile
            import os
            path = os.path.expanduser("~/Desktop") if is_darwin else None

            with tempfile.NamedTemporaryFile(mode="wb", dir=path, delete=not is_darwin) as tf:
                msg = "Downloading file: {}.   Status: {}"
                try:
                    status = self._ftp.retrbinary("RETR " + f_path, tf.write)
                    self.update_ftp_info(msg.format(f_path, status))
                except all_errors as e:
                    self.update_ftp_info(msg.format(f_path, e))

                tf.flush()
                cmd = ["open" if is_darwin else "xdg-open", tf.name]
                subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        finally:
            GLib.idle_add(self._ftp_view.set_sensitive, True)

    def on_ftp_edit(self, renderer):
        model, paths = self._ftp_view.get_selection().get_selected_rows()
        if not paths:
            return

        if len(paths) > 1:
            self._app.show_error_dialog("Please, select only one item!")
            return

        renderer.set_property("editable", True)
        self._ftp_view.set_cursor(paths, self._ftp_view.get_column(0), True)

    def on_ftp_edited(self, renderer, path, new_value):
        renderer.set_property("editable", False)
        row = self._ftp_model[path]
        old_name = row[self.Column.NAME]
        if old_name == new_value:
            return

        resp = self._ftp.rename_file(old_name, new_value)
        self.update_ftp_info("{}   Status: {}".format(old_name, resp))
        if resp[0] == "2":
            row[self.Column.NAME] = new_value

    def on_file_edit(self, renderer):
        model, paths = self._file_view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self._app.show_error_dialog("Please, select only one item!")
            return

        renderer.set_property("editable", True)
        self._file_view.set_cursor(paths, self._file_view.get_column(0), True)

    def on_file_edited(self, renderer, path, new_value):
        renderer.set_property("editable", False)
        row = self._file_model[path]
        old_name = row[self.Column.NAME]
        if old_name == new_value:
            return

        path = Path(row[self.Column.ATTR])
        if path.exists():
            try:
                new_path = path.rename("{}/{}".format(path.parent, new_value))
            except ValueError as e:
                log(e)
                self._app.show_error_dialog(str(e))
            else:
                if new_path.name == new_value:
                    row[self.Column.NAME] = new_value
                    row[self.Column.ATTR] = str(new_path.resolve())

    def on_file_remove(self, item=None):
        if show_dialog(DialogType.QUESTION, self._app._main_window) != Gtk.ResponseType.OK:
            return

        model, paths = self._file_view.get_selection().get_selected_rows()
        to_delete = []

        for path in filter(lambda p: model[p][self.Column.NAME] != self.ROOT, paths):
            f_path = Path(model[path][self.Column.ATTR])
            try:
                rmtree(f_path, ignore_errors=True) if f_path.is_dir() else f_path.unlink()
            except OSError as e:
                log(e)
            else:
                to_delete.append(model.get_iter(path))

        list(map(model.remove, to_delete))

    def on_ftp_file_remove(self, item=None):
        if show_dialog(DialogType.QUESTION, self._app._main_window) != Gtk.ResponseType.OK:
            return

        model, paths = self._ftp_view.get_selection().get_selected_rows()
        to_delete = []

        for path in filter(lambda p: model[p][self.Column.NAME] != self.ROOT, paths):
            row = model[path][:]
            name = row[self.Column.NAME]
            if row[self.Column.SIZE] == self.FOLDER:
                resp = self._ftp.delete_dir(name, self.update_ftp_info)
            else:
                resp = self._ftp.delete_file(name, self.update_ftp_info)

            if resp[0] == "2":
                to_delete.append(model.get_iter(path))

        list(map(model.remove, to_delete))

    def on_file_create_folder(self, renderer):
        itr = self._file_model.get_iter_first()
        if not itr:
            return

        name = self.get_new_folder_name(self._file_model)
        cur_path = self._file_model.get_value(itr, self.Column.ATTR)
        path = Path("{}/{}".format(cur_path, name))

        try:
            path.mkdir()
        except OSError as e:
            log(e)
            self._app.show_error_dialog(str(e))
        else:
            itr = self._file_model.append(File(self._folder_icon, path.name, self.FOLDER, "", str(path.resolve()), "0"))
            renderer.set_property("editable", True)
            self._file_view.set_cursor(self._file_model.get_path(itr), self._file_view.get_column(0), True)

    def on_ftp_create_folder(self, renderer):
        itr = self._ftp_model.get_iter_first()
        if not itr:
            return

        cur_path = self._ftp_model.get_value(itr, self.Column.ATTR)
        name = self.get_new_folder_name(self._ftp_model)

        try:
            folder = "{}/{}".format(cur_path, name)
            resp = self._ftp.mkd(folder)
        except all_errors as e:
            self.update_ftp_info(str(e))
            log(e)
        else:
            if resp == "{}/{}".format(cur_path, name):
                itr = self._ftp_model.append(File(self._folder_icon, name, self.FOLDER, "", "drwxr-xr-x", "0"))
                renderer.set_property("editable", True)
                self._ftp_view.set_cursor(self._ftp_model.get_path(itr), self._ftp_view.get_column(0), True)

    def get_new_folder_name(self, model):
        """ Returns the default name for the newly created folder. """
        name = "new folder"
        names = {r[self.Column.NAME] for r in model}
        count = 0
        while name in names:
            count += 1
            name = "{}{}".format(name, count)
        return name

    # ***************** Drag-and-drop ********************* #

    def init_drag_and_drop(self):
        self._ftp_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._ftp_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self._ftp_view.drag_source_add_uri_targets()
        self._ftp_view.drag_dest_add_uri_targets()

        self._file_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._file_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self._file_view.drag_source_add_uri_targets()
        self._file_view.drag_dest_add_uri_targets()

        self._ftp_view.get_selection().set_select_function(lambda *args: self._select_enabled)
        self._file_view.get_selection().set_select_function(lambda *args: self._select_enabled)

    def on_view_drag_begin(self, view, context):
        model, paths = view.get_selection().get_selected_rows()
        if len(paths) < 1:
            return

        pix = self._app.get_drag_icon_pixbuf(model, paths, self.Column.NAME, self.Column.SIZE)
        Gtk.drag_set_icon_pixbuf(context, pix, 0, 0)
        return True

    def on_ftp_drag_data_get(self, view, context, data, info, time):
        model, paths = view.get_selection().get_selected_rows()
        if len(paths) > 0:
            sep = self.URI_SEP if self._settings.is_darwin else "\n"
            uris = []
            for r in [model[p][:] for p in paths]:
                if r[self.Column.SIZE] != self.LINK and r[self.Column.NAME] != self.ROOT:
                    uris.append(Path("/{}:{}".format(r[self.Column.NAME], r[self.Column.ATTR])).as_uri())
            data.set_uris([sep.join(uris)])

    @run_task
    def on_ftp_drag_data_received(self, view, context, x, y, data: Gtk.SelectionData, info, time):
        if not self._ftp:
            return

        resp = "2"
        try:
            GLib.idle_add(self._app._wait_dialog.show)

            uris = data.get_uris()
            if self._settings.is_darwin and len(uris) == 1:
                uris = uris[0].split(self.URI_SEP)

            for uri in uris:
                uri = urlparse(unquote(uri)).path
                path = Path(uri)
                if path.is_dir():
                    try:
                        self._ftp.mkd(path.name)
                    except all_errors as e:
                        pass  # NOP
                    self._ftp.cwd(path.name)
                    resp = self._ftp.upload_dir(str(path.resolve()) + "/", self.update_ftp_info)
                else:
                    resp = self._ftp.send_file(path.name, str(path.parent) + "/", callback=self.update_ftp_info)
        finally:
            GLib.idle_add(self._app._wait_dialog.hide)
            if resp and resp[0] == "2":
                itr = self._ftp_model.get_iter_first()
                if itr:
                    self.init_ftp_data(self._ftp_model.get_value(itr, self.Column.ATTR))
        Gtk.drag_finish(context, True, False, time)
        return True

    def on_file_drag_data_get(self, view, context, data: Gtk.SelectionData, info, time):
        model, paths = view.get_selection().get_selected_rows()
        if len(paths) > 0:
            sep = self.URI_SEP if self._settings.is_darwin else "\n"
            uris = [sep.join([Path(model[p][self.Column.ATTR]).as_uri() for p in paths])]
            data.set_uris(uris)

    @run_task
    def on_file_drag_data_received(self, view, context, x, y, data, info, time):
        cur_path = self._file_model.get_value(self._file_model.get_iter_first(), self.Column.ATTR) + "/"
        try:
            GLib.idle_add(self._app._wait_dialog.show)

            uris = data.get_uris()
            if self._settings.is_darwin and len(uris) == 1:
                uris = uris[0].split(self.URI_SEP)

            for uri in uris:
                name, sep, attr = unquote(Path(uri).name).partition(":")
                if not attr:
                    return True

                if attr[0] == "d":
                    self._ftp.download_dir(name, cur_path, self.update_ftp_info)
                else:
                    self._ftp.download_file(name, cur_path, self.update_ftp_info)
        except OSError as e:
            log(e)
        finally:
            GLib.idle_add(self._app._wait_dialog.hide)
            self.init_file_data(cur_path)

        Gtk.drag_finish(context, True, False, time)
        return True

    def on_view_drag_end(self, view, context):
        self._select_enabled = True
        view.get_selection().unselect_all()

    @run_idle
    def update_ftp_info(self, message):
        message = message.strip()
        self._ftp_info_label.set_text(message)
        self._ftp_info_label.set_tooltip_text(message)

    def on_view_key_press(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.F7:
            if self._ftp_view.is_focus():
                self.on_ftp_create_folder(self._ftp_name_renderer)
            elif self._file_view.is_focus():
                self.on_file_create_folder(self._file_name_renderer)
        elif key is KeyboardKey.F2 or ctrl and KeyboardKey.R:
            if self._ftp_view.is_focus():
                self.on_ftp_edit(self._ftp_name_renderer)
            elif self._file_view.is_focus():
                self.on_file_edit(self._file_name_renderer)
        elif key is KeyboardKey.DELETE:
            if self._ftp_view.is_focus():
                self.on_ftp_file_remove()
            elif self._file_view.is_focus():
                self.on_file_remove()

    def on_view_press(self, view, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY:
            target = view.get_path_at_pos(event.x, event.y)
            mask = not (event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK))
            if target and mask and view.get_selection().path_is_selected(target[0]):
                self._select_enabled = False

    def on_view_release(self, view, event):
        """ Handles a mouse click (release) to view. """
        # Enable selection.
        self._select_enabled = True

    def get_size_from_bytes(self, size):
        """ Simple convert function from bytes to other units like K, M or G. """
        try:
            b = float(size)
        except ValueError:
            return size
        else:
            kb, mb, gb = 1024.0, 1048576.0, 1073741824.0

            if b < kb:
                return str(b)
            elif kb <= b < mb:
                return "{0:.1f} K".format(b / kb)
            elif mb <= b < gb:
                return "{0:.1f} M".format(b / mb)
            elif gb <= b:
                return "{0:.1f} G".format(b / gb)


if __name__ == '__main__':
    pass
