# Scaling notes

## W05-D dictionary scale probe

Generated: 2026-05-23T20:41:21.721900+00:00

Synthetic document: 10,000 tracked theorem atoms followed by 10,000 `\cref` references.  The probe is designed to exercise the dictionary csname families `\codep@brcount@<key>`, `\codep@brnode@<key>@<k>`, `\codep@rendered@<key>`, `\codep@rlflag@<key>`, and `\codep@anchor@<key>`.

| Engine | Config | Status | Exit | Passes | Wall seconds | main_memory words | string pool | csnames | Capacity events |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| pdflatex | pool_size=9000000 | PASS | 0 | 3/3 | 447.626 | 4,326,405 / 5,000,000 | 6,508,596 / 8,146,041 | 280,010 / 615,000 | none |
| lualatex | default | PASS | 0 | 3/3 | 152.571 | 10,779,791 | not reported | 273,724 / 665,536 | none |
| xelatex | extra_mem_bot=5000000, extra_mem_top=5000000, pool_size=9000000 | PASS | 0 | 3/3 | 417.033 | 9,291,887 / 13,865,479 | 6,387,895 / 8,162,479 | 279,845 / 615,000 | none |

Capacity assessment:

- No `hash_extra`, `pool_size`, `csname_size`, or other TeX capacity exhaustion events were detected in the final successful engine logs.
- pdflatex default-config probe hit `! TeX capacity exceeded, sorry [pool size=5396041].`; the recorded final pass used `pool_size=9000000`.
- xelatex default-config probe hit `! TeX capacity exceeded, sorry [pool size=5412479].`; `! TeX capacity exceeded, sorry [main memory size=5000000].`; the recorded final pass used `extra_mem_bot=5000000, extra_mem_top=5000000, pool_size=9000000`.
- Recommendation: Use lualatex for 10k-atom documents under default settings. pdflatex, xelatex also completed the probe, but only after the TeX capacity variables shown in the config column were raised.
- No `--hash-extra` or `--main-memory` flags were required.  Engines that hit the default string-pool ceiling were retried with the `pool_size` kpathsea variable shown in the config column.

Raw JSON metrics: `.claude/comms/waves/W05-D/scale-probe-metrics.json` (gitignored).
