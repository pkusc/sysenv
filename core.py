#!/usr/bin/env python


"""

This file should NOT be directly used by users.
Please use functions in `sysenv/env.bashrc` instead.
Currently these functions are:
    * env-reload
    * env-mpi-select
    * env-edit


Usage:
    python sysenv/core.py <action> <env_conf_path> <out_path>

    <action> could be:
        * "reload"
        * "mpi-select"

    <env_conf_path>:
        This is where the environment configuration file is placed, usually `$HOME/env.conf`.

    <out_path>:
        This is where the output bashrc file will be placed.
        The output file should immediately be sourced (by functions in `env.bashrc`).

"""

from __future__ import print_function
from collections import defaultdict
import sys
import json
import os
import copy
import codecs
import string
import re

g_StrExpandPattern = re.compile(r"""
    \$ (?: (?P<dollar>\$)                           # tuple index: 0
         | (?P<raw>[A-Za-z_][A-Za-z0-9_]*)          # tuple index: 1
         | {(?P<brace>\.?[A-Za-z_][A-Za-z0-9_.]*)}  # tuple index: 2
         | (?P<invalid>.|$)                         # tuple index: 3
         )""", re.VERBOSE | re.DOTALL)


g_EnvCoufPath = ""
g_OutPath = ""
g_OutMetaPath = ""


def expand_string_one_impl(template, known_map):

    # Helper function for .sub()
    def convert(match):
        # Check the most common path first.
        name = match.group("raw") or match.group("brace")
        if name is not None:
            return known_map[name] if (name in known_map) else ""
        elif match.group("dollar") is not None:
            return "$"
        elif match.group("invalid") is not None:
            raise ValueError("Unrecognized variable definition in %s" % template)

    return g_StrExpandPattern.sub(convert, template)


def query_expand_string_vars(template):
    found = g_StrExpandPattern.findall(template)
    result = set()
    for tuple4 in found:  # tuple4 = (P<dollar>, P<raw>, P<brace>, P<invalid>)
        if len(tuple4[1]) > 0:      # P<raw>
            result.add(tuple4[1])
        elif len(tuple4[2]) > 0:    # P<brace>
            result.add(tuple4[2])
        elif len(tuple4[3]) > 0:    # P<invalid>
            raise ValueError("Unrecognized variable definition in %s" % template)
    return list(result)


def expand_string_one(template, var_list, known_maps):
    #
    # `known_maps` looks like:
    # {
    #   "var1": [ "value11", "value12" ],
    #   "var2": [ "value21", "value22" ],
    #   ...
    # }
    #
    # `template` looks like:
    #   "This is $$, $var1 $var2 $var_non_existent"
    #
    # Returns a list of string: the expanded results. (Cartesian product)
    #
    for var in var_list:
        assert (var in known_maps)
        assert (len(known_maps[var]) >= 1)

    result = []

    dicts = [[], []]
    which = 0
    for var in var_list:
        other = 1 - which
        dicts[which] = []
        if len(dicts[other]) == 0:
            for s in known_maps[var]:
                dicts[which].append({var: s})
        else:
            for d in dicts[other]:
                for s in known_maps[var]:
                    newd = copy.deepcopy(d)
                    assert (var not in newd)
                    newd[var] = s
                    dicts[which].append(newd)
        which = other

    if len(dicts[1 - which]) == 0:
        result.append(expand_string_one_impl(template, {}))
    else:
        for var_dict in dicts[1 - which]:
            # print(var_dict)
            result.append(expand_string_one_impl(template, var_dict))

    # print(result)
    return result


def restore_env():
    unset_vars = []
    result = copy.deepcopy(os.environ)
    if not os.path.isfile(g_OutMetaPath):
        return result, unset_vars

    # Meta file structure:
    # {
    #   "conf": {
    #     "env_name1": [ "v11", "v12", ... ],
    #     "env_name2": [ "v21", "v22", ... ],
    #     ...
    #   },
    #   "create": [
    #     "env_nameX", "env_nameY", ...
    #   ]
    # }
    with codecs.open(g_OutMetaPath, "r", "utf-8") as metaFile:
        meta = json.load(metaFile)
        old_conf = meta["conf"]
        old_create = meta["create"]

    for env_name in old_conf:
        if env_name not in result:
            continue
        for env_value in old_conf[env_name]:
            if result[env_name] == env_value:
                result[env_name] = ""
            elif result[env_name].startswith(env_value + ":"):
                result[env_name] = result[env_name][len(env_value) + 1:]
            elif result[env_name].endswith(":" + env_value):
                result[env_name] = result[env_name][:-(len(env_value) + 1)]
            else:
                result[env_name] = result[env_name].replace(":" + env_value + ":", ":")

        # If the variable is empty now, and it's created by the last reload,
        # remove this variable.
        if (len(result[env_name]) == 0) and (env_name in old_create):
            del result[env_name]
            unset_vars.append(env_name)

    return result, unset_vars


def expand_strings(curr_conf):
    (curr_env, unset_vars) = restore_env()
    expand_as = {}
    status_done = {}

    result = {}
    created_vars = set()

    def inner_expand(name):
        if name in status_done:
            if status_done[name]:
                return
            else:
                raise RuntimeError("Recursive environment variable dependency in '%s'" % name)
        status_done[name] = False
        expand_as[name] = []

        if name in curr_conf:
            if name not in curr_env:
                created_vars.add(name)

            result[name] = []
            for line in curr_conf[name]:
                # print(line)
                var_list = query_expand_string_vars(line)
                for match_name in var_list:
                    inner_expand(match_name)
                expanded = expand_string_one(line, var_list, expand_as)
                result[name] += expanded
                expand_as[name] += expanded
                # print()

        # Append existing system environments
        if name in curr_env:
            expand_as[name] += filter(lambda s: len(s) > 0, curr_env[name].split(':'))

        # If the variable doesn't exist at last, specify an empty string.
        # Just as if the system had defined it an empty string.
        if len(expand_as[name]) == 0:
            expand_as[name].append("")

        status_done[name] = True

    for env_name in curr_conf:
        inner_expand(env_name)

    return curr_env, result, list(created_vars), unset_vars


def read_conf_file():
    result = defaultdict(list)
    current_lists = None
    patten = re.compile(r'\s*(\.?[A-Za-z_][A-Za-z0-9_]*)\s*')
    with codecs.open(g_EnvCoufPath, 'r', 'utf-8') as conffile:
        for line in conffile:
            line = line.strip("\r\n\t ")

            # Skip empty lines & comments
            if len(line) == 0 or line.startswith('#'):
                continue

            if line[0] == '[' and line[-1] == ']':  # Now starting a new section
                current_lists = list(map(lambda name: result[name], patten.findall(line[1:-1])))
                if len(current_lists) == 0:
                    raise ValueError("The environment name '%s' is invalid" % line)
            else:
                # Check that only legal characters are in this line
                #if '\\' in line:
                #    raise ValueError("The following line contains invalid character(s): %s" % line)

                # Replace head '~' with $HOME
                if line[0] == '~':
                    if g_Home is None:
                        raise ValueError("'~' is used, but $HOME is not set")
                    line = "$HOME" + line[1:]

                for current_list in current_lists:
                    current_list.append(line)

    return result


def env_reload():
    curr_conf = read_conf_file()
    (curr_env, new_conf, created_vars, unset_vars) = expand_strings(curr_conf)

    # Serialize to meta file
    with codecs.open(g_OutMetaPath, "w", "utf-8") as metafile:
        json.dump({"conf": new_conf, "create": created_vars}, metafile)

    # Print the result
    with codecs.open(g_OutPath, "w", "utf-8") as outfile:
        for env_name in new_conf:
            if env_name.startswith("."):
                continue
            if env_name in unset_vars:
                unset_vars.remove(env_name)

            if env_name in curr_env:
                outline = ":".join(new_conf[env_name] + [curr_env[env_name]])
            else:
                outline = ":".join(new_conf[env_name])
            outline = outline.replace("\\", "\\\\").replace('"', '\\"').replace('$', '\\$')
            outfile.write('export %s="%s"\n' % (env_name, outline))

        for env_name in unset_vars:
            outfile.write('unset "%s"\n' % env_name)

        # These are previously modified variables, but now they are NOT in env.conf file.
        # Restore them to the original values
        for env_name in curr_env:
            if (env_name in new_conf) or (env_name in unset_vars):
                continue
            if curr_env[env_name] == os.environ[env_name]:
                continue
            outline = curr_env[env_name]
            outline = outline.replace("\\", "\\\\").replace('"', '\\"').replace('$', '\\$')
            outfile.write('export %s="%s"\n' % (env_name, outline))


if __name__ == "__main__":
    # Number of arguments should be 4
    # [ "core.py" "<action>" "<env_conf_path>" "<out_path>" ]
    if len(sys.argv) != 4:
        raise SyntaxError("[FATAL] There should be exactly 3 parameters")

    g_EnvCoufPath = sys.argv[2]
    g_OutPath = sys.argv[3]
    g_OutMetaPath = g_OutPath + ".meta"
    g_Home = os.environ["HOME"] or None

    if sys.argv[1] == 'reload':
        env_reload()
    elif sys.argv[1] == 'mpi-select':
        #env_mpi_select()
        pass
    else:
        raise SyntaxError("[FATAL] Action '%s' is not defined" % sys.argv[1])

