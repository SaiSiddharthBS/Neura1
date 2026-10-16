# TR-112: Thermal derating test, PSU-24 Rev 2 regulator candidates

Synthetic document. Voltline Controls Pvt. Ltd., Quality Lab.
Prepared by: Priya Nair. Reviewed by: Ananya Rao. Date: 2025-03-10.

--- Page 1 ---

## Purpose

Compare NB54360 (current) and NB54361-L (proposed cost-down) on PSU-24 Rev 2 under the TP-PSU-07 thermal and load qualification procedure.

--- Page 2 ---

## Setup

Sealed IP65 enclosure representative of a VC-200 cabinet installation. Full load 3 A on the 3.3 V rail. Ambient stepped from 40C to 70C in 5C steps, 2 hours per step.

--- Page 3 ---

## Measurements

Case temperature, output ripple, and regulation were logged at each step for both candidates.

--- Page 4 ---

## Results

| Candidate | Max ambient with regulation held | Failure mode |
|---|---|---|
| NB54360 | 70C (test limit), 11C junction margin | None |
| NB54361-L | 65C | Thermal shutdown at 68C ambient |

Conclusion: NB54361-L does not meet the 70C ambient requirement for sealed cabinet installations. NB54360 passes.

--- Page 5 ---

## Applicability

Results apply to PSU-24 Rev 2 as used in VC-200 and VG-50.
