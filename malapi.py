#!/usr/bin/env python3
from datetime import datetime
from html import unescape
import os.path
import re
from urllib.request import urlopen, urlretrieve
import xml.etree.ElementTree as ET

from libsyntyche.common import read_json, local_path

_xmltemplate = """\
<?xml version="1.0" encoding="UTF-8"?>
<entry>
    <episode>{ep}</episode>
    <status>{status}</status>
    <score>{score}</score>
    <storage_type></storage_type>
    <storage_value></storage_value>
    <times_rewatched></times_rewatched>
    <rewatch_value></rewatch_value>
    <date_start>{datestart}</date_start>
    <date_finish>{datefinish}</date_finish>
    <priority>0</priority>
    <enable_discussion>0</enable_discussion>
    <enable_rewatching>0</enable_rewatching>
    <comments></comments>
    <fansub_group></fansub_group>
    <tags></tags>
</entry>"""


def build_anime_xml_data(ep=0, status=6, score=0, datestart='', datefinish=''):
    return _xmltemplate.format(ep=ep, status=status, score=score,
                               datestart=datestart, datefinish=datefinish)

def extract_html_data(rawhtml):
    """
    Get the relevant data:
    * Studio(s)
    * Episode length
    * Rating
    """
    ratingrx = r'<span.+?>Rating:</span>\s*(\S+?)\s+-\s+.+?\s*</div>'
    studiorx = r'<span.+?>Studios:</span>\s*<a href="/anime/producer/\d+/.+?" title=".+?">(.+?)</a>'
    nostudiorx = r'<span.+?>Studios:</span>\s*None found, <a href=".+?">add some</a>'
    eplengthrx = r'<span.+?>Duration:</span>\s*((?P<hours>\d+)\s+hr\.\s*)?((?P<mins>\d+)\s+min\.\s*)?(per\s+ep\.)?\s*</div>'
    rating = re.search(ratingrx, rawhtml).group(1)
    try:
        studio = re.search(studiorx, rawhtml).group(1)
    except AttributeError:
        #if re.search(nostudiorx, rawhtml) is not None:
        studio = ''
    raweplength = re.search(eplengthrx, rawhtml).groupdict(0)
    eplength = int(raweplength['hours'])*3600 + int(raweplength['mins'])*60
    return {
        'rating': unescape(rating),
        'studio': unescape(studio),
        'episode_length': eplength
    }

def generate_default_value(datatype):
    return {
        'int': 0,
        'str': '',
        'bool': False,
        'list': []
    }[datatype]

def parse_rawvalue(rawvalue, datatype):
    if datatype == 'str':
        return rawvalue
    elif datatype == 'date':
        if rawvalue == '0000-00-00':
            return None
        else:
            return datetime.strptime(rawvalue, '%Y-%m-%d').date()
    elif datatype == 'int':
        return int(rawvalue)
    elif datatype == 'bool':
        return bool(rawvalue)
    elif datatype == 'mal-watch-status':
        if rawvalue.isdigit():
            return {
                '1': 'watching',
                '2': 'completed',
                '3': 'on hold',
                '4': 'dropped',
                '6': 'plan to watch'
            }[rawvalue]
        else:
            return rawvalue
    elif datatype == 'mal-type':
        return {
            '1': 'TV',
            '2': 'OVA',
            '3': 'movie',
            '4': 'special',
            '5': 'ONA'
        }[rawvalue]

def parse_animelist_xml(rawxml, malid, htmldata, template):
    root = ET.fromstring(rawxml)
    entry = {}
    for xmlentry in root:
        if xmlentry.tag != 'anime':
            continue
        entryid = xmlentry.find('series_animedb_id').text
        if int(entryid) != malid:
            continue
        for tag, data in template.items():
            if data['source'] == 'xmllist':
                rawvalue = xmlentry.find(data['id']).text
                value = parse_rawvalue(rawvalue, data['type'])
            elif data['source'] == 'htmlscraping':
                value = htmldata[tag]
            elif data['source'] == 'manual':
                value = generate_default_value(data['type'])
            entry[tag] = value
        break
    if not entry:
        raise KeyError('Anime with id {} not found'.format(malid))
    return entry

def get_anime_image(html, malid, outdir):
    rx = r'<a href="http://myanimelist.net/anime/\d+/.+?/pics">\s*<img src="(http://.+?)" alt'
    imgurl = re.search(rx, html).group(1)
    urlretrieve(imgurl, os.path.join(outdir, str(malid) + '.jpg'))

def get_mal_data(malid, maluser, imgdir):
    #TEMPSHIT
    template = read_json(os.path.join(local_path('templates'), 'defaultentry-meta.json'))
    #ENDTEMPSHIT
    htmlurl = 'http://myanimelist.net/anime.php?id={}'.format(malid)
    html = urlopen(htmlurl).read().decode('utf-8')
    htmldata = extract_html_data(html)
    xmlurl = 'http://myanimelist.net/malappinfo.php?status=1&type=anime&u={}'.format(maluser)
    xml = urlopen(xmlurl).read().decode('utf-8')
    entry = parse_animelist_xml(xml, malid, htmldata, template)
    get_anime_image(html, malid, imgdir)
    return entry
