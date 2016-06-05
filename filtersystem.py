import re


def _match_tags_original(tag, oldtags, negative):
    """
    See if the tag exists in oldtags.
    """
    if '*' in tag:
        rx = re.compile(tag.replace('*', '.+')+'$')
        for t in oldtags:
            if rx.match(t):
                # If it exists and shouldn't be there, quit
                if negative:
                    return False
                # If it exists and should be there, move on to next tag
                else:
                    break
        else:
            # If it doesn't exist and should be there, quit
            if not negative:
                return False
    else:
        # If it's there and shouldn't, or isn't there but should be, quit
        if (negative and tag in oldtags) or (not negative and tag not in oldtags):
            return False
    # Otherwise it's fine
    return True

def match_tags(rawtag, oldtags):
    """
    See if the tag exists in oldtags.
    """
    tag = rawtag.strip()
    if not tag:
        if not oldtags:
            return True
        else:
            return False
    if '*' in tag:
        rx = re.compile(tag.replace('*', '.+')+'$')
        for t in oldtags:
            if rx.match(t):
                # If it exists, move on to next tag
                break
        else:
            # If it doesn't exist, quit
            return False
    else:
        # If isn't there, quit
        if tag not in oldtags:
            return False
    # Otherwise it's fine
    return True



def _handle_chunk(chunk, entrydata, matchfuncs):
    """
    Parse the chunk to see what it is and how it should be matched and to
    what attribute.

    Return a bool to indicate if the chunk matches or not.
    """
    # If it's an expression, send it along
    if not isinstance(chunk, str):
        return _parse(chunk, entrydata, matchfuncs)
    # Otherwise get on with it
    negative = chunk.startswith('-')
    chunk = chunk[negative:]
    # Tags
    # TODO: add a more generic way of having these kinds of special cases
    if chunk.startswith('#'):
        result = matchfuncs['tags'](chunk[1:], entrydata['tags'])
    else:
        try:
            attribute, arg = re.fullmatch(r'(.+?):(.*)', chunk).groups()
        except AttributeError:
            raise SyntaxError('Invalid filter chunk: {}'.format(chunk))
        if attribute not in entrydata:
            raise SyntaxError('Unknown attribute: {}'.format(attribute))
        result = matchfuncs[attribute](arg, entrydata[attribute])
    return not result if negative else result



def _parse(exp, entrydata, matchfuncs):
    """
    Parse the actual command to see if it matches the tags.
    """
    #def handle(x):
    #    """ Match x if it's a tag, otherwise parse it as an expression """
    #    return (_match if isinstance(x, str) else _parse)(x, oldtags)

    if exp[0] is None and len(exp) == 2:
        return _handle_chunk(exp[1], entrydata, matchfuncs)
    elif exp[0] == 'AND':
        for e in exp[1:]:
            if not _handle_chunk(e, entrydata, matchfuncs):
                return False
        return True
    elif exp[0] == 'OR':
        for e in exp[1:]:
            if _handle_chunk(e, entrydata, matchfuncs):
                return True
        return False
    else:
        raise SyntaxError('Invalid expression')


#def match_tag_filter(tag_filter, oldtags):
#    return _parse(tag_filter, oldtags)

def run_filter(filterexp, entrydata, matchfuncs):
    return _parse(filterexp, entrydata, matchfuncs)



def filter_text(attribute, payload, entries):
    """
    Return a tuple with the entries that include the specified text
    in the payload variable. The filtering in case-insensitive.
    """
    if not payload:
        return (entry for entry in entries\
                if not getattr(entry, attribute))
    else:
        return (entry for entry in entries\
                if payload.lower() in getattr(entry, attribute).lower())

def filter_number(attribute, payload, entries):
    from operator import lt,gt,le,ge
    compfuncs = {'<':lt, '>':gt, '<=':le, '>=':ge}
    expressions = [(compfuncs[m.group(1)], int(m.group(2).replace('k','000')))
                   for m in re.finditer(r'([<>][=]?)(\d+k?)', payload)]
    def matches(entry):
        return all(fn(getattr(entry, attribute), num) for fn, num in expressions)
    return filter(matches, entries)

def filter_tags(attribute, payload, entries, tagmacros):
    if not payload:
        return (entry for entry in entries \
                if not getattr(entry, attribute))
    else:
        tag_filter = compile_tag_filter(payload, tagmacros)
        return (entry for entry in entries \
                if match_tag_filter(tag_filter, getattr(entry, attribute)))

def filter_entries(entries, filters, attributedata, tagmacros):
    """
    Return a tuple with all entries that match the filters.

    filters is an iterable with (attribute, payload) pairs where payload is
    the string to be used with the attribute's specified filter function.
    """
    filtered_entries = entries
    for attribute, payload in filters:
        func = attributedata[attribute]['filter']
        if func == filter_tags:
            filtered_entries = func(attribute, payload, filtered_entries, tagmacros)
        else:
            filtered_entries = func(attribute, payload, filtered_entries)
    return tuple(filtered_entries)

def sort_entries(entries, attribute, reverse):
    return tuple(sorted(entries, key=attrgetter(attribute), reverse=reverse))

def generate_visible_entries(entries, filters, attributedata, sort_by, reverse, tagmacros):
    filtered_entries = filter_entries(entries, filters, attributedata, tagmacros)
    return sort_entries(filtered_entries, sort_by, reverse)