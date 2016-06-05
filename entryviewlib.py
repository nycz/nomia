from PyQt4 import QtWebKit, QtCore

from abc import ABCMeta, abstractmethod

from libsyntyche.common import read_json, write_json


class EntryList(metaclass=ABCMeta):
    @abstractmethod
    def set_datapath(self, datapath):
        pass

    @abstractmethod
    def read_data(self):
        pass

    @abstractmethod
    def write_data(self):
        pass

    @abstractmethod
    def set_entry_value(self, entryid, attribute, newvalue):
        pass


class JSONEntryList(EntryList):
    def __init__(self):
        self._datapath = None
        self._entries = {}

    def set_datapath(self, datapath):
        self._datapath = datapath

    def read_data(self):
        # TODO: attribute-specific shit here
        self._entries = read_json(self._datapath)

    def write_data(self):
        # TODO: attribute-specific shit here
        write_json(self._datapath, self._entries)

    def set_entry_value(self, entryid, attribute, newvalue):
        self._entries[entryid][attribute] = newvalue




# ============= VIEW ================

class EntryView(metaclass=ABCMeta):
    @abstractmethod
    def set_entries(self, entries):
        pass

    @abstractmethod
    def sort_entries(self, attribute, reverse=False):
        pass

    @abstractmethod
    def set_hidden_entries(self, hiddenentries):
        pass

    @abstractmethod
    def set_entry_data(self, entryid, data):
        pass

    @abstractmethod
    def get_entry_id(self, number):
        pass


class HTMLEntryView(EntryView):
    def __init__(self, parent, entryelementid, separatorelementid,
                 stylesheetpath):
        self.entryelementid = entryelementid
        self.separatorelementid = separatorelementid
        self.sortkey = ''
        self.sortreverse = False
        self.hiddenentries = set()
        self._entrynumbers = []
        self.webview = QtWebKit.QWebView(parent)
        self.webview.setDisabled(True)
        self.set_stylesheet(stylesheetpath)
        # Pass it on
        self.wheelEvent = self.webview.wheelEvent
        self.keyPressEvent = self.webview.keyPressEvent
        self.keyReleaseEvent = self.webview.keyReleaseEvent
        # Default
        self.pagetemplate = '<!DOCTYPE html>\n<html>\n<head><meta charset="utf-8" />'\
                            '<style type="text/css"></style></head><body>{}</body></html>'

    def set_stylesheet(self, path):
        self.webview.settings().setUserStyleSheetUrl(QtCore.QUrl('file:///{}'.format(path)))

    def update_html(self, entries):
        def key(entry):
            id_, datadict = entry
            if not self.sortkey:
                return id_
            else:
                return datadict[self.sortkey]
        sortedvisibleentries = [
            (id_, datadict)
            for id_, datadict in sorted(entries.items(), key=key, reverse=self.sortreverse)
            if id_ not in self.hiddenentries
        ]
        self._entrynumbers = [id_ for id_, _ in sortedvisibleentries]
        htmlentries = (
            self.format_entry(n, id_, entry)
            for n, (id_, entry) in enumerate(sortedvisibleentries)
        )
        self.webview.setHtml(self.pagetemplate.format('\n'.join(htmlentries)))

    def set_entries(self, entries):
        self.update_html(entries)

    def sort_entries(self, attribute, entries, reverse=False):
        if self.sortkey == attribute and self.sortreverse == reverse:
            return
        self.sortkey = attribute
        self.sortreverse = reverse
        self.update_html(entries)

    def set_hidden_entries(self, hiddenentries, entries):
        if not self.hiddenentries ^ hiddenentries:
            return
        self.hiddenentries = hiddenentries
        self.update_html(entries)

    def get_entry_id(self, number):
        return self._entrynumbers[number]

    def set_entry_data(self, entryid, data):
        eid = self.entryelementid.format(entryid)
        frame = self.webview.page().mainFrame()
        entryelement = frame.findFirstElement(eid)
        html = self.format_entry(self._entrynumbers.index(entryid), entryid, data)
        sid = self.separatorelementid.format(entryid)
        separatorelement = frame.findFirstElement(sid)
        separatorelement.removeFromDocument()
        entryelement.setOuterXml(html)


    def format_entry(self, n, id_, entry):
        raise NotImplementedError




#class Input():
#    pass


####################

#class Terminal():
#    pass


#class Autocompleter():




if __name__ == '__main__':
    x = HTMLEntryView(None)
