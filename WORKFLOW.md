# AIGLSXMRERESOLVE - Technical Workflow

## Overview

Automated resolution of XMRE (Cross-Module Reference Error) signals from GLS elaboration.
For each XMRE error, the tool locates the equivalent GLS signal in the partition netlist
and writes structured match/unmatch reports with signal type annotation and auto-selected
best candidates.

---

## Input / Output

**Inputs**:
- XMRE message log (e.g. `parpmc_xmre_messages.log`) — from VCS/Synopsys GLS elaboration
- Partition directory containing `<partition>.pt_nonpg.v.gz` — GLS netlist (Synopsys PT non-PG)

**Outputs**:
- `xmre_match`   — matched RTL entries with GLS signal candidates (RTL_N / SCH_N_M format)
- `xmre_unmatch` — unresolved RTL entries (RTL_N format)

---

## 4-Phase Resolution Process

### PHASE 1: Parse XMRE Log

**Purpose**: Extract one resolution target per XMRE block

**XMRE block structure**:
```
Error-[XMRE] Cross-module reference resolution error
  token 'SUS_SIG_MON_0'.  Originating module 'PCH_TEMP_BOOT_HACKS' ...
  Source info: force
  {pcd_tb.pcd.parpmc.parpmc_pwell_wrapper....SUS_SIG_MON_0.PCHPWR_PIN[0]}
```

**Extracted fields**:
- `token` — the identifier GLS could not resolve (e.g. `SUS_SIG_MON_0`)
- `path_line` — full RTL signal path (e.g. `pcd_tb.pcd.parpmc....SUS_SIG_MON_0.PCHPWR_PIN[0]`)
- `partition` — derived from `pcd_tb.pcd.<partition>.` in the path (per-block, not from filename)

**Path anatomy**:
```
pcd_tb . pcd . parpmc . parpmc_pwell_wrapper . ... . SUS_SIG_MON_0 . PCHPWR_PIN[0]
 TB root         ^^^                                  ^^^              ^^^
             partition                             instance         signal name
             (= last element = token when TOKEN.SIGNAL)
```

---

### PHASE 2: Build Netlist Index

**Purpose**: Build two in-memory data structures from the GLS netlist

**2a. Module Hierarchy Map** (built once per partition, ~3 min for 86K modules)

Parsed from `<partition>.pt_nonpg.v.gz`:

```
modules[mod_name] = {
  'ports':     { port_name: direction }      # 'input' | 'output' | 'inout'
                                             # keys in declaration order (MSB first)
  'instances': { inst_name: {
      'mod_type':         str,               # instantiated module type
      'unconnected_ports': set()             # ports bound to SYNOPSYS_UNCONNECTED_*
  }}
}
```

Port declaration order is preserved (Python dict insertion order). This is used for
multi-bit bus sorting (MSB→LSB = declaration order in netlist).

**2b. SYNOPSYS_UNCONNECTED Port Set** (~2 sec, 92K entries for parpmc)

Built via:
```
zgrep -oE '\.[^ ]+ \( SYNOPSYS_UNCONNECTED' <netlist>
```

Any signal name appearing here is disconnected in GLS and excluded from results.

---

### PHASE 3: Signal Matching (3 Cases)

For each XMRE block, the token determines which case applies:

---

#### Case 1 — TOKEN.SIGNAL → Flattened Escaped Net

**Trigger**: token appears mid-path as `...TOKEN.SIGNAL`

**What happened**: GLS synthesis flattened instance boundary:
```
RTL:  SUS_SIG_MON_0.PCHPWR_PIN[0]
GLS:  \SUS_SIG_MON_0_PCHPWR_PIN[0]   (escaped, trailing space boundary)
      \new_SUS_SIG_MON_0_PCHPWR_PIN[0]
      \load_SUS_SIG_MON_0_PCHPWR_PIN[0]
```

**Search pattern**:
```
\\[^ ]*TOKEN[^ ]*_SIGNAL[^ ]* <space>
```

**Fuzzy fallback**: If not found, replace numeric indices in TOKEN:
```
ST_DIS_MASK_1  →  ST_DIS_MASK_[0-9]+
```
Covers GLS index renaming (e.g. `_1_` → `_0_`).

**Hierarchy fix for INPUT ports**: Each matched escaped signal is checked against the
module map. If the signal is declared as `input` in a sub-module, the sub-instance name
is inserted into the path:
```
pmcisusgcrr1.\handcode_rdata_PMC_PWR_CTL_DCG_EN_PMC_UC[0]   ← WRONG (it's an input)
pmcisusgcrr1.pmcisusgcrrgen1.\handcode_rdata_PMC_PWR_CTL_DCG_EN_PMC_UC[0]  ← CORRECT
```

---

#### Case 2 — TOKEN at end → Hierarchical Output Port Search

**Trigger**: token is the last element of the path (plain signal name)

**Search**: Walk the module hierarchy from the parent instance, up to 2 levels deep.
Return only `output` / `inout` ports not bound to `SYNOPSYS_UNCONNECTED`.

**Fuzzy fallback**: If no escaped net found, retry with `_\d+` → `_[0-9]+`.

**Example**:
```
RTL:  pmcisusunit_wrapper1.i_pmcisuspmu_0.i_pmcisuspmur.pmc_pgd_pltrst_b
GLS:  pmcisusunit_wrapper1.i_pmcisuspmu_0.i_pmcisuspmur.i_pmcisuspg.pmc_pgd_pltrst_b
      (2 levels deeper, output port, not SYNOPSYS_UNCONNECTED)
```

---

#### Case 3 — TOKEN.SIGNAL → Register Flop Instance

**Trigger**: Same as Case 1 (TOKEN.SIGNAL), applied after escaped net search

**What happened**: GLS inferred a DFF cell for the register field:
```
RTL:  SUSPMCFG.EXT_SUS_PD_EN
GLS:  SUSPMCFG_reg_EXT_SUS_PD_EN_0  ← DFF instance, output via .o port
```

**Search pattern** (line-anchored to capture full instance name):
```
^[^ ]+ [^ ]*TOKEN_reg_SIGNAL[^ ]* \(
```

**auto_vector multi-bit variant**: When multiple register fields are packed into one cell:
```
Instance: auto_vector_handcode_rdata_PMC_PWR_CTL_reg_SIP_SC_CG_EN_0
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_DCG_EN_SRAM_0
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_CT_EN_PMC_0      ← segment 3
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_DCG_EN_MBB_0
Port:  .o3  (index = position of matching _MBIT_ segment)
```

---

### PHASE 4: Candidate Selection & Write Output

After collecting all candidates for an XMRE block, a **selection algorithm** picks the
best match, with alternatives commented out (`#SCH_N_M`).

#### Signal Type Annotation

Every SCH line ends with the signal type:
- `output` — declared as output port in its containing module
- `input`  — declared as input port (sub-hierarchy placement applied)
- `common` — internal net (no port declaration found)

#### Selection Priority

**Single-best case** (most signals): one best candidate is uncommented, rest are `#`:

| Priority | Rule |
|---|---|
| 1st | Signal type: `output` > `common` > `input` |
| 2nd | Name closeness: exact match > suffix variant (e.g. `_PMC` suffix) |
| 3rd (output) | Reg-flop (`.o`/`.oN`) > synthesis-prefixed > shallow hierarchy |
| 3rd (common) | plain > `handcode_wdata_` > `we_` > `write_` > `load_` > `new_` > `handcode_rdata_` |

**Name closeness** checks what follows the token in the GLS signal name:
- `DCG_EN_SPXB` → `\PMC_PWR_CTL_DCG_EN_SPXB[0]` (exact, closeness=0) wins over
  `\PMC_PWR_CTL_DCG_EN_SPXB_PMC[0]` (suffix `_PMC`, closeness=1)
- For reg-flop paths, uses GLS key `TOKEN_reg_SIGNAL` (GLS inserts `_reg_` separator)

**Output synthesis prefix** (`valid_`, `new_`, `load_` prefixed output signals) are
penalised below plain output signals.

#### Multi-bit Bus Case (register struct expansion)

**Trigger**: token has no `[`, AND >1 plain escaped-net candidates with DISTINCT base names,
AND **no exact-match** candidate exists (all candidates have struct-field suffixes → confirms
this is a struct expansion, not suffix variants of the same field).

All plain candidates are kept **uncommented**, sorted by **port declaration order** in the
netlist (= MSB first, as declared in the module port list):

```
RTL_59  STRCFCNF0_UV_SB_REGS          ← register struct with 32 fields
SCH_59_1  \STRCFCNF0_UV_SB_REGS_TRCFCNF_VALID[0]   ← bit 31 (MSB, declared first)
SCH_59_2  \STRCFCNF0_UV_SB_REGS_RSVD[6]             ← bit 30
...
SCH_59_32 \STRCFCNF0_UV_SB_REGS_TRCFCNF_CONFIG[0]   ← bit 0 (LSB, declared last)
#SCH_59_33 \load_STRCFCNF0_UV_SB_REGS_TRCFCNF_CONFIG[0]   ← prefixed → commented
```

**SCH indexing**: selected (uncommented) candidates = SCH_N_1 … SCH_N_M,
commented alternatives = SCH_N_(M+1) … SCH_N_K.

#### Output format

**xmre_match** — blank-line-separated blocks:
```
RTL_1 pcd_tb.pcd.parpmc....SUS_SIG_MON_0.PCHPWR_PIN[0]
SCH_1_1 pcd_tb.pcd.parpmc....\new_SUS_SIG_MON_0_PCHPWR_PIN[0] input
#SCH_1_2 pcd_tb.pcd.parpmc....\load_SUS_SIG_MON_0_PCHPWR_PIN[0] common

RTL_2 pcd_tb.pcd.parpmc....SUSPMCFG.EXT_SUS_PD_EN
SCH_2_1 pcd_tb.pcd.parpmc....SUSPMCFG_reg_EXT_SUS_PD_EN_0.o output
#SCH_2_2 pcd_tb.pcd.parpmc....\SUSPMCFG_EXT_SUS_PD_EN[0] common
```

**xmre_unmatch** — one per line:
```
RTL_1 pcd_tb.pcd.parpmc....up_PMC_PRINT_INFO_VALUE[31:0]
```

---

## Filtering Rules

| Rule | Reason |
|---|---|
| Exclude SYNOPSYS_UNCONNECTED ports | Signal is explicitly disconnected in GLS |
| Exclude input ports (Case 2 hierarchical search) | Only output signals are valid cross-module targets |
| Exclude output ports bound to SYNOPSYS_UNCONNECTED in parent | Port exists but drives nothing |
| Synthesis-prefix outputs (`valid_`, `new_`) ranked lower | Prefer plain RTL-visible signal |
| Prefixed common signals (`load_`, `we_`, `handcode_rdata_`) ranked lower | Prefer original net name |

---

## Data Flow Diagram

```
parpmc_xmre_messages.log
        │
        ▼
┌─────────────────┐     ┌──────────────────────────────────┐
│  PHASE 1        │     │  PHASE 2                         │
│  Parse XMRE     │     │  Build Netlist Index             │
│  121 blocks     │     │                                  │
│  token + path   │     │  parpmc.pt_nonpg.v.gz            │
│  partition name │     │  ├── Module map (86K modules)    │
│  (per-block)    │     │  │   ports in declaration order  │
└────────┬────────┘     │  └── Synopsys port set (92K)     │
         │              └──────────────┬───────────────────┘
         │                             │
         ▼                             ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 3: Signal Matching                               │
│                                                         │
│  TOKEN.SIGNAL ──► Case 1: zgrep escaped net             │
│                           fuzzy index retry             │
│                           INPUT port sub-hier fix       │
│               ──► Case 3: zgrep TOKEN_reg_SIGNAL        │
│                           auto_vector oN port           │
│                                                         │
│  TOKEN (end)  ──► Case 2: hierarchical port search      │
│                           output/inout only             │
│                           max depth = 2                 │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 4: Candidate Selection & Write Output            │
│                                                         │
│  ┌─ Single-best ──────────────────────────────────┐    │
│  │  Sort by: type > closeness > sub-priority      │    │
│  │  Best → SCH_N_1 (uncommented)                  │    │
│  │  Rest → #SCH_N_2 … #SCH_N_K (commented)        │    │
│  └────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ Multi-bit bus ─────────────────────────────────┐   │
│  │  All plain candidates → uncommented             │   │
│  │  Sorted by netlist port declaration order       │   │
│  │  (= MSB first)                                  │   │
│  │  Prefixed variants → commented                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  xmre_match   — 70 RTL entries, signal type annotated  │
│  xmre_unmatch — 43 RTL entries                         │
└─────────────────────────────────────────────────────────┘
```

---

## Performance (parpmc, 121 XMRE blocks)

| Step | Time |
|---|---|
| Module map build (86K modules) | ~3 min |
| Synopsys port set scan | ~2 sec |
| Per-block matching (121 × zgrep on 49MB gz) | ~8 min |
| **Total** | **~11 min** |

---

**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**AI Assistant**: GitHub Copilot (Claude Sonnet 4.6 - 202502)


## Overview

Automated resolution of XMRE (Cross-Module Reference Error) signals from GLS elaboration.
For each XMRE error, the tool locates the equivalent GLS signal in the partition netlist
and writes structured match/unmatch reports.

---

## Input / Output

**Inputs**:
- XMRE message log (e.g. `parpmc_xmre_messages.log`) — from VCS/Synopsys GLS elaboration
- Partition directory containing `<partition>.pt_nonpg.v.gz` — GLS netlist (Synopsys PT non-PG)

**Outputs**:
- `xmre_match`   — matched RTL entries with GLS signal candidates (RTL_N / SCH_N_M format)
- `xmre_unmatch` — unresolved RTL entries (RTL_N format)

---

## 4-Phase Resolution Process

### PHASE 1: Parse XMRE Log

**Purpose**: Extract one resolution target per XMRE block

**XMRE block structure**:
```
Error-[XMRE] Cross-module reference resolution error
  token 'SUS_SIG_MON_0'.  Originating module 'PCH_TEMP_BOOT_HACKS' ...
  Source info: force
  {pcd_tb.pcd.parpmc.parpmc_pwell_wrapper....SUS_SIG_MON_0.PCHPWR_PIN[0]}
```

**Extracted fields**:
- `token` — the identifier GLS could not resolve (e.g. `SUS_SIG_MON_0`)
- `path_line` — full RTL signal path (e.g. `pcd_tb.pcd.parpmc....SUS_SIG_MON_0.PCHPWR_PIN[0]`)
- `partition` — derived from `pcd_tb.pcd.<partition>.` in the path

**Path anatomy**:
```
pcd_tb . pcd . parpmc . parpmc_pwell_wrapper . ... . SUS_SIG_MON_0 . PCHPWR_PIN[0]
 TB root         ^^^                                  ^^^              ^^^
             partition                             instance         signal name
             (= last element = token when TOKEN.SIGNAL)
```

---

### PHASE 2: Build Netlist Index

**Purpose**: Build two in-memory data structures from the GLS netlist

**2a. Module Hierarchy Map** (built once per partition, ~3 min for 86K modules)

Parsed from `<partition>.pt_nonpg.v.gz`:

```
modules[mod_name] = {
  'ports':     { port_name: direction }      # 'input' | 'output' | 'inout'
  'instances': { inst_name: {
      'mod_type':         str,               # instantiated module type
      'unconnected_ports': set()             # ports bound to SYNOPSYS_UNCONNECTED_*
  }}
}
```

Example netlist constructs recognized:

| Construct | Example |
|---|---|
| Module declaration | `module parpmc_pmcisusgcrrgen ( ... );` |
| Port declaration | `output \PMC_PWR_CTL_DCG_EN_SPXB[0] ;` |
| Instance (single line) | `g1iorn002ad1n02x5 ctmi_1 ( .a(x), .o(y) );` |
| Instance (multi-line) | parsed with paren-depth counter |
| SYNOPSYS_UNCONNECTED | `.port ( SYNOPSYS_UNCONNECTED_12345 )` → filtered |

**2b. SYNOPSYS_UNCONNECTED Port Set** (~2 sec, 92K entries for parpmc)

Built via:
```
zgrep -oE '\.[^ ]+ \( SYNOPSYS_UNCONNECTED' <netlist>
```

Any signal name appearing here is disconnected in GLS and excluded from results.

---

### PHASE 3: Signal Matching (3 Cases)

For each XMRE block, the token determines which case applies:

---

#### Case 1 — TOKEN.SIGNAL → Flattened Escaped Net

**Trigger**: token appears mid-path as `...TOKEN.SIGNAL`

**What happened**: GLS synthesis flattened instance boundary:
```
RTL:  SUS_SIG_MON_0.PCHPWR_PIN[0]
GLS:  \SUS_SIG_MON_0_PCHPWR_PIN[0]   (escaped, trailing space boundary)
      \new_SUS_SIG_MON_0_PCHPWR_PIN[0]
      \load_SUS_SIG_MON_0_PCHPWR_PIN[0]
```

**Search pattern**:
```
\\[^ ]*TOKEN[^ ]*_SIGNAL[^ ]* <space>
```

**Fuzzy fallback**: If not found, replace numeric indices in TOKEN:
```
ST_DIS_MASK_1  →  ST_DIS_MASK_[0-9]+
```
Covers GLS index renaming (e.g. `_1_` → `_0_`).

**Hierarchy fix for INPUT ports**: Each matched escaped signal is checked against the
module map. If the signal is declared as `input` in a sub-module, the sub-instance name
is inserted into the path:
```
pmcisusgcrr1.\handcode_rdata_PMC_PWR_CTL_DCG_EN_PMC_UC[0]   ← WRONG (it's an input)
pmcisusgcrr1.pmcisusgcrrgen1.\handcode_rdata_PMC_PWR_CTL_DCG_EN_PMC_UC[0]  ← CORRECT
```

---

#### Case 2 — TOKEN at end → Hierarchical Output Port Search

**Trigger**: token is the last element of the path (plain signal name)

**Search**: Walk the module hierarchy from the parent instance, up to 2 levels deep.
Return only `output` / `inout` ports not bound to `SYNOPSYS_UNCONNECTED`.

**Fuzzy fallback**: If no escaped net found, retry with `_\d+` → `_[0-9]+`.

**Example**:
```
RTL:  pmcisusunit_wrapper1.i_pmcisuspmu_0.i_pmcisuspmur.pmc_pgd_pltrst_b
GLS:  pmcisusunit_wrapper1.i_pmcisuspmu_0.i_pmcisuspmur.i_pmcisuspg.pmc_pgd_pltrst_b
      (2 levels deeper, output port, not SYNOPSYS_UNCONNECTED)
```

---

#### Case 3 — TOKEN.SIGNAL → Register Flop Instance

**Trigger**: Same as Case 1 (TOKEN.SIGNAL), applied after escaped net search

**What happened**: GLS inferred a DFF cell for the register field:
```
RTL:  SUSPMCFG.EXT_SUS_PD_EN
GLS:  SUSPMCFG_reg_EXT_SUS_PD_EN_0  ← DFF instance, output via .o port
```

**Search pattern** (line-anchored to capture full instance name):
```
^[^ ]+ [^ ]*TOKEN_reg_SIGNAL[^ ]* \(
```

**auto_vector multi-bit variant**: When multiple register fields are packed into one cell:
```
Instance: auto_vector_handcode_rdata_PMC_PWR_CTL_reg_SIP_SC_CG_EN_0
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_DCG_EN_SRAM_0
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_CT_EN_PMC_0      ← segment 3
          _MBIT_handcode_rdata_PMC_PWR_CTL_reg_DCG_EN_MBB_0
Port:  .o3  (index = position of matching _MBIT_ segment)
```

---

### PHASE 4: Write Output

**xmre_match** — blank-line-separated blocks, 1-based indexing:
```
RTL_1 pcd_tb.pcd.parpmc....SUS_SIG_MON_0.PCHPWR_PIN[0]
SCH_1_1 pcd_tb.pcd.parpmc....\SUS_SIG_MON_0_PCHPWR_PIN[0]
SCH_1_2 pcd_tb.pcd.parpmc....\new_SUS_SIG_MON_0_PCHPWR_PIN[0]

RTL_2 pcd_tb.pcd.parpmc....SUSPMCFG.EXT_SUS_PD_EN
SCH_2_1 pcd_tb.pcd.parpmc....SUSPMCFG_reg_EXT_SUS_PD_EN_0.o
```

**xmre_unmatch** — one per line:
```
RTL_1 pcd_tb.pcd.parpmc....up_PMC_PRINT_INFO_VALUE[31:0]
RTL_2 pcd_tb.pcd.parpmc....nxt_PMC_PRINT_INFO_VALUE[31:0]
```

**Deduplication**: The same RTL path may appear in multiple XMRE blocks (same signal
referenced from multiple source locations). Each unique RTL path is written once.

**Validation**: Prints warning if XMRE block count ≠ unique RTL path count (duplicates present).

---

## Filtering Rules

| Rule | Reason |
|---|---|
| Exclude SYNOPSYS_UNCONNECTED ports | Signal is explicitly disconnected in GLS |
| Exclude input ports (Case 2) | Only output signals are valid cross-module targets |
| Exclude output ports bound to SYNOPSYS_UNCONNECTED in parent | Port exists but drives nothing |

---

## Data Flow Diagram

```
parpmc_xmre_messages.log
        │
        ▼
┌─────────────────┐     ┌──────────────────────────────────┐
│  PHASE 1        │     │  PHASE 2                         │
│  Parse XMRE     │     │  Build Netlist Index             │
│  121 blocks     │     │                                  │
│  token + path   │     │  parpmc.pt_nonpg.v.gz            │
│  partition name │     │  ├── Module map (86K modules)    │
└────────┬────────┘     │  └── Synopsys port set (92K)     │
         │              └──────────────┬───────────────────┘
         │                             │
         ▼                             ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 3: Signal Matching                               │
│                                                         │
│  TOKEN.SIGNAL ──► Case 1: zgrep escaped net             │
│                           fuzzy index retry             │
│                           INPUT port sub-hier fix       │
│               ──► Case 3: zgrep TOKEN_reg_SIGNAL        │
│                           auto_vector oN port           │
│                                                         │
│  TOKEN (end)  ──► Case 2: hierarchical port search      │
│                           output/inout only             │
│                           max depth = 2                 │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  PHASE 4: Write Output                                  │
│  xmre_match   — 70 RTL entries, 1-based RTL_N/SCH_N_M  │
│  xmre_unmatch — 43 RTL entries, 1-based RTL_N           │
└─────────────────────────────────────────────────────────┘
```

---

## Performance (parpmc, 121 XMRE blocks)

| Step | Time |
|---|---|
| Module map build (86K modules) | ~3 min |
| Synopsys port set scan | ~2 sec |
| Per-block matching (121 × zgrep on 49MB gz) | ~8 min |
| **Total** | **~11 min** |

---

**Author**: Fikri (raden.ali.fikri.mubarak@intel.com)
**AI Assistant**: GitHub Copilot (Claude Sonnet 4.5 - 202502)
