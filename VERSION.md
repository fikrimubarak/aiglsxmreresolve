# AIGLSXMRERESOLVE Version History

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
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**Stability**: Stable
