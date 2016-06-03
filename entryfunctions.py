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


def match_string(arg, data):
    return arg.lower() in data.lower()

def _get_comparison_function(arg):
    from operator import lt,gt,le,ge,eq
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
    if not arg.strip():
        return data == 0
    elif data == 0:
        return False
    op, rest = _get_comparison_function(arg)
    if not rest.isdecimal():
        raise SyntaxError('Invalid int match expression')
    return op(data, int(rest))

def match_space(arg, data):
    op, rest = _get_comparison_function(arg)
    rx = re.fullmatch(r'(?i)(\d+|\d+\.\d+)([kmgt]?)', rest)
    

def match_date(arg, data):
    pass

def match_duration(arg, data):
    op, rest = _get_comparison_function(arg)
    rx = re.fullmatch(r'((?P<h>\d+)h)?((?P<m>\d+)m(in)?)?((?P<s>\d+)s)?', rest)
    if rx is None:
        raise SyntaxError('Invalid duration match expression: {}'.format(arg))
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
    pass

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
        if not rx:
            raise SyntaxError('Invalid space format')
        rawnum, rawunit = rx.groups('')
        return int(float(rawnum) * _multipliers[rawunit])


def parse_tags(arg, reverse=False):
    if reverse:
        return ', '.join(sorted(arg))
    else:
        tags = set(re.split(r'\s*,\s*', arg))
        for tag in tags:
            if not re.fullmatch(r'[^()|]+', tag):
                raise SyntaxError('Invalid tag')
        return tags
