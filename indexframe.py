from collections import namedtuple, defaultdict
from itertools import chain
from operator import itemgetter
import os
import os.path
from os.path import exists, join
import re
import subprocess

from PyQt4 import QtGui, QtWebKit
from PyQt4.QtCore import pyqtSignal, Qt, QEvent, QUrl

from libsyntyche import taggedlist
from libsyntyche.taggedlist import parse_text, parse_tags, filter_text, filter_number, filter_tags
from libsyntyche.common import local_path, read_file, read_json, write_json, kill_theming
from libsyntyche.terminal import GenericTerminalInputBox, GenericTerminalOutputBox, GenericTerminal


class IndexFrame(QtGui.QWidget):

    view_entry = pyqtSignal(tuple)
    view_meta = pyqtSignal(tuple)
    show_popup = pyqtSignal(str, str, str, str)
    quit = pyqtSignal(str)

    def __init__(self, parent, dry_run, configdir):
        super().__init__(parent)
        # Layout and shit
        layout = QtGui.QVBoxLayout(self)
        kill_theming(layout)
        self.webview = QtWebKit.QWebView(self)
        self.webview.settings().setUserStyleSheetUrl(QUrl('file:///'+join(configdir, '.index.css')))
        self.webview.setDisabled(True)
        layout.addWidget(self.webview, stretch=1)
        self.terminal = Terminal(self, self.get_tags)
        layout.addWidget(self.terminal)
        self.connect_signals()
        # Misc shizzle
        self.print_ = self.terminal.print_
        self.error = self.terminal.error
        self.set_terminal_text = self.terminal.prompt
        self.dry_run = dry_run
        self.htmltemplates = load_html_templates()
        self.css = None # Is set every time the config is reloaded
        self.defaulttagcolor = None # Is set every time the style is reloaded
        # Hotkeys
        hotkeypairs = (
            ('reload', self.reload_view),
            ('zoom in', self.zoom_in),
            ('zoom out', self.zoom_out),
            ('reset zoom', self.zoom_reset)
        )
        self.hotkeys = {
            key: QtGui.QShortcut(QtGui.QKeySequence(), self, callback)
            for key, callback in hotkeypairs
        }
        # Entries and stuff
        self.entries = ()
        self.visible_entries = ()
        activefilters = namedtuple('activefilters', 'title description tags wordcount backstorywordcount backstorypages')
        self.active_filters = activefilters(* 6 * (None,))
        self.sorted_by = ('title', False)
        self.undostack = ()

    def connect_signals(self):
        t = self.terminal
        connects = (
            (t.filter_,                 self.filter_entries),
            (t.sort,                    self.sort_entries),
            (t.toggle,                  self.toggle_entry_info),
            (t.edit,                    self.edit_entry),
            #(t.new_entry,               self.new_entry),
            (t.input_term.scroll_index, self.webview.event),
            (t.list_,                   self.list_),
            (t.quit,                    self.quit.emit),
            (t.show_readme,             self.show_popup.emit),
            (t.test,                    self.dev_command),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings):
        self.htmltemplates = load_html_templates()
        self.settings = settings
        self.terminal.update_settings(settings)
        # Update hotkeys
        for key, shortcut in self.hotkeys.items():
            shortcut.setKey(QtGui.QKeySequence(settings['hotkeys'][key]))
        self.reload_view()

    def zoom_in(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()+0.1)

    def zoom_out(self):
        self.webview.setZoomFactor(self.webview.zoomFactor()-0.1)

    def zoom_reset(self):
        self.webview.setZoomFactor(1)


    def reload_view(self):
        """
        Reload the entrylist by scanning the metadata files and then refresh
        the view with the updated entrylist.

        Is also the method that generates the entrylist the first time.
        So don't look for a init_everything method/function or anything, kay?
        """
        self.attributedata, self.entries = index_entries(self.settings['path'])
        self.visible_entries = self.regenerate_visible_entries()
        print('reloaded')
        self.refresh_view(keep_position=True)

    def refresh_view(self, keep_position=False):
        """
        Refresh the view with the filtered entries and the current css.
        The full entrylist is not touched by this.
        """
        frame = self.webview.page().mainFrame()
        pos = frame.scrollBarValue(Qt.Vertical)
        body = generate_html_body(self.visible_entries,
                                  self.htmltemplates.tags,
                                  self.htmltemplates.entry,
                                  self.settings['entry length template'],
                                  self.settings['tag colors'],
                                  self.defaulttagcolor)
        self.webview.setHtml(self.htmltemplates.index_page.format(body=body))
        #self.set_css(self.css)
        if keep_position:
            frame.setScrollBarValue(Qt.Vertical, pos)
        print('refreshed')

    def dev_command(self, arg):
        #element = self.webview.page().mainFrame().findFirstElement('style')
        #print(element.toPlainText()[:100])
        #element.setPlainText(read_file('test.css'))
        self.webview.settings().setUserStyleSheetUrl(QUrl('file:///'+local_path('test.css')))


        #print(self.webview.settings())
        #self.webview.settings().setUserStyleSheetUrl(QUrl('file:///'+local_path('test.css')))

    #def set_css(self, css):
    #    element = self.webview.page().mainFrame().findFirstElement('style')
    #    element.setPlainText(css)

    def get_tags(self):
        """
        Return all tags and how many times they appear among the entries.
        Called by the terminal for the tab completion.
        """
        tags = defaultdict(int)
        for e in self.entries:
            for t in e.tags:
                tags[t] += 1
        return list(tags.items())

    def list_(self, arg):
        if arg.startswith('f'):
            filters = ('{} {}'.format(cmd, payload) for cmd, payload in self.active_filters)
            if self.active_filters:
                self.print_(', '.join(filters))
            else:
                self.error('No active filters')
        elif arg.startswith('t'):
            # Sort alphabetically or after uses
            sortarg = 1
            if len(arg) == 2 and arg[1] == 'a':
                sortarg = 0
            self.old_pos = self.webview.page().mainFrame().scrollBarValue(Qt.Vertical)
            entry_template = '<div class="list_entry"><span class="tag" style="background-color:{color};">{tagname}</span><span class="length">({count:,})</span></div>'
            defcol = self.defaulttagcolor
            t_entries = (entry_template.format(color=self.settings['tag colors'].get(tag, defcol),
                                               tagname=tag, count=num)
                         for tag, num in sorted(self.get_tags(), key=itemgetter(sortarg), reverse=sortarg))
            body = '<br>'.join(t_entries)
            html = '<style type="text/css">{css}</style>\
                    <body><div id="taglist">{body}</div></body>'.format(body=body, css=self.css)
            self.show_popup.emit(html, '', '', 'html')


    def regenerate_visible_entries(self, entries=None, active_filters=None,
                                   attributedata=None, sort_by=None, reverse=None,
                                   tagmacros=None):
        """
        Convenience method to regenerate all the visible entries from scratch
        using the active filters, the full entries list (not the
        visible_entries) and the sort order.

        Each of the variables can be overriden by their appropriate keyword
        argument if needed.

        NOTE: This should return stuff b/c of clarity, despite the fact that
        it should always return it into the self.visible_entries variable.
        """
        # Drop the empty posts in the active_filters named tuple
        raw_active_filters = self.active_filters if active_filters is None else active_filters
        filters = [(k,v) for k,v in raw_active_filters._asdict().items() if v is not None]
        return taggedlist.generate_visible_entries(
            self.entries if entries is None else entries,
            filters,
            self.attributedata if attributedata is None else attributedata,
            self.sorted_by[0] if sort_by is None else sort_by,
            self.sorted_by[1] if reverse is None else reverse,
            self.settings['tag macros'] if tagmacros is None else tagmacros,
        )

    def filter_entries(self, arg):
        """
        The main filter method, called by terminal command.

        If arg is not present, print active filters.
        If arg is -, reset all filters.
        If arg is a category followed by -, reset that filter.
        If arg is a category (t or d) followed by _, show all entries with
        nothing in that particular category (eg. empty description).
        If arg is a category, prompt with the active filter (if any).
        """
        filters = {'n': 'title',
                   'd': 'description',
                   't': 'tags',
                   'c': 'wordcount',
                   'b': 'backstorywordcount',
                   'p': 'backstorypages'}
        filterchars = ''.join(filters)
        # Print active filters
        if not arg:
            active_filters = ['{}: {}'.format(cmd, payload)
                             for cmd, payload in self.active_filters._asdict().items()
                             if payload is not None]
            if active_filters:
                self.print_('; '.join(active_filters))
            else:
                self.error('No active filters')
            return
        # Reset all filters
        elif arg.strip() == '-':
            kwargs = dict(zip(filters.values(), len(filters)*(None,)))
            self.active_filters = self.active_filters._replace(**kwargs)
            visible_entries = self.regenerate_visible_entries()
            resultstr = 'Filters reset: {}/{} entries visible'
        # Reset specified filter
        elif re.fullmatch(r'[{}]-\s*'.format(filterchars), arg):
            self.active_filters = self.active_filters._replace(**{filters[arg[0]]:None})
            visible_entries = self.regenerate_visible_entries()
            resultstr = 'Filter on {} reset: {{}}/{{}} entries visible'.format(filters[arg[0]])
        else:
            # Prompt active filter
            if arg.strip() in filters.keys():
                payload = getattr(self.active_filters, filters[arg])
                if payload is None:
                    payload = ''
                self.set_terminal_text('f' + arg.strip() + ' ' + payload)
                return
            # Filter empty entries
            if re.fullmatch(r'[dt]_\s*'.format(filterchars), arg):
                cmd = arg[0]
                payload = ''
            # Regular filter command
            elif re.fullmatch(r'[{}] +\S.*'.format(filterchars), arg):
                cmd = arg[0]
                payload = arg.split(None,1)[1].strip()
            # Invalid filter command
            else:
                self.error('Invalid filter command')
                return
            # Do the filtering
            self.active_filters = self.active_filters._replace(**{filters[cmd]: payload})
            try:
                visible_entries = self.regenerate_visible_entries()
            except SyntaxError as e:
                # This should be an error from the tag parser
                self.error('[Tag parsing] {}'.format(e))
                return
            resultstr = 'Filtered: {}/{} entries visible'
        # Only actually update stuff if the entries have changed
        if visible_entries != self.visible_entries:
            self.visible_entries = visible_entries
            self.refresh_view()
        # Print the output
        filtered, total = len(self.visible_entries), len(self.entries)
        self.print_(resultstr.format(filtered, total))

    def sort_entries(self, arg):
        """
        The main sort method, called by terminal command.

        If arg is not specified, print the current sort order.
        """
        acronyms = {'n': 'title',
                    'c': 'wordcount',
                    'b': 'backstorywordcount',
                    'p': 'backstorypages',
                    'm': 'lastmodified'}
        if not arg:
            attr = self.sorted_by[0]
            order = ('ascending', 'descending')[self.sorted_by[1]]
            self.print_('Sorted by {}, {}'.format(attr, order))
            return
        if arg[0] not in acronyms:
            self.error('Unknown attribute to sort by: "{}"'.format(arg[0]))
            return
        if not re.fullmatch(r'\w-?\s*', arg):
            self.error('Incorrect sort command')
            return
        reverse = arg.strip().endswith('-')
        self.sorted_by = (acronyms[arg[0]], reverse)
        sorted_entries = taggedlist.sort_entries(self.visible_entries,
                                                 acronyms[arg[0]],
                                                 reverse)
        if sorted_entries != self.visible_entries:
            self.visible_entries = sorted_entries
            self.refresh_view()

    def edit_entry(self, arg):
        """
        The main edit method, called by terminal command.

        If arg is "u", undo the last edit.
        Otherwise, either replace/add/remove tags from the visible entries
        or edit attributes of a single entry.
        """
        if arg.strip() == 'u':
            if not self.undostack:
                self.error('Nothing to undo')
                return
            undoitem = self.undostack[-1]
            self.undostack = self.undostack[:-1]
            self.entries = taggedlist.undo(self.entries, undoitem)
            self.visible_entries = self.regenerate_visible_entries()
            self.refresh_view(keep_position=True)
            if not self.dry_run:
                write_metadata(undoitem)
            self.print_('{} edits reverted'.format(len(undoitem)))
            return
        replace_tags = re.fullmatch(r't\*\s*(.*?)\s*,\s*(.*?)\s*', arg)
        main_data = re.fullmatch(r'[dtn](\d+)(.*)', arg)
        # Replace/add/remove a bunch of tags
        if replace_tags:
            oldtag, newtag = replace_tags.groups()
            if not oldtag and not newtag:
                self.error('No tags specified, nothing to do')
                return
            entries = taggedlist.replace_tags(oldtag,
                                              newtag,
                                              self.entries,
                                              self.visible_entries,
                                              'tags')
            if entries != self.entries:
                old, changed = taggedlist.get_diff(self.entries, entries)
                self.undostack = self.undostack + (old,)
                self.entries = entries
                self.visible_entries = self.regenerate_visible_entries()
                self.refresh_view(keep_position=True)
                if not self.dry_run:
                    write_metadata(changed)
                self.print_('Edited tags in {} entries'.format(len(changed)))
            else:
                self.error('No tags edited')
        # Edit a single entry
        elif main_data:
            entry_id = int(main_data.group(1))
            if entry_id >= len(self.visible_entries):
                self.error('Index out of range')
                return
            payload = main_data.group(2).strip()
            category = {'d': 'description', 'n': 'title', 't': 'tags'}[arg[0]]
            # No data specified, so the current is provided instead
            if not payload:
                data = getattr(self.visible_entries[entry_id], category)
                new = ', '.join(sorted(data)) if arg[0] == 't' else data
                self.set_terminal_text('e' + arg.strip() + ' ' + new)
            else:
                index = self.visible_entries[entry_id][0]
                entries = taggedlist.edit_entry(index,
                                                self.entries,
                                                category,
                                                payload,
                                                self.attributedata)
                if entries != self.entries:
                    self.undostack = self.undostack + ((self.visible_entries[entry_id],),)
                    self.entries = entries
                    self.visible_entries = self.regenerate_visible_entries()
                    self.refresh_view(keep_position=True)
                    if not self.dry_run:
                        write_metadata((self.entries[index],))
                    self.print_('Entry edited')
        else:
            self.error('Invalid edit command')

    def toggle_entry_info(self, arg):
        """
        Main show entry method, called by the terminal. This toggles the
        box with extra info for the selected entry.

        arg should be the index of the entry to be viewed.
        """
        if arg not in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        element = self.webview.page().mainFrame().findFirstElement('div#entry_info_{}'.format(arg))
        display = element.styleProperty('display', QtWebKit.QWebElement.ComputedStyle)
        if display == 'none':
            newdisplay = '-webkit-flex'
        else:
            newdisplay = 'none'
        element.setStyleProperty('display', newdisplay)
        #print(element.styleProperty('display', QtWebKit.QWebElement.ComputedStyle))


    def open_entry(self, arg):
        """
        Main open entry method, called by the terminal.

        arg should be the index of the entry to be viewed.
        """
        if not isinstance(arg, int):
            raise AssertionError('BAD CODE: the open entry arg should be an int')
        if arg not in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        self.view_entry.emit(self.visible_entries[arg])


    def new_entry(self, arg):
        """
        Main new entry method, called by the terminal.
        """
        def metadatafile(path):
            dirname, fname = os.path.split(path)
            return join(dirname, '.' + fname + '.metadata')
        file_exists = False
        tags = []
        new_entry_rx = re.match(r'\s*\(([^\(]*?)\)\s*(.+)\s*', arg)
        if not new_entry_rx:
            self.error('Invalid new entry command')
            return
        tagstr, path = new_entry_rx.groups()
        fullpath = os.path.expanduser(join(self.settings['path'], path))
        dirname, fname = os.path.split(fullpath)
        metadatafile = join(dirname, '.' + fname + '.metadata')
        if tagstr:
            tags = list({tag.strip() for tag in tagstr.split(',')})
        if exists(metadatafile):
            self.error('Metadata already exists for that file')
            return
        if exists(fullpath):
            file_exists = True
        # Fix the capitalization
        title = re.sub(r"\w[\w']*",
                       lambda mo: mo.group(0)[0].upper() + mo.group(0)[1:].lower(),
                       os.path.splitext(fname)[0].replace('-', ' '))
        try:
            open(fullpath, 'a').close()
            write_json(metadatafile, {'title': title, 'description': '', 'tags': tags})
        except Exception as e:
            self.error('Couldn\'t create the files: {}'.format(str(e)))
        else:
            self.reload_view()
            if file_exists:
                self.print_('New entry created, metadatafile added to existing file')
            else:
                self.print_('New entry created')



    def external_run_entry(self, arg):
        """
        Main external run method, called by terminal command.
        """
        if not arg.isdigit():
            partialnames = [n for n, entry in enumerate(self.visible_entries)
                            if arg.lower() in entry.title.lower()]
            if not partialnames:
                self.error('Entry not found: "{}"'.format(arg))
                return
            elif len(partialnames) > 1:
                self.error('Ambiguous name, matches {} entries'.format(len(partialnames)))
                return
            elif len(partialnames) == 1:
                arg = partialnames[0]
        elif not int(arg) in range(len(self.visible_entries)):
            self.error('Index out of range')
            return
        if not self.settings.get('editor', None):
            self.error('No editor command defined')
            return
        subprocess.Popen([self.settings['editor'],
                          self.visible_entries[int(arg)].file])
        self.print_('Opening entry with {}'.format(self.settings['editor']))


def load_html_templates():
    html = namedtuple('HTMLTemplates', 'entry index_page tags')
    path = lambda fname: local_path(join('templates', fname))
    return html(read_file(path('entry_template.html')),
                read_file(path('index_page_template.html')),
                read_file(path('tags_template.html')))


# ===== Filter functions ======================================

def filter_date(attribute, payload, entries):
    pass

def filter_diskspace(attribute, payload, entries):
    pass

def filter_duration(attribute, payload, entries):
    pass

# ===== Parse functions =======================================

def parse_bool(rawtext):
    return rawtext

def parse_date(rawtext):
    return rawtext

def parse_diskspace(rawtext):
    return rawtext

def parse_duration(rawtext):
    return rawtext

def parse_int(rawtext):
    return rawtext

def parse_score(rawtext):
    return rawtext





def index_entries(fname):
    """
    Find all files that match the filter, and return a sorted list
    of them with wordcount, paths and all data from the metadata file.
    """
    attributes = {
        'MAL_id': {
            'filter': filter_number,
            'parser': parse_int
        },
        'airing_finished': {
            'filter': filter_date,
            'parser': parse_date
        },
        'airing_started': {
            'filter': filter_date,
            'parser': parse_date
        },
        'comment': {
            'filter': filter_text,
            'parser': parse_text
        },
        'description': {
            'filter': filter_text,
            'parser': parse_text
        },
        'episode_length': {
            'filter': filter_duration,
            'parser': parse_duration
        },
        'episodes_progress': {
            'filter': filter_number,
            'parser': parse_int
        },
        'episodes_total': {
            'filter': filter_number,
            'parser': parse_int
        },
        'score_art': {
            'filter': filter_number,
            'parser': parse_score
        },
        'score_characters': {
            'filter': filter_number,
            'parser': parse_score
        },
        'score_enjoyment': {
            'filter': filter_number,
            'parser': parse_score
        },
        'score_overall': {
            'filter': filter_number,
            'parser': parse_score
        },
        'score_sound': {
            'filter': filter_number,
            'parser': parse_score
        },
        'score_story': {
            'filter': filter_number,
            'parser': parse_score
        },
        'space': {
            'filter': filter_diskspace,
            'parser': parse_diskspace
        },
        'space_per_episode': {
            'filter': filter_diskspace,
            'parser': parse_diskspace
        },
        'tags': {
            'filter': filter_tags,
            'parser': parse_tags
        },
        'title': {
            'filter': filter_text,
            'parser': parse_text
        },
        'watching_finished': {
            'filter': filter_date,
            'parser': parse_date
        },
        'watching_started': {
            'filter': filter_date,
            'parser': parse_date
        },
    }
    entries = read_json(fname)
    for entry in entries:
        for k in ['rating', 'status', 'studio', 'type']:
            entry['tags'].append('{}: {}'.format(k, entry[k]))
            del entry[k]
        if entry['available_locally']:
            entry['tags'].append('local')
        del entry['available_locally']

    Entry = namedtuple('Entry', ('index',) + tuple(sorted(attributes.keys())))
    #print(next(reversed(list(zip(*sorted(entries[0].items()))))))
    entrylist = (Entry(n, *[v for k,v in sorted(argdict.items())]) for n, argdict in enumerate(entries))
    return attributes, tuple(entrylist)

def generate_html_body(visible_entries, tagstemplate, entrytemplate, entrylengthtemplate, tagcolors, deftagcolor):
    """
    Return html generated from the visible entries.
    """
    def format_tags(tags):
        specialtagrx = r'(status|rating|studio|type): '
        return '<wbr>'.join(
            tagstemplate.format(tag=t.replace(' ', '&nbsp;').replace('-', '&#8209;'),
                                color=tagcolors.get(t, deftagcolor))
            for t in sorted(tags) if re.match(specialtagrx, t) is None)
    def format_desc(desc):
        return desc if desc else '<span class="empty_desc">[no desc]</span>'
    def get_tag(tags, prefix):
        return next(x.split(' ', 1)[1] for x in tags if x.startswith(prefix))
    def get_image(malindex):
        return join(local_path('imgcache'), str(malindex) + '.jpg')
    def get_score(num):
        return num if num > 0 else '-'
    entries = (entrytemplate.format(
            id=n,
            title=entry.title,
            tags=format_tags(entry.tags),
            desc=format_desc(entry.description),
            statustext=get_tag(entry.tags, 'status: '),
            statusclass=get_tag(entry.tags, 'status: ').replace(' ', ''),
            rating=get_tag(entry.tags, 'rating: '),
            score=get_score(entry.score_overall),
            type=get_tag(entry.tags, 'type: '),
            progress=entry.episodes_progress,
            image=get_image(entry.MAL_id),
            maxeps=entry.episodes_total,
            # Extended
            studio=get_tag(entry.tags, 'studio'),
            eplength=entry.episode_length,
            totalspace=entry.space,
            epspace=entry.space_per_episode,
            airingstart=entry.airing_started,
            airingend=entry.airing_finished,
            watchingstart=entry.watching_started,
            watchingend=entry.watching_finished,
            charscore=get_score(entry.score_characters),
            storyscore=get_score(entry.score_story),
            soundscore=get_score(entry.score_sound),
            artscore=get_score(entry.score_art),
            funscore=get_score(entry.score_enjoyment),
            comment=entry.comment)
        for n,entry in enumerate(visible_entries))
    return '<hr />'.join(entries)



# TERMINAL

class TerminalInputBox(GenericTerminalInputBox):
    scroll_index = pyqtSignal(QtGui.QKeyEvent)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
            nev = QtGui.QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
            self.scroll_index.emit(nev)
        else:
            return super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
            nev = QtGui.QKeyEvent(QEvent.KeyRelease, event.key(), Qt.NoModifier)
            self.scroll_index.emit(nev)
        else:
            return super().keyReleaseEvent(event)


class Terminal(GenericTerminal):
    filter_ = pyqtSignal(str)
    sort = pyqtSignal(str)
    toggle = pyqtSignal(int)
    quit = pyqtSignal(str)
    edit = pyqtSignal(str)
    list_ = pyqtSignal(str)
    new_entry = pyqtSignal(str)
    show_readme = pyqtSignal(str, str, str, str)
    test = pyqtSignal(str)

    def __init__(self, parent, get_tags):
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox)
        self.get_tags = get_tags
        self.autocomplete_type = '' # 'path' or 'tag'
        # These two are set in reload_settings() in sapfo.py
        self.rootpath = ''
        self.tagmacros = {}
        self.commands = {
            'f': (self.filter_, 'Filter'),
            'e': (self.edit, 'Edit'),
            's': (self.sort, 'Sort'),
            'q': (self.quit, 'Quit'),
            '?': (self.cmd_help, 'List commands or help for [command]'),
            'l': (self.list_, 'List'),
            #'n': (self.new_entry, 'New entry'),
            'h': (self.cmd_show_readme, 'Show readme'),
            't': (self.test, 'DEVCOMMAND'),
        }

    def cmd_show_readme(self, arg):
        self.show_readme.emit('', local_path('README.md'), None, 'markdown')

    def update_settings(self, settings):
        self.rootpath = settings['path']
        self.tagmacros = settings['tag macros']
        # Terminal animation settings
        self.output_term.animate = settings['animate terminal output']
        interval = settings['terminal animation interval']
        if interval < 1:
            self.error('Too low animation interval')
        self.output_term.set_timer_interval(max(1, interval))

    def command_parsing_injection(self, arg):
        if arg.isdigit():
            self.toggle.emit(int(arg))
            return True

    def autocomplete(self, reverse):

        def get_interval(t, pos, separators):
            """ Return the interval of the string that is going to be autocompleted """
            start, end = 0, len(t)
            for n,i in enumerate(t):
                if n < pos and i in separators:
                    start = n + 1
                if n >= pos and i in separators:
                    end = n
                    break
            return start, end

        def autocomplete_tags(text, pos, separators, prefix=''):
            self.autocomplete_type = 'tag'
            start, end = get_interval(text, pos, separators)
            ws_prefix, dash, target_text = re.match(r'(\s*)(-?)(.*)',text[start:end]).groups()
            new_text = self.run_autocompletion(target_text, reverse)
            output = prefix + text[:start] + ws_prefix + dash + new_text + text[end:]
            self.prompt(output)
            self.input_term.setCursorPosition(len(output) - len(text[end:]))

        text = self.input_term.text()
        pos = self.input_term.cursorPosition()

        # Auto complete the ft and the et command
        tabsep_rx = re.match(r'(ft|et\*|et\d+\s*)(.*)', text)
        if tabsep_rx:
            prefix, payload = tabsep_rx.groups()
            if pos < len(prefix):
                return
            separators = {'f': '(),|', 'e': ','}
            autocomplete_tags(payload, pos - len(prefix), separators[prefix[0]], prefix=prefix)
        # Autocomplete the n command
        elif re.match(r'n\s*\([^\(]*?(\)\s*.*)?$', text):
            taggroup_pos_start = text.find('(') + 1
            taggroup_pos_end = text.find(')') if ')' in text else len(text)
            if pos < taggroup_pos_start:
                return
            # If the cursor is right of the ), autocomplete it as a path
            if pos > taggroup_pos_end:
                self.autocomplete_type = 'path'
                start = taggroup_pos_end + 1
                new_text = self.run_autocompletion(text[start:].lstrip(), reverse)
                self.prompt(text[:start] + ' ' + new_text)
            # If the cursor is within the tags' parentheses, autocomplete it as a tag
            else:
                autocomplete_tags(text, pos, '(),')


    def get_ac_suggestions(self, prefix):
        if self.autocomplete_type == 'tag':
            tags = next(zip(*sorted(self.get_tags(), key=itemgetter(1), reverse=True)))
            macros = ('@' + x for x in sorted(self.tagmacros.keys()))
            return [x for x in chain(tags, macros) if x.startswith(prefix)]
        elif self.autocomplete_type == 'path':
            root = os.path.expanduser(self.rootpath)
            dirpath, namepart = os.path.split(join(root, prefix))
            if not os.path.isdir(dirpath):
                return []
            suggestions = [join(dirpath, p) for p in sorted(os.listdir(dirpath))
                           if p.lower().startswith(namepart.lower())]
            # Remove the root prefix and add a / at the end if it's a directory
            return [p.replace(root, '', 1).lstrip(os.path.sep) + (os.path.sep*os.path.isdir(p))
                    for p in suggestions]




