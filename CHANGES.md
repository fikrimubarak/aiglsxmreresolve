# AIGLSXMRERESOLVE Change Log

All notable changes to the GLS XMRE Signal Resolver.

---

## [1.4.0] - 2026-03-30 - Recursive Netlist Search

### Added
- **Recursive netlist discovery**: `find_netlist()` helper searches `partition_dir` and all
  subdirectories for `<partition>.pt_nonpg.v.gz`. Previously only the top-level directory
  was checked — now works with layouts like `src/all_gls_netlist/<subdir>/<partition>.pt_nonpg.v.gz`.
- Netlist path is cached per partition so `os.walk` only runs once per partition name.

---

## [1.3.0] - 2026-03-13 - Rename SCH to NET in xmre_match

### Changed
- **Output label renamed**: `SCH_N_M` → `NET_N_M` in `xmre_match` (selected and commented lines).
  Reflects that the resolved paths are GLS netlist signals, not schematic names.

---

## [1.2.0] - 2026-02-27 - Output Rank Refinement & Port Order Fix

### Changed
- **Output sub-priority refactored** into explicit `_output_rank()` function with 4 tiers:
  - Rank 1: reg-flop (`.o`/`.oN`) with plain instance name → best output
  - Rank 2: plain non-reg-flop output signal
  - Rank 4: non-reg-flop output with synthesis prefix on signal name (`valid_`, `new_`, `load_`)
  - Rank 5: reg-flop whose instance name has synthesis prefix (`pwc_clk_gate_`, etc.) → worst output
- **`sort_key` for output** now uses `rank * 1000 + hier_depth` instead of the old
  `0 if reg_flop else 1 + prefix_pri * 10 + hier_depth`. This makes `pwc_clk_gate_`
  instances reliably lower-priority than `auto_vector_` instances regardless of alphabetical order.

### Fixed
- **Multi-bit bus secondary sort**: `port_key` returns `(decl_order, -bit_idx)` so that
  within the same netlist field, higher bit indices (MSB) sort before lower (LSB).
  Previously only `decl_order` was used, which could mis-order bits if two fields share
  adjacent declaration positions.

### Added
- `_INST_SYNTH_RE` compiled regex for instance-name synthesis prefix detection.
- `_output_rank(path)` helper function (replaces inline `sub` calculation for outputs).

---

## [1.1.0] - 2026-02-25 - Auto-Selection & Signal Type

### Added
- **Signal type annotation**: every SCH line ends with `output`, `common`, or `input`
  - `output` — declared output port in its containing module
  - `input`  — declared input port (sub-hierarchy placement applied)
  - `common` — internal net (no port declaration found)
- **Auto-selection**: best candidate left uncommented (NET_N_1); alternatives prefixed
  with `#` (e.g. `#NET_N_2`) — all paths still visible for manual override
- **Candidate selection priority**: type (`output` > `common` > `input`) →
  name closeness → sub-priority (see WORKFLOW.md for full rules)
- **Name closeness scoring**: exact name match (closeness=0) beats suffix variant
  (closeness=1), e.g. `DCG_EN_SPXB` preferred over `DCG_EN_SPXB_PMC`
- **`reg_token` for reg-flop closeness**: uses GLS form `TOKEN_reg_SIGNAL` when
  evaluating name closeness for register flop candidates
- **Output synthesis prefix penalty**: `valid_`, `new_`, `load_` prefixed output
  signals ranked below plain output signals
- **Multi-bit bus ordering**: when token maps to a register struct (multiple distinct
  field names, no exact match), all plain candidates kept uncommented and sorted by
  netlist port declaration order (= MSB first, as declared in module port list)
- **NET indexing update**: selected (uncommented) = NET_N_1 … NET_N_M;
  commented alternatives = NET_N_(M+1) … NET_N_K

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
- 1-based RTL_N / NET_N_M output indexing
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

**Latest Version**: 1.4.0
**Release Date**: 2026-03-30
**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**Status**: Production Ready ✓
