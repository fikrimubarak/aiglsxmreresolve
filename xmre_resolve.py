#!/usr/bin/env python3
"""
AIGLSXMRERESOLVE - GLS XMRE Signal Resolver v1.0
==================================================

Resolves Cross-Module Reference Errors (XMRE) from GLS elaboration by searching
the corresponding GLS partition netlist (.pt_nonpg.v.gz) for matching signals.

For each XMRE error block, the tool identifies the unresolved RTL signal path and
searches using three strategies:
  Case 1: TOKEN.SIGNAL  -> escaped net \\TOKEN_SIGNAL[bit]  (synthesis flattening)
  Case 2: plain TOKEN   -> hierarchical port search (output/inout, up to 2 levels)
  Case 3: TOKEN.SIGNAL  -> register flop instance TOKEN_reg_SIGNAL.o
                           or auto_vector_..._MBIT_....oN

Matched signals are written to xmre_match; unresolved to xmre_unmatch.

Features:
- Escaped net name search with fuzzy numeric index matching (_N_ -> _[0-9]+_)
- Full module hierarchy map built from netlist (86K+ modules)
- SYNOPSYS_UNCONNECTED port filtering (excludes disconnected nets)
- INPUT port sub-hierarchy placement (handcode_rdata_ ports routed to sub-instance)
- Register flop and auto_vector instance detection with output port resolution

Usage:
    python3 xmre_resolve.py <xmre_log> <partition_dir> [-o OUTPUT_DIR]

Author: Fikri (raden.ali.fikri.mubarak@intel.com)
AI Assistant: GitHub Copilot (Claude Sonnet 4.5 - 202502)
Repository: /nfs/site/disks/zsc16_rmubarak_stod001/aitest/aiglsxmreresolve/
Documentation: README.md, QUICK_START.md
Version: 1.0 (2026-02-20)
"""

import argparse
import gzip
import os
import re
import subprocess
import sys


# ============================================================================
# COMMAND LINE ARGUMENTS
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='AIGLSXMRERESOLVE - GLS XMRE Signal Resolver v1.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage (output in current directory)
  %(prog)s parpmc_xmre_messages.log ./GLS/

  # Specify output directory
  %(prog)s parpmc_xmre_messages.log ./GLS/ -o ./results/

  # Short form
  %(prog)s parpmc_xmre_messages.log /path/to/GLS_dir/ -o /tmp/xmre_out/

  # Get help
  %(prog)s --help

For more information, see README.md or QUICK_START.md
        '''
    )
    parser.add_argument(
        'xmre_log',
        help='Path to the XMRE message log file (e.g. parpmc_xmre_messages.log)'
    )
    parser.add_argument(
        'partition_dir',
        help='Directory containing <partition>.pt_nonpg.v.gz netlist file'
    )
    parser.add_argument(
        '-o', '--output-dir',
        default=None,
        metavar='DIR',
        help='Directory to write xmre_match and xmre_unmatch (default: current working directory)'
    )
    return parser.parse_args()


def resolve_paths(args):
    """Resolve and validate all file paths from parsed arguments."""
    xmre_log = os.path.abspath(args.xmre_log)
    if not os.path.isfile(xmre_log):
        sys.exit(f"ERROR: XMRE log not found: {xmre_log}")

    partition_dir = os.path.abspath(args.partition_dir)
    if not os.path.isdir(partition_dir):
        sys.exit(f"ERROR: Partition directory not found: {partition_dir}")

    output_dir = os.path.abspath(args.output_dir) if args.output_dir else os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    return xmre_log, partition_dir, output_dir


def get_partition_from_block(block):
    """Extract partition name from the pcd_tb.pcd.<partition>. signal path in an XMRE block."""
    m = re.search(r'pcd_tb\.pcd\.(\w+)\.', block)
    return m.group(1) if m else None


# ============================================================================
# NETLIST PARSER - builds module hierarchy map
# ============================================================================


def build_module_map(netlist):
    """
    Parse the GLS netlist and build a module hierarchy map.

    Returns:
        modules dict:  modules[name] = {
            'ports':     {port_name: direction ('input'|'output'|'inout')},
            'instances': {inst_name: {'mod_type': str, 'unconnected_ports': set()}}
        }
    """
    print(f"  Building module map for {os.path.basename(netlist)}...", flush=True)
    modules = {}
    current_module = None
    in_instance = False
    current_inst_name = None
    current_inst_text = ''
    paren_depth = 0
    KEYWORDS = {
        'input', 'output', 'inout', 'wire', 'reg', 'assign', 'module', 'endmodule',
        'always', 'initial', 'if', 'else', 'case', 'for', 'begin', 'end', 'parameter',
        'localparam', 'function', 'task', 'generate', 'genvar'
    }

    with gzip.open(netlist, 'rt', errors='replace') as f:
        for line in f:
            s = line.strip()

            if in_instance:
                current_inst_text += ' ' + s
                paren_depth += s.count('(') - s.count(')')
                if paren_depth <= 0:
                    for m in re.finditer(r'\.(\w+)\s*\(\s*SYNOPSYS_UNCONNECTED', current_inst_text):
                        modules[current_module]['instances'][current_inst_name]['unconnected_ports'].add(m.group(1))
                    in_instance = False
                    current_inst_text = ''
                    paren_depth = 0
                continue

            # Module declaration
            m = re.match(r'^module\s+(\w+)\b', s)
            if m:
                current_module = m.group(1)
                if current_module not in modules:
                    modules[current_module] = {'ports': {}, 'instances': {}}
                continue

            if s.startswith('endmodule'):
                current_module = None
                continue

            if current_module is None:
                continue

            # Port declaration: input/output/inout [optional_width] signal_name ;
            m = re.match(r'^(input|output|inout)\b\s+(?:\\)?(?:\[[^\]]*\]\s+)?(\S+?)\s*;', s)
            if m:
                modules[current_module]['ports'][m.group(2)] = m.group(1)
                continue

            # Instance: module_type inst_name (
            m = re.match(r'^(\w+)\s+(\w+)\s*\(', s)
            if m and m.group(1) not in KEYWORDS:
                mod_type, inst_name = m.group(1), m.group(2)
                modules[current_module]['instances'][inst_name] = {
                    'mod_type': mod_type,
                    'unconnected_ports': set()
                }
                depth = s.count('(') - s.count(')')
                if depth <= 0:
                    for pm in re.finditer(r'\.(\w+)\s*\(\s*SYNOPSYS_UNCONNECTED', s):
                        modules[current_module]['instances'][inst_name]['unconnected_ports'].add(pm.group(1))
                else:
                    in_instance = True
                    current_inst_name = inst_name
                    current_inst_text = s
                    paren_depth = depth

    print(f"  Loaded {len(modules)} modules", flush=True)
    return modules


def build_synopsys_port_set(netlist):
    """Build a set of port names that are connected to SYNOPSYS_UNCONNECTED in the netlist."""
    print("Building synopsys port set...", flush=True)
    r = subprocess.run(
        ["zgrep", "-oE", r'\.[^ ]+ \( SYNOPSYS_UNCONNECTED', netlist],
        capture_output=True, text=True
    )
    synopsys_ports = set()
    for line in r.stdout.splitlines():
        port = line.split(' ')[0].lstrip('.')
        if port:
            synopsys_ports.add(port)
    print(f"  {len(synopsys_ports)} unique synopsys-unconnected ports", flush=True)
    return synopsys_ports


# ============================================================================
# SIGNAL SEARCH HELPERS
# ============================================================================

def get_module_type(modules, inst_name):
    """Return all module types that inst_name is instantiated as (across all parent modules)."""
    found = set()
    for mod in modules.values():
        if inst_name in mod['instances']:
            found.add(mod['instances'][inst_name]['mod_type'])
    return found


def find_signal_paths(modules, parent_module_type, signal_name, max_depth=2):
    """
    Search for signal_name as an output/inout port within parent_module_type hierarchy.
    Rules:
      - Exclude input ports
      - Exclude output ports connected to SYNOPSYS_UNCONNECTED in their parent instance
    Returns sorted list of relative paths (e.g. 'subinst.signal_name').
    """
    results = []

    def search(mod_type, prefix, depth, containing_mod, containing_inst):
        if mod_type not in modules:
            return
        if signal_name in modules[mod_type]['ports']:
            direction = modules[mod_type]['ports'][signal_name]
            if direction != 'input':
                unconn = (modules.get(containing_mod, {})
                          .get('instances', {})
                          .get(containing_inst, {})
                          .get('unconnected_ports', set()))
                if signal_name not in unconn:
                    results.append((prefix + signal_name, direction))
        if depth >= max_depth:
            return
        for inst, inst_data in modules[mod_type]['instances'].items():
            search(inst_data['mod_type'], prefix + inst + '.', depth + 1, mod_type, inst)

    if parent_module_type in modules:
        for inst, inst_data in modules[parent_module_type]['instances'].items():
            search(inst_data['mod_type'], inst + '.', 1, parent_module_type, inst)

    return sorted(set(results))


def zgrep_E(pattern, netlist):
    """Run zgrep -oE and return sorted unique non-empty matches."""
    r = subprocess.run(["zgrep", "-oE", pattern, netlist], capture_output=True, text=True)
    return sorted(set(l.strip() for l in r.stdout.splitlines() if l.strip()))


def fuzzy_index_pat(name):
    """Replace _N_ and trailing _N with _[0-9]+_ / _[0-9]+ to handle GLS index changes."""
    p = re.sub(r'_(\d+)_', '_[0-9]+_', name)
    p = re.sub(r'_(\d+)$', '_[0-9]+', p)
    return p


# ============================================================================
# MATCHING LOGIC
# ============================================================================

def resolve_block(block, partition, modules, synopsys_ports, netlist):
    """
    Resolve one XMRE block. Returns (path_line, sch_paths) or (path_line, []) on no match.
    Returns (None, None) if the block cannot be parsed.
    """
    m = re.search(r"token '([^']+)'", block)
    if not m:
        return None, None
    token = m.group(1)

    path_line = None
    for line in block.splitlines():
        if f"pcd_tb.pcd.{partition}" in line:
            pm = re.search(r'(pcd_tb\.pcd\.' + partition + r'[\w\.\[\]\\$]+)', line)
            if pm:
                path_line = pm.group(1).rstrip(';),')
                break
    if not path_line:
        return None, None

    def _zgrep(pat):
        return zgrep_E(pat, netlist)

    def is_valid(sig):
        return sig not in synopsys_ports

    after_match = re.search(re.escape(token) + r'\.([\w\[\]]+)', path_line)

    if after_match:
        # Case 1: TOKEN.SIGNAL → escaped net \[prefix_]TOKEN[_suffix]_SIGNAL[bit]
        signal_after = after_match.group(1)
        sig_esc = signal_after.replace('[', r'\[').replace(']', r'\]')

        grep_pat = r'\\[^ ]*' + re.escape(token) + r'[^ ]*_' + sig_esc + r'[^ ]* '
        found = _zgrep(grep_pat)
        if not found:
            fuzzy = fuzzy_index_pat(token)
            if fuzzy != token:
                grep_pat = r'\\[^ ]*' + fuzzy + r'[^ ]*_' + sig_esc + r'[^ ]* '
                found = _zgrep(grep_pat)

        hier_end = path_line.rfind('.' + token + '.' + signal_after)
        hier_prefix = path_line[:hier_end]

        # Resolve hierarchy for each found signal (INPUT ports live one level deeper)
        last_inst = hier_prefix.split('.')[-1]
        parent_mods = get_module_type(modules, last_inst)
        sch_paths = []
        for sig in found:
            if not is_valid(sig):
                continue
            bare = sig.lstrip('\\')
            placed = False
            for pmt in parent_mods:
                if pmt not in modules:
                    continue
                if bare in modules[pmt]['ports']:
                    sig_type = modules[pmt]['ports'][bare]
                    sch_paths.append((hier_prefix + '.' + sig, sig_type))
                    placed = True
                    break
                for subinst_name, subinst_data in modules[pmt]['instances'].items():
                    sm = subinst_data['mod_type']
                    if (sm in modules
                            and bare in modules[sm]['ports']
                            and modules[sm]['ports'][bare] == 'input'):
                        sch_paths.append((hier_prefix + '.' + subinst_name + '.' + sig, 'input'))
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                sch_paths.append((hier_prefix + '.' + sig, 'common'))  # fallback

        # Case 3: register flop / auto_vector instance  TOKEN_reg_SIGNAL_N  → .o / .oN
        def reg_search(tok_pat, sig_pat):
            pat = r'^[^ ]+ [^ ]*' + tok_pat + r'_reg_' + sig_pat + r'[^ ]* \('
            return _zgrep(pat)

        sig_esc2 = re.escape(signal_after)
        reg_lines = reg_search(re.escape(token), sig_esc2)
        if not reg_lines:
            fuzzy = fuzzy_index_pat(token)
            if fuzzy != token:
                reg_lines = reg_search(fuzzy, sig_esc2)

        search_key = token + '_reg_' + signal_after
        for line in reg_lines:
            parts = line.split()
            if len(parts) < 2:
                continue
            inst_name = parts[1]
            if inst_name.startswith('auto_vector_'):
                body = inst_name[len('auto_vector_'):]
                segments = body.split('_MBIT_')
                port = None
                for i, seg in enumerate(segments):
                    if search_key in seg:
                        port = f'o{i + 1}'
                        break
                if port:
                    sch_paths.append((hier_prefix + '.' + inst_name + '.' + port, 'output'))
            else:
                sch_paths.append((hier_prefix + '.' + inst_name + '.o', 'output'))

        sch_paths = sorted(set(sch_paths))

    else:
        # Case 2: TOKEN at end → escaped exact/fuzzy search + hierarchical port search
        token_clean = token.split('[')[0]
        hier_prefix = '.'.join(path_line.split('.')[:-(1)])
        path_parts = [p for p in path_line.replace('\\', '').split('.') if p]
        try:
            tidx = next(i for i, p in enumerate(path_parts) if p.split('[')[0] == token_clean)
            parent_inst = path_parts[tidx - 1] if tidx > 0 else None
        except StopIteration:
            parent_inst = None

        sch_paths = []
        grep_pat = r'\\[^ ]*' + re.escape(token_clean) + r'[^ ]* '
        escaped = _zgrep(grep_pat)
        if not escaped:
            fuzzy = fuzzy_index_pat(token_clean)
            if fuzzy != token_clean:
                grep_pat = r'\\[^ ]*' + fuzzy + r'[^ ]* '
                escaped = _zgrep(grep_pat)
        for sig in escaped:
            sch_paths.append((hier_prefix + '.' + sig, 'common'))
        if parent_inst:
            for pmt in get_module_type(modules, parent_inst):
                for sp, direction in find_signal_paths(modules, pmt, token_clean, max_depth=2):
                    sch_paths.append((hier_prefix + '.' + sp, direction))
        sch_paths = sorted(set(sch_paths))

    return path_line, sch_paths


# ============================================================================
# OUTPUT WRITER
# ============================================================================

def write_outputs(matches, unmatches, output_dir):
    """Write xmre_match and xmre_unmatch files with 1-based RTL/SCH indexing."""
    match_out = []
    unmatch_out = []
    seen_rtl = {}

    for _idx, rtl, schs in matches:
        if rtl not in seen_rtl:
            seen_rtl[rtl] = True
            n = len(seen_rtl)
            block_lines = [f"RTL_{n} {rtl}"]
            for si, (sch, sig_type) in enumerate(schs):
                block_lines.append(f"SCH_{n}_{si + 1} {sch} {sig_type}")
            match_out.append("\n".join(block_lines))

    seen_unmatch = {}
    for _idx, rtl in unmatches:
        if rtl not in seen_unmatch:
            seen_unmatch[rtl] = True
            n = len(seen_unmatch)
            unmatch_out.append(f"RTL_{n} {rtl}")

    match_path = os.path.join(output_dir, "xmre_match")
    unmatch_path = os.path.join(output_dir, "xmre_unmatch")

    with open(match_path, "w") as f:
        f.write("\n\n".join(match_out) + "\n")
    with open(unmatch_path, "w") as f:
        f.write("\n".join(unmatch_out) + "\n")

    print(f"Written {match_path}")
    print(f"Written {unmatch_path}")

    return seen_rtl, seen_unmatch


# ============================================================================
# MAIN
# ============================================================================

def main():
    args = parse_args()
    xmre_log, partition_dir, output_dir = resolve_paths(args)

    print("=" * 72)
    print("AIGLSXMRERESOLVE - GLS XMRE Signal Resolver")
    print("=" * 72)
    print()
    print(f"XMRE log:      {xmre_log}")
    print(f"Partition dir: {partition_dir}")
    print(f"Output dir:    {output_dir}")
    print()

    print("Parsing XMRE log...", flush=True)
    with open(xmre_log) as f:
        content = f.read()
    blocks = re.split(r'(?=Error-\[XMRE\])', content)
    blocks = [b.strip() for b in blocks if b.strip()]
    print(f"  {len(blocks)} XMRE blocks found", flush=True)

    # Lazy per-partition caches (module map + synopsys port set)
    module_map_cache = {}
    synopsys_cache = {}

    matches = []
    unmatches = []
    for idx, block in enumerate(blocks):
        partition = get_partition_from_block(block)
        if not partition:
            continue

        # Load netlist for this partition on first encounter
        if partition not in module_map_cache:
            netlist = os.path.join(partition_dir, f"{partition}.pt_nonpg.v.gz")
            if not os.path.isfile(netlist):
                print(f"  WARNING: Netlist not found for partition '{partition}': {netlist}", flush=True)
                unmatches.append((idx, f"<netlist missing: {partition}>"))
                continue
            print(f"Loading partition: {partition}", flush=True)
            module_map_cache[partition] = build_module_map(netlist)
            synopsys_cache[partition] = build_synopsys_port_set(netlist)

        netlist = os.path.join(partition_dir, f"{partition}.pt_nonpg.v.gz")
        modules = module_map_cache[partition]
        synopsys_ports = synopsys_cache[partition]

        path_line, sch_paths = resolve_block(block, partition, modules, synopsys_ports, netlist)
        if path_line is None:
            continue
        if sch_paths:
            matches.append((idx, path_line, sch_paths))
        else:
            unmatches.append((idx, path_line))

    partitions_used = sorted(module_map_cache.keys())
    print(f"\nPartitions processed: {', '.join(partitions_used)}")
    print(f"Total: {len(matches)} matched, {len(unmatches)} unmatched out of {len(blocks)}")

    seen_rtl, seen_unmatch = write_outputs(matches, unmatches, output_dir)

    # Validation
    n_xmre = len(blocks)
    n_total_rtl = len(seen_rtl) + len(seen_unmatch)
    print()
    print("=" * 72)
    print("Resolution Complete")
    print("=" * 72)
    print(f"✓ Matched:   {len(seen_rtl)} RTL entries")
    print(f"○ Unmatched: {len(seen_unmatch)} RTL entries")
    print()
    print("Results written to:")
    print(f"  - {os.path.join(output_dir, 'xmre_match')}")
    print(f"  - {os.path.join(output_dir, 'xmre_unmatch')}")
    print()
    print("Validation:")
    print(f"  XMRE messages        : {n_xmre}")
    print(f"  xmre_match  entries  : {len(seen_rtl)}")
    print(f"  xmre_unmatch entries : {len(seen_unmatch)}")
    print(f"  Total unique RTL     : {n_total_rtl}")
    if n_xmre == n_total_rtl:
        print("  CHECK PASSED: counts match")
    else:
        print(f"  WARNING: {n_xmre} XMRE msgs != {n_total_rtl} unique RTL paths (duplicates present)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
