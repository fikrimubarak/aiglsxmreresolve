# AIGLSXMRERESOLVE - Quick Start Guide

## 3-Step Setup

### Step 1: Prepare Your Files

```bash
# Navigate to your working directory
cd /path/to/your/workdir

# Confirm your XMRE log and GLS directory
ls parpmc_xmre_messages.log
ls RZLPCDWA0P05_ww34_2_rchalo_PRECTS_GLS/parpmc.pt_nonpg.v.gz
```

### Step 2: Run the Resolver

```bash
# Basic usage (results written to current directory)
python3 /nfs/site/disks/zsc16_rmubarak_stod001/aitest/aiglsxmreresolve/xmre_resolve.py \
  parpmc_xmre_messages.log \
  RZLPCDWA0P05_ww34_2_rchalo_PRECTS_GLS/

# Specify output directory
python3 xmre_resolve.py parpmc_xmre_messages.log ./GLS/ -o ./results/

# Get help
python3 xmre_resolve.py --help
```

### Step 3: Review Results

```bash
# Check matched signals
cat xmre_match

# Check unresolved signals
cat xmre_unmatch

# Count results
grep -c '^RTL_' xmre_match xmre_unmatch
```

## Expected Output

```
========================================================================
AIGLSXMRERESOLVE - GLS XMRE Signal Resolver
========================================================================

XMRE log:      /path/parpmc_xmre_messages.log
Partition:     parpmc
Netlist:       /path/parpmc.pt_nonpg.v.gz
Output dir:    /path/results/

Building module map...
  Loaded 86278 modules
Building synopsys port set...
  92861 unique synopsys-unconnected ports
Parsing XMRE log...
  121 XMRE blocks found

Total: 76 matched, 45 unmatched out of 121

========================================================================
Resolution Complete
========================================================================
✓ Matched:   70 RTL entries
○ Unmatched: 43 RTL entries

Results written to:
  - /path/results/xmre_match
  - /path/results/xmre_unmatch

Validation:
  XMRE messages        : 121
  xmre_match  entries  : 70
  xmre_unmatch entries : 43
  Total unique RTL     : 113
  WARNING: 121 XMRE msgs != 113 unique RTL paths (duplicates present)
```

## Common Commands

```bash
# Count total matched vs unmatched RTL entries
grep -c '^RTL_' xmre_match
grep -c '^RTL_' xmre_unmatch

# View all SCH candidates for a specific RTL entry
grep -A10 '^RTL_5 ' xmre_match

# Check if a signal was matched
grep 'SUSPMCFG' xmre_match xmre_unmatch
```

## Troubleshooting

### "ERROR: Netlist not found"
- Check partition_dir contains `<partition>.pt_nonpg.v.gz`
- Verify partition name matches log filename prefix:
  `parpmc_xmre_messages.log` → looks for `parpmc.pt_nonpg.v.gz`

### "ERROR: Cannot derive partition name"
- Log filename must follow `<partition>_xmre_messages.log` format

### Signal appears in unmatch but you know it exists
- It may be a `SYNOPSYS_UNCONNECTED` port (filtered out by design)
- Numeric index may have changed beyond fuzzy range
- Signal may be deeper than 2 hierarchy levels

### Tool runs slowly
- Module map build (~3 min for 86K modules) is expected — one-time per run
- Each XMRE block requires one `zgrep` on the compressed netlist

---

**Tool Location**: `/nfs/site/disks/zsc16_rmubarak_stod001/aitest/aiglsxmreresolve/`
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
