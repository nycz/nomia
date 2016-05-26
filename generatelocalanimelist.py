#!/usr/bin/env python3
from html import unescape
import os
import os.path
import re
import xml.etree.ElementTree as ET


from libsyntyche.common import read_file, write_json, read_json, local_path

"""
THIS IS EXTREMELY TEMPORARY CODE
IS NOT AN OFFICIAL PART OF NOMIA

at least not yet

this should run once to generate the basic list
"""




def extract_html_data(rootdir):
    """
    Get the relevant data from the files:
    * Studio(s)
    * Episode length
    * Rating
    """
    ratingrx = r'<span.+?>Rating:</span>\s*(.+?)\s*</div>'
    studiorx = r'<span.+?>Studios:</span>\s*<a href="/anime/producer/\d+/.+?" title=".+?">(.+?)</a>'
    nostudiorx = r'<span.+?>Studios:</span>\s*None found, <a href=".+?">add some</a>'
    eplengthrx = r'<span.+?>Duration:</span>\s*((?P<hours>\d+)\s+hr\.\s*)?((?P<mins>\d+)\s+min\.\s*)?(per\s+ep\.)?\s*</div>'
    data = {}
    for fname in os.listdir(rootdir):
        rawdata = read_file(os.path.join(rootdir, fname))
        try:
            rating = re.search(ratingrx, rawdata).group(1)
        except AttributeError:
            print('rating', fname)
            return
        try:
            studio = re.search(studiorx, rawdata).group(1)
        except AttributeError:
            if re.search(nostudiorx, rawdata) is not None:
                studio = ''
            else:
                print('studio', fname)
        try:
            raweplength = re.search(eplengthrx, rawdata).groupdict(0)
        except AttributeError:
            print('ep length', fname)
            return
        eplength = int(raweplength['hours']) + int(raweplength['mins'])
        data[fname] = {
            'rating': unescape(rating),
            'studio': unescape(studio),
            'episode_length': eplength
        }
    return data



def generate_default_value(datatype):
    return {
        'int': 0,
        'str': '',
        'bool': False,
        'list': []
    }[datatype]

def parse_rawvalue(rawvalue, datatype):
    if datatype in ('str', 'date'):
        #TODO: proper date?
        return rawvalue
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
            '3': 'Movie',
            '4': 'Specials',
            '5': 'ONA'
        }[rawvalue]



def parse_animelist_xml(root, htmldata, template):
    entries = []
    for xmlentry in root:
        if xmlentry.tag != 'anime':
            continue
        entry = {}
        entryid = xmlentry.find('series_animedb_id').text
        for tag, data in template.items():
            if data['source'] == 'xmllist':
                rawvalue = xmlentry.find(data['id']).text
                value = parse_rawvalue(rawvalue, data['type'])
            elif data['source'] == 'htmlscraping':
                value = htmldata[entryid][tag]
            elif data['source'] == 'manual':
                value = generate_default_value(data['type'])
            entry[tag] = value
        entries.append(entry)
    return entries


def generate_list_of_anime_urls(entries):
    """
    DO NOT RUN THIS ALL THE TIME OKAY
    """
    from urllib.request import urlopen
    n = 1
    l = len(entries)
    for urln in [x['MAL id'] for x in entries]:
        print('{} ({}/{})'.format(urln, n, l))
        data = urlopen("http://myanimelist.net/anime.php?id={}".format(urln)).read().decode('utf-8')
        with open('malanimetempcache/{}'.format(urln), 'w', encoding='utf-8') as f:
            f.write(data)
        n += 1







def main():
    template = read_json(os.path.join(local_path('templates'), 'defaultentry-meta.json'))
    malanimelist = ET.parse(local_path('animelist-2016-05-26.xml'))
    htmldata = extract_html_data(local_path('malanimetempcache'))
    entries = parse_animelist_xml(malanimelist.getroot(), htmldata, template)
    write_json(local_path('animelisttest.json'), entries)


if __name__ == '__main__':
    main()
    #html = extract_html_data(local_path('malanimetempcache'))
    #l = [x['studio'] for x in html.values()]
    #from collections import Counter
    #from operator import itemgetter
    #c = Counter(l)
    #cl = sorted(((x, c[x]) for x in set(l)), key=itemgetter(1))

    #print(*cl, sep='\n')
    ##print(*s, sep='\n')
    #print('unique/total: {}/{}'.format(len(cl), len(html)))