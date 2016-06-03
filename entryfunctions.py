from datetime import datetime, date
import re


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

