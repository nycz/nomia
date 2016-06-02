import re


class AutoCompleter():
    def __init__(self):
        self.aclist = []
        self.suggestions = None
        self.index = 0
        self.resetflag = True

    def reset_suggestions(self) -> None:
        """
        Reset the list of suggestions.

        This should probably be called every time the cursor changes position
        not due to the autocompletion itself.
        """
        self.suggestions = []
        self.index = 0
        self.resetflag = True

    def add_completion(self, name='', prefix='', start=r'^', end=r'$',
                       illegal_chars='', get_suggestion_list=None) -> None:
        """
        Add an autocompletion pattern to autocompleter.

        Note that the prefix will be removed from the string the start and end
        regexes are matched against.

        Args:
            name: The pattern's identifier. Should be unique.
            prefix: A regex that matches the start of the input string but
                which will not be considered for autocompletion.
            start: A regex that matches the start of the autocompleted text.
            end: A regex that matches the end of the autocompleted text.
            illegal_chars: A string with all character that the autocompleted
                text may not include.
        """
        if get_suggestion_list is None:
            raise ValueError('AC pattern {} must have a suggestion list function!'.format(name))
        self.aclist.append({
                'name': name,
                'prefix': prefix,
                'start': start,
                'end': end,
                'illegal_chars': illegal_chars,
                'getsuggestions': get_suggestion_list
            })

    def _contains_illegal_chars(self, text: str, illegal_chars: str) -> bool:
        """
        Check if a string includes any illegal characters.

        Args:
            text: The string to be checked.
            illegal_chars: A string with the characters text may not include.
        """
        for char in illegal_chars:
            if char in text:
                return True
        return False

    def autocomplete(self, rawtext, rawpos, reverse=False):
        """
        Run autocompletion on a string.

        Args:
            rawtext: The string of which some part should be autocompleted.
            rawpos: An int with the position of the cursor in the string.
            reverse: Whether to go backwards or forwards in the list of
                suggestions.

        Return:
            A string with the full new text and an int with the change in
            cursor position.
        """
        for ac in self.aclist:
            prefix = re.match(ac['prefix'], rawtext)
            if prefix is None:
                continue
            prefixlength = len(prefix.group(0))
            # Dont match anything if the cursor is in the prefix
            if rawpos < prefixlength:
                continue
            pos = rawpos - prefixlength
            text = rawtext[prefixlength:]
            startmatches = [x for x in re.finditer(ac['start'], text)
                            if x.end() <= pos]
            endmatches = [x for x in re.finditer(ac['end'], text)
                          if x.start() >= pos]
            if not startmatches or not endmatches:
                continue
            start = startmatches[-1].end()
            end = endmatches[0].start()
            matchtext = text[start:end]
            if self._contains_illegal_chars(matchtext, ac['illegal_chars']):
                continue
            newtext = self._generate_suggestion(ac, matchtext, reverse)
            newpos = len(prefix.group(0) + text[:start] + newtext)
            return prefix.group(0) + text[:start] + newtext + text[end:], newpos
        return rawtext, rawpos

    def _generate_suggestion(self, ac, text, reverse):
        # Generate new suggestions if none exist
        if not self.suggestions:
            self.suggestions = ac['getsuggestions'](ac['name'], text)
        # If there's only one possibility, set it and move on
        if len(self.suggestions) == 1:
            text = self.suggestions[0]
            self.reset_suggestions()
        # Otherwise start scrolling through 'em
        elif self.suggestions:
            if self.resetflag:
                # Set index to last if you're just starting and going in reverse
                if reverse:
                    self.index = len(self.suggestions)-1
                self.resetflag = False
            else:
                if reverse:
                    self.index -= 1
                    if self.index == -1:
                        self.index = len(self.suggestions)-1
                else:
                    self.index += 1
                    if self.index == len(self.suggestions):
                        self.index = 0
            text = self.suggestions[self.index]
        return text




def main():
    #kalpana_ac = AC()
    #kalpana_ac.add_completion(name='filename',
    #                          prefix=r'[nos]\s*',
    #                          start=r'^',
    #                          end=r'$',
    #                          illegal_chars='')
    def get_tags(name, text):
        return ['arst', 'bloop', 'uaaau', 'huhu']

    sapfo_ac = AutoCompleter()
    sapfo_ac.add_completion(name='filter:tags',
                            prefix='ft',
                            start=r'(^|[()|,])\s*-?',
                            end=r'$|[()|,]',
                            illegal_chars='()|,',
                            get_suggestion_list=get_tags)
    #sapfo_ac.add_completion(name='filter:tagmacros',
    #                        prefix=r'ft\s*',
    #                        start=r'(^|[()|,])\s*-?@',
    #                        end=r'$|[()|,]',
    #                        illegal_chars='()|,')

    #sapfo_ac.add_completion(name='new:tags',
    #                        prefix=r'n\s*',
    #                        start=r'[(,]\s*',
    #                        end=r'\),',
    #                        illegal_chars='(),')
    #sapfo_ac.add_completion(name='new:filename',
    #                        prefix=r'n\s*',
    #                        start=r'^\([^)]*\)\s*',
    #                        end=r'$',
    #                        illegal_chars='')

    print(sapfo_ac.autocomplete('ft ',3))
    print(sapfo_ac.autocomplete('ft ',3))
    print(sapfo_ac.autocomplete('ft ',3))
    sapfo_ac.reset_suggestions()
    print(sapfo_ac.autocomplete('ft ',3))
    print(sapfo_ac.autocomplete('ft ',3))









if __name__ == '__main__':
    main()