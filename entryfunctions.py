from datetime import datetime, date
import re

_multipliers = {
    '': 1,
    'kib': 2**10,
    'mib': 2**20,
    'gib': 2**30,
    'tib': 2**40,
    'kb': 10**3,
    'mb': 10**6,
    'gb': 10**9,
    'tb': 10**12
}
_monthabbrs = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def match_string(arg, data):
    if not arg:
        return data == ''
    return arg.lower() in data.lower()

def _get_comparison_function(arg, keepspaces=False):
    from operator import lt,gt,le,ge,eq
    if not keepspaces:
        arg = arg.replace(' ', '')
    if not arg:
        raise SyntaxError('Invalid argument')
    compfuncs = {'<':lt, '>':gt, '<=':le, '>=':ge, '=': eq, '': eq}
    opstr, rest = re.fullmatch(r'([<>]?=?)(.+)', arg).groups()
    return compfuncs[opstr], rest

def match_int(arg, data):
    op, rest = _get_comparison_function(arg)
    if not rest.isdecimal():
        raise SyntaxError('Invalid int match expression')
    return op(data, int(rest))

def match_score(arg, data):
    # Only show unscored entries when explicitly told to
    if not arg:
        return data == 0
    elif data == 0:
        return False
    op, rest = _get_comparison_function(arg)
    if not rest.isdecimal():
        raise SyntaxError('Invalid int match expression')
    return op(data, int(rest))

def match_space(arg, data):
    op, rest = _get_comparison_function(arg)
    rx = re.fullmatch(r'(?i)(\d+|\d+\.\d+)\s*([kmgt]i?b?)?', rest)
    if rx is None:
        raise SyntaxError('Invalid space match expression')
    rawnum, rawunit = rx.groups('')
    return op(data, int(float(rawnum) * _multipliers[rawunit]))

def match_date(arg, data):
    op, rest = _get_comparison_function(arg.lower(), keepspaces=True)
    yearrx = re.fullmatch(r'(19|20)?(\d\d)', rest.strip())
    monthyearrx = re.fullmatch(r'(\w+)\s*(\d{4})', rest.strip())
    currentyear = date.today().year
    if yearrx:
        century, tens = yearrx.groups()
        if yearrx.group(1) is None:
            century = '19' if int('20'+tens) > currentyear else '20'
        year = int(century + tens)
        return op(data.year, year)
    elif monthyearrx:
        monthname, year = monthyearrx.groups()
        try:
            month = _monthabbrs.index(monthname)+1
        except ValueError:
            raise SyntaxError('Invalid month')
        return op(data.year*12+data.month, int(year)*12+month)
    else:
        try:
            fulldate = datetime.strptime(rest.strip(), '%Y-%m-%d').date()
        except ValueError:
            raise SyntaxError('Invalid date match expression')
        else:
            return op(data, fulldate)

def match_duration(arg, data):
    op, rest = _get_comparison_function(arg)
    rx = re.fullmatch(r'((?P<h>\d+)h)?((?P<m>\d+)m(in)?)?((?P<s>\d+)s)?', rest)
    if rx is None:
        raise SyntaxError('Invalid duration match expression')
    d = rx.groupdict(0)
    totalseconds = int(d['h'])*3600+int(d['m'])*60+int(d['s'])
    return op(data, totalseconds)



# CONVERSION TO AND FROM THE INPUT (TERMINAL)

def parse_int(arg, reverse=False):
    if reverse:
        return str(arg)
    else:
        if not arg.isdecimal():
            raise SyntaxError('Invalid int')
        return int(arg)

def parse_score(arg, reverse=False):
    if reverse:
        return str(arg)
    else:
        if not arg.isdecimal():
            raise SyntaxError('Invalid score')
        if int(arg) not in range(0,11):
            raise SyntaxError('Score has to be between 0 and 10')
        return int(arg)

def parse_string(arg, reverse=False):
    return arg

def parse_date(arg, reverse=False):
    if reverse:
        if arg is None:
            return ''
        else:
            return arg.strftime('%Y-%m-%d')
    else:
        if arg.lower() == 'today':
            return date.today()
        else:
            try:
                datearg = datetime.strptime(arg, '%Y-%m-%d').date()
            except ValueError:
                raise SyntaxError('Invalid date format')
            else:
                return datearg

def parse_duration(arg, reverse=False):
    if reverse:
        time = [
            ('h', arg // 3600),
            ('m', arg // 60 % 60),
            ('s', arg % 60)
        ]
        return ' '.join('{}{}'.format(num, unit)
                        for unit, num in time if num > 0)
    else:
        fixedarg = arg.lower().replace(' ', '')
        rx = re.fullmatch(r'((?P<h>\d+)h)?((?P<m>\d+)m(in)?)?((?P<s>\d+)s)?', fixedarg)
        if rx is None:
            raise SyntaxError('Invalid duration format')
        d = rx.groupdict(0)
        totalseconds = int(d['h'])*3600+int(d['m'])*60+int(d['s'])
        return totalseconds

def parse_space(arg, reverse=False):
    if reverse:
        for x in ['', 'kib', 'mib', 'gib']:
            if arg < 1024:
                result = '{:.1f}{}'.format(arg, x)
                break
            arg /= 1024
        else:
            result = '{:,.1f}tib'.format(arg)
        # Remove the decimal if it's a zero
        return result.replace('.0','')
    else:
        rx = re.fullmatch(r'(\d+|\d+\.\d+)\s*([kmgt]i?b?)?', arg.lower())
        if rx is None:
            raise SyntaxError('Invalid space format')
        rawnum, rawunit = rx.groups('')
        return int(float(rawnum) * _multipliers[rawunit])

def parse_tags(arg, reverse=False):
    if reverse:
        return ', '.join(sorted(arg))
    else:
        tags = set(re.split(r'\s*,\s*', arg))
        for tag in tags:
            if re.fullmatch(r'[^()|]+', tag) is None:
                raise SyntaxError('Invalid tag')
        return tags
