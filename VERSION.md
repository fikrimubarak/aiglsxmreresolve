# AIGLSXMRERESOLVE Version History

## Version 1.2 (2026-02-27) - Output Rank Refinement & Port Order Fix

### Overview
Improved output candidate ranking with explicit instance-name synthesis detection,
and added secondary bit-index sort for multi-bit bus port declaration ordering.

### Changes
✓ **Output rank by instance prefix**: `pwc_clk_gate_` (and `valid_`, `new_`, `load_`)
  prefixed reg-flop instances are now explicitly ranked as Rank 5 (worst output priority),
  below plain `auto_vector_` reg-flops (Rank 1). Previously relied on alphabetical tiebreak.
✓ **`_output_rank()` function**: new helper encoding the 4-tier output sub-priority:
  Rank 1 = plain reg-flop → Rank 2 = plain output → Rank 4 = synthesis-prefixed signal →
  Rank 5 = synthesis-prefixed instance reg-flop
✓ **Multi-bit bus secondary sort**: `port_key` now returns `(decl_order, -bit_idx)`,
  ensuring MSB-first ordering within the same field when ports share a declaration position.

---

## Version 1.1 (2026-02-25) - Auto-Selection & Signal Type

### Overview
Added signal type annotation, auto-selection of best candidate, name closeness scoring,
and multi-bit bus port-declaration ordering.

### New Features
✓ Signal type annotation: `output` / `common` / `input` on every SCH line
✓ Auto-selection: best candidate uncommented, alternatives `#`-prefixed
✓ Selection priority: type → closeness → sub-priority (output/common rules)
✓ Name closeness scoring: exact match beats suffix variant (e.g. `_PMC`)
✓ `reg_token` support: correct closeness for reg-flop paths (`TOKEN_reg_SIGNAL`)
✓ Output synthesis prefix penalty (`valid_`, `new_`, `load_`)
✓ Multi-bit bus ordering: all struct-field candidates sorted MSB→LSB by netlist declaration order
✓ SCH indexing: selected = 1..M (uncommented), alternatives = M+1..K (`#`)

---

## Version 1.0 (2026-02-20) - Initial Release

### Overview
Production-ready GLS XMRE signal resolver with three matching cases and multiple fixes.

### Performance Metrics (parpmc, 121 XMRE blocks)
- **Matched RTL entries**: 70 (62%)
- **Unmatched RTL entries**: 43 (38%)
- **Unique RTL paths**: 113 (8 duplicate blocks)

### Features
✓ XMRE block parser (token + RTL path extraction)
✓ Module hierarchy map from compressed GLS netlist
✓ SYNOPSYS_UNCONNECTED port filtering
✓ Case 1: Escaped net search with fuzzy index matching
✓ Case 2: Hierarchical output/inout port search (2 levels)
✓ Case 3: Register flop + auto_vector instance detection
✓ INPUT port sub-hierarchy placement
✓ 1-based RTL_N / SCH_N_M indexing
✓ Duplicate deduplication with validation check
✓ Command-line argument support

### Dependencies
- Python 3.6+
- No external libraries (standard library only: re, gzip, os, subprocess)
- `zgrep` system command

### Compatibility
- XMRE log format from VCS/Synopsys GLS elaboration
- GLS netlists: `.pt_nonpg.v.gz` (Synopsys PT non-PG format)
- Partition naming: `<partition>_xmre_messages.log`

---

**Current Status**: Production Ready ✓
**Current Version**: 1.2 (2026-02-27)
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**Stability**: Stable
