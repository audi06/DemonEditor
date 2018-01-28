import os
import shutil
from collections import namedtuple
from html.parser import HTMLParser

from app.commons import log
from app.properties import Profile


_ENIGMA2_PICON_NAME = "1_0_{}_{:X}_{:X}_{:X}_1680000_0_0_0.png"
_NEUTRINO_PICON_NAME = "{:x}{:04x}{:04x}.png"


Provider = namedtuple("Provider", ["logo", "name", "url", "on_id", "selected"])
Picon = namedtuple("Picon", ["ref", "ssid", "v_pid"])


class PiconsParser(HTMLParser):
    """ Parser for package html page. (https://www.lyngsat.com/packages/*provider-name*.html) """

    def __init__(self, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._current_row = []
        self._current_cell = []
        self.picons = []

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'th':
            self._is_th = True
        if tag == "img":
            self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'td':
            self._is_td = False
        elif tag == 'th':
            self._is_th = False

        if tag in ('td', 'th'):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == 'tr':
            row = self._current_row
            ln = len(row)
            if 9 < ln < 13:
                url = None
                if row[0].startswith("../logo/"):
                    url = row[0]
                elif row[1].startswith("../logo/"):
                    url = row[1]

                ssid = row[-4]
                if url and len(ssid) > 2:
                    self.picons.append(Picon(url, ssid, row[-3]))

            self._current_row = []

    def error(self, message):
        pass

    @staticmethod
    def parse(open_path, picons_path, tmp_path, on_id, profile=Profile.ENIGMA_2):
        with open(open_path, encoding="utf-8", errors="replace") as f:
            parser = PiconsParser()
            parser.reset()
            parser.feed(f.read())
            picons = parser.picons
            if picons:
                os.makedirs(picons_path, exist_ok=True)
                for p in picons:
                    try:
                        picon_file_name = picons_path + PiconsParser.format(p.ssid, on_id, p.v_pid, profile)
                        shutil.copyfile(tmp_path + "www.lyngsat.com/" + p.ref.lstrip("."), picon_file_name)
                    except (TypeError, ValueError) as e:
                        log("Picons format parse error: {} {} {}".format(p.ref, p.ssid, p.v_pid) + "\n" + str(e))
                        print(e)

    @staticmethod
    def format(ssid, on_id, v_pid, profile: Profile):
        tr_id = int(ssid[:-2] if len(ssid) < 4 else ssid[:2])
        if profile is Profile.ENIGMA_2:
            return _ENIGMA2_PICON_NAME.format(1 if v_pid else 2, int(ssid), tr_id, int(on_id))
        elif profile is Profile.NEUTRINO_MP:
            return _NEUTRINO_PICON_NAME.format(tr_id, int(on_id), int(ssid))
        else:
            return "{}.png".format(ssid)


class ProviderParser(HTMLParser):
    """ Parser for satellite html page. (https://www.lyngsat.com/*sat-name*.html) """

    def __init__(self, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._ON_ID_BLACK_LIST = ("65535", "?", "0", "1")
        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self.rows = []
        self._ids = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'tr':
            self._is_th = True
        if tag == "img":
            if attrs[0][1].startswith("logo/"):
                self._current_row.append(attrs[0][1])
        if tag == "a":
            if "https://www.lyngsat.com/packages/" in attrs[0][1]:
                self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'td':
            self._is_td = False
        elif tag == 'tr':
            self._is_th = False

        if tag in ('td', 'th'):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == 'tr':
            row = self._current_row
            if len(row) == 12:
                on_id, sep, tid = str(row[-2]).partition("-")
                if tid and on_id not in self._ON_ID_BLACK_LIST and on_id not in self._ids:
                    row[-2] = on_id
                    self.rows.append(row)
                    self._ids.add(on_id)
            self._current_row = []

    def error(self, message):
        pass


def parse_providers(open_path):
    with open(open_path, encoding="utf-8", errors="replace") as f:
        parser = ProviderParser()
        parser.reset()
        parser.feed(f.read())
        rows = parser.rows

        if rows:
            return [Provider(logo=r[2], name=r[5], url=r[6], on_id=r[-2], selected=True) for r in rows]


if __name__ == "__main__":
    pass
