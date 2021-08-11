import os
import sys
import json
import re
from collections import namedtuple
from cudatext import *
from cudax_lib import get_translation, _json_loads

_   = get_translation(__file__)  # I18N

CompCfg = namedtuple('CompCfg', 'word_prefix word_range attr_range spaced_l spaced_r')


LOG = False

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')
fn_db = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'completion-db.json')

CFG_SECTION = "bootstrap_complete"
PROJ_VERSIONS = 'bootstrap_complete_versions'
# https://infra.spec.whatwg.org/#ascii-whitespace
CLASS_SEP = {'"',  "'",  '\x09', '\x0a', '\x0c', '\x0d', '\x20'}
SNIP_ID = 'strap_snip'
# 5 groups - attributes
# ^ first - all combined, + two - quoted, + unquoted name present, + unquoted empty
CLASS_ATTR_PTRN = re.compile('\\bclass=("([^"]*)|\'([^\']*)|(\w[^\s>]*)|())')

opt_versions = [4]  # default, when project versions is missing


def r_enumerate(l):
    """ reversed enumerate """
    i = len(l) - 1
    for it in reversed(l):
        yield (i,it)
        i -= 1

class Command:

    def __init__(self):
        global opt_versions

        _versions = ini_read(fn_config, CFG_SECTION, 'versions', '')
        if _versions:
            opt_versions = list(map(int, _versions.split(',')))

        self._data = None

        self._prefixes = None
        self._comp_cfgs = None

    @property
    def comp_items(self):
        if self._data is None:

            from .completion_db import DATA

            self._data = DATA
        return self._data

    def get_items(self, prefix, versions):
        """ returns generator of bootstrap completion items matching
            specified class-name prefix and versions
        """
        pass;       LOG and print(f'--- bstrap: get compeltion items for: {prefix, versions}')
        it = iter(self.comp_items)
        while True:
            ver = next(it, None)
            if ver is None:
                return
            val = next(it)
            if ver in versions  and  val.startswith(prefix):
                yield val,ver

    def get_versions(self):
        """ returns a list of acceptable versions; from project - if opened, or `opt_versions` option value
        """

        if 'cuda_project_man' in sys.modules:

            import cuda_project_man as p

            _pvars = p.global_project_info.get('vars')
            if _pvars is not None:
                # find my versions option string
                ver_op_str = next(filter(lambda s: s.startswith(PROJ_VERSIONS+'='), _pvars), None)
                if ver_op_str:
                    val_str = ver_op_str[len(PROJ_VERSIONS)+1:]
                    return list(map(int, val_str.split(',')))

        return opt_versions


    def config(self):
        _versions_str = ','.join(map(str, opt_versions))
        ini_write(fn_config, CFG_SECTION, 'versions', _versions_str )
        file_open(fn_config)

    def config_proj(self):

        import cuda_project_man as p

        if p.global_project_info.get('filename'):
            vars_ = p.global_project_info.get('vars')
            # open project properties window if option is already present
            if vars_  and  any(s.startswith(PROJ_VERSIONS+'=') for s in vars_):
                app_proc(PROC_EXEC_PLUGIN, 'cuda_project_man,config_proj,')
                return

            _msg = 'To set Bootstrap versions per project, add the following option to the Project Properties dialog:\n' \
                    '  bootstrap_complete_versions=<versions>\n\n' \
                    'Where <versions> is a comma-separated string of integers.\n'\
                    'Press OK to open the Project Properties dialog now.'
            res = msg_box(_(_msg), MB_OKCANCEL + MB_ICONINFO)
            if res == ID_OK:
                # open project properties window
                app_proc(PROC_EXEC_PLUGIN, 'cuda_project_man,config_proj,')
        else:
            msg_status(_('No project opened'))


    def on_complete(self, ed_self):
        """ shows completion dialog: `ed_self.complete_alt()`
        """
        pass;       LOG and print(f'- bstrap compelte')
        carets = ed_self.get_carets()
        if not all(c[3]==-1 for c in carets):   # abort if selection
            return

        try:
            comp_cfgs = [_get_caret_completion_cfg(ed_self, c) for c in carets]
        except InvalidCaretException as ex:
            pass;       LOG and print(f'.bstrap fail: {ex}')
            return

        # possble prefixes set: single empty, single, multiple
        prefixes = {cfg.word_prefix for cfg in comp_cfgs}
        _prefix = next(iter(prefixes))  if len(prefixes) == 1 else  ''
        # completion items
        items = list(set( self.get_items(_prefix, set(self.get_versions())) ))
        if not items:
            pass;       LOG and print(f'.no matching completion: `{_prefix}*`')
            return
        pass;       LOG and print(f' -- prefixes: {prefixes}')

        if len(carets) > 1:
            # leave only first caret so `ed.complete_alt` can work
            ed_self.set_caret(carets[0][0], carets[0][1])

        self._comp_cfgs = comp_cfgs
        self._prefixes = prefixes

        items = _merge_item_versions(items)
        compl_text = '\n'.join('{0}\tBootstrap: {1}\t{0}'.format(txt, vers) for txt,vers in items)
        ed_self.complete_alt(compl_text, SNIP_ID, 0)
        return True


    def on_snippet(self, ed_self, snippet_id, snippet_text):
        """ places chosen completion item
            places carets after completion
        """
        if snippet_id != SNIP_ID:       return

        pass;       LOG and print(f'- bstrap: on snip: {snippet_text}')

        replace_attr = len(self._comp_cfgs) > 1     # if multicaret - replace whole attribute value
        new_carets = []
        for cc in self._comp_cfgs:
            caret = _complete(ed_self, snippet_text, cc, replace_attr)
            new_carets.append(caret)

        _set_carets(ed_self, new_carets)

        self._prefixes = None
        self._comp_cfgs = None


def _complete(ed_self, snippet_text, comp_cfg, replace_attr=False):
    if replace_attr:
        return ed_self.replace(*comp_cfg.attr_range, snippet_text)
    else:
        if   not comp_cfg.spaced_l:   snippet_text = ' '+snippet_text
        elif not comp_cfg.spaced_r:   snippet_text = snippet_text+' '
        return ed_self.replace(*comp_cfg.word_range, snippet_text)


def _set_carets(ed_self, carets):
    ed_self.set_caret(*carets[0], options=CARET_OPTION_NO_SCROLL)
    for caret in carets[1:]:
        ed_self.set_caret(*caret, id=CARET_ADD, options=CARET_OPTION_NO_SCROLL)


prefix_len = len('class=')

def _get_caret_completion_cfg(ed_self, caret):
    """ returns `ConpCfg` -- info about what to be replaced with completion on specified caret position
        raises `InvalidCaretException` if caret position cannot be processed
    """
    x,y = caret[:2]
    line = ed_self.get_text_line(y)
    if x > len(line):
        raise InvalidCaretException("Caret is beyond text")

    for m in CLASS_ATTR_PTRN.finditer(line):
        start,end = m.span(0)
        #print(f' -- match: {(start, x, end), m}')
        if start <= x <= end: # TODO test
            if x-start >= prefix_len:
                # found match range for caret - `m`
                break
            else:
                raise InvalidCaretException("Caret is outside of class attribute 2")
    else:
        raise InvalidCaretException("Caret is outside of class attribute 1")

    #print(f' -- success match: {m, m.groups()}')

    # verify caret in matched attribute span
    attr_val = m[1]
    gx0,gx1 = m.span(1)
    #print(f' -- match attrr: span {m.span(1), attr_val}, caret: {x}')

    if not (gx0 <= x <= gx1):
        raise InvalidCaretException("Caret is outside of attribute value")

    if not attr_val:    # empty attr value, quoted or not
        prefix = ''
        word_range = attr_range = (gx0,y, gx1,y)  # empty range
        spaced_l = spaced_r = True
        #print(f' --- match -- empty range')
    else:       # attr is populated
        class_name_x0 = next((i for i in range(x-1, gx0-1, -1) if line[i] in CLASS_SEP), gx0-1) + 1
        class_name_x1 = next((i for i in range(x, gx1)  if line[i] in CLASS_SEP), gx1)
        #print(f' --- match -- class_name: {line[:class_name_x0], line[class_name_x0:x], line[x:class_name_x1], class_name_x0, class_name_x1, }')

        # if unquoted class name present - replace it -- no spacing
        if class_name_x0 == x  and  attr_val[0] in {'"', "'"}:  class_name_x1 = class_name_x0

        prefix = line[class_name_x0:x]
        word_range = (class_name_x0,y,  class_name_x1,y)
        attr_range = (gx0,y, gx1,y)
        spaced_l = True    # never a need for spacing to left?
        spaced_r = x == gx1  or  class_name_x1 == gx1  or  line[class_name_x1] in CLASS_SEP

    cc = CompCfg(word_prefix=prefix, word_range=word_range, attr_range=attr_range,
                    spaced_l=spaced_l, spaced_r=spaced_r)
    pass;       LOG and print(f'NOTE: comp cfg: {cc}')
    return cc


def _merge_item_versions(comp_items):
    comp_items.sort(key=lambda a: (a[0].lower(), a[1]) )
    comp_items.append((None, 0)) # last - fake item -- to send last real item in the for loop

    last_s = None
    vers = []
    for s,ver in comp_items:
        if last_s != s  and  last_s:
            yield (last_s, ' '.join(map(str, vers)))
            vers.clear()

        last_s = s
        vers.append(ver)


class InvalidCaretException(Exception):
    pass
