import os
import sys
import json
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
PREFIX = 'class="'
CLASS_SEP = {'"',  '\x09', '\x0a', '\x0c', '\x0d', '\x20'} # https://infra.spec.whatwg.org/#ascii-whitespace
SNIP_ID = 'strap_snip'

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
                yield val

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

        items.sort(key=lambda a:a.lower())
        compl_text = '\n'.join('{0}\t\t{0}'.format(txt) for txt in items)
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


def _get_caret_completion_cfg(ed_self, caret):
    """ returns `ConpCfg` -- info about what to be replaced with completion on specified caret position
        raises `InvalidCaretException` if caret position cannot be processed
    """
    x,y = caret[:2]
    line = ed_self.get_text_line(y)
    if x > len(line):
        raise InvalidCaretException("Caret is beyond text")

    line_,_line = line[:x],line[x:]
    x_attr_start = line_.rfind(PREFIX)
    if x_attr_start == -1:
        raise InvalidCaretException("Caret is outside of class attribute 1")
    x_attr_x0 = x_attr_start + len(PREFIX)
    _attr_2_end = _line.find('"')
    x_attr_x1 = len(line)  if _attr_2_end == -1 else  len(line_)+_attr_2_end

    # abort if there is `"` between caret and class-attribute-value-start
    if line_.find('"', x_attr_x0) != -1:
        raise InvalidCaretException(f"Caret is outside of class attribute 2")

    class_name_x0 = next(i for i,ch in r_enumerate(line_) if ch in CLASS_SEP) + 1
    class_name_x1 = next((i for i,ch in enumerate(_line)  if ch in CLASS_SEP), len(_line)) + len(line_)

    # if at the edge of word - make zero-len range
    if class_name_x0 == len(line_):     class_name_x1 = class_name_x0   # at start of word

    prefix = line_[class_name_x0:]
    word_range = (class_name_x0,y,  class_name_x1,y)
    attr_range = (x_attr_x0,y, x_attr_x1,y)
    # check if have space or quote to the left or right
    spaced_l = line[class_name_x0-1] in CLASS_SEP
    spaced_r = class_name_x1 == len(line)  or  line[class_name_x1] in CLASS_SEP
    return CompCfg(word_prefix=prefix, word_range=word_range, attr_range=attr_range,
                    spaced_l=spaced_l, spaced_r=spaced_r)


class InvalidCaretException(Exception):
    pass
