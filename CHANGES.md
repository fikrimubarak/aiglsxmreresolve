# AIGLSXMRERESOLVE Change Log

All notable changes to the GLS XMRE Signal Resolver.

---

## [1.0.0] - 2026-02-20 - Initial Release

### Added
- XMRE block parser: extracts token and RTL path from elaboration log
- Partition name derived from `pcd_tb.pcd.<partition>.` signal path per XMRE block
- Per-block partition detection with lazy netlist loading (cached after first load)
- Module hierarchy map builder (86K+ modules from `.pt_nonpg.v.gz`)
- SYNOPSYS_UNCONNECTED port set builder (excludes disconnected nets)
- Case 1: Escaped net search (`\TOKEN_SIGNAL[bit]`)
- Case 2: Hierarchical port search (output/inout, up to 2 levels)
- Case 3: Register flop instance detection (`.o` and `.oN` ports)
- Fuzzy numeric index matching (`_1_` → `_[0-9]+_`)
- INPUT port sub-hierarchy placement (`handcode_rdata_` routed to sub-instance)
- auto_vector multi-bit flop support (oN port by MBIT segment index)
- 1-based RTL_N / SCH_N_M output indexing
- Blank-line-separated blocks in xmre_match
- Duplicate RTL path deduplication with validation count
- Command-line arguments: xmre_log (required), partition_dir (required), -o (optional)

### Performance (parpmc partition, 121 XMRE blocks)
- 70 RTL entries matched (62%)
- 43 RTL entries unmatched (38%)
- 113 unique RTL paths (8 duplicates across blocks)

---

## Development History

### 2026-02-20 - Fix: Case 1 bit-suffix pattern
**Problem**: `\TOKEN_SIGNAL[0]` not matched — pattern ended before `[0]`
**Solution**: Added `[^ ]*` before trailing space: `sig_esc + r'[^ ]* '`
**Impact**: ~20 additional matches recovered

### 2026-02-20 - Case 3: Register flop detection
**Problem**: `SUSPMCFG.EXT_SUS_PD_EN` unmatched — synthesized to DFF instance
**Solution**: Search `TOKEN_reg_SIGNAL*` instance names, append `.o`
**Impact**: All register flop signals now resolved

### 2026-02-20 - Case 3: auto_vector oN port resolution
**Problem**: `PMC_PWR_CTL.CT_EN_PMC` pointing to wrong instance (`PMC_PWR_CTL_reg_CT_EN_PMC_0_MBIT_...`)
**Solution**: For `auto_vector_` instances, split by `_MBIT_`, locate segment containing
             `TOKEN_reg_SIGNAL`, return `.oN` where N = segment index + 1
**Impact**: Correct output port reported for multi-bit auto_vector flops

### 2026-02-20 - Fix: INPUT port sub-hierarchy placement
**Problem**: `\handcode_rdata_PMC_PWR_CTL_DCG_EN_PMC_UC[0]` placed at wrong hierarchy level
**Solution**: For each found escaped signal, check if it is an INPUT port of the parent
             module; if so, insert the sub-instance name (e.g. `pmcisusgcrrgen1`) into path
**Impact**: INPUT ports correctly placed one level deeper

### 2026-02-20 - Fix: SYNOPSYS_UNCONNECTED filtering
**Problem**: `\SUSPMCFG_EXT_SUS_PD_EN[0]` included even though ported to SYNOPSYS_UNCONNECTED
**Solution**: Build port set from `zgrep '\.[^ ]+ \( SYNOPSYS_UNCONNECTED'`; exclude from results
**Impact**: Disconnected ports removed from all SCH candidates

### 2026-02-20 - Fix: Fuzzy numeric index matching
**Problem**: `\ST_DIS_MASK_1_OSSE_ST_DIS_IND[0]` unmatched — GLS renamed index 1→0
**Solution**: When exact search fails, retry with `_\d+_` → `_[0-9]+_` substitution
**Impact**: Index-renamed signals now resolved

---

**Latest Version**: 1.0.0
**Release Date**: 2026-02-20
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**Status**: Production Ready ✓
