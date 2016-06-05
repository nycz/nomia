from collections import Counter
from collections.abc import Set
from datetime import datetime
from operator import attrgetter
from os.path import join
import re

from PyQt4 import QtWebKit, QtGui, QtCore
from PyQt4.QtCore import pyqtSignal, Qt, QEvent

from libsyntyche.common import read_json, read_file, local_path, kill_theming, write_file, write_json
from libsyntyche.tagsystem import compile_tag_filter
from libsyntyche.terminal import GenericTerminalInputBox, GenericTerminalOutputBox, GenericTerminal

from autocompletion import AutoCompleter
from filtersystem import run_filter, match_tags
from entryviewlib import HTMLEntryView, EntryList
from entryfunctions import *


class NomiaEntryList():

    def __init__(self, dryrun):
        self.dateformat = '%Y-%m-%d'
        self.dryrun = dryrun

    def set_datapath(self, datapath):
        self.datapath = datapath
        self.entries = self.read_data(datapath)
        self.undostack = []

    def read_data(self, datapath):
        data = read_json(datapath)
        dateattributes = ['airing_started', 'airing_finished', 'watching_started', 'watching_finished']
        for entry in data.values():
            for x in dateattributes:
                if entry[x] is not None:
                    entry[x] = datetime.strptime(entry[x], self.dateformat).date()
            entry['tags'] = set(entry['tags'])
        return data

    def nonstandard_data_to_json(self, obj):
        try:
            datestring = obj.strftime(self.dateformat)
        except AttributeError:
            pass
        else:
            return datestring
        if isinstance(obj, Set):
            return list(obj)
        raise TypeError

    def write_data(self, datapath):
        if self.dryrun:
            return
        write_json(datapath, self.entries,
                   default=self.nonstandard_data_to_json)

    def set_entry_value(self, entryid, attribute, value):
        oldvalue = self.entries[entryid][attribute]
        undoitem = (entryid, attribute, oldvalue)
        self.undostack.append([undoitem])
        self.entries[entryid][attribute] = value
        self.write_data(self.datapath)

    def set_entry_values(self, actions):
        if not actions:
            return
        undoitems = []
        for entryid, attribute, value in actions:
            oldvalue = self.entries[entryid][attribute]
            undoitems.append((entryid, attribute, oldvalue))
            self.entries[entryid][attribute] = value
        self.undostack.append(undoitems)
        self.write_data(self.datapath)

    def undo_last_change(self):
        actions = self.undostack.pop()
        updates = []
        for entryid, attribute, value in actions:
            self.entries[entryid][attribute] = value
            updates.append((entryid, self.entries[entryid]))
        self.write_data(self.datapath)
        return updates




class NomiaHTMLEntryView(HTMLEntryView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expandedentries = set()

    def format_entry(self, n, id_, entry):
        def format_tags(tags):
            return '<wbr>'.join(
                self.templates['tags'].format(tag=t.replace(' ', '&nbsp;').replace('-', '&#8209;'),
                                    color='#657')#tagcolors.get(t, deftagcolor))
                for t in sorted(tags))
        def format_desc(desc):
            return desc if desc else '<span class="empty_desc">[no desc]</span>'
        def get_image(malindex):
            return join(local_path('imgcache'), str(malindex) + '.jpg')
        def get_score(num):
            return num if num > 0 else '-'
        def format_duration(totalseconds):
            time = [
                ('h', totalseconds // 3600),
                ('m', totalseconds // 60 % 60),
                ('s', totalseconds % 60),
            ]
            return ', '.join('{}{}'.format(num, unit) for unit, num in time if num > 0)
        def format_daterange(date1, date2):
            if date1 is None and date2 is None:
                return 'N/A'
            d = ['?' if x is None else x.strftime('%Y-%m-%d') for x in (date1,date2)]
            return '{} – {}'.format(*d)
        def format_bytes(rawbytes):
            if rawbytes <= 0:
                return 'N/A'
            for x in ['', 'KiB', 'MiB', 'GiB']:
                if rawbytes < 1024:
                    return '{:.1f} {}'.format(rawbytes, x)
                rawbytes /= 1024
            return '{:,.1f} TiB'.format(rawbytes)
        fentry = {
            'id': id_,
            'title': entry['title'],
            'tags': format_tags(entry['tags']),
            'desc': format_desc(entry['description']),
            'statustext': entry['status'],
            'statusclass': entry['status'].replace(' ', ''),
            'rating': entry['rating'],
            'score': get_score(entry['score_overall']),
            'type': entry['type'],
            'progress': entry['episodes_progress'],
            'image': get_image(entry['mal_id']),
            'maxeps': entry['episodes_total'],
            # Extended
            'studio': entry['studio'],
            'eplength': format_duration(entry['episode_length']),
            'space': format_bytes(entry['space']),
            'epspace': format_bytes(entry['space_per_episode']),
            'airing': format_daterange(entry['airing_started'], entry['airing_finished']),
            'watching': format_daterange(entry['watching_started'], entry['watching_finished']),
            'charscore': get_score(entry['score_characters']),
            'storyscore': get_score(entry['score_story']),
            'soundscore': get_score(entry['score_sound']),
            'artscore': get_score(entry['score_art']),
            'funscore': get_score(entry['score_enjoyment']),
            'comment': entry['comment']
        }
        return self.templates['entry'].format(num=n, **fentry)

    def toggle_entry_info(self, n):
        entryid = self.get_entry_id(n)
        elementid = self.entryelementid.format(entryid)
        element = self.webview.page().mainFrame().findFirstElement(elementid)
        child = element.findFirst('div.entry_info')
        if entryid in self.expandedentries:
            newdisplay = 'none'
            self.expandedentries.remove(entryid)
        else:
            newdisplay = '-webkit-flex'
            self.expandedentries.add(entryid)
        child.setStyleProperty('display', newdisplay)

    def set_entry_data(self, entryid, *args, **kwargs):
        super().set_entry_data(entryid, *args, **kwargs)
        # Re-expand it if it was expanded before
        if entryid in self.expandedentries:
            frame = self.webview.page().mainFrame()
            elementid = self.entryelementid.format(entryid)
            element = frame.findFirstElement(elementid).findFirst('div.entry_info')
            element.setStyleProperty('display', '-webkit-flex')

    def update_html(self, *args, **kwargs):
        super().update_html(*args, **kwargs)
        self.expandedentries.clear()


def load_html_templates():
    path = lambda fname: local_path(join('templates', fname))
    return {
        'entry': read_file(path('entry_template.html')),
        'page': read_file(path('index_page_template.html')),
        'tags': read_file(path('tags_template.html'))
    }


class TerminalIndexController():
    pass


class IndexFrame(QtGui.QWidget):

    def __init__(self, parent, dryrun, configdir):
        super().__init__(parent)
        self.configdir = configdir
        layout = QtGui.QVBoxLayout(self)
        kill_theming(layout)
        self.entrylist = NomiaEntryList(dryrun)
        self.view = NomiaHTMLEntryView(self, '#entry{}', '#hr{}', join(configdir, '.index.css'))
        self.view.templates = load_html_templates()
        layout.addWidget(self.view.webview, stretch=1)
        self.terminal = Terminal(self)
        layout.addWidget(self.terminal)
        self.connect_signals()
        #self.view.set_stylesheet()
        self.currentfilter = None
        self.attributes = self.init_attributes()
        self.autocompleted_attributes = [
            'rating',
            'status',
            'studio',
            'tags',
            'type'
        ]
        self.autocompleter = self.init_autocompleter()

    def init_autocompleter(self):
        ac = AutoCompleter()
        self.terminal.input_term.tab_pressed.connect(self.autocomplete)
        self.terminal.input_term.reset_ac_suggestions.connect(ac.reset_suggestions)
        # Filtering
        ac.add_completion(name='filter:macros',
                          prefix=r'f\s*',
                          start=r'(^|[(),|])\s*-?@',
                          end=r'$|[(),|]',
                          illegal_chars='()|,',
                          get_suggestion_list=self.get_autocompletion_data)
        ac.add_completion(name='filter:attr:tags',
                          prefix=r'f\s*',
                          start=r'(^|[(),|])\s*-?#',
                          end=r'$|[(),|]',
                          illegal_chars='()|,',
                          get_suggestion_list=self.get_autocompletion_data)
        ac.add_completion(name='filter:attrname',
                          prefix=r'f\s*',
                          start=r'(^|[(),|])\s*-?',
                          end=r'$|[:(),|]',
                          illegal_chars=':()|,',
                          get_suggestion_list=self.get_autocompletion_data)
        for attribute in self.autocompleted_attributes:
            ac.add_completion(name='filter:attr:{}'.format(attribute),
                              prefix=r'f\s*',
                              start=r'(^|[(),|])\s*-?{}:\s*'.format(attribute),
                              end=r'$|[(),|]',
                              illegal_chars='()|,',
                              get_suggestion_list=self.get_autocompletion_data)
        # Sorting
        ac.add_completion(name='sort',
                          prefix=r's\s*-?',
                          get_suggestion_list=self.get_autocompletion_data)
        # Editing
        ac.add_completion(name='edit:attrname',
                          prefix=r'e\d+\s*',
                          end=r'$|:',
                          illegal_chars=':',
                          get_suggestion_list=self.get_autocompletion_data)
        for attribute in self.autocompleted_attributes:
            if attribute == 'tags':
                ac.add_completion(name='edit:attr:{}'.format(attribute),
                                  prefix=r'e\d+\s*',
                                  start=r'(^{}:|,)\s*'.format(attribute),
                                  end=r'$|,',
                                  illegal_chars=',',
                                  get_suggestion_list=self.get_autocompletion_data)
            else:
                ac.add_completion(name='edit:attr:{}'.format(attribute),
                                  prefix=r'e\d+\s*',
                                  start=r'^{}:'.format(attribute),
                                  get_suggestion_list=self.get_autocompletion_data)
        # Tag replacement
        ac.add_completion(name='replace:attr:tags',
                          prefix=r'e\*\s*',
                          start=r'(^|,)\s*#',
                          end=r'$|,',
                          get_suggestion_list=self.get_autocompletion_data)
        ac.add_completion(name='replace:attrname',
                          prefix=r'e\*\s*',
                          end=r'$|:',
                          illegal_chars=':',
                          get_suggestion_list=self.get_autocompletion_data)
        ac.add_completion(name='replace:attr:tags',
                          prefix=r'e\*\s*',
                          start=r'(^\s*tags:|,)\s*',
                          get_suggestion_list=self.get_autocompletion_data)
        return ac

    def autocomplete(self, reverse):
        input_term = self.terminal.input_term
        text = input_term.text()
        pos = input_term.cursorPosition()
        newtext, newpos = self.autocompleter.autocomplete(text, pos, reverse)
        input_term.setText(newtext)
        input_term.setCursorPosition(newpos)

    def connect_signals(self):
        t = self.terminal
        connects = (
            (t.filter_,                 self.filter_entries),
            (t.sort,                    self.sort_entries),
            (t.toggle,                  self.toggle_entry_info),
            (t.edit,                    self.edit_entry),
            ##(t.new_entry,               self.new_entry),
            #(t.input_term.scroll_index, self.webview.event),
            #(t.list_,                   self.list_),
            #(t.quit,                    self.quit.emit),
            #(t.show_readme,             self.show_popup.emit),
            (t.test,                    self.dev_command),
        )
        for signal, slot in connects:
            signal.connect(slot)

    def update_settings(self, settings):
        self.settings = settings

    def init_attributes(self):
        return {
            'mal_id': [match_int, parse_int],
            'airing_finished': [match_date, parse_date],
            'airing_started': [match_date, parse_date],
            'comment': [match_string, parse_string],
            'description': [match_string, parse_string],
            'episode_length': [match_duration, parse_duration],
            'episodes_progress': [match_int, parse_int],
            'episodes_total': [match_int, parse_int],
            'rating': [match_string, parse_string],
            'score_art': [match_score, parse_score],
            'score_characters': [match_score, parse_score],
            'score_enjoyment': [match_score, parse_score],
            'score_overall': [match_score, parse_score],
            'score_sound': [match_score, parse_score],
            'score_story': [match_score, parse_score],
            'space': [match_space, parse_space],
            'space_per_episode': [match_space, parse_space],
            'status': [match_string, parse_string],
            'studio': [match_string, parse_string],
            'tags': [match_tags, parse_tags],
            'title': [match_string, parse_string],
            'type': [match_string, parse_string],
            'watching_finished': [match_date, parse_date],
            'watching_started': [match_date, parse_date],
        }

    def populate_view(self):
        self.entrylist.set_datapath(self.settings['path'])
        self.view.set_entries(self.entrylist.entries)
        self.terminal.attributes = self.attributes.keys()

    def get_autocompletion_data(self, name, text):
        if name in ['filter:attrname', 'edit:attrname', 'sort']:
            suggestions = [x for x in sorted(self.attributes.keys()) if x.startswith(text)]
            if len(suggestions) == 1 and name != 'sort':
                return [suggestions[0] + ': ']
            else:
                return suggestions
        elif name == 'replace:attrname':
            return [x for x in ['tags: '] if x.startswith(text)]
        elif name == 'filter:macros':
            return [x for x in sorted(self.settings['filter macros']) if x.startswith(text)]
        elif name.startswith('filter:attr:') or name.startswith('edit:attr:') or name.startswith('replace:attr:'):
            attribute = name.split(':', 2)[2]
            if attribute == 'tags':
                data = (tag for entry in self.entrylist.entries.values()
                        for tag in entry['tags']
                        if tag.startswith(text))
            else:
                data = (entry[attribute] for entry in self.entrylist.entries.values()
                        if entry[attribute].startswith(text))
        else:
            raise NotImplementedError('TODO: {}'.format(name))
        try:
            result = list(zip(*Counter(data).most_common()))[0]
        except IndexError:
            return []
        else:
            return result

    def refresh_view(self, keep_position=False):
        pass

    def toggle_entry_info(self, arg):
        """
        Main show entry method, called by the terminal. This toggles the
        box with extra info for the selected entry.

        arg should be the index of the entry to be viewed.
        """
        #if arg not in range(len(self.visible_entries)):
        #    self.error('Index out of range')
        #    return
        self.view.toggle_entry_info(int(arg))

        #element = self.webview.page().mainFrame().findFirstElement('div#entry_info_{}'.format(arg))
        #display = element.styleProperty('display', QtWebKit.QWebElement.ComputedStyle)
        #if display == 'none':
        #    newdisplay = '-webkit-flex'
        #else:
        #    newdisplay = 'none'
        #element.setStyleProperty('display', newdisplay)

    def dev_command(self, arg):
        write_file('dump.html', self.view.webview.page().mainFrame().toHtml())


    def filter_entries(self, arg):
        if not arg:
            if self.currentfilter:
                self.terminal.prompt('f ' + self.currentfilter)
            else:
                self.terminal.error('No active filter')
            return
        if arg.strip() == '-':
            self.currentfilter = None
            self.view.set_hidden_entries(set(), self.entrylist.entries)
            return
        try:
            filterexpression = compile_tag_filter(arg, self.settings['filter macros'])
        except SyntaxError as e:
            self.terminal.error(str(e))
            return
        hiddenentries = set()
        matchfuncs = {k:v[0] for k,v in self.attributes.items()}
        try:
            for id_, entry in self.entrylist.entries.items():
                if not run_filter(filterexpression, entry, matchfuncs):
                    hiddenentries.add(id_)
        except SyntaxError as e:
            self.terminal.error(str(e))
            return
        self.currentfilter = arg
        self.view.set_hidden_entries(hiddenentries, self.entrylist.entries)

    def sort_entries(self, arg):
        reverse = arg.startswith('-')
        arg = arg[reverse:]
        if arg not in self.attributes:
            self.terminal.error('Unknown attribute: {}'.format(arg))
            return
        self.view.sort_entries(arg, self.entrylist.entries, reverse)

    def replace_tags(self, oldtag, newtag):
        if not oldtag and not newtag:
            self.terminal.error('No tags specified')
            return
        selectedentries = set(self.entrylist.entries.keys()) - self.view.hiddenentries
        if oldtag:
            selectedentries = {id_ for id_ in selectedentries
                               if oldtag in self.entrylist.entries[id_]['tags']}
        newtagset = {newtag} if newtag else set()
        actions = [(id_, 'tags', self.entrylist.entries[id_]['tags'] - {oldtag} | newtagset)
                   for id_ in selectedentries]
        self.entrylist.set_entry_values(actions)
        for id_ in selectedentries:
            self.view.set_entry_data(id_, self.entrylist.entries[id_])

    def edit_entry(self, arg):
        if arg.strip() == 'u':
            try:
                actions = self.entrylist.undo_last_change()
            except IndexError:
                self.terminal.error('Nothing to undo')
            else:
                for entryid, data in actions:
                    self.view.set_entry_data(entryid, data)
            return
        replacerx = re.fullmatch(r'\*\s*tags:\s*([^,]*?)\s*,\s*([^,]*?)\s*', arg)
        if replacerx:
            self.replace_tags(*replacerx.groups())
            return
        replacerx2 = re.fullmatch(r'\*\s*(#[^,]+?)?\s*,\s*(#[^,]+?)?\s*', arg)
        if replacerx2:
            self.replace_tags(*[x[1:] for x in replacerx2.groups(' ')])
            return
        promptrx = re.fullmatch(r'(?P<num>\d+)\s*(?P<attrname>[^:]+)(:(?P<data>.*))?', arg)
        if promptrx is None:
            self.terminal.error('Invalid edit command')
            return
        num = int(promptrx.groupdict()['num'])
        try:
            entryid = self.view.get_entry_id(num)
        except IndexError:
            self.terminal.error('Index out of range')
            return
        attribute = promptrx.groupdict()['attrname']
        if attribute not in self.attributes:
            self.terminal.error('Unknown attribute')
            return
        parsefunc = self.attributes[attribute][1]
        # Prompt the current data if none is provided
        if not promptrx.groupdict('')['data'].strip():
            data = parsefunc(self.entrylist.entries[entryid][attribute], reverse=True)
            promptstr = 'e{num} {attrname}: {newdata}'.format(newdata=data, **promptrx.groupdict())
            self.terminal.prompt(promptstr)
            return
        # Otherwise get to it
        try:
            parseddata = parsefunc(promptrx.groupdict()['data'].strip())
        except SyntaxError as e:
            self.terminal.error(str(e))
            return
        self.entrylist.set_entry_value(entryid, attribute, parseddata)
        self.view.set_entry_data(entryid, self.entrylist.entries[entryid])


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

    def __init__(self, parent):
        super().__init__(parent, TerminalInputBox, GenericTerminalOutputBox)
        # nuke libsyntyche's autocompletion
        self.input_term.tab_pressed.disconnect()
        self.input_term.reset_ac_suggestions.disconnect()
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
