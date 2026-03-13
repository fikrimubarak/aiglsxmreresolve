# AIGLSXMRERESOLVE - GLS XMRE Signal Resolver

Automated tool for resolving Cross-Module Reference Errors (XMRE) from GLS elaboration.
Searches the GLS partition netlist for matching signals and produces structured match/unmatch reports.

## Overview

**AIGLSXMRERESOLVE** is a signal resolution tool that:
- **Parses** XMRE error blocks from elaboration log files
- **Searches** the GLS netlist (`.pt_nonpg.v.gz`) for matching signals
- **Reports** matched signals to `xmre_match` and unresolved paths to `xmre_unmatch`
- **Handles** three matching cases: flattened escaped nets, hierarchical ports, register flops
- **Annotates** each candidate with signal type (`output` / `common` / `input`)
- **Auto-selects** best candidate (uncommented), with alternatives `#`-commented

## Quick Start

```bash
# Basic usage (output in current directory)
python3 /nfs/site/disks/zsc16_rmubarak_stod001/aitest/aiglsxmreresolve/xmre_resolve.py \
  parpmc_xmre_messages.log ./GLS_dir/

# Specify output directory
python3 xmre_resolve.py parpmc_xmre_messages.log ./GLS_dir/ -o ./results/

# Get help
python3 xmre_resolve.py --help
```

## Prerequisites

- Python 3.6+
- `zgrep` available in PATH (standard on Linux)
- No external Python packages required

## Arguments

| Argument | Required | Description |
|---|---|---|
| `xmre_log` | Yes | XMRE message log file (e.g. `parpmc_xmre_messages.log`) |
| `partition_dir` | Yes | Directory containing `<partition>.pt_nonpg.v.gz` |
| `-o / --output-dir` | No | Output directory for results (default: current directory) |

The partition name is derived automatically from the signal path inside each XMRE block:
`pcd_tb.pcd.<partition>.<rest>` → partition = `<partition>` → netlist = `<partition>.pt_nonpg.v.gz`

Different blocks in the same log may reference different partitions. Each partition netlist is
loaded once and cached for subsequent blocks.

## Matching Strategy

### Case 1: TOKEN.SIGNAL → Flattened Escaped Net
GLS synthesis flattens `SUS_SIG_MON_0.PCHPWR_PIN[0]` into `\SUS_SIG_MON_0_PCHPWR_PIN[0]`.
The tool searches for `\[prefix_]TOKEN[_suffix]_SIGNAL[bit]` patterns.

Also applies fuzzy numeric index matching: `_1_` → `_[0-9]+_` when exact search fails.

### Case 2: Plain TOKEN at End → Hierarchical Port Search
Searches output/inout ports up to 2 hierarchy levels deeper than the RTL path.
Filters out: input ports, ports connected to `SYNOPSYS_UNCONNECTED_*`.

### Case 3: TOKEN.SIGNAL → Register Flop Instance
Detects synthesis register flops named `TOKEN_reg_SIGNAL_N` with output port `.o`.
Also handles `auto_vector_..._MBIT_...` multi-bit flop instances, resolving the
correct `.oN` port by matching the segment index.

## Candidate Selection

After collecting all candidates for an XMRE block, the best match is auto-selected
(uncommented); alternatives are kept with a `#` prefix for reference.

**Selection priority**: signal type → name closeness → sub-priority
- **Type**: `output` > `common` > `input`
- **Closeness**: exact name match (closeness=0) beats suffix variant, e.g. `DCG_EN_SPXB`
  wins over `DCG_EN_SPXB_PMC` (closeness=1). For reg-flop paths, uses GLS form
  `TOKEN_reg_SIGNAL` (GLS inserts `_reg_` separator).
- **Output sub-priority**: Rank 1 plain reg-flop (`.o`/`.oN`, plain instance) > Rank 2 plain
  output signal > Rank 4 synthesis-prefixed signal (`valid_`, `new_`, `load_`) > Rank 5
  synthesis-prefixed instance reg-flop (`pwc_clk_gate_`, etc.). Within each rank, shallower
  hierarchy wins.
- **Common sub-priority**: plain > `handcode_wdata_` > `we_` > `write_` > `load_` >
  `new_` > `handcode_rdata_`

**Multi-bit bus** (register struct expansion): when all candidates are struct-field
variants of a token with no `[bit]`, all plain candidates are kept uncommented and
sorted by netlist port declaration order (MSB first).

## Output Format

### xmre_match
```
RTL_1 pcd_tb.pcd.parpmc....SUS_SIG_MON_0.PCHPWR_PIN[0]
NET_1_1 pcd_tb.pcd.parpmc....\new_SUS_SIG_MON_0_PCHPWR_PIN[0] input
#NET_1_2 pcd_tb.pcd.parpmc....\load_SUS_SIG_MON_0_PCHPWR_PIN[0] common

RTL_2 pcd_tb.pcd.parpmc....SUSPMCFG.EXT_SUS_PD_EN
NET_2_1 pcd_tb.pcd.parpmc....SUSPMCFG_reg_EXT_SUS_PD_EN_0.o output
#NET_2_2 pcd_tb.pcd.parpmc....\SUSPMCFG_EXT_SUS_PD_EN[0] common
```

### xmre_unmatch
```
RTL_1 pcd_tb.pcd.parpmc....up_PMC_PRINT_INFO_VALUE[31:0]
RTL_2 pcd_tb.pcd.parpmc....nxt_PMC_PRINT_INFO_VALUE[31:0]
```

## Project Structure

```
aiglsxmreresolve/
├── README.md              # This file
├── QUICK_START.md         # Quick reference guide
├── CHANGES.md             # Change log
├── VERSION.md             # Version history
├── AI_CONTRIBUTION.md     # AI development notes
├── xmre_resolve.py        # Main resolver script
└── requirements.txt       # Python dependencies (stdlib only)
```

## Performance

- Module map build: ~3 minutes for 86K-module netlists (one-time per run)
- SYNOPSYS port scan: ~2 seconds
- Per-block matching: ~1 second each (zgrep on 49MB gzip)
- Total for 121 XMRE blocks: ~10 minutes

## Author

**Fikri**
Email: raden.ali.fikri.mubarak@intel.com
Organization: Intel Corporation - PCH Validation Team

## AI Assistant

Developed with assistance from **GitHub Copilot (Claude Sonnet 4.6)**
See `AI_CONTRIBUTION.md` for details.

## License

Internal Intel tool - Not for external distribution

---

**Status**: Production Ready ✓
**Version**: 1.1 (2026-02-25)
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**AI Assistant**: GitHub Copilot (Claude Sonnet 4.6)
